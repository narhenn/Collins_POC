"""
Aerospace Tier-B rule: Exhaust Gas Temperature baseline deviation.
Learns normal EGT from warmup window, then flags when temperature
rises significantly above baseline (hot-section distress signal).
"""
import math
from behaviors.registry import Behavior, Tier, TelemetrySample, Finding


class EGTDeviationBaseline(Behavior):
    """Statistical baseline on turbine EGT. Learns a normal range during
    warmup, then fires when EGT rises significantly above learned mean.
    High EGT indicates compressor degradation, blade erosion, or nozzle coking."""
    behavior_id = "aero.egt_deviation_baseline"
    tier = Tier.B
    watches = ["aero:exhaustGasTemp"]
    reads = ["the live stream of exhaust gas temperature readings"]
    emits = "A critical Finding when EGT exceeds the learned baseline by > z_threshold sigma."

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

        # Only flag HIGH EGT (degradation drives temp up)
        if z <= self.z_threshold:
            self._firing[ent] = False
            return []

        if self._firing.get(ent):
            return []
        self._firing[ent] = True

        confidence = min(1.0, abs(z) / (self.z_threshold * 2))
        return [Finding(
            behavior_id=self.behavior_id,
            tier=self.tier,
            flags=ent,
            severity="critical",
            message=(f"EGT deviation — {sample.value:.1f}C is "
                     f"{z:+.1f}sigma above baseline "
                     f"(mu={mean:.1f}C, sigma={std:.1f}C). "
                     f"Possible hot-section distress: blade erosion, "
                     f"nozzle coking, or compressor degradation."),
            confidence=round(confidence, 2),
            evidence={
                "value": sample.value,
                "z_score": round(z, 2),
                "baseline_mean": round(mean, 1),
                "baseline_std": round(std, 2),
                "z_threshold": self.z_threshold,
                "signal": sample.signal,
            },
        )]
