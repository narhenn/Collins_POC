"""Aerospace MRO behavior rules — Tier A (physics), B (statistical), C (threshold)."""

from behaviors.aerospace.tier_a_egt_physics import EGTPhysicsResidual
from behaviors.aerospace.tier_b_egt import EGTDeviationBaseline
from behaviors.aerospace.tier_b_shaft import ShaftSpeedBaseline
from behaviors.aerospace.tier_c_hydraulic import HydraulicPressureLowRule
from behaviors.aerospace.tier_c_avionics_temp import AvionicsBayOverTempRule

__all__ = [
    "EGTPhysicsResidual",
    "EGTDeviationBaseline",
    "ShaftSpeedBaseline",
    "HydraulicPressureLowRule",
    "AvionicsBayOverTempRule",
]
