"""
scenario.py — the wire-EDM fault catalogue + a non-destructive what-if.

The same six faults the forward sim understands, described for the UI / agents,
plus project(): fork a starting state, arm a fault, and project it forward with
the prediction engine WITHOUT touching the live twin.
"""
from __future__ import annotations

import copy

from edm.physics import EDMPhysics, EDMState
from edm.predict import predict as _predict

# fault id -> (label, what it is, the subsystem it attacks)
FAULTS = {
    "wire_break": {
        "label": "Wire breakage",
        "description": "The wire electrode is about to part: short-circuit bursts "
                       "spike, tension collapses and the cut halts. Scraps the part "
                       "and stops the machine until re-threaded.",
        "subsystem": "wire_system",
    },
    "dielectric_contamination": {
        "label": "Dielectric contamination",
        "description": "De-ioniser resin is spent, so conductivity climbs and the "
                       "gap can no longer hold off. Ignition turns erratic and the "
                       "short-circuit rate rises.",
        "subsystem": "dielectric",
    },
    "flushing_loss": {
        "label": "Flushing loss",
        "description": "A clogged filter or failing pump drops flushing flow and "
                       "pressure; debris bridges the kerf, the cut slows and shorts "
                       "rise toward a wire break.",
        "subsystem": "dielectric",
    },
    "guide_wear": {
        "label": "Guide / roller wear",
        "description": "Worn diamond guides let the wire wander: accuracy and surface "
                       "finish degrade and tension becomes unstable.",
        "subsystem": "guides_axes",
    },
    "chiller_failure": {
        "label": "Dielectric chiller failure",
        "description": "The chiller can no longer hold the bath temperature; warm "
                       "dielectric loses insulating strength and conductivity climbs.",
        "subsystem": "dielectric",
    },
    "servo_instability": {
        "label": "Servo / gap-control instability",
        "description": "The gap servo hunts instead of holding a stable gap, producing "
                       "bursts of short circuits and an unstable discharge.",
        "subsystem": "generator",
    },
}


def catalog() -> list[dict]:
    """The fault catalogue as a list, for the scenario UI."""
    return [{"id": k, **v} for k, v in FAULTS.items()]


def project(start_state: EDMState | None = None, *, fault: str = "none",
            severity: float = 0.7, intensity: float | None = None,
            horizon_min: float = 120.0, points: int = 120) -> dict:
    """Fork a state, arm `fault`, and project forward — no writes to the twin."""
    phys = EDMPhysics()
    state = copy.deepcopy(start_state) if start_state else phys.init_state()
    if intensity is not None:
        state.intensity = float(intensity)
    if fault and fault != "none":
        phys.inject(state, fault, severity)
    out = _predict(state, horizon_min=horizon_min, points=points, physics=phys)
    out["fault"] = fault
    return out
