import os
import json
import logging
from typing import Dict, Any, List, Optional

from src.k8s_inspector import KubernetesInspector
from src.schemas import DiagnosisReport, SeverityLevel, RemediationStep, AgentThoughtStep

logger = logging.getLogger("ai_engine")

class AITroubleshooterEngine:
    """
    On-Demand K8s AI Troubleshooting Agent using Google GenAI SDK with Tool Calling / ReAct loop.
    """

    SYSTEM_INSTRUCTION = """
You are an expert Senior Kubernetes Site Reliability Engineer (SRE) and Troubleshooter.
Your task is to perform an on-demand investigation of a Kubernetes cluster namespace to diagnose root causes of failure and provide EXACT, copy-pasteable remediation fix commands.

Follow this troubleshooting strategy:
1. Scan the namespace health to identify any pods, deployments, services, or PVCs with abnormal states or high restart counts.
2. If unhealthy pods exist:
   - Read container logs and specs to extract exit codes (e.g., Exit Code 137 = OOMKilled, Exit Code 1/255 = Application error/missing config, Exit Code 127 = Entrypoint error).
   - Identify the parent controller (Deployment, StatefulSet, DaemonSet) and container names.
3. Remediation Command Rules:
   - Provide direct FIX commands (e.g., `kubectl patch deployment <name> -n <ns> ...`, `kubectl set image ...`, `kubectl rollout restart ...`, `kubectl set resources ...`) rather than generic diagnostic commands like `kubectl describe` or `kubectl logs`.
   - Ensure commands include the exact target namespace `-n <namespace>`.

Safety Rule: Do NOT invent hypothetical errors. Base your diagnosis strictly on empirical data retrieved from the cluster tools.
"""

    def __init__(self, inspector: KubernetesInspector):
        self.inspector = inspector
        self.api_key = os.environ.get("GEMINI_API_KEY", "")
        self.model_name = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
        self.client = None

        if self.api_key:
            try:
                from google import genai
                self.client = genai.Client(api_key=self.api_key)
                logger.info(f"Initialized Google GenAI client for model '{self.model_name}'.")
            except Exception as e:
                logger.warning(f"Could not initialize Google GenAI client: {e}. Will use fallback heuristic engine.")

    def run_investigation(self, cluster: Optional[str] = None, namespace: str = "default", user_prompt: Optional[str] = None) -> Dict[str, Any]:
        """
        Executes an on-demand investigation pipeline for the target cluster context and namespace.
        Returns both the list of agent thought steps and the final DiagnosisReport.
        """
        # Switch context if multi-cluster mode
        if cluster:
            self.inspector.switch_context(cluster)

        thought_steps: List[AgentThoughtStep] = []

        # Step 1: Health Scan
        cluster_info = f"cluster '{cluster}' / " if cluster else ""
        thought_steps.append(AgentThoughtStep(
            step=1,
            action="Scanning Telemetry",
            details=f"Querying Pod states, container restart counts, and warning events in {cluster_info}namespace '{namespace}'."
        ))

        health_data = self.inspector.scan_namespace_health(namespace=namespace)
        unhealthy_count = health_data.get("unhealthy_pod_count", 0)

        # Step 2: Deep Dive Data Collection
        deep_dive_data = {}
        if unhealthy_count > 0:
            for pod in health_data.get("unhealthy_pods", []):
                pod_name = pod["name"]
                
                container_names = [c["name"] if isinstance(c, dict) else c for c in pod["containers"]]
                thought_steps.append(AgentThoughtStep(
                    step=len(thought_steps) + 1,
                    action=f"Deep Dive: Pod '{pod_name}'",
                    details=f"Fetching logs, spec conditions, and status for container(s): {', '.join(container_names)}."
                ))

                # Fetch logs
                pod_logs = self.inspector.get_pod_logs(namespace=namespace, pod_name=pod_name, tail_lines=150)
                # Fetch details
                pod_details = self.inspector.get_pod_details(namespace=namespace, pod_name=pod_name)

                deep_dive_data[pod_name] = {
                    "details": pod_details,
                    "logs": pod_logs
                }
        else:
            thought_steps.append(AgentThoughtStep(
                step=len(thought_steps) + 1,
                action="Namespace Assessment",
                details=f"No pods in CrashLoopBackOff, OOMKilled, or Pending states detected in '{namespace}'."
            ))

        # Step 2.5: Security & Configuration Audit
        thought_steps.append(AgentThoughtStep(
            step=len(thought_steps) + 1,
            action="Security & Configuration Audit",
            details=f"Auditing workloads in namespace '{namespace}' for resource limits, probes, and privilege configurations."
        ))
        audit_data = self.inspector.run_security_audit(namespace=namespace)

        # Step 3: Reasoning & Report Generation (LLM or Heuristic Engine)
        thought_steps.append(AgentThoughtStep(
            step=len(thought_steps) + 1,
            action="Synthesizing Root Cause & Remediation",
            details="Analyzing telemetry logs, K8s specs, and security audit violations to build actionable diagnosis report."
        ))

        if self.client:
            report = self._generate_report_with_llm(namespace, user_prompt, health_data, deep_dive_data, audit_data)
        else:
            report = self._generate_heuristic_report(namespace, user_prompt, health_data, deep_dive_data, audit_data)

        return {
            "thought_steps": [t.model_dump() if hasattr(t, 'model_dump') else t.dict() for t in thought_steps],
            "report": report.model_dump() if hasattr(report, 'model_dump') else report.dict()
        }

    def _generate_report_with_llm(
        self, namespace: str, user_prompt: Optional[str], health_data: Dict[str, Any], deep_dive_data: Dict[str, Any], audit_data: List[Dict[str, Any]]
    ) -> DiagnosisReport:
        """Invokes Gemini 2.0 Flash with structured Pydantic schema enforcing exact report format."""
        from google.genai import types

        context_prompt = f"""
TARGET NAMESPACE: {namespace}
USER NOTE/PROMPT: {user_prompt or 'None provided'}

CLUSTER TELEMETRY SUMMARY:
{json.dumps(health_data, indent=2, default=str)}

DEEP-DIVE POD LOGS & SPECS:
{json.dumps(deep_dive_data, indent=2, default=str)}

CONFIG & SECURITY AUDIT VIOLATIONS:
{json.dumps(audit_data, indent=2)}
"""

        try:
            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=[context_prompt],
                    config=types.GenerateContentConfig(
                        system_instruction=self.SYSTEM_INSTRUCTION,
                        response_mime_type="application/json",
                        response_schema=DiagnosisReport,
                        temperature=0.1
                    )
                )
            except Exception as model_err:
                logger.warning(f"Model '{self.model_name}' failed ({model_err}), trying fallback 'gemini-1.5-flash'...")
                response = self.client.models.generate_content(
                    model="gemini-1.5-flash",
                    contents=[context_prompt],
                    config=types.GenerateContentConfig(
                        system_instruction=self.SYSTEM_INSTRUCTION,
                        response_mime_type="application/json",
                        response_schema=DiagnosisReport,
                        temperature=0.1
                    )
                )

            report_dict = json.loads(response.text)
            return DiagnosisReport(**report_dict)
        except Exception as e:
            logger.error(f"Error calling Gemini API for K8s diagnosis: {e}")
            return self._generate_heuristic_report(namespace, user_prompt, health_data, deep_dive_data, audit_data)

    def _generate_heuristic_report(
        self, namespace: str, user_prompt: Optional[str], health_data: Dict[str, Any], deep_dive_data: Dict[str, Any], audit_data: List[Dict[str, Any]] = None
    ) -> DiagnosisReport:
        """Deterministic heuristic analysis when GEMINI_API_KEY is omitted or offline."""
        from src.schemas import SecurityAuditViolation

        unhealthy_pods = health_data.get("unhealthy_pods", [])
        events = health_data.get("recent_warning_events", [])

        # Map security audit violations
        security_violations = []
        if audit_data:
            for violation in audit_data:
                security_violations.append(SecurityAuditViolation(**violation))

        if not unhealthy_pods and not events:
            return DiagnosisReport(
                severity=SeverityLevel.HEALTHY,
                summary=f"Namespace '{namespace}' is operating normally with all pods in healthy states.",
                root_cause="No pods in CrashLoopBackOff, OOMKilled, ImagePullBackOff, or Pending states were detected.",
                affected_resources=[],
                remediation_steps=[
                    RemediationStep(
                        step_number=1,
                        title="Monitor Cluster Metrics",
                        command=f"kubectl get pods -n {namespace}",
                        explanation="Continue monitoring namespace pod status and metrics server resource utilization."
                    )
                ],
                security_audits=security_violations,
                prevention_tips=["Ensure proper resource requests and limits are defined for all deployments."]
            )

        affected = [p["name"] for p in unhealthy_pods]
        remediation_steps = []
        root_causes = []

        for p in unhealthy_pods:
            p_name = p["name"]
            owner_kind = p.get("owner_kind", "Pod")
            owner_name = p.get("owner_name", p_name)
            target_res = f"{owner_kind.lower()}/{owner_name}" if owner_kind != "Pod" else f"pod/{p_name}"
            containers = p.get("containers", [])
            c_name = containers[0]["name"] if (containers and isinstance(containers[0], dict)) else "container"
            c_image = containers[0]["image"] if (containers and isinstance(containers[0], dict)) else "image"

            reasons = ", ".join(p.get("fault_reasons", []))
            logs = deep_dive_data.get(p_name, {}).get("logs", "")

            if "OOMKilled" in reasons or "exit code 137" in logs.lower():
                root_causes.append(f"Pod '{p_name}' ({owner_kind} '{owner_name}') was OOMKilled (Exit Code 137). Container '{c_name}' exceeded assigned memory limits.")
                remediation_steps.append(RemediationStep(
                    step_number=len(remediation_steps) + 1,
                    title=f"Increase Memory Limits for {owner_kind} '{owner_name}'",
                    command=f"kubectl patch {target_res} -n {namespace} --type='json' -p='[{{\"op\": \"replace\", \"path\": \"/spec/template/spec/containers/0/resources/limits/memory\", \"value\":\"512Mi\"}}]'",
                    explanation="Patches container memory limit spec from current quota to 512Mi to prevent OOM termination.",
                    patch_kind=owner_kind,
                    patch_name=owner_name,
                    patch_body='[{"op": "replace", "path": "/spec/template/spec/containers/0/resources/limits/memory", "value": "512Mi"}]'
                ))
            elif "ImagePullBackOff" in reasons or "ErrImagePull" in reasons:
                root_causes.append(f"Pod '{p_name}' failed to pull container image '{c_image}'. Invalid image tag or missing registry secret.")
                remediation_steps.append(RemediationStep(
                    step_number=len(remediation_steps) + 1,
                    title=f"Update Container Image for {owner_kind} '{owner_name}'",
                    command=f"kubectl set image {target_res} {c_name}=<valid-image-tag> -n {namespace}",
                    explanation="Updates the deployment container spec to a verified, accessible container image tag.",
                    patch_kind=owner_kind,
                    patch_name=owner_name,
                    patch_body=f'[{{"op": "replace", "path": "/spec/template/spec/containers/0/image", "value": "nginx:1.25"}}]'
                ))
            elif "CrashLoopBackOff" in reasons:
                root_causes.append(f"Pod '{p_name}' ({owner_kind} '{owner_name}') is in CrashLoopBackOff state due to application crash during startup.")
                remediation_steps.append(RemediationStep(
                    step_number=len(remediation_steps) + 1,
                    title=f"Restart & Rollout {owner_kind} '{owner_name}'",
                    command=f"kubectl rollout restart {target_res} -n {namespace}",
                    explanation="Triggers a fresh rolling update after updating environment variables or dependent services."
                ))
                remediation_steps.append(RemediationStep(
                    step_number=len(remediation_steps) + 1,
                    title=f"Inspect App Logs (--previous)",
                    command=f"kubectl logs pod/{p_name} -n {namespace} --previous --tail=100",
                    explanation="Fetches stdout/stderr output from the previously terminated container instance before it crashed."
                ))

        if not root_causes:
            root_causes.append(f"Detected {len(unhealthy_pods)} unhealthy pod(s) with active warning events in namespace '{namespace}'.")
            remediation_steps.append(RemediationStep(
                step_number=1,
                title="Inspect Pod Details & Events",
                command=f"kubectl get events -n {namespace} --sort-by='.metadata.creationTimestamp'",
                explanation="Scans chronological warning events to pinpoint scheduler or persistent volume binding failures."
            ))

        return DiagnosisReport(
            severity=SeverityLevel.CRITICAL if len(unhealthy_pods) > 1 else SeverityLevel.HIGH,
            summary=f"Identified {len(unhealthy_pods)} faulty pod(s) in namespace '{namespace}'.",
            root_cause="\n\n".join(root_causes),
            affected_resources=affected,
            remediation_steps=remediation_steps,
            security_audits=security_violations,
            prevention_tips=[
                "Configure health probes (livenessProbe and readinessProbe) with reasonable delay thresholds.",
                "Define resource requests and limits in Pod Spec to prevent resource starvation.",
                "Use container image tags (e.g. v1.2.3) instead of :latest to guarantee deployment reproducibility."
            ]
        )
