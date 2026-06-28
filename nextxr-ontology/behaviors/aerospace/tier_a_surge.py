"""
Aerospace Tier-A rule: compressor surge / stall residual.

Surge is a transient aerodynamic instability: the compressor momentarily stops
pumping, so shaft speed (N1) drops sharply while EGT spikes (combustion gas
backs up). Neither signal alone is conclusive — it's the *correlation* of a fast
N1 drop with elevated EGT that identifies a surge, which is exactly the kind of
cross-signal physics reasoning a digital twin adds over a flat alarm.

Watches N1; reads the co-located EGT the ingestion layer stamps on the node.
"""
from collections import deque

from behaviors.registry import Behavior, Tier, TelemetrySample, Finding


class SurgeStallResidual(Behavior):
    behavior_id = "aero.surge_stall"
    tier = Tier.A
    watches = ["aero:shaftSpeedN1"]
    reads = ["shaft speed N1 trend + co-located EGT from the node"]
    emits = "A critical Finding when a fast N1 drop coincides with elevated EGT."

    def __init__(self, drop_frac: float = 0.07, egt_elevated_c: float = 700.0,
                 window: int = 6):
        self.drop_frac = drop_frac          # N1 drop vs recent peak to flag
        self.egt_elevated_c = egt_elevated_c
        self._hist: dict[str, deque] = {}
        self._fired: dict[str, bool] = {}

    def evaluate(self, sample: TelemetrySample, query) -> list[Finding]:
        ent = sample.entity_id
        hist = self._hist.setdefault(ent, deque(maxlen=8))
        hist.append(sample.value)

        peak = max(hist) if hist else sample.value
        if peak <= 0:
            return []
        drop = (peak - sample.value) / peak

        # co-located EGT (ingestion stamps latest values as node properties)
        egt = None
        try:
            node = query.get_node(sample.tenant_id, ent)
            if node and node.get("exhaustGasTemp") is not None:
                egt = float(node["exhaustGasTemp"])
        except Exception:
            egt = None

        surging = drop >= self.drop_frac and (egt is None or egt >= self.egt_elevated_c)
        if not surging:
            if drop < self.drop_frac * 0.5:
                self._fired[ent] = False
            return []
        if self._fired.get(ent):
            return []
        self._fired[ent] = True

        return [Finding(
            behavior_id=self.behavior_id, tier=self.tier, flags=ent,
            severity="critical",
            message=(f"Compressor surge / stall — N1 dropped {drop*100:.0f}% to "
                     f"{sample.value:.0f} RPM"
                     + (f" with EGT at {egt:.0f} C" if egt is not None else "")
                     + ". Aerodynamic instability: reduce throttle, check inlet and "
                       "variable geometry, inspect compressor for damage."),
            confidence=min(1.0, drop / (self.drop_frac * 2)),
            evidence={"n1": sample.value, "n1_peak": round(peak, 0),
                      "drop_frac": round(drop, 3),
                      "egt": egt, "signal": sample.signal})]
