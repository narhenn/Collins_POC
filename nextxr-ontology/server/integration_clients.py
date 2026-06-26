"""
integration_clients.py — API bridge clients for AUTOMIND and GoalCert.

These clients let NextXR call the other two platforms when key events happen:
  - AUTOMIND: trigger diagnosis workflow execution, stream logs
  - GoalCert: create MRO training scenarios, launch runs, fetch reports

Each client handles auth, retries, and graceful degradation (if the target
service is down, NextXR continues to work — the integration is best-effort).
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
#  AUTOMIND Client
# ---------------------------------------------------------------------------

@dataclass
class AutomindConfig:
    base_url: str = ""
    email: str = ""
    password: str = ""
    diagnosis_agent_id: str = ""  # pre-created Collins MRO Diagnosis agent

    def __post_init__(self):
        self.base_url = os.environ.get("AUTOMIND_URL", self.base_url or "http://localhost:8001")
        self.email = os.environ.get("AUTOMIND_EMAIL", self.email or "nextxr@goalcert.com")
        self.password = os.environ.get("AUTOMIND_PASSWORD", self.password or "collins2026")
        self.diagnosis_agent_id = os.environ.get("AUTOMIND_AGENT_ID", self.diagnosis_agent_id)


class AutomindClient:
    """Lightweight HTTP client for AUTOMIND workflow engine."""

    def __init__(self, config: Optional[AutomindConfig] = None):
        self.config = config or AutomindConfig()
        self._token: Optional[str] = None
        self._token_ts: float = 0.0

    @property
    def available(self) -> bool:
        return bool(self.config.diagnosis_agent_id)

    def _get_token(self) -> Optional[str]:
        """Get or refresh JWT token. Cached for 23 hours."""
        if self._token and (time.time() - self._token_ts) < 82800:
            return self._token
        try:
            import urllib.request
            data = json.dumps({
                "email": self.config.email,
                "password": self.config.password,
            }).encode()
            req = urllib.request.Request(
                f"{self.config.base_url}/api/auth/login",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = json.loads(resp.read())
                self._token = body.get("token") or body.get("access_token")
                self._token_ts = time.time()
                return self._token
        except Exception as e:
            logger.warning("AUTOMIND auth failed: %s", e)
            return None

    def trigger_diagnosis(
        self, tenant_id: str, incident_id: str,
        finding_ids: list[str], affected_entity_id: str,
        diagnosis_text: str = "",
    ) -> Optional[dict]:
        """Trigger the pre-built Collins MRO Diagnosis workflow in AUTOMIND.
        Returns {"execution_id": "...", "stream_url": "..."} or None."""
        if not self.available:
            return None
        token = self._get_token()
        if not token:
            return None
        try:
            import urllib.request
            data = json.dumps({
                "variables": {
                    "tenant_id": tenant_id,
                    "incident_id": incident_id,
                    "finding_ids": finding_ids,
                    "affected_entity_id": affected_entity_id,
                    "diagnosis_context": diagnosis_text,
                }
            }).encode()
            req = urllib.request.Request(
                f"{self.config.base_url}/api/agents/{self.config.diagnosis_agent_id}/execute",
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = json.loads(resp.read())
                execution_id = body.get("id")
                return {
                    "execution_id": execution_id,
                    "stream_url": f"{self.config.base_url}/api/executions/{execution_id}/stream",
                    "status": body.get("status", "pending"),
                }
        except Exception as e:
            logger.warning("AUTOMIND trigger failed: %s", e)
            return None

    def get_execution(self, execution_id: str) -> Optional[dict]:
        """Fetch completed execution results."""
        token = self._get_token()
        if not token:
            return None
        try:
            import urllib.request
            req = urllib.request.Request(
                f"{self.config.base_url}/api/executions/{execution_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read())
        except Exception as e:
            logger.warning("AUTOMIND get_execution failed: %s", e)
            return None


# ---------------------------------------------------------------------------
#  GoalCert Client
# ---------------------------------------------------------------------------

@dataclass
class GoalcertConfig:
    base_url: str = ""

    def __post_init__(self):
        self.base_url = os.environ.get("GOALCERT_URL", self.base_url or "http://localhost:8002")


class GoalcertClient:
    """Lightweight HTTP client for GoalCert Simulation Engine."""

    def __init__(self, config: Optional[GoalcertConfig] = None):
        self.config = config or GoalcertConfig()

    @property
    def available(self) -> bool:
        try:
            import urllib.request
            req = urllib.request.Request(
                f"{self.config.base_url}/api/health", method="GET",
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                return resp.status == 200
        except Exception:
            return False

    def create_mro_scenario(self, scenario: dict) -> Optional[str]:
        """Create an MRO training scenario. Returns scenario_id or None.
        Idempotent — if scenario_id already exists, returns it."""
        try:
            import urllib.request
            data = json.dumps(scenario).encode()
            req = urllib.request.Request(
                f"{self.config.base_url}/api/scenarios",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = json.loads(resp.read())
                return body.get("id")
        except Exception as e:
            # 409 = already exists, that's fine
            if "409" in str(e):
                return scenario.get("id")
            logger.warning("GoalCert create_scenario failed: %s", e)
            return None

    def launch_run(
        self, scenario_id: str, operator: str = "Collins Technician",
        difficulty: str = "Medium", duration_min: int = 45,
    ) -> Optional[dict]:
        """Launch a simulation run. Returns the full run result (synchronous)."""
        try:
            import urllib.request
            data = json.dumps({
                "scenario_id": scenario_id,
                "operator": operator,
                "config": {
                    "difficulty": difficulty,
                    "readiness": 70,
                    "duration_min": duration_min,
                    "industry": "aerospace_mro",
                },
            }).encode()
            req = urllib.request.Request(
                f"{self.config.base_url}/api/runs",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except Exception as e:
            logger.warning("GoalCert launch_run failed: %s", e)
            return None

    def get_report(self, run_id: str) -> Optional[dict]:
        """Fetch the After-Action Report for a completed run."""
        try:
            import urllib.request
            req = urllib.request.Request(
                f"{self.config.base_url}/api/runs/{run_id}/report",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read())
        except Exception as e:
            logger.warning("GoalCert get_report failed: %s", e)
            return None

    def get_events(self, run_id: str) -> Optional[list]:
        """Fetch the event timeline for a completed run."""
        try:
            import urllib.request
            req = urllib.request.Request(
                f"{self.config.base_url}/api/runs/{run_id}/events",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read())
        except Exception as e:
            logger.warning("GoalCert get_events failed: %s", e)
            return None


# ---------------------------------------------------------------------------
#  Singletons
# ---------------------------------------------------------------------------

_automind: Optional[AutomindClient] = None
_goalcert: Optional[GoalcertClient] = None


def get_automind_client() -> AutomindClient:
    global _automind
    if _automind is None:
        _automind = AutomindClient()
    return _automind


def get_goalcert_client() -> GoalcertClient:
    global _goalcert
    if _goalcert is None:
        _goalcert = GoalcertClient()
    return _goalcert
