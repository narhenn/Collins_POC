"""
Aerospace Tier-C rule: Avionics bay over-temperature (sustained threshold).
Fires when bay temperature exceeds the safe limit for avionics equipment
for a sustained duration — indicates cooling system degradation.
"""
from behaviors.registry import Behavior, Tier, TelemetrySample, Finding


class AvionicsBayOverTempRule(Behavior):
    """Sustained threshold on avionics bay temperature. Fires when temperature
    exceeds the safe operating limit for a sustained period. Avionics equipment
    has tight thermal budgets — typically setpoint +/- 2C."""
    behavior_id = "aero.avionics_bay_overtemp"
    tier = Tier.C
    watches = ["aero:avionicsBayTemp"]
    reads = ["avionics bay ambient temperature"]
    emits = "A warning Finding when bay temp exceeds limit for sustained duration."

    def __init__(self, temp_limit: float = 28.0, duration_minutes: float = 3.0):
        self.temp_limit = temp_limit
        self.duration_minutes = duration_minutes
        self._state: dict[str, dict] = {}

    def evaluate(self, sample: TelemetrySample, query) -> list[Finding]:
        st = self._state.setdefault(sample.entity_id, {
            "excursion_start": None,
            "fired": False,
        })

        if sample.value <= self.temp_limit:
            st["excursion_start"] = None
            st["fired"] = False
            return []

        # Start tracking excursion
        if st["excursion_start"] is None:
            st["excursion_start"] = sample.timestamp
            return []

        # Check sustained duration
        elapsed = (sample.timestamp - st["excursion_start"]).total_seconds() / 60.0
        if elapsed < self.duration_minutes:
            return []

        if st["fired"]:
            return []
        st["fired"] = True

        return [Finding(
            behavior_id=self.behavior_id,
            tier=self.tier,
            flags=sample.entity_id,
            severity="warning",
            message=(f"Avionics bay over-temperature — {sample.value:.1f}C "
                     f"exceeds {self.temp_limit:.0f}C limit for "
                     f"{elapsed:.0f} min. Cooling system degradation likely. "
                     f"Risk of avionics equipment thermal damage."),
            confidence=0.95,
            evidence={
                "value": sample.value,
                "unit": "DEG_C",
                "temp_limit": self.temp_limit,
                "excursion_minutes": round(elapsed, 1),
                "duration_threshold": self.duration_minutes,
                "signal": sample.signal,
            },
        )]
