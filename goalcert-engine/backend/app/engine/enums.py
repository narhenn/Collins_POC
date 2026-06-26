"""Core enumerations for the simulation engine.

String-valued enums so they serialise cleanly to JSON for the timeline, API and DB.
"""
from __future__ import annotations

from enum import Enum


class SecurityState(str, Enum):
    SAFE = "safe"
    SUSPICIOUS = "suspicious"
    COMPROMISED = "compromised"
    CONTAINED = "contained"  # blue isolated/remediated the asset


class Health(str, Enum):
    NOMINAL = "nominal"
    DEGRADED = "degraded"
    DOWN = "down"


class Side(str, Enum):
    RED = "red"
    BLUE = "blue"
    SOC = "soc"
    MGMT = "mgmt"
    SYSTEM = "system"


class Difficulty(str, Enum):
    EASY = "Easy"
    MEDIUM = "Medium"
    HARD = "Hard"
    EXPERT = "Expert"

    @property
    def rank(self) -> int:
        return {"Easy": 1, "Medium": 2, "Hard": 3, "Expert": 4}[self.value]

    @property
    def factor(self) -> float:
        """Detection/response latency multiplier — harder = slower defenders."""
        return {"Easy": 0.5, "Medium": 1.0, "Hard": 1.5, "Expert": 2.5}[self.value]


class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        return {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}[self.value]


class EventType(str, Enum):
    SYSTEM = "system"        # engine lifecycle / briefing
    PHASE = "phase"          # phase transition
    ATTACK = "attack"        # red technique applied (success)
    BLOCK = "block"          # technique prevented by a control
    FAIL = "fail"            # technique failed (preconditions unmet)
    TELEMETRY = "telemetry"  # asset/technique log line (feeds the console)
    DETECTION = "detection"  # a control raised an alert (feeds the alert feed)
    RESPONSE = "response"    # blue/soc containment action
    INJECT = "inject"        # scripted/manual inject surfaced to the operator
    OBJECTIVE = "objective"  # objective progress
    STATE = "state"          # asset state/health change (drives the network map)
    SCORE = "score"          # score / kpi update


class AssetCategory(str, Enum):
    ENDPOINT = "endpoint"
    SERVER = "server"
    IDENTITY = "identity"
    NETWORK = "network"
    SECURITY = "security"
    DATA = "data"
    CLOUD = "cloud"
    OT = "ot"


class CredScope(str, Enum):
    NONE = "none"
    USER = "user"
    PRIVILEGED = "privileged"
    DOMAIN_ADMIN = "domain_admin"

    @property
    def rank(self) -> int:
        return {"none": 0, "user": 1, "privileged": 2, "domain_admin": 3}[self.value]
