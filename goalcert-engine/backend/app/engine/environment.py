"""EnvironmentSpec — the operator-composed environment — and the World builder.

The asset-selection feature produces an EnvironmentSpec (which assets, their zones/criticality,
and which controls are enabled/where). build_world() instantiates it into a live World, applying
asset/control type defaults and auto-attaching asset-scoped controls by category.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from .enums import Health, SecurityState
from .models.assets import get_asset_type
from .models.controls import get_control_type
from .world import AssetInstance, ControlInstance, World


class AssetSpec(BaseModel):
    id: str
    type: str
    name: str | None = None
    role: str | None = None
    zone: str | None = None
    criticality: int | None = None
    data_sensitivity: int | None = None
    props: dict | None = None


class ControlSpec(BaseModel):
    id: str
    type: str
    name: str | None = None
    enabled: bool = True
    scope: str | None = None             # override default scope
    targets: list[str] | None = None     # asset ids (asset scope) / zones (zone scope)
    props: dict | None = None


class EnvironmentSpec(BaseModel):
    assets: list[AssetSpec] = Field(default_factory=list)
    controls: list[ControlSpec] = Field(default_factory=list)

    def asset_types(self) -> set[str]:
        return {a.type for a in self.assets}


def _build_asset(spec: AssetSpec) -> AssetInstance:
    at = get_asset_type(spec.type)
    props = dict(at.default_props())
    if spec.props:
        props.update(spec.props)
    return AssetInstance(
        id=spec.id,
        type_key=spec.type,
        name=spec.name or at.NAME,
        role=spec.role,
        zone=spec.zone or at.DEFAULT_ZONE,
        criticality=spec.criticality if spec.criticality is not None else at.DEFAULT_CRITICALITY,
        data_sensitivity=(spec.data_sensitivity if spec.data_sensitivity is not None
                          else at.DEFAULT_DATA_SENSITIVITY),
        security_state=SecurityState.SAFE,
        health=Health.NOMINAL,
        props=props,
    )


def build_world(env: EnvironmentSpec) -> World:
    assets = [_build_asset(a) for a in env.assets]
    asset_by_id = {a.id: a for a in assets}

    controls: list[ControlInstance] = []
    for cspec in env.controls:
        ct = get_control_type(cspec.type)
        scope = cspec.scope or ct.DEFAULT_SCOPE
        targets = list(cspec.targets) if cspec.targets is not None else []
        # Composer convenience: asset-scoped control with no explicit targets auto-attaches
        # to every asset whose category it covers.
        if scope == "asset" and not targets and ct.ATTACHES_TO:
            cats = {c.value for c in ct.ATTACHES_TO}
            targets = [a.id for a in assets if get_asset_type(a.type_key).CATEGORY.value in cats]
        controls.append(ControlInstance(
            id=cspec.id,
            type_key=cspec.type,
            name=cspec.name or ct.NAME,
            enabled=cspec.enabled,
            scope=scope,  # type: ignore[arg-type]
            targets=targets,
            props=cspec.props or {},
        ))

    # Validate control targets reference real assets (asset scope).
    for c in controls:
        if c.scope == "asset":
            c.targets = [t for t in c.targets if t in asset_by_id]

    return World(assets=assets, controls=controls)
