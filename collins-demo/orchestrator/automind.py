"""
automind.py — client for the AUTOMIND agent platform.

AUTOMIND provides the agents that work on top of the twin. The orchestrator
logs in once, ensures a "Turbine MRO Diagnosis" agent exists, and executes it
with live twin context (findings + signals) when the user asks for a diagnosis.
Uses AUTOMIND's public REST API only.
"""
from __future__ import annotations

import logging
import time
import httpx

from config import config

logger = logging.getLogger("orchestrator.automind")

BASE = config.AUTOMIND_URL.rstrip("/") + "/api"

_token: str | None = None
_token_ts: float = 0.0
_agent_id: str | None = None


def _client(token: str | None = None) -> httpx.Client:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return httpx.Client(base_url=BASE, timeout=60.0, headers=headers)


def health() -> dict:
    try:
        with httpx.Client(timeout=10.0) as c:
            r = c.get(config.AUTOMIND_URL.rstrip("/") + "/docs")
            return {"ok": r.status_code == 200}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def _login() -> str | None:
    """Get/refresh a JWT. Registers the demo user if login fails."""
    global _token, _token_ts
    if _token and (time.time() - _token_ts) < 3600:
        return _token
    creds = {"email": config.AUTOMIND_EMAIL, "password": config.AUTOMIND_PASSWORD}
    with _client() as c:
        for path, body in (("/auth/login", creds),
                           ("/auth/register", {"name": "Collins Demo", **creds})):
            try:
                r = c.post(path, json=body)
                if r.status_code in (200, 201):
                    data = r.json()
                    _token = data.get("token") or data.get("access_token")
                    _token_ts = time.time()
                    if _token:
                        return _token
            except Exception as e:  # noqa: BLE001
                logger.debug("auth %s: %s", path, e)
    return None


def status() -> dict:
    """Lightweight reachability + auth status for the UI."""
    tok = _login()
    return {"reachable": health().get("ok", False), "authenticated": bool(tok)}


def ensure_agent(token: str) -> str | None:
    """Find or generate the Turbine MRO Diagnosis agent. Cached."""
    global _agent_id
    if _agent_id:
        return _agent_id
    with _client(token) as c:
        try:
            r = c.get("/agents")
            if r.status_code == 200:
                for a in r.json():
                    if "MRO Diagnosis" in (a.get("name") or ""):
                        _agent_id = a.get("id")
                        return _agent_id
        except Exception as e:  # noqa: BLE001
            logger.debug("list agents: %s", e)
        # Generate one from a description.
        try:
            r = c.post("/agents/generate", json={
                "description": (
                    "Turbine MRO Diagnosis agent. Given turbine telemetry findings "
                    "and sensor readings, analyse the likely root cause and "
                    "recommend prioritised maintenance actions for a technician.")})
            if r.status_code in (200, 201):
                _agent_id = r.json().get("id")
                return _agent_id
            logger.warning("agent generate %s: %s", r.status_code, r.text[:200])
        except Exception as e:  # noqa: BLE001
            logger.warning("agent generate failed: %s", e)
    return None


def diagnose(context: dict) -> dict:
    """Execute the diagnosis agent with live twin context."""
    token = _login()
    if not token:
        return {"status": "unavailable",
                "message": "AUTOMIND not reachable / not authenticated."}
    agent_id = ensure_agent(token)
    if not agent_id:
        return {"status": "unavailable",
                "message": "Could not provision an AUTOMIND agent (LLM key set on AUTOMIND?)."}
    with _client(token) as c:
        try:
            r = c.post(f"/agents/{agent_id}/execute", json={"variables": context})
            if r.status_code not in (200, 201):
                return {"status": "degraded",
                        "message": f"execute failed ({r.status_code})"}
            body = r.json()
            execution_id = body.get("id")
            result = body
            # Poll for completion (best-effort, short).
            for _ in range(15):
                if body.get("status") in ("completed", "failed", "error"):
                    break
                time.sleep(1)
                er = c.get(f"/executions/{execution_id}")
                if er.status_code == 200:
                    body = er.json()
                    result = body
            return {"status": "ok", "execution_id": execution_id,
                    "agent_id": agent_id, "result": result}
        except Exception as e:  # noqa: BLE001
            return {"status": "degraded", "message": str(e)}
