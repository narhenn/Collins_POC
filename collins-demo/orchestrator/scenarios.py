"""
scenarios.py — the scenario library + authored-scenario store.

The library is the set of "built" scenarios the operator can pick from; the
store holds scenarios the agent authors at runtime. Both feed the same run path
(nextxr.project + Claude outcome analysis).
"""
from __future__ import annotations

import time
import uuid

# Curated, demo-ready scenarios mapped to the turbine physics faults.
LIBRARY = [
    {"id": "hot_section", "name": "Hot-Section Distress (Blade Erosion)",
     "category": "Thermal", "fault": "blade_erosion", "severity": 0.9,
     "throttle": 0.97, "horizon_min": 30,
     "description": "Turbine blade erosion drives EGT toward the redline."},
    {"id": "oil_leak", "name": "Oil Leakage / Starvation",
     "category": "Lubrication", "fault": "oil_starvation", "severity": 0.85,
     "throttle": 0.9, "horizon_min": 30,
     "description": "An oil leak raises oil temperature and starves pressure."},
    {"id": "high_vibration", "name": "High Vibration / Bearing Wear",
     "category": "Mechanical", "fault": "bearing_wear", "severity": 0.85,
     "throttle": 0.9, "horizon_min": 30,
     "description": "Bearing wear raises shaft vibration and droops N1."},
    {"id": "surge", "name": "Compressor Surge / Stall",
     "category": "Aerodynamic", "fault": "surge", "severity": 0.9,
     "throttle": 0.95, "horizon_min": 20,
     "description": "Aerodynamic instability: N1 collapse with an EGT spike."},
    {"id": "nozzle_coking", "name": "Fuel Nozzle Coking",
     "category": "Combustion", "fault": "nozzle_coking", "severity": 0.8,
     "throttle": 0.92, "horizon_min": 40,
     "description": "Coked nozzles cause uneven combustion and a hot streak."},
    {"id": "fouling", "name": "Compressor Fouling",
     "category": "Thermal", "fault": "compressor_fouling", "severity": 0.75,
     "throttle": 0.9, "horizon_min": 45,
     "description": "Fouling reduces airflow and creeps EGT upward."},
    {"id": "sensor_failure", "name": "EGT Sensor Failure (Blind Spot)",
     "category": "Instrumentation", "fault": "sensor_failure", "severity": 0.9,
     "throttle": 0.97, "horizon_min": 30,
     "description": "The EGT reading freezes while the engine overheats — only "
                    "the physics residual catches it."},
]

_authored: list[dict] = []


def library() -> list[dict]:
    return LIBRARY + _authored


def get(scenario_id: str) -> dict | None:
    for s in library():
        if s["id"] == scenario_id:
            return s
    return None


def add_authored(spec) -> dict:
    """spec is an AuthoredScenario; store it and return the library entry."""
    entry = {
        "id": f"auth-{uuid.uuid4().hex[:8]}",
        "name": spec.name,
        "category": "Authored",
        "fault": spec.fault,
        "severity": spec.severity,
        "throttle": spec.throttle,
        "horizon_min": spec.horizon_min,
        "description": spec.expected_outcome,
        "rationale": spec.rationale,
        "authored": True,
        "created_at": time.time(),
    }
    _authored.insert(0, entry)
    return entry
