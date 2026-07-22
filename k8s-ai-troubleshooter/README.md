# Kubernetes AI Troubleshooting Agent

An **on-demand diagnostic microservice** and Web Dashboard designed to investigate Kubernetes cluster failures, identify root causes, and provide actionable `kubectl` remediation scripts using Google Gemini AI.

---

## Architecture Overview

```
User Click "Investigate Cluster"
          │
          ▼
┌───────────────────────────┐
│ FastAPI On-Demand Server  │ ──(Mounted ServiceAccount)──> K8s API Server (Read-Only)
└─────────────┬─────────────┘                               │
              │                                             │ Read Logs, Events, Specs
              ▼                                             ▼
┌───────────────────────────┐                     ┌───────────────────────────┐
│ Data Redactor & Sanitizer │                     │ Telemetry & Pod State     │
└─────────────┬─────────────┘                     └───────────────────────────┘
              │
              ▼
┌───────────────────────────┐
│ Gemini AI Engine          │
│ (Structured Output)       │
└─────────────┬─────────────┘
              │
              ▼
┌───────────────────────────┐
│ Actionable Diagnosis UI   │
│ - Severity Badge          │
│ - Root Cause Breakdown    │
│ - Copyable Fix Commands   │
└───────────────────────────┘
```

---

## Features

- **On-Demand Inspection**: Triggered explicitly via API or Web UI (No continuous reconciling operators).
- **Strict Read-Only RBAC**: Uses dedicated `ServiceAccount` with `get`, `list`, `watch` permissions.
- **Data Redaction**: Automatically scrubs secrets, bearer tokens, API keys, and sensitive environment variables before sending logs to LLM.
- **Structured AI Diagnosis**: Returns structured severity, root cause, affected resources, copyable `kubectl` remediation scripts, and prevention best practices.
- **Offline / Heuristic Mode**: Includes deterministic fallback analysis when `GEMINI_API_KEY` is omitted or offline.

---

## Quickstart (Local Dev Mode)

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Set Gemini API Key (Optional for AI reasoning)**:
   ```bash
   export GEMINI_API_KEY="your-gemini-api-key"
   ```

3. **Run Backend Server**:
   ```bash
   python -m src.main
   ```
   Access dashboard at `http://localhost:8080` (uses your local `~/.kube/config`).

---

## Deploying to Kubernetes Cluster

1. **Apply RBAC Manifests**:
   ```bash
   kubectl apply -f k8s/rbac.yaml
   ```

2. **Create Secret for Gemini API Key (Optional)**:
   ```bash
   kubectl create secret generic gemini-credentials --from-literal=api-key="YOUR_GEMINI_API_KEY"
   ```

3. **Deploy Container**:
   ```bash
   kubectl apply -f k8s/deployment.yaml
   ```

4. **Access Web Dashboard**:
   ```bash
   kubectl port-forward svc/k8s-ai-troubleshooter-svc 8080:8080
   ```
   Open `http://localhost:8080`.
