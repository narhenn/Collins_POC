"""
Aerospace Tier-A rule: EGT physics residual.
Uses a simplified Brayton-cycle relationship to predict EGT from fuel flow
and shaft speed. When the actual EGT diverges from the physics prediction,
it signals turbine degradation that statistics alone cannot explain.

This is the strongest signal in the 3-tier stack: if the physics model
says EGT should be 660C but it is 720C, something has physically changed
in the engine (blade erosion, nozzle coking, seal leakage).

Model: EGT_predicted = nominalEGT * (fuelFlow / nominalFuelFlow)^alpha
                       * (nominalN1 / N1)^beta + ambient_correction
Residual = actual_EGT - EGT_predicted
Fire when |residual| > threshold (default 30C).
"""

from behaviors.registry import Behavior, Tier, TelemetrySample, Finding


class EGTPhysicsResidual(Behavior):
    """First-principles EGT model. Predicts EGT from fuel flow and N1 using
    simplified gas-turbine thermodynamics. Fires when the actual EGT diverges
    from the physics prediction by more than the threshold."""
    behavior_id = "aero.egt_physics_residual"
    tier = Tier.A
    watches = ["aero:exhaustGasTemp"]
    reads = ["fuel flow and shaft speed from the same entity (via graph query)"]
    emits = "A critical Finding when EGT residual exceeds the physics threshold."

    def __init__(self, threshold_c: float = 30.0,
                 nominal_egt: float = 650.0,
                 nominal_fuel: float = 800.0,
                 nominal_n1: float = 5200.0,
                 alpha: float = 0.3,
                 beta: float = 0.2):
        self.threshold_c = threshold_c
        self.nominal_egt = nominal_egt
        self.nominal_fuel = nominal_fuel
        self.nominal_n1 = nominal_n1
        self.alpha = alpha
        self.beta = beta
        self._last_fuel: dict[str, float] = {}
        self._last_n1: dict[str, float] = {}
        self._firing: dict[str, bool] = {}

    def evaluate(self, sample: TelemetrySample, query) -> list[Finding]:
        ent = sample.entity_id

        # Try to get fuel flow and N1 from the graph (last known values)
        fuel = self.nominal_fuel
        n1 = self.nominal_n1
        try:
            node = query.get_node(sample.tenant_id, ent)
            if node:
                # Read co-located signals from the feed state
                fuel = float(node.get("fuelFlow", self._last_fuel.get(ent, self.nominal_fuel)))
                n1 = float(node.get("shaftSpeedN1", self._last_n1.get(ent, self.nominal_n1)))
        except Exception:
            fuel = self._last_fuel.get(ent, self.nominal_fuel)
            n1 = self._last_n1.get(ent, self.nominal_n1)

        # Simplified Brayton-cycle EGT prediction
        fuel_ratio = max(fuel / self.nominal_fuel, 0.1)
        n1_ratio = max(self.nominal_n1 / max(n1, 100.0), 0.5)
        egt_predicted = self.nominal_egt * (fuel_ratio ** self.alpha) * (n1_ratio ** self.beta)

        residual = sample.value - egt_predicted

        if abs(residual) <= self.threshold_c:
            self._firing[ent] = False
            return []

        if self._firing.get(ent):
            return []
        self._firing[ent] = True

        return [Finding(
            behavior_id=self.behavior_id,
            tier=self.tier,
            flags=ent,
            severity="critical",
            message=(f"EGT physics residual — actual {sample.value:.1f}C vs "
                     f"predicted {egt_predicted:.1f}C (residual: {residual:+.1f}C). "
                     f"The thermal model indicates a physical change in the engine: "
                     f"possible blade erosion, nozzle coking, or compressor seal leakage. "
                     f"This cannot be explained by operating conditions alone."),
            confidence=min(1.0, abs(residual) / (self.threshold_c * 2)),
            evidence={
                "actual_egt": sample.value,
                "predicted_egt": round(egt_predicted, 1),
                "residual_c": round(residual, 1),
                "threshold_c": self.threshold_c,
                "fuel_flow": fuel,
                "shaft_speed_n1": n1,
                "signal": sample.signal,
            },
        )]
