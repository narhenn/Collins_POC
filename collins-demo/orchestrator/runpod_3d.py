"""
runpod_3d.py — RunPod serverless image-to-3D client.

Drop-in alternative to Tripo. Sends a base64 image to a RunPod endpoint
running TripoSR (or similar), polls for the GLB result, and saves it
locally. The rest of the pipeline (routes, frontend polling, GLB serving)
is provider-agnostic and works unchanged.

Env vars:
    RUNPOD_API_KEY      — RunPod API key (rpa_...)
    RUNPOD_ENDPOINT_ID  — serverless endpoint ID (e.g. h52njo7ydmwuao)
"""
from __future__ import annotations

import base64
import logging
import time
from pathlib import Path

import httpx

from config import config

logger = logging.getLogger("orchestrator.runpod_3d")

MODEL_DIR = Path(__file__).resolve().parent / "_models"
MODEL_DIR.mkdir(exist_ok=True)

_BASE = "https://api.runpod.ai/v2"


def _headers() -> dict:
    return {"Authorization": f"Bearer {config.RUNPOD_API_KEY}",
            "Content-Type": "application/json"}


def _url(path: str) -> str:
    return f"{_BASE}/{config.RUNPOD_ENDPOINT_ID}{path}"


# ── Generation ────────────────────────────────────────────────────────

def start_image_task(image_bytes: bytes, filename: str = "machine.png",
                     mc_resolution: int = 256,
                     foreground_ratio: float = 0.85) -> tuple[str | None, str | None]:
    """Send image to RunPod endpoint. Returns (job_id, error).

    The endpoint expects {"input": {"image": "<base64>"}} and returns
    {"id": "<job_id>", "status": "IN_QUEUE"}.
    """
    image_b64 = base64.b64encode(image_bytes).decode()
    payload = {
        "input": {
            "image": image_b64,
            "mc_resolution": mc_resolution,
            "foreground_ratio": foreground_ratio,
        }
    }
    try:
        with httpx.Client(timeout=30.0) as c:
            r = c.post(_url("/run"), headers=_headers(), json=payload)
            if r.status_code != 200:
                return None, f"RunPod HTTP {r.status_code}: {r.text[:200]}"
            j = r.json()
            job_id = j.get("id")
            if not job_id:
                return None, f"RunPod returned no job ID: {j}"
            logger.info("RunPod job started: %s", job_id)
            return job_id, None
    except Exception as e:  # noqa: BLE001
        return None, str(e)


def get_task(task_id: str) -> dict:
    """Poll RunPod job status. Returns {status, progress, glb_b64}.

    RunPod statuses: IN_QUEUE, IN_PROGRESS, COMPLETED, FAILED, CANCELLED.
    We map to the same shape tripo.get_task returns so the job_status()
    registry works unchanged.
    """
    try:
        with httpx.Client(timeout=30.0) as c:
            r = c.get(_url(f"/status/{task_id}"), headers=_headers())
            if r.status_code != 200:
                return {"status": "error", "progress": 0,
                        "detail": f"HTTP {r.status_code}"}
            j = r.json()
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "progress": 0, "detail": str(e)}

    rp_status = j.get("status", "UNKNOWN")

    # map RunPod status → our status
    if rp_status == "COMPLETED":
        output = j.get("output", {})
        glb_b64 = None
        if isinstance(output, dict):
            glb_b64 = output.get("glb") or output.get("model") or output.get("output")
        elif isinstance(output, str):
            glb_b64 = output
        return {"status": "success", "progress": 100,
                "glb_b64": glb_b64,
                "exec_ms": j.get("executionTime")}
    elif rp_status == "FAILED":
        return {"status": "failed", "progress": 0,
                "detail": j.get("error", "RunPod job failed")}
    elif rp_status == "CANCELLED":
        return {"status": "failed", "progress": 0, "detail": "Cancelled"}
    elif rp_status == "IN_PROGRESS":
        return {"status": "running", "progress": 50}
    else:  # IN_QUEUE
        return {"status": "queued", "progress": 10}


def save_glb(glb_b64: str, tenant: str) -> str | None:
    """Decode base64 GLB and save to _models/{tenant}.glb.
    Returns the local serve path on success."""
    dest = MODEL_DIR / f"{tenant}.glb"
    try:
        dest.write_bytes(base64.b64decode(glb_b64))
        logger.info("GLB saved: %s (%d bytes)", dest, dest.stat().st_size)
        return f"/api/model/{tenant}.glb"
    except Exception as e:  # noqa: BLE001
        logger.warning("GLB save failed: %s", e)
        return None


def model_path(tenant: str) -> Path:
    return MODEL_DIR / f"{tenant}.glb"


# ── In-memory job registry (same interface as tripo.py) ───────────────

_jobs: dict[str, dict] = {}


def register_job(task_id: str, tenant: str) -> None:
    _jobs[task_id] = {"tenant": tenant, "status": "queued",
                      "progress": 0, "model_url": None}


def job_status(task_id: str) -> dict:
    """Lazy poll: only hits RunPod if job isn't terminal yet."""
    job = _jobs.get(task_id)
    if job is None:
        return {"status": "unknown", "progress": 0}
    if job["status"] in ("success", "failed", "error"):
        return job

    t = get_task(task_id)
    job["status"] = t["status"]
    job["progress"] = t.get("progress", job["progress"])
    if t.get("detail"):
        job["detail"] = t["detail"]

    # on success, decode the GLB and save locally
    if t["status"] == "success" and t.get("glb_b64"):
        local = save_glb(t["glb_b64"], job["tenant"])
        job["model_url"] = local
        job["status"] = "success" if local else "error"
        if t.get("exec_ms"):
            logger.info("RunPod generation took %dms", t["exec_ms"])
    elif t["status"] == "success" and not t.get("glb_b64"):
        job["status"] = "error"
        job["detail"] = "RunPod returned success but no GLB data"

    return job


# ── Account balance ──────────────────────────────────────────────────

def balance() -> dict:
    """Query RunPod account balance via GraphQL."""
    if not config.runpod_enabled:
        return {"error": "no_key"}
    try:
        with httpx.Client(timeout=15.0) as c:
            r = c.post(
                f"https://api.runpod.io/graphql?api_key={config.RUNPOD_API_KEY}",
                json={"query": "{ myself { clientBalance currentSpendPerHr } }"},
                headers={"Content-Type": "application/json"},
            )
            data = r.json().get("data", {}).get("myself", {})
            return {"balance": data.get("clientBalance"),
                    "spend_per_hr": data.get("currentSpendPerHr")}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def log_balance(context: str = "") -> dict:
    b = balance()
    if "error" in b:
        logger.warning("RunPod balance — unavailable (%s)%s",
                       b["error"], f" [{context}]" if context else "")
    else:
        logger.info("RunPod balance — $%.2f, spend/hr $%.4f%s",
                    b.get("balance", 0), b.get("spend_per_hr", 0),
                    f"  [{context}]" if context else "")
    return b


def b64_to_bytes(image_b64: str) -> bytes:
    """Strip data-URL prefix if present and decode."""
    if image_b64.startswith("data:"):
        image_b64 = image_b64.split(",", 1)[-1]
    return base64.b64decode(image_b64)
