from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field

class SeverityLevel(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    HEALTHY = "HEALTHY"

class SecurityAuditViolation(BaseModel):
    resource: str = Field(description="Target resource kind and name (e.g. Deployment/my-app)")
    rule: str = Field(description="Rule description (e.g. Missing CPU Limits)")
    severity: str = Field(description="Severity (HIGH, MEDIUM, LOW)")
    description: str = Field(description="Detailed explanation of the violation")
    remediation: str = Field(description="Remediation fix recommendation")

class RemediationStep(BaseModel):
    step_number: int = Field(description="Step order (1, 2, 3...)")
    title: str = Field(description="Short action title")
    command: Optional[str] = Field(None, description="Executable kubectl or helm command if applicable")
    explanation: str = Field(description="Why this step is necessary and what it accomplishes")
    patch_kind: Optional[str] = Field(None, description="Target resource kind (e.g. Deployment, Service) for patch preview")
    patch_name: Optional[str] = Field(None, description="Target resource name for patch preview")
    patch_body: Optional[str] = Field(None, description="JSON/YAML patch string content for dry-run preview")

class DiagnosisReport(BaseModel):
    severity: SeverityLevel = Field(description="Overall severity assessment")
    summary: str = Field(description="Concise 1-2 sentence executive summary of cluster/namespace health")
    root_cause: str = Field(description="Detailed technical breakdown of identified faults or root causes")
    affected_resources: List[str] = Field(default_factory=list, description="List of affected pod, service, deployment, or PVC names")
    remediation_steps: List[RemediationStep] = Field(default_factory=list, description="Ordered step-by-step fix commands and actions")
    security_audits: List[SecurityAuditViolation] = Field(default_factory=list, description="List of configuration security and best-practice audit violations")
    prevention_tips: List[str] = Field(default_factory=list, description="Recommendations to prevent future occurrences")

class InvestigationRequest(BaseModel):
    cluster: Optional[str] = Field(None, description="Optional cluster context name (for multi-cluster mode)")
    namespace: str = Field("default", description="Kubernetes namespace to investigate")
    prompt: Optional[str] = Field(None, description="Optional user note or specific problem description")

class ClusterInfo(BaseModel):
    name: str = Field(description="Cluster context name")
    is_current: bool = Field(False, description="Whether this is the active default context")

class NamespaceInfo(BaseModel):
    name: str
    status: str
    pod_count: int
    unhealthy_pod_count: int

class AgentThoughtStep(BaseModel):
    step: int
    action: str
    details: str

class DryRunDiffRequest(BaseModel):
    cluster: Optional[str] = None
    namespace: str
    kind: str
    name: str
    patch_body: str
