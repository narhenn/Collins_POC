"""
simulate_collins.py — aerospace MRO facility telemetry generator.

Generates telemetry for Collins Aerospace MRO equipment: turbine EGT,
shaft speed N1, hydraulic pressure, avionics bay temperature. Each
generator has a normal phase followed by a fault profile so every
aerospace behavior rule gets a chance to fire.

Also reuses CFP generators for facility infrastructure (UPS, chiller COP,
transformer temp, filter delta-P, pump vibration) since MRO facilities
have all these systems.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from behaviors.registry import TelemetrySample
from feed.simulate_cfp import (
    interleave,
    simulate_ups,
    simulate_transformer_temp,
    simulate_filter_dp,
    simulate_chiller_cop,
    simulate_vibration,
)


def _base_time():
    return datetime(2026, 6, 26, 8, 0, tzinfo=timezone.utc)


def simulate_egt(tenant_id: str, entity_id: str, *,
                 minutes: int = 40, fault_at: int = 25, seed: int = 200):
    """Exhaust Gas Temperature: normal ~650C, ramps to ~780C at fault
    (hot-section distress — blade erosion or nozzle coking)."""
    rng = random.Random(seed)
    t0 = _base_time()
    for m in range(minutes):
        ts = t0 + timedelta(minutes=m)
        if m < fault_at:
            value = 650.0 + rng.gauss(0, 5.0)
        else:
            # gradual ramp simulating turbine degradation
            ramp = min(130.0, (m - fault_at) * 8.5)
            value = 650.0 + ramp + rng.gauss(0, 3.0)
        yield TelemetrySample(
            signal="aero:exhaustGasTemp", entity_id=entity_id,
            value=round(value, 1), unit="DEG_C",
            timestamp=ts, tenant_id=tenant_id,
        )


def simulate_shaft_speed(tenant_id: str, entity_id: str, *,
                         minutes: int = 45, fault_at: int = 30, seed: int = 201):
    """Shaft speed N1: normal ~5200 RPM, develops droop at fault
    (bearing wear → increased friction → N1 sags)."""
    rng = random.Random(seed)
    t0 = _base_time()
    for m in range(minutes):
        ts = t0 + timedelta(minutes=m)
        if m < fault_at:
            value = 5200.0 + rng.gauss(0, 8.0)
        else:
            # progressive N1 droop from bearing friction
            droop = min(60.0, (m - fault_at) * 3.5)
            value = 5200.0 - droop + rng.gauss(0, 6.0)
        yield TelemetrySample(
            signal="aero:shaftSpeedN1", entity_id=entity_id,
            value=round(value, 0), unit="REV-PER-MIN",
            timestamp=ts, tenant_id=tenant_id,
        )


def simulate_hydraulic_pressure(tenant_id: str, entity_id: str, *,
                                minutes: int = 35, leak_at: int = 20, seed: int = 202):
    """Hydraulic pressure: normal ~3000 PSI, drops at leak_at
    (seal failure → internal leakage)."""
    rng = random.Random(seed)
    t0 = _base_time()
    for m in range(minutes):
        ts = t0 + timedelta(minutes=m)
        if m < leak_at:
            value = 3000.0 + rng.gauss(0, 20.0)
        else:
            # progressive pressure loss from seal degradation
            drop = min(1400.0, (m - leak_at) * 45.0)
            value = 3000.0 - drop + rng.gauss(0, 15.0)
            value = max(0.0, value)
        yield TelemetrySample(
            signal="aero:hydraulicPressure", entity_id=entity_id,
            value=round(value, 0), unit="PSI",
            timestamp=ts, tenant_id=tenant_id,
        )


def simulate_avionics_temp(tenant_id: str, entity_id: str, *,
                           minutes: int = 40, fault_at: int = 22, seed: int = 203):
    """Avionics bay temperature: normal 22C, rises on chiller degradation
    (cascade from cooling loss → avionics thermal excursion)."""
    rng = random.Random(seed)
    t0 = _base_time()
    for m in range(minutes):
        ts = t0 + timedelta(minutes=m)
        if m < fault_at:
            value = 22.0 + rng.gauss(0, 0.3)
        else:
            # gradual temperature rise as cooling degrades
            ramp = min(12.0, (m - fault_at) * 0.65)
            value = 22.0 + ramp + rng.gauss(0, 0.2)
        yield TelemetrySample(
            signal="aero:avionicsBayTemp", entity_id=entity_id,
            value=round(value, 1), unit="DEG_C",
            timestamp=ts, tenant_id=tenant_id,
        )


def simulate_mro_facility(tenant_id: str, asset_ids: dict[str, str]):
    """Run the full Collins MRO facility simulation with aerospace +
    facility infrastructure systems.

    asset_ids maps role to entity_id:
        {
            "turbine_rig_1": "<rig entity id>",
            "turbine_rig_2": "<rig entity id>",
            "hydraulic_1": "<hydraulic actuator entity id>",
            "avionics_bay_1": "<avionics bay entity id>",
            "chiller": "<chiller entity id>",
            "ups": "<ups entity id>",
            "transformer": "<transformer entity id>",
            "filter": "<filter entity id>",
            "pump": "<pump entity id>",
        }
    """
    generators = []

    # Aerospace-specific generators
    if "turbine_rig_1" in asset_ids:
        generators.append(simulate_egt(
            tenant_id, asset_ids["turbine_rig_1"], minutes=40, fault_at=25))
        generators.append(simulate_shaft_speed(
            tenant_id, asset_ids["turbine_rig_1"], minutes=45, fault_at=30))
    if "hydraulic_1" in asset_ids:
        generators.append(simulate_hydraulic_pressure(
            tenant_id, asset_ids["hydraulic_1"], minutes=35, leak_at=20))
    if "avionics_bay_1" in asset_ids:
        generators.append(simulate_avionics_temp(
            tenant_id, asset_ids["avionics_bay_1"], minutes=40, fault_at=22))

    # Reuse CFP generators for facility infrastructure
    if "chiller" in asset_ids:
        generators.append(simulate_chiller_cop(
            tenant_id, asset_ids["chiller"], minutes=40))
    if "ups" in asset_ids:
        generators.append(simulate_ups(
            tenant_id, asset_ids["ups"], minutes=30, fault_at=25))
    if "transformer" in asset_ids:
        generators.append(simulate_transformer_temp(
            tenant_id, asset_ids["transformer"], minutes=30, fault_at=25))
    if "filter" in asset_ids:
        generators.append(simulate_filter_dp(
            tenant_id, asset_ids["filter"], minutes=35, fault_at=25))
    if "pump" in asset_ids:
        generators.append(simulate_vibration(
            tenant_id, asset_ids["pump"], minutes=45, fault_at=30))

    yield from interleave(*generators)
