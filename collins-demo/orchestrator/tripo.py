"""
tripo.py — Tripo 2D->3D generation client (image-to-3D).

Flow:  upload image -> create image_to_model task -> poll -> download GLB.
The GLB is cached locally and served from our own origin (no CDN CORS/expiry).
Reads TRIPO_API_KEY from env; surfaces the real Tripo error message on failure;
exposes the account balance for a terminal credits readout (not the frontend).
"""
from __future__ import annotations

import base64
import logging
from pathlib import Path

import httpx

from config import config

logger = logging.getLogger("orchestrator.tripo")

MODEL_DIR = Path(__file__).resolve().parent / "_models"
MODEL_DIR.mkdir(exist_ok=True)


def _headers() -> dict:
    return {"Authorization": f"Bearer {config.TRIPO_API_KEY}"}


def _base() -> str:
    return config.TRIPO_BASE.rstrip("/")


def _unwrap(resp: httpx.Response) -> tuple[dict, str | None]:
    """Return (data, error). Tripo wraps as {code, data, message}; code 0 = ok."""
    try:
        j = resp.json()
    except Exception:
        return {}, f"HTTP {resp.status_code}: {resp.text[:160]}"
    if isinstance(j, dict) and j.get("code") not in (0, None):
        msg = j.get("message") or "error"
        sug = j.get("suggestion")
        return {}, f"{msg}" + (f" ({sug})" if sug else "") + f" [code {j.get('code')}]"
    if resp.status_code != 200:
        return {}, f"HTTP {resp.status_code}: {resp.text[:160]}"
    return (j.get("data") or {}) if isinstance(j, dict) else {}, None


# ── Account balance (credits) ─────────────────────────────────────────

def balance() -> dict:
    """{'balance': float, 'frozen': float} or {'error': str}."""
    if not config.tripo_enabled:
        return {"error": "no_key"}
    try:
        with httpx.Client(timeout=15.0) as c:
            d, err = _unwrap(c.get(f"{_base()}/user/balance", headers=_headers()))
            return d if not err else {"error": err}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def log_balance(context: str = "") -> dict:
    """Print the credit balance to the orchestrator terminal."""
    b = balance()
    if "error" in b:
        logger.warning("TRIPO credits — unavailable (%s)%s", b["error"],
                       f" [{context}]" if context else "")
    else:
        logger.info("TRIPO credits — balance: %s, frozen: %s%s",
                    b.get("balance"), b.get("frozen"),
                    f"  [{context}]" if context else "")
    return b


# ── Generation ────────────────────────────────────────────────────────

def upload_image(image_bytes: bytes, filename: str = "machine.png") -> tuple[str | None, str | None]:
    ext = (filename.rsplit(".", 1)[-1] or "png").lower()
    mime = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
    try:
        with httpx.Client(timeout=60.0) as c:
            d, err = _unwrap(c.post(f"{_base()}/upload", headers=_headers(),
                                    files={"file": (filename, image_bytes, mime)}))
            if err:
                return None, err
            return d.get("image_token") or d.get("token") or d.get("file_token"), None
    except Exception as e:  # noqa: BLE001
        return None, str(e)


def start_image_task(image_bytes: bytes, filename: str = "machine.png") -> tuple[str | None, str | None]:
    """Upload + create image_to_model task. Returns (task_id, error)."""
    token, err = upload_image(image_bytes, filename)
    if err or not token:
        return None, err or "upload returned no token"
    ext = (filename.rsplit(".", 1)[-1] or "png").lower()
    if ext == "jpeg":
        ext = "jpg"
    try:
        with httpx.Client(timeout=60.0) as c:
            d, err = _unwrap(c.post(f"{_base()}/task",
                headers={**_headers(), "Content-Type": "application/json"},
                json={"type": "image_to_model", "file": {"type": ext, "file_token": token}}))
            if err:
                return None, err
            return d.get("task_id"), None
    except Exception as e:  # noqa: BLE001
        return None, str(e)


def get_task(task_id: str) -> dict:
    with httpx.Client(timeout=30.0) as c:
        d, err = _unwrap(c.get(f"{_base()}/task/{task_id}", headers=_headers()))
    if err:
        return {"status": "error", "progress": 0, "detail": err}
    status = d.get("status", "unknown")
    out = d.get("output") or d.get("result") or {}
    model_url = (out.get("pbr_model") or out.get("model")
                 or out.get("base_model") or out.get("model_glb"))
    return {"status": status, "progress": d.get("progress", 0),
            "model_url": model_url, "rendered_image": out.get("rendered_image")}


def download_model(url: str, tenant: str) -> str | None:
    dest = MODEL_DIR / f"{tenant}.glb"
    try:
        with httpx.Client(timeout=180.0, follow_redirects=True) as c:
            r = c.get(url)
            if r.status_code != 200:
                logger.warning("model download HTTP %s", r.status_code)
                return None
            dest.write_bytes(r.content)
        return f"/api/model/{tenant}.glb"
    except Exception as e:  # noqa: BLE001
        logger.warning("model download failed: %s", e)
        return None


def model_path(tenant: str) -> Path:
    return MODEL_DIR / f"{tenant}.glb"


# ── In-memory job registry ────────────────────────────────────────────

_jobs: dict[str, dict] = {}


def register_job(task_id: str, tenant: str) -> None:
    _jobs[task_id] = {"tenant": tenant, "status": "queued", "progress": 0, "model_url": None}


def job_status(task_id: str) -> dict:
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
    if t["status"] == "success" and t.get("model_url"):
        local = download_model(t["model_url"], job["tenant"])
        job["model_url"] = local
        job["status"] = "success" if local else "error"
        log_balance("after generation")
    return job


def b64_to_bytes(image_b64: str) -> bytes:
    if image_b64.startswith("data:"):
        image_b64 = image_b64.split(",", 1)[-1]
    return base64.b64decode(image_b64)
