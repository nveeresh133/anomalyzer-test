import logging
import yaml
import difflib
from typing import Dict, Any, List, Optional
from kubernetes import client, config
from kubernetes.client.rest import ApiException

from src.redactor import DataRedactor

logger = logging.getLogger("k8s_inspector")

class KubernetesInspector:
    """
    In-cluster Kubernetes client wrapper providing safe, read-only diagnostic tools.
    Supports both in-cluster config (when deployed in Pod) and local kubeconfig (dev mode).
    """

    def __init__(self):
        self.current_context = None
        self.in_cluster = False
        self._initialize_config()

    def _initialize_config(self, context_name: Optional[str] = None):
        try:
            config.load_incluster_config()
            self.in_cluster = True
            self.current_context = "in-cluster"
            logger.info("Successfully loaded in-cluster Kubernetes configuration.")
        except Exception:
            try:
                contexts, active_context = config.list_kube_config_contexts()
                target_ctx = context_name or (active_context["name"] if active_context else None)
                config.load_kube_config(context=target_ctx)
                self.current_context = target_ctx
                logger.info(f"Loaded kubeconfig for context '{target_ctx}'.")
            except Exception as e:
                logger.warning(f"Failed to load Kubernetes configuration: {e}")

        self.core_v1 = client.CoreV1Api()
        self.apps_v1 = client.AppsV1Api()

    def list_clusters(self) -> List[Dict[str, Any]]:
        """Lists available cluster contexts from kubeconfig."""
        if self.in_cluster:
            return [{"name": "in-cluster", "is_current": True}]
        try:
            contexts, active_context = config.list_kube_config_contexts()
            active_name = active_context["name"] if active_context else ""
            result = []
            for ctx in contexts:
                ctx_name = ctx["name"]
                result.append({
                    "name": ctx_name,
                    "is_current": (ctx_name == self.current_context or ctx_name == active_name)
                })
            return result
        except Exception as e:
            logger.warning(f"Could not list kubeconfig contexts: {e}")
            return [{"name": self.current_context or "default", "is_current": True}]

    def switch_context(self, context_name: Optional[str]):
        """Switches the Kubernetes API client context."""
        if not context_name or context_name == self.current_context or self.in_cluster:
            return
        logger.info(f"Switching K8s inspector context to '{context_name}'...")
        self._initialize_config(context_name=context_name)

    def list_namespaces(self) -> List[Dict[str, Any]]:
        """Lists all accessible namespaces in the cluster."""
        try:
            namespaces = self.core_v1.list_namespace()
            result = []
            for ns in namespaces.items:
                result.append({
                    "name": ns.metadata.name,
                    "status": ns.status.phase
                })
            return result
        except ApiException as e:
            logger.error(f"Error listing namespaces: {e}")
            return [{"name": "default", "status": "Active"}]

    def scan_namespace_health(self, namespace: str = "default") -> Dict[str, Any]:
        """
        Scans a namespace for pod statuses, container restart counts,
        and abnormal states (CrashLoopBackOff, OOMKilled, ImagePullBackOff, Pending).
        """
        try:
            pods = self.core_v1.list_namespaced_pod(namespace=namespace)
            unhealthy_pods = []
            total_pods = len(pods.items)

            for pod in pods.items:
                pod_name = pod.metadata.name
                phase = pod.status.phase
                container_statuses = pod.status.container_statuses or []

                is_faulty = False
                fault_reasons = []
                restarts = 0

                if phase not in ["Running", "Succeeded"]:
                    is_faulty = True
                    fault_reasons.append(f"Pod phase is {phase}")

                for cs in container_statuses:
                    restarts += cs.restart_count
                    if cs.restart_count > 0:
                        fault_reasons.append(f"Container '{cs.name}' restarted {cs.restart_count} times")
                        if cs.restart_count >= 3:
                            is_faulty = True

                    waiting = cs.state.waiting
                    terminated = cs.state.terminated

                    if waiting and waiting.reason in ["CrashLoopBackOff", "ImagePullBackOff", "ErrImagePull", "ContainerCreating"]:
                        is_faulty = True
                        fault_reasons.append(f"Container '{cs.name}' state: {waiting.reason} - {waiting.message or ''}")
                    
                    if terminated and terminated.reason in ["OOMKilled", "Error"]:
                        is_faulty = True
                        fault_reasons.append(f"Container '{cs.name}' terminated: {terminated.reason} (exit code {terminated.exit_code})")

                if is_faulty:
                    owner_kind = "Pod"
                    owner_name = pod_name
                    if pod.metadata.owner_references:
                        owner = pod.metadata.owner_references[0]
                        owner_kind = owner.kind
                        owner_name = owner.name
                        if owner_kind == "ReplicaSet" and "-" in owner_name:
                            owner_name = owner_name.rsplit("-", 1)[0]
                            owner_kind = "Deployment"

                    unhealthy_pods.append({
                        "name": pod_name,
                        "owner_kind": owner_kind,
                        "owner_name": owner_name,
                        "phase": phase,
                        "restarts": restarts,
                        "fault_reasons": fault_reasons,
                        "node_name": pod.spec.node_name,
                        "containers": [{"name": c.name, "image": c.image} for c in pod.spec.containers]
                    })

            events = self.get_namespace_events(namespace=namespace, limit=10)

            return {
                "namespace": namespace,
                "total_pods": total_pods,
                "unhealthy_pod_count": len(unhealthy_pods),
                "unhealthy_pods": unhealthy_pods,
                "recent_warning_events": events
            }

        except ApiException as e:
            logger.error(f"Error scanning namespace health for '{namespace}': {e}")
            return {"namespace": namespace, "error": str(e)}

    def get_pod_details(self, namespace: str, pod_name: str) -> Dict[str, Any]:
        """Fetches detailed spec, conditions, container exit codes for a specific pod."""
        try:
            pod = self.core_v1.read_namespaced_pod(name=pod_name, namespace=namespace)
            
            containers_info = []
            for c in pod.spec.containers:
                env_vars = DataRedactor.sanitize_env_vars([{"name": e.name, "value": e.value} for e in (c.env or [])])
                containers_info.append({
                    "name": c.name,
                    "image": c.image,
                    "resources": c.resources.to_dict() if c.resources else {},
                    "env": env_vars
                })

            statuses = []
            if pod.status.container_statuses:
                for cs in pod.status.container_statuses:
                    statuses.append({
                        "name": cs.name,
                        "ready": cs.ready,
                        "restart_count": cs.restart_count,
                        "state": cs.state.to_dict() if cs.state else {}
                    })

            conditions = [{"type": cond.type, "status": cond.status, "reason": cond.reason} for cond in (pod.status.conditions or [])]

            return {
                "name": pod_name,
                "namespace": namespace,
                "phase": pod.status.phase,
                "node_name": pod.spec.node_name,
                "containers": containers_info,
                "container_statuses": statuses,
                "conditions": conditions
            }
        except ApiException as e:
            return {"pod_name": pod_name, "error": f"Failed to describe pod: {e.reason}"}

    def get_pod_logs(self, namespace: str, pod_name: str, container_name: Optional[str] = None, previous: bool = False, tail_lines: int = 150) -> str:
        """Fetches stdout/stderr logs from a pod container and scrubs sensitive data."""
        try:
            logs = self.core_v1.read_namespaced_pod_log(
                name=pod_name,
                namespace=namespace,
                container=container_name,
                previous=previous,
                tail_lines=tail_lines
            )
            return DataRedactor.scrub_text(logs)
        except ApiException as e:
            if not previous:
                # Retry fetching previous terminated container logs if current fails
                try:
                    logs = self.core_v1.read_namespaced_pod_log(
                        name=pod_name,
                        namespace=namespace,
                        container=container_name,
                        previous=True,
                        tail_lines=tail_lines
                    )
                    return f"[Previous Container Logs]\n" + DataRedactor.scrub_text(logs)
                except Exception:
                    pass
            return f"Error fetching logs for pod '{pod_name}': {e.reason}"

    def get_namespace_events(self, namespace: str, limit: int = 15) -> List[Dict[str, Any]]:
        """Fetches recent Warning events in the specified namespace."""
        try:
            events = self.core_v1.list_namespaced_event(namespace=namespace)
            formatted = []
            
            # Sort events by last timestamp
            sorted_events = sorted(
                events.items,
                key=lambda x: x.last_timestamp or x.event_time or x.metadata.creation_timestamp,
                reverse=True
            )

            for event in sorted_events[:limit]:
                if event.type == "Warning" or "Failed" in (event.reason or ""):
                    formatted.append({
                        "type": event.type,
                        "reason": event.reason,
                        "message": DataRedactor.scrub_text(event.message or ""),
                        "object": f"{event.involved_object.kind}/{event.involved_object.name}",
                        "count": event.count
                    })
            return formatted
        except ApiException as e:
            logger.error(f"Error reading namespace events: {e}")
            return []

    def check_service_endpoints(self, namespace: str, service_name: str) -> Dict[str, Any]:
        """Checks if a Kubernetes service has ready backing endpoints/pods."""
        try:
            svc = self.core_v1.read_namespaced_service(name=service_name, namespace=namespace)
            selector = svc.spec.selector or {}
            
            endpoints = self.core_v1.read_namespaced_endpoints(name=service_name, namespace=namespace)
            
            ready_addresses = []
            if endpoints.subsets:
                for subset in endpoints.subsets:
                    if subset.addresses:
                        for addr in subset.addresses:
                            ready_addresses.append(addr.ip)

            return {
                "service_name": service_name,
                "selector": selector,
                "type": svc.spec.type,
                "cluster_ip": svc.spec.cluster_ip,
                "ready_endpoint_count": len(ready_addresses),
                "ready_endpoints": ready_addresses
            }
        except ApiException as e:
            return {"service_name": service_name, "error": f"Failed to inspect service: {e.reason}"}

    def run_security_audit(self, namespace: str) -> List[Dict[str, Any]]:
        """
        Scans deploy configurations in the namespace for security risks and best-practice violations.
        """
        violations = []
        try:
            deploys = self.apps_v1.list_namespaced_deployment(namespace=namespace)
            for d in deploys.items:
                res_name = f"Deployment/{d.metadata.name}"
                pod_spec = d.spec.template.spec

                # Check replica count
                if (d.spec.replicas or 0) < 2:
                    violations.append({
                        "resource": res_name,
                        "rule": "Low Workload Redundancy",
                        "severity": "LOW",
                        "description": "Deployment has replica count set to 1. Single pod failure will cause service disruption.",
                        "remediation": f"kubectl scale deployment/{d.metadata.name} --replicas=2 -n {namespace}"
                    })

                for idx, c in enumerate(pod_spec.containers):
                    c_name = c.name
                    desc_prefix = f"Container '{c_name}' in resource '{res_name}'"

                    # 1. Check Resources requests/limits
                    res = c.resources
                    if not res or not res.limits or "memory" not in res.limits:
                        violations.append({
                            "resource": res_name,
                            "rule": "Missing Memory Resource Limits",
                            "severity": "HIGH",
                            "description": f"{desc_prefix} does not define memory limits. Could cause node memory starvation.",
                            "remediation": f"kubectl patch deployment/{d.metadata.name} -n {namespace} --type='json' -p='[{{\"op\": \"add\", \"path\": \"/spec/template/spec/containers/{idx}/resources/limits\", \"value\": {{\"memory\": \"512Mi\"}}}}]'"
                        })
                    if not res or not res.requests or "cpu" not in res.requests:
                        violations.append({
                            "resource": res_name,
                            "rule": "Missing CPU Resource Requests",
                            "severity": "MEDIUM",
                            "description": f"{desc_prefix} does not define CPU requests. Kubernetes scheduler cannot binpack optimally.",
                            "remediation": f"kubectl patch deployment/{d.metadata.name} -n {namespace} --type='json' -p='[{{\"op\": \"add\", \"path\": \"/spec/template/spec/containers/{idx}/resources/requests\", \"value\": {{\"cpu\": \"100m\"}}}}]'"
                        })

                    # 2. Check Health Probes
                    if not c.liveness_probe:
                        violations.append({
                            "resource": res_name,
                            "rule": "Missing Liveness Probe",
                            "severity": "MEDIUM",
                            "description": f"{desc_prefix} is missing a livenessProbe configuration. Kubernetes cannot self-heal if container hangs.",
                            "remediation": "Configure livenessProbe under container spec with health endpoint or tcp socket."
                        })
                    if not c.readiness_probe:
                        violations.append({
                            "resource": res_name,
                            "rule": "Missing Readiness Probe",
                            "severity": "MEDIUM",
                            "description": f"{desc_prefix} is missing a readinessProbe. Traffic could flow to pod before application is ready.",
                            "remediation": "Configure readinessProbe under container spec."
                        })

                    # 3. Check Image Tags
                    img = c.image or ""
                    if ":" not in img or img.endswith(":latest"):
                        violations.append({
                            "resource": res_name,
                            "rule": "Image Tag Anti-Pattern",
                            "severity": "MEDIUM",
                            "description": f"{desc_prefix} uses image tag '{img}'. Running ':latest' tag risks non-deterministic deployments.",
                            "remediation": f"kubectl set image deployment/{d.metadata.name} {c_name}=<image-name>:<explicit-version-tag> -n {namespace}"
                        })

                    # 4. Check SecurityContext
                    sec = c.security_context
                    if not sec:
                        violations.append({
                            "resource": res_name,
                            "rule": "Missing Container Security Context",
                            "severity": "MEDIUM",
                            "description": f"{desc_prefix} lacks a securityContext configuration.",
                            "remediation": f"kubectl patch deployment/{d.metadata.name} -n {namespace} --type='json' -p='[{{\"op\": \"add\", \"path\": \"/spec/template/spec/containers/{idx}/securityContext\", \"value\": {{\"runAsNonRoot\": true, \"allowPrivilegeEscalation\": false}}}}]'"
                        })
                    else:
                        if sec.privileged:
                            violations.append({
                                "resource": res_name,
                                "rule": "Privileged Container Escaped",
                                "severity": "HIGH",
                                "description": f"{desc_prefix} runs in privileged mode. Container has full root access to host OS.",
                                "remediation": f"kubectl patch deployment/{d.metadata.name} -n {namespace} --type='json' -p='[{{\"op\": \"replace\", \"path\": \"/spec/template/spec/containers/{idx}/securityContext/privileged\", \"value\": false}}]'"
                            })
                        if sec.allow_privilege_escalation is not False:
                            violations.append({
                                "resource": res_name,
                                "rule": "Privilege Escalation Allowed",
                                "severity": "HIGH",
                                "description": f"{desc_prefix} permits container processes to gain more privileges than parent process.",
                                "remediation": f"kubectl patch deployment/{d.metadata.name} -n {namespace} --type='json' -p='[{{\"op\": \"replace\", \"path\": \"/spec/template/spec/containers/{idx}/securityContext/allowPrivilegeEscalation\", \"value\": false}}]'"
                            })
                        if sec.read_only_root_filesystem is not True:
                            violations.append({
                                "resource": res_name,
                                "rule": "Writable Root Filesystem",
                                "severity": "LOW",
                                "description": f"{desc_prefix} runs with write permissions on container root filesystem.",
                                "remediation": f"kubectl patch deployment/{d.metadata.name} -n {namespace} --type='json' -p='[{{\"op\": \"replace\", \"path\": \"/spec/template/spec/containers/{idx}/securityContext/readOnlyRootFilesystem\", \"value\": true}}]'"
                            })

            return violations
        except Exception as e:
            logger.error(f"Error auditing namespace resources: {e}")
            return violations

    def get_patch_dry_run_diff(self, namespace: str, kind: str, name: str, patch_data: Any) -> str:
        """
        Executes a dry-run client-side patch request and generates a unified YAML diff of the changes.
        """
        import json
        kind_lower = kind.lower()
        
        try:
            # Step 1: Fetch original resource and convert to clean YAML
            if kind_lower == "deployment":
                current = self.apps_v1.read_namespaced_deployment(name=name, namespace=namespace)
                patched = self.apps_v1.patch_namespaced_deployment(name=name, namespace=namespace, body=patch_data, dry_run="All")
            elif kind_lower == "service":
                current = self.core_v1.read_namespaced_service(name=name, namespace=namespace)
                patched = self.core_v1.patch_namespaced_service(name=name, namespace=namespace, body=patch_data, dry_run="All")
            elif kind_lower == "statefulset":
                current = self.apps_v1.read_namespaced_stateful_set(name=name, namespace=namespace)
                patched = self.apps_v1.patch_namespaced_stateful_set(name=name, namespace=namespace, body=patch_data, dry_run="All")
            elif kind_lower == "daemonset":
                current = self.apps_v1.read_namespaced_daemon_set(name=name, namespace=namespace)
                patched = self.apps_v1.patch_namespaced_daemon_set(name=name, namespace=namespace, body=patch_data, dry_run="All")
            elif kind_lower == "pod":
                current = self.core_v1.read_namespaced_pod(name=name, namespace=namespace)
                patched = self.core_v1.patch_namespaced_pod(name=name, namespace=namespace, body=patch_data, dry_run="All")
            elif kind_lower == "pvc":
                current = self.core_v1.read_namespaced_persistent_volume_claim(name=name, namespace=namespace)
                patched = self.core_v1.patch_namespaced_persistent_volume_claim(name=name, namespace=namespace, body=patch_data, dry_run="All")
            else:
                return f"Unsupported resource kind for diff preview: {kind}"

            # Step 2: Clean dictionaries using JSON dump/load fallback (resolves datetime and K8s object type issues)
            current_dict = json.loads(json.dumps(current.to_dict(), default=str))
            patched_dict = json.loads(json.dumps(patched.to_dict(), default=str))

            # Strip volatile runtime fields (metadata.managedFields, status, resourceVersion, uid)
            for d in [current_dict, patched_dict]:
                if "metadata" in d:
                    d["metadata"].pop("managedFields", None)
                    d["metadata"].pop("resourceVersion", None)
                    d["metadata"].pop("uid", None)
                    d["metadata"].pop("creationTimestamp", None)
                d.pop("status", None)

            current_yaml = yaml.dump(current_dict, default_flow_style=False, sort_keys=False)
            patched_yaml = yaml.dump(patched_dict, default_flow_style=False, sort_keys=False)

            # Step 3: Run diff comparison
            diff_lines = list(difflib.unified_diff(
                current_yaml.splitlines(),
                patched_yaml.splitlines(),
                fromfile=f"Current Config ({kind}/{name})",
                tofile=f"Proposed Config ({kind}/{name})",
                lineterm=""
            ))

            if not diff_lines:
                return "No configuration changes detected."
            return "\n".join(diff_lines)

        except ApiException as e:
            return f"Kubernetes API Dry-run failed: {e.reason} ({e.status})\n{e.body}"
        except Exception as e:
            return f"Failed to generate configuration diff: {str(e)}"

