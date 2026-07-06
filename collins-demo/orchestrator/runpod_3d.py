"""
runpod_3d.py — RunPod serverless TRELLIS image-to-3D client, driving the full
production pipeline:

    upload → pipeline3d.preprocess (quality gate, enhancement, bg removal,
    subject framing) → TRELLIS on RunPod with REAL sampler parameters
    (pipeline3d.params quality presets; multi-image supported) →
    pipeline3d.postprocess (GLB validation + mesh stats) → serve.

The worker ignores unknown input fields, so the full-parameter payload is safe
against the legacy worker; deploy apps/trellis-worker to actually honour the
sampler settings, multi-image conditioning and metadata echo.

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

# The production pipeline layer needs Pillow/numpy/trimesh. Keep it OPTIONAL so
# the orchestrator (and the live-twin demo) always boots even if those aren't
# installed — generation then runs without the preprocess/validation extras.
try:
    from pipeline3d import preset, prepare_image, validate_glb, mesh_stats
    _PIPELINE_OK = True
except Exception as _e:  # noqa: BLE001
    _PIPELINE_OK = False
    logger.warning("pipeline3d unavailable (%s) — 3D generation runs without "
                   "preprocess/validation. Install: pip install pillow numpy trimesh", _e)

    def preset(quality):                              # minimal stand-in
        class _P:
            def payload(self):
                return {"texture_size": 1024, "output_format": "glb"}
        return _P()

    def prepare_image(data, remove_background: bool = True):
        return data, {"warnings": ["pipeline3d not installed — image sent as-is"],
                      "server_preprocess": True, "steps": []}

    def validate_glb(data):
        ok = len(data) > 20 and data[:4] == b"glTF"
        return {"ok": ok, "errors": [] if ok else ["not a binary glTF"],
                "size": len(data)}

    def mesh_stats(path):
        return {"available": False}

MODEL_DIR = Path(__file__).resolve().parent / "_models"
MODEL_DIR.mkdir(exist_ok=True)

_BASE = "https://api.runpod.ai/v2"


def _headers() -> dict:
    return {"Authorization": f"Bearer {config.RUNPOD_API_KEY}",
            "Content-Type": "application/json"}


def _url(path: str) -> str:
    return f"{_BASE}/{config.RUNPOD_ENDPOINT_ID}{path}"


# ── Generation ────────────────────────────────────────────────────────

# preprocess reports parked here until register_job() claims them
_pending_reports: dict[str, dict] = {}


def start_image_task(image_bytes: bytes, filename: str = "machine.png",
                     quality: str = "standard",
                     extra_images: list[bytes] | None = None,
                     mc_resolution: int | None = None,          # legacy, ignored
                     foreground_ratio: float | None = None      # legacy, ignored
                     ) -> tuple[str | None, str | None]:
    """Run the input layer locally, then send the conditioning image(s) plus the
    full TRELLIS parameter set to the RunPod endpoint. Returns (job_id, error).

    quality: draft|standard|ultra (legacy fast/high map to draft/standard).
    extra_images: optional additional views of the SAME object — the new worker
    runs multi-image conditioning, a large accuracy win on complex objects.
    """
    params = preset(quality)
    try:
        prepped, report = prepare_image(image_bytes)
    except Exception as e:  # noqa: BLE001 — never block generation on the gate
        prepped, report = image_bytes, {"warnings": [f"preprocess failed: {e}"],
                                        "server_preprocess": True, "steps": []}
    images_b64 = [base64.b64encode(prepped).decode()]
    for extra in (extra_images or [])[:3]:
        try:
            p2, _ = prepare_image(extra)
            images_b64.append(base64.b64encode(p2).decode())
        except Exception:  # noqa: BLE001
            images_b64.append(base64.b64encode(extra).decode())

    p = params.payload()
    p["preprocess"] = bool(report.get("server_preprocess", True))
    payload = {"input": {
        # legacy worker reads "image"; new worker prefers "images"
        "image": images_b64[0],
        "images": images_b64,
        **p,
    }}
    try:
        with httpx.Client(timeout=60.0) as c:
            r = c.post(_url("/run"), headers=_headers(), json=payload)
            if r.status_code != 200:
                return None, f"RunPod HTTP {r.status_code}: {r.text[:200]}"
            j = r.json()
            job_id = j.get("id")
            if not job_id:
                return None, f"RunPod returned no job ID: {j}"
            _pending_reports[job_id] = {
                "preprocess": report, "quality": quality,
                "params": p, "views": len(images_b64)}
            logger.info("RunPod job started: %s (quality=%s, views=%d, prep=%s)",
                        job_id, quality, len(images_b64),
                        "; ".join(report.get("steps", [])) or "none")
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
        glb_b64, meta = None, None
        if isinstance(output, dict):
            glb_b64 = output.get("glb") or output.get("model") or output.get("output")
            meta = output.get("metadata")          # new worker echoes params + timings
        elif isinstance(output, str):
            glb_b64 = output
        return {"status": "success", "progress": 100,
                "glb_b64": glb_b64, "metadata": meta,
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


def save_glb(glb_b64: str, tenant: str) -> tuple[str | None, dict]:
    """Decode, VALIDATE and save the GLB to _models/{tenant}.glb.
    Returns (serve_path | None, delivery_report)."""
    dest = MODEL_DIR / f"{tenant}.glb"
    try:
        data = base64.b64decode(glb_b64)
        check = validate_glb(data)
        if not check["ok"]:
            logger.warning("GLB failed validation: %s", check["errors"])
            return None, {"validation": check}
        dest.write_bytes(data)
        stats = mesh_stats(dest)
        logger.info("GLB saved: %s (%d bytes, %s verts)", dest, len(data),
                    stats.get("vertices", "?"))
        return f"/api/model/{tenant}.glb", {"validation": check, "mesh": stats}
    except Exception as e:  # noqa: BLE001
        logger.warning("GLB save failed: %s", e)
        return None, {"error": str(e)}


def model_path(tenant: str) -> Path:
    return MODEL_DIR / f"{tenant}.glb"


# ── In-memory job registry (same interface as tripo.py) ───────────────

_jobs: dict[str, dict] = {}


def register_job(task_id: str, tenant: str) -> None:
    _jobs[task_id] = {"tenant": tenant, "status": "queued",
                      "progress": 0, "model_url": None,
                      "pipeline": _pending_reports.pop(task_id, {})}


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

    # on success, decode + validate the GLB and save locally
    if t["status"] == "success" and t.get("glb_b64"):
        local, delivery = save_glb(t["glb_b64"], job["tenant"])
        job["model_url"] = local
        job.setdefault("pipeline", {})["delivery"] = delivery
        if t.get("metadata"):
            job["pipeline"]["worker"] = t["metadata"]
        job["status"] = "success" if local else "error"
        if not local:
            job["detail"] = "GLB failed validation: " + "; ".join(
                delivery.get("validation", {}).get("errors", []) or
                [delivery.get("error", "unknown")])
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
