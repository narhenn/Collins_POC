"""Deterministic technique resolution: prevention, success, effects, telemetry,
detection scheduling and response scheduling. No RNG; pure functions of (world, config)."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..catalog.spec import TechniqueSpec
from ..config import RunConfig
from ..enums import CredScope, Health, SecurityState
from ..events import Emit
from ..models.assets import get_asset_type
from ..world import AssetInstance, World
from .preconditions import control_active_for, evaluate

RESPONSE_BASE_SECONDS = 300.0


@dataclass
class Resolution:
    status: str                       # "success" | "blocked" | "failed"
    prevented_by: str | None = None   # control type that blocked
    reason: str | None = None         # failed precondition label
    affected_assets: list[str] = field(default_factory=list)


def resolve(
    spec: TechniqueSpec, world: World, target: AssetInstance | None, config: RunConfig
) -> Resolution:
    """Decide whether the technique is prevented, fails preconditions, or succeeds."""
    # 1) Prevention — an active, covering control blocks the technique at/under its difficulty.
    for ctype in sorted(spec.prevention):
        threshold = spec.prevention[ctype]
        if config.difficulty.rank <= threshold and control_active_for(world, ctype, target):
            return Resolution(status="blocked", prevented_by=ctype)

    # 2) Preconditions — required attacker progress / environment.
    if spec.requires_target and target is None:
        return Resolution(status="failed", reason="no_target")
    ok, reason = evaluate(spec.preconditions, world, target)
    if not ok:
        return Resolution(status="failed", reason=reason)

    return Resolution(status="success")


def apply_effects(spec: TechniqueSpec, world: World, target: AssetInstance | None) -> list[str]:
    """Mutate world per the technique effects. Returns ids of assets whose state changed."""
    affected: list[str] = []
    for eff in spec.effects:
        if eff.kind in ("compromise", "foothold"):
            if target is not None:
                target.security_state = SecurityState.COMPROMISED
                world.attacker.add_foothold(target.id)
                affected.append(target.id)
        elif eff.kind == "suspicious":
            if target is not None and target.security_state == SecurityState.SAFE:
                target.security_state = SecurityState.SUSPICIOUS
                affected.append(target.id)
        elif eff.kind == "creds":
            world.attacker.raise_creds(CredScope(eff.value or "user"))
        elif eff.kind == "flag":
            world.attacker.flags[eff.value or "flag"] = True
        elif eff.kind == "degrade":
            if target is not None:
                target.health = Health.DEGRADED
                affected.append(target.id)
        elif eff.kind == "down":
            if target is not None:
                target.health = Health.DOWN
                target.security_state = SecurityState.COMPROMISED
                affected.append(target.id)
        elif eff.kind == "disable_control":
            ct = eff.value or ""
            if ct and ct not in world.attacker.disabled_control_types:
                world.attacker.disabled_control_types.append(ct)
        elif eff.kind == "exfiltrate":
            world.attacker.flags["exfiltrated"] = True
            if target is not None:
                target.props["exfiltrated"] = True
    return affected


def build_emits(spec: TechniqueSpec, world: World, target: AssetInstance | None) -> list[Emit]:
    """Telemetry produced by the technique and by the affected asset's reaction model."""
    out: list[Emit] = []
    tname = target.name if target is not None else "the environment"
    for tmpl in spec.emits:
        out.append(Emit(channel=tmpl.channel, severity=tmpl.severity,
                        text=tmpl.text.replace("{target}", tname)))
    if spec.react_kind and target is not None:
        out.extend(get_asset_type(target.type_key).react(target, spec.react_kind, world))
    return out


def compute_detection(
    spec: TechniqueSpec, world: World, target: AssetInstance | None,
    config: RunConfig, success_t: int,
) -> tuple[int, str, str] | None:
    """Earliest detection across active covering controls -> (detect_t, control_type, control_id)."""
    best: tuple[int, str, str] | None = None
    for ctype in sorted(spec.detection):
        ctrl = control_active_for(world, ctype, target)
        if ctrl is None:
            continue
        detect_t = success_t + config.latency(spec.detection[ctype])
        cand = (detect_t, ctype, ctrl.id)
        if best is None or (cand[0], cand[1]) < (best[0], best[1]):
            best = cand
    return best


def compute_response(
    spec: TechniqueSpec, target: AssetInstance | None, config: RunConfig, detect_t: int
) -> int | None:
    """When SOC/blue containment lands, if this technique is containable."""
    if not spec.containable or target is None:
        return None
    return detect_t + config.latency(RESPONSE_BASE_SECONDS)
