"""Collins Aerospace MRO — Chiller Condenser Fault Repair Scenario.

A technician training drill generated from NextXR Digital Twin's diagnosis chain.
The twin detected COP degradation on Chiller-01 (condenser fouling). This scenario
walks the technician through the full repair procedure: fault isolation, LOTO,
diagnosis, component replacement, recharge, restoration, and verification.

Uses MRO techniques from catalog/mro_techniques.py — no cyber techniques.
"""
from __future__ import annotations

from app.engine.environment import AssetSpec, ControlSpec, EnvironmentSpec
from app.engine.scenario import Objectives, PlaybookStep, Scenario, TargetSelector


def build() -> Scenario:
    return Scenario(
        id="collins_chiller_mro",
        name="Collins MRO — Chiller Condenser Fault Repair",
        type="ics",
        industry="aerospace_mro",
        badge="badge-orange",
        label="MRO Training Drill",
        description=(
            "Technician training scenario for condenser fouling repair on Collins "
            "Aerospace MRO facility Chiller-01. Generated from NextXR Digital Twin "
            "diagnosis chain: COP degradation detected by 3-tier behavior engine "
            "(Tier-C threshold + Tier-B z-score + Tier-A physics residual). "
            "Procedure: fault isolation, LOTO, pressure test, Schrader valve "
            "replacement, R-410A recharge, functional test, twin resync."
        ),
        nominal_duration_min=45,
        difficulties=["Easy", "Medium", "Hard"],
        mitre_tactics=[
            "Fault Isolation", "Safety Lockout", "Diagnosis",
            "Repair Execution", "System Restoration", "Verification",
        ],
        phases=[
            "Fault Isolation", "Safety Lockout", "Diagnosis",
            "Repair Execution", "System Restoration", "Verification",
        ],
        recommended_topology=EnvironmentSpec(
            assets=[
                AssetSpec(
                    id="chiller-01", type="ot_plc",
                    name="Chiller-01 (Collins MRO)", role="primary_asset",
                    zone="ot", criticality=5,
                ),
                AssetSpec(
                    id="ahu-av01", type="ot_plc",
                    name="AHU-AV01 (Avionics Bay 1)", role="plc",
                    zone="ot", criticality=4,
                ),
                AssetSpec(
                    id="ahu-av02", type="ot_plc",
                    name="AHU-AV02 (Avionics Bay 2)", role="plc",
                    zone="ot", criticality=4,
                ),
                AssetSpec(
                    id="bms-controller", type="mes",
                    name="BMS Controller", role="it_ot_bridge",
                    zone="ot_dmz", criticality=3,
                ),
                AssetSpec(
                    id="nextxr-twin", type="digital_twin",
                    name="NextXR Digital Twin", role="scada_hmi",
                    zone="ot_dmz", criticality=3,
                ),
            ],
            controls=[
                ControlSpec(id="c-siem", type="siem", enabled=True),
                ControlSpec(id="c-seg", type="segmentation", enabled=True),
            ],
        ),
        playbook=[
            # Phase 1: Fault Isolation
            PlaybookStep(
                id="s01", technique="mro_fault_alert",
                phase="Fault Isolation", at_min=1, is_inject=True,
                label="NextXR Twin Alert: Chiller-01 COP dropped to 3.2 "
                      "(baseline 5.1). Condenser fouling suspected. "
                      "Fault code P0234 active.",
            ),
            PlaybookStep(
                id="s02", technique="mro_work_order",
                phase="Fault Isolation", at_min=3, is_inject=False,
                label="Work order WO-2026-4212 generated from diagnosis chain. "
                      "Assigned to technician.",
            ),

            # Phase 2: Safety Lockout
            PlaybookStep(
                id="s03", technique="mro_loto",
                phase="Safety Lockout", at_min=6,
                target=TargetSelector(by="role", value="primary_asset"),
                label="Apply LOTO to Chiller-01. Verify zero energy state. "
                      "Tag all isolation points per EASA Part 145.A.45.",
            ),

            # Phase 3: Diagnosis
            PlaybookStep(
                id="s04", technique="mro_pressure_test",
                phase="Diagnosis", at_min=10,
                target=TargetSelector(by="role", value="primary_asset"),
                label="Connect refrigerant manifold gauges. Record suction "
                      "pressure: 42 PSI (nominal 68 PSI). Confirm leak at "
                      "Schrader valve.",
            ),
            PlaybookStep(
                id="s05", technique="mro_visual_inspection",
                phase="Diagnosis", at_min=13,
                target=TargetSelector(by="role", value="primary_asset"),
                label="Document condenser coil condition with photos. "
                      "Heavy fouling observed on inlet face.",
            ),

            # Phase 4: Repair Execution
            PlaybookStep(
                id="s06", technique="mro_component_replace",
                phase="Repair Execution", at_min=18,
                target=TargetSelector(by="role", value="primary_asset"),
                label="Replace Schrader valve core (part #SV-3042). "
                      "Chemical wash condenser coils.",
            ),
            PlaybookStep(
                id="s07", technique="mro_system_evacuation",
                phase="Repair Execution", at_min=25,
                target=TargetSelector(by="role", value="primary_asset"),
                label="Evacuate system to 500 microns. Hold vacuum 15 min "
                      "to verify no residual leak.",
            ),
            PlaybookStep(
                id="s08", technique="mro_recharge",
                phase="Repair Execution", at_min=30,
                target=TargetSelector(by="role", value="primary_asset"),
                label="Recharge R-410A to 12.5 kg (spec: 12.2-12.8 kg). "
                      "Seal service ports.",
            ),

            # Phase 5: System Restoration
            PlaybookStep(
                id="s09", technique="mro_loto_remove",
                phase="System Restoration", at_min=35,
                target=TargetSelector(by="role", value="primary_asset"),
                label="Remove all LOTO tags. Restore power to Chiller-01. "
                      "Verify BMS shows unit online.",
            ),

            # Phase 6: Verification
            PlaybookStep(
                id="s10", technique="mro_functional_test",
                phase="Verification", at_min=38,
                target=TargetSelector(by="role", value="primary_asset"),
                label="Run Chiller-01 for 10 min. Verify: suction pressure "
                      "68 PSI, COP > 4.5, no leak detected.",
            ),
            PlaybookStep(
                id="s11", technique="mro_twin_resync",
                phase="Verification", at_min=42, is_inject=True,
                label="NextXR Twin resynced. Fault code P0234 cleared. "
                      "COP reading: 5.0. Work order WO-2026-4212 closed. "
                      "Total downtime: 2.5 hours.",
            ),
        ],
        objectives=Objectives(
            red=[
                "Complete LOTO before any physical work on the chiller",
                "Correctly identify root cause (Schrader valve leak + condenser fouling)",
                "Execute repair within the 45-minute training window",
                "Restore chiller COP to > 4.5 post-repair",
                "Document all steps for AS9100 compliance",
            ],
            blue=[
                "Verify LOTO was applied before diagnosis phase",
                "Confirm refrigerant specification compliance (R-410A, 12.2-12.8 kg)",
                "Detect if technician skips vacuum hold test",
                "Ensure digital twin resync and fault code clearance",
                "Validate work order documentation trail per EASA Part 145",
            ],
        ),
    )
