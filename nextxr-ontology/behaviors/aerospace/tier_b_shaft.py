"""
Aerospace Tier-B rule: Shaft Speed N1 baseline deviation.
Learns normal N1 from warmup, flags deviations in BOTH directions
(bearing wear can cause oscillation — both high and low excursions).
"""
import math
from behaviors.registry import Behavior, Tier, TelemetrySample, Finding


class ShaftSpeedBaseline(Behavior):
    """Statistical baseline on turbine shaft speed N1. Fires on deviations
    in both directions — bearing wear causes speed oscillation."""
    behavior_id = "aero.shaft_speed_baseline"
    tier = Tier.B
    watches = ["aero:shaftSpeedN1"]
    reads = ["the live stream of shaft speed N1 readings"]
    emits = "A warning Finding when N1 deviates from baseline by > z_threshold sigma."

    def __init__(self, warmup: int = 15, z_threshold: float = 2.5):
        self.warmup = warmup
        self.z_threshold = z_threshold
        self._samples: dict[str, list[float]] = {}
        self._baseline: dict[str, tuple[float, float]] = {}
        self._firing: dict[str, bool] = {}

    def _fit(self, values: list[float]) -> tuple[float, float]:
        n = len(values)
        mean = sum(values) / n
        var = sum((v - mean) ** 2 for v in values) / n
        std = math.sqrt(var)
        return mean, std

    def evaluate(self, sample: TelemetrySample, query) -> list[Finding]:
        ent = sample.entity_id

        # Learning phase
        if ent not in self._baseline:
            buf = self._samples.setdefault(ent, [])
            buf.append(sample.value)
            if len(buf) >= self.warmup:
                self._baseline[ent] = self._fit(buf)
            return []

        # Scoring phase
        mean, std = self._baseline[ent]
        if std < 1e-9:
            return []

        z = (sample.value - mean) / std

        # Flag BOTH directions (oscillation = bearing wear)
        if abs(z) <= self.z_threshold:
            self._firing[ent] = False
            return []

        if self._firing.get(ent):
            return []
        self._firing[ent] = True

        direction = "above" if z > 0 else "below"
        confidence = min(1.0, abs(z) / (self.z_threshold * 2))
        return [Finding(
            behavior_id=self.behavior_id,
            tier=self.tier,
            flags=ent,
            severity="warning",
            message=(f"Shaft speed N1 deviation — {sample.value:.0f} RPM is "
                     f"{z:+.1f}sigma {direction} baseline "
                     f"(mu={mean:.0f} RPM, sigma={std:.1f}). "
                     f"Possible bearing wear or rotor imbalance."),
            confidence=round(confidence, 2),
            evidence={
                "value": sample.value,
                "z_score": round(z, 2),
                "baseline_mean": round(mean, 1),
                "baseline_std": round(std, 2),
                "z_threshold": self.z_threshold,
                "direction": direction,
                "signal": sample.signal,
            },
        )]
