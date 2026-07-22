import os
import logging
from pathlib import Path
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from src.schemas import InvestigationRequest, NamespaceInfo
from src.k8s_inspector import KubernetesInspector
from src.ai_engine import AITroubleshooterEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("main")

app = FastAPI(
    title="Kubernetes AI Troubleshooting Agent",
    description="On-Demand AI-powered Diagnostic Service for Kubernetes Clusters",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize K8s Inspector and AI Engine
inspector = KubernetesInspector()
engine = AITroubleshooterEngine(inspector=inspector)

# Mount Static Files
STATIC_DIR = Path(__file__).parent.parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/", response_class=FileResponse)
async def serve_dashboard():
    """Serves the primary web dashboard interface."""
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"message": "Kubernetes AI Troubleshooting Agent API is Running"}

from typing import Optional
from src.schemas import InvestigationRequest, NamespaceInfo, ClusterInfo, DryRunDiffRequest

@app.get("/api/v1/health")
async def health_check():
    """Health check endpoint indicating service status and Gemini API key configuration."""
    return {
        "status": "healthy",
        "service": "k8s-ai-troubleshooter",
        "current_context": inspector.current_context,
        "gemini_api_configured": bool(engine.api_key)
    }

@app.get("/api/v1/clusters")
async def get_clusters():
    """Returns list of available Kubernetes cluster contexts."""
    try:
        clusters = inspector.list_clusters()
        return [ClusterInfo(**c) for c in clusters]
    except Exception as e:
        logger.error(f"Error fetching clusters: {e}")
        return [ClusterInfo(name=inspector.current_context or "default", is_current=True)]

@app.get("/api/v1/namespaces")
async def get_namespaces(cluster: Optional[str] = None):
    """Returns list of cluster namespaces for the selected cluster context."""
    try:
        if cluster:
            inspector.switch_context(cluster)
        raw_ns = inspector.list_namespaces()
        result = []
        for ns in raw_ns:
            ns_name = ns["name"]
            scan = inspector.scan_namespace_health(namespace=ns_name)
            result.append(NamespaceInfo(
                name=ns_name,
                status=ns.get("status", "Active"),
                pod_count=scan.get("total_pods", 0),
                unhealthy_pod_count=scan.get("unhealthy_pod_count", 0)
            ))
        return result
    except Exception as e:
        logger.error(f"Error fetching namespaces: {e}")
        return [{"name": "default", "status": "Active", "pod_count": 0, "unhealthy_pod_count": 0}]

@app.post("/api/v1/investigate")
async def investigate_cluster(req: InvestigationRequest):
    """
    On-Demand Endpoint: Triggers complete diagnostic scan and AI reasoning pipeline
    for the specified cluster context and namespace.
    """
    logger.info(f"Triggered on-demand investigation for cluster '{req.cluster}' / namespace '{req.namespace}' with prompt: '{req.prompt}'")
    try:
        result = engine.run_investigation(cluster=req.cluster, namespace=req.namespace, user_prompt=req.prompt)
        return result
    except Exception as e:
        logger.exception("Failed to execute investigation")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Investigation failed: {str(e)}"
        )

@app.post("/api/v1/dry-run/diff")
async def get_dry_run_diff(req: DryRunDiffRequest):
    """
    Simulates a patch via Kubernetes API dry-run and returns a unified YAML diff.
    """
    try:
        if req.cluster:
            inspector.switch_context(req.cluster)
            
        import json
        try:
            patch_data = json.loads(req.patch_body)
        except json.JSONDecodeError:
            import yaml
            try:
                patch_data = yaml.safe_load(req.patch_body)
            except Exception:
                patch_data = req.patch_body

        diff_text = inspector.get_patch_dry_run_diff(
            namespace=req.namespace,
            kind=req.kind,
            name=req.name,
            patch_data=patch_data
        )
        return {"diff_text": diff_text}
    except Exception as e:
        logger.exception("Failed to generate dry-run diff")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Dry-run comparison failed: {str(e)}"
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host="0.0.0.0", port=8080, reload=True)
