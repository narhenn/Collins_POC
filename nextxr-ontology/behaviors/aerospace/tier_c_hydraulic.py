"""
Aerospace Tier-C rule: Hydraulic pressure low threshold.
Fires when system pressure drops below the safe operating limit,
indicating seal failure or internal leakage.
"""
from behaviors.registry import Behavior, Tier, TelemetrySample, Finding


class HydraulicPressureLowRule(Behavior):
    """Fires when hydraulic system pressure drops below the minimum safe
    operating limit. Indicates seal failure, internal leakage, or pump
    degradation in hydraulic test rigs or flight control actuators."""
    behavior_id = "aero.hydraulic_pressure_low"
    tier = Tier.C
    watches = ["aero:hydraulicPressure"]
    reads = ["hydraulic system pressure in PSI"]
    emits = "A critical Finding when pressure drops below min_psi threshold."

    def __init__(self, min_psi: float = 2000.0):
        self.min_psi = min_psi
        self._state: dict[str, dict] = {}

    def evaluate(self, sample: TelemetrySample, query) -> list[Finding]:
        st = self._state.setdefault(sample.entity_id, {"fired": False})

        if sample.value >= self.min_psi:
            st["fired"] = False
            return []

        if st["fired"]:
            return []
        st["fired"] = True

        return [Finding(
            behavior_id=self.behavior_id,
            tier=self.tier,
            flags=sample.entity_id,
            severity="critical",
            message=(f"Hydraulic pressure low — {sample.value:.0f} PSI "
                     f"(minimum safe: {self.min_psi:.0f} PSI). "
                     f"Possible seal failure or internal leakage. "
                     f"Downstream actuators may lose authority."),
            confidence=1.0,
            evidence={
                "value": sample.value,
                "unit": "PSI",
                "min_threshold": self.min_psi,
                "signal": sample.signal,
            },
        )]
