"""Run configuration — the operator-tunable knobs that deterministically shape outcomes."""
from __future__ import annotations

from pydantic import BaseModel, Field

from .enums import Difficulty


class RunConfig(BaseModel):
    """Operator configuration for a single simulation run.

    Everything here feeds the deterministic resolvers. Identical config + environment +
    scenario always produces an identical timeline.
    """

    difficulty: Difficulty = Difficulty.MEDIUM
    # Team readiness 0..100 — higher means faster, more reliable detection & response.
    readiness: int = Field(default=60, ge=0, le=100)
    # Total simulated duration in minutes (used for pacing/phase spacing, not outcomes).
    duration_min: int = Field(default=120, ge=5, le=480)
    industry: str = "generic"
    # Reserved for a future seeded-stochastic resolver. Unused in the deterministic core.
    seed: int = 0

    @property
    def readiness_factor(self) -> float:
        """Latency multiplier from readiness: readiness 0 -> 1.0x, 100 -> 0.5x (faster)."""
        return 1.0 - (self.readiness / 200.0)

    @property
    def readiness_norm(self) -> float:
        """Readiness normalised to 0..1."""
        return self.readiness / 100.0

    def latency(self, base_seconds: float) -> int:
        """Apply difficulty + readiness to a base latency, in whole sim-seconds (>=1)."""
        scaled = base_seconds * self.difficulty.factor * self.readiness_factor
        return max(1, round(scaled))
