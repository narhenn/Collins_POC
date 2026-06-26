"""Scenario = attacker playbook + recommended environment (intent, not outcome).

A scenario expresses *what the attacker attempts* and *what environment makes the run
meaningful*. Outcomes emerge from the engine resolving the playbook against the world.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .environment import EnvironmentSpec


class TargetSelector(BaseModel):
    by: Literal["role", "type"] = "role"
    value: str
    # which match to use when several exist
    pick: Literal["first", "all"] = "first"


class PlaybookStep(BaseModel):
    id: str
    technique: str                      # technique key from the catalog
    phase: str                          # phase name (must be in scenario.phases)
    at_min: float = 0.0                 # nominal minute offset within the scenario timeline
    target: TargetSelector | None = None
    is_inject: bool = False
    label: str | None = None            # optional human description override


class Objectives(BaseModel):
    red: list[str] = Field(default_factory=list)
    blue: list[str] = Field(default_factory=list)


class Scenario(BaseModel):
    schema_version: int = 1
    id: str
    name: str
    type: str = "purple"                # red|blue|purple|soc|ics|cloud...
    industry: str = "generic"
    badge: str = "badge-purple"
    label: str = "Purple Team"
    description: str = ""
    difficulties: list[str] = Field(default_factory=lambda: ["Easy", "Medium", "Hard", "Expert"])
    nominal_duration_min: int = 120
    mitre_tactics: list[str] = Field(default_factory=list)
    phases: list[str] = Field(default_factory=list)
    recommended_topology: EnvironmentSpec
    playbook: list[PlaybookStep] = Field(default_factory=list)
    objectives: Objectives = Field(default_factory=Objectives)
    report_sections: list[str] = Field(default_factory=lambda: [
        "exec_summary", "timeline", "mitre_map", "scorecard",
        "regulatory_impact", "financial_impact", "recommendations",
        "maturity_score", "corrective_actions",
    ])
