"""MRO (Maintenance, Repair, Overhaul) technique catalog for aerospace facilities.

These techniques model physical maintenance procedure steps rather than cyber
attacks. They use the same engine primitives: flag-based precondition chaining,
degrade/down effects on assets, and detection channels for supervisor oversight.

Scoring reinterpretation for MRO:
  red_success  = technician execution points (completing each step correctly)
  blue_detect  = supervisor/QA oversight points (verifying procedure adherence)
  blue_contain = regulatory compliance points (catching unsafe shortcuts)
"""
from __future__ import annotations

from ..enums import Severity
from .spec import (
    Effect,
    EmitTemplate,
    Precondition,
    ScoreSpec,
    TechniqueSpec,
    register,
)

# Supervisor detection latencies (seconds) — how quickly QA catches issues
QA_FAST = 30.0
QA_NORMAL = 120.0
BMS_ALERT = 60.0


def _pre(*items: tuple[str, str | None]) -> list[Precondition]:
    return [Precondition(kind=k, value=v) for k, v in items]


# --------------------------------------------------------------------------- #
#  MRO Fault Isolation
# --------------------------------------------------------------------------- #
register(TechniqueSpec(
    key="mro_fault_alert",
    name="Digital Twin Fault Alert",
    tactic="Fault Isolation",
    severity=Severity.HIGH,
    requires_target=False,
    preconditions=_pre(("start", None)),
    detection={"siem": BMS_ALERT},
    emits=[
        EmitTemplate(channel="ot", severity=Severity.HIGH,
                     text="NextXR Digital Twin detects anomaly on {target} — fault code active"),
    ],
    effects=[Effect(kind="flag", value="fault_detected")],
    containable=False,
    score=ScoreSpec(red_success=10, blue_detect=10, blue_contain=0),
))

register(TechniqueSpec(
    key="mro_work_order",
    name="Generate Maintenance Work Order",
    tactic="Fault Isolation",
    severity=Severity.INFO,
    requires_target=False,
    preconditions=_pre(("flag", "fault_detected")),
    detection={"siem": QA_NORMAL},
    emits=[
        EmitTemplate(channel="sys", severity=Severity.INFO,
                     text="Work order generated from diagnosis chain — assigned to technician"),
    ],
    effects=[Effect(kind="flag", value="work_order_issued")],
    containable=False,
    score=ScoreSpec(red_success=15, blue_detect=5, blue_contain=0),
))


# --------------------------------------------------------------------------- #
#  Safety Lockout (LOTO)
# --------------------------------------------------------------------------- #
register(TechniqueSpec(
    key="mro_loto",
    name="Lockout/Tagout Procedure",
    tactic="Safety Lockout",
    severity=Severity.CRITICAL,
    requires_target=True,
    preconditions=_pre(("flag", "work_order_issued"), ("asset", "ot_plc")),
    prevention={"segmentation": 1},  # safety interlock prevents bypass at Easy
    detection={"siem": QA_FAST},
    emits=[
        EmitTemplate(channel="ot", severity=Severity.MEDIUM,
                     text="LOTO applied to {target} — energy isolation confirmed"),
    ],
    effects=[
        Effect(kind="flag", value="loto_applied"),
        Effect(kind="degrade", value=None),  # asset goes to degraded state
    ],
    score=ScoreSpec(red_success=25, blue_detect=15, blue_contain=20),
))


# --------------------------------------------------------------------------- #
#  Diagnosis
# --------------------------------------------------------------------------- #
register(TechniqueSpec(
    key="mro_pressure_test",
    name="System Pressure Test",
    tactic="Diagnosis",
    severity=Severity.MEDIUM,
    requires_target=True,
    preconditions=_pre(("flag", "loto_applied"), ("asset", "ot_plc")),
    detection={"siem": QA_NORMAL},
    emits=[
        EmitTemplate(channel="ot", severity=Severity.MEDIUM,
                     text="Manifold gauges connected to {target} — pressure readings recorded"),
    ],
    effects=[Effect(kind="flag", value="diagnosis_confirmed")],
    score=ScoreSpec(red_success=30, blue_detect=20, blue_contain=0),
))

register(TechniqueSpec(
    key="mro_visual_inspection",
    name="Visual Inspection & Documentation",
    tactic="Diagnosis",
    severity=Severity.LOW,
    requires_target=True,
    preconditions=_pre(("flag", "loto_applied")),
    detection={"siem": QA_NORMAL},
    emits=[
        EmitTemplate(channel="sys", severity=Severity.LOW,
                     text="Visual inspection of {target} documented with photos"),
    ],
    effects=[Effect(kind="flag", value="inspection_documented")],
    score=ScoreSpec(red_success=15, blue_detect=10, blue_contain=0),
))


# --------------------------------------------------------------------------- #
#  Repair Execution
# --------------------------------------------------------------------------- #
register(TechniqueSpec(
    key="mro_component_replace",
    name="Component Replacement",
    tactic="Repair Execution",
    severity=Severity.HIGH,
    requires_target=True,
    preconditions=_pre(("flag", "diagnosis_confirmed"), ("asset", "ot_plc")),
    detection={"siem": QA_FAST},
    emits=[
        EmitTemplate(channel="ot", severity=Severity.MEDIUM,
                     text="Faulty component removed from {target} — replacement installed"),
    ],
    effects=[Effect(kind="flag", value="component_replaced")],
    score=ScoreSpec(red_success=40, blue_detect=20, blue_contain=15),
))

register(TechniqueSpec(
    key="mro_system_evacuation",
    name="System Evacuation & Preparation",
    tactic="Repair Execution",
    severity=Severity.MEDIUM,
    requires_target=True,
    preconditions=_pre(("flag", "component_replaced")),
    detection={"siem": QA_NORMAL},
    emits=[
        EmitTemplate(channel="ot", severity=Severity.LOW,
                     text="System evacuated to spec on {target} — ready for recharge"),
    ],
    effects=[Effect(kind="flag", value="system_prepared")],
    score=ScoreSpec(red_success=20, blue_detect=10, blue_contain=0),
))

register(TechniqueSpec(
    key="mro_recharge",
    name="Fluid/Refrigerant Recharge",
    tactic="Repair Execution",
    severity=Severity.MEDIUM,
    requires_target=True,
    preconditions=_pre(("flag", "system_prepared"), ("asset", "ot_plc")),
    detection={"siem": QA_FAST},
    emits=[
        EmitTemplate(channel="ot", severity=Severity.MEDIUM,
                     text="Refrigerant/fluid recharged to spec on {target} — service ports sealed"),
    ],
    effects=[Effect(kind="flag", value="recharge_complete")],
    score=ScoreSpec(red_success=30, blue_detect=15, blue_contain=10),
))


# --------------------------------------------------------------------------- #
#  System Restoration
# --------------------------------------------------------------------------- #
register(TechniqueSpec(
    key="mro_loto_remove",
    name="Remove LOTO — Restore Power",
    tactic="System Restoration",
    severity=Severity.HIGH,
    requires_target=True,
    preconditions=_pre(("flag", "recharge_complete"), ("flag", "loto_applied")),
    detection={"siem": QA_FAST},
    emits=[
        EmitTemplate(channel="ot", severity=Severity.HIGH,
                     text="LOTO removed from {target} — power/service restored"),
    ],
    effects=[Effect(kind="flag", value="power_restored")],
    score=ScoreSpec(red_success=20, blue_detect=15, blue_contain=20),
))


# --------------------------------------------------------------------------- #
#  Verification
# --------------------------------------------------------------------------- #
register(TechniqueSpec(
    key="mro_functional_test",
    name="Post-Repair Functional Test",
    tactic="Verification",
    severity=Severity.MEDIUM,
    requires_target=True,
    preconditions=_pre(("flag", "power_restored"), ("asset", "ot_plc")),
    detection={"siem": BMS_ALERT},
    emits=[
        EmitTemplate(channel="ot", severity=Severity.MEDIUM,
                     text="Functional test on {target} — operating parameters within spec"),
    ],
    effects=[Effect(kind="flag", value="functional_verified")],
    score=ScoreSpec(red_success=30, blue_detect=20, blue_contain=0),
))

register(TechniqueSpec(
    key="mro_twin_resync",
    name="Digital Twin Resync & Closeout",
    tactic="Verification",
    severity=Severity.LOW,
    requires_target=False,
    preconditions=_pre(("flag", "functional_verified")),
    detection={"siem": QA_NORMAL},
    emits=[
        EmitTemplate(channel="sys", severity=Severity.LOW,
                     text="NextXR Digital Twin resynced — fault code cleared, work order closed"),
    ],
    effects=[Effect(kind="flag", value="closeout_complete")],
    containable=False,
    score=ScoreSpec(red_success=15, blue_detect=10, blue_contain=0),
))
