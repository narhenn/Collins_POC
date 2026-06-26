"""The deterministic simulation orchestrator.

run(scenario, environment, config) -> RunResult

Event-queue driven so that scheduled detections and containments interleave with later
attack steps — meaning blue containment can truncate the attacker's path (emergent outcomes).
Pure: no wall-clock, no RNG. Identical inputs always produce an identical timeline.
"""
from __future__ import annotations

import heapq

from .catalog.spec import get_technique
from .config import RunConfig
from .enums import EventType, SecurityState, Severity, Side
from .environment import EnvironmentSpec, build_world
from .events import SimEvent
from .kpis import compute_kpis
from .resolve import resolver as R
from .result import ObjectiveStatus, RunResult
from .scenario import Scenario, TargetSelector
from .world import AssetInstance, World

# ordering of same-timestamp events
_KIND_PRIORITY = {"phase": 0, "attack": 1, "detection": 4, "response": 5}


def _select_target(world: World, sel: TargetSelector | None) -> AssetInstance | None:
    if sel is None:
        return None
    matches = world.by_role(sel.value) if sel.by == "role" else world.by_type(sel.value)
    return matches[0] if matches else None


def _asset_snapshot(world: World) -> list[dict]:
    return [
        {
            "id": a.id, "type": a.type_key, "name": a.name, "role": a.role,
            "zone": a.zone, "criticality": a.criticality,
            "security_state": a.security_state.value, "health": a.health.value,
        }
        for a in world.all_assets()
    ]


_RED_KW = {
    "foothold": ("access", "compromise", "foothold", "phish", "initial"),
    "privilege": ("privilege", "escalat", "credential", "admin"),
    "domain_admin": ("domain admin",),
    "persistence": ("persist",),
    "exfil": ("exfil",),
    "ransomware": ("ransom", "encrypt", "deploy"),
    "ot": ("ot", "plc", "process", "production", "physical", "scada"),
}
_BLUE_KW = {
    "detect": ("detect", "identif", "hunt", "evidence", "forensic", "preserve", "timeline", "scope"),
    "contain": ("contain", "isolat", "block"),
    "prevent": ("prevent",),
    "recover": ("recover", "restore", "continuity", "backup"),
    "notify": ("notif", "report", "regulat", "communicat", "escalat", "draft"),
}


def _objective_met(text: str, milestones: dict[str, bool], keywords: dict[str, tuple]) -> bool:
    low = text.lower()
    matched_any = False
    for milestone, kws in keywords.items():
        if any(kw in low for kw in kws):
            matched_any = True
            if milestones.get(milestone):
                return True
    return False if matched_any else False


def run(scenario: Scenario, env: EnvironmentSpec, config: RunConfig) -> RunResult:
    world = build_world(env)
    events: list[SimEvent] = []
    duration_s = config.duration_min * 60
    nominal = max(1, scenario.nominal_duration_min)
    scale = config.duration_min / nominal

    seq = 0

    def emit(t: int, etype: EventType, **kw) -> None:
        nonlocal seq
        events.append(SimEvent(seq=seq, t=t, type=etype, **kw))
        seq += 1

    def step_time(at_min: float) -> int:
        return max(0, round(at_min * 60 * scale))

    # ---- intro events --------------------------------------------------------
    emit(0, EventType.SYSTEM, side=Side.SYSTEM, actor="engine",
         title="Initialised", message=f"Scenario loaded: {scenario.name}")
    emit(0, EventType.SYSTEM, side=Side.SYSTEM, actor="white-cell",
         severity=Severity.INFO, title="Briefing", message=scenario.description)

    # ---- seed the event queue with attack steps ------------------------------
    heap: list[tuple] = []
    counter = 0
    for step in scenario.playbook:
        phase_idx = scenario.phases.index(step.phase) if step.phase in scenario.phases else 0
        heapq.heappush(
            heap,
            (step_time(step.at_min), _KIND_PRIORITY["attack"], counter,
             {"kind": "attack", "step": step, "phase_idx": phase_idx}),
        )
        counter += 1

    # ---- accumulators --------------------------------------------------------
    attempts = successes = detected = contained = blocked = 0
    dwells: list[int] = []
    mttrs: list[int] = []
    first_detection_t: int | None = None
    red_score = blue_score = 0
    current_phase_idx = -1

    def score_event(t: int) -> None:
        emit(t, EventType.SCORE, side=Side.SYSTEM, actor="scoring",
             title="score", data={"red": red_score, "blue": blue_score})

    # ---- main loop -----------------------------------------------------------
    while heap:
        t, _prio, _c, payload = heapq.heappop(heap)
        if t > duration_s:
            continue
        kind = payload["kind"]

        if kind == "attack":
            step = payload["step"]
            spec = get_technique(step.technique)
            target = _select_target(world, step.target)
            phase = step.phase
            tname = target.name if target else "environment"

            # phase transition
            if payload["phase_idx"] > current_phase_idx:
                current_phase_idx = payload["phase_idx"]
                emit(t, EventType.PHASE, side=Side.SYSTEM, actor="white-cell",
                     phase=phase, title=f"Phase: {phase}", message=f"Entering phase: {phase}")

            if step.is_inject:
                emit(t, EventType.INJECT, side=Side.RED, actor="white-cell", phase=phase,
                     severity=spec.severity, technique=spec.mitre, title="Inject",
                     message=step.label or spec.name,
                     asset_id=target.id if target else None, asset_label=tname if target else None)

            attempts += 1
            res = R.resolve(spec, world, target, config)

            if res.status == "blocked":
                blocked += 1
                blue_score += spec.score.blue_contain
                emit(t, EventType.BLOCK, side=Side.BLUE, actor=res.prevented_by or "control",
                     phase=phase, severity=Severity.MEDIUM, technique=spec.mitre,
                     title=f"Prevented: {spec.name}",
                     message=f"{spec.name} blocked by {res.prevented_by} ({tname})",
                     asset_id=target.id if target else None, asset_label=tname if target else None)
                score_event(t)

            elif res.status == "failed":
                emit(t, EventType.FAIL, side=Side.RED, actor="red-team", phase=phase,
                     severity=Severity.LOW, technique=spec.mitre,
                     title=f"Attempt failed: {spec.name}",
                     message=f"Preconditions unmet ({res.reason}); attacker cannot {spec.name} on {tname}",
                     asset_id=target.id if target else None, asset_label=tname if target else None)

            else:  # success
                successes += 1
                red_score += spec.score.red_success
                affected = R.apply_effects(spec, world, target)
                emit(t, EventType.ATTACK, side=Side.RED, actor="red-team", phase=phase,
                     severity=spec.severity, technique=spec.mitre, title=spec.name,
                     message=(step.label or spec.name) + (f" → {tname}" if target else ""),
                     asset_id=target.id if target else None, asset_label=tname if target else None)
                for em in R.build_emits(spec, world, target):
                    emit(t, EventType.TELEMETRY, side=Side.SYSTEM, actor=em.channel, phase=phase,
                         severity=em.severity, channel=em.channel, technique=spec.mitre,
                         title=spec.name, message=em.text,
                         asset_id=target.id if target else None,
                         asset_label=tname if target else None)
                for aid in affected:
                    a = world.get(aid)
                    if a is None:
                        continue
                    emit(t, EventType.STATE, side=Side.SYSTEM, actor="env", asset_id=aid,
                         asset_label=a.name, title="State change",
                         message=f"{a.name}: {a.security_state.value} / {a.health.value}",
                         data={"security_state": a.security_state.value, "health": a.health.value})
                det = R.compute_detection(spec, world, target, config, t)
                if det is not None:
                    dt, ctype, cid = det
                    heapq.heappush(heap, (dt, _KIND_PRIORITY["detection"], counter, {
                        "kind": "detection", "spec_key": spec.key, "success_t": t,
                        "ctype": ctype, "cid": cid,
                        "target_id": target.id if target else None, "phase": phase,
                    }))
                    counter += 1
                score_event(t)

        elif kind == "detection":
            spec = get_technique(payload["spec_key"])
            ctype = payload["ctype"]
            cid = payload["cid"]
            if ctype in world.attacker.disabled_control_types:
                continue
            ctrl = world.controls.get(cid)
            if ctrl is None or not ctrl.active:
                continue  # control was disabled/removed before the alert could fire
            detected += 1
            dwell = t - payload["success_t"]
            dwells.append(dwell)
            if first_detection_t is None:
                first_detection_t = t
            blue_score += spec.score.blue_detect
            target = world.get(payload["target_id"]) if payload["target_id"] else None
            tlabel = target.name if target else None
            emit(t, EventType.DETECTION, side=Side.SOC, actor=ctype.upper(), phase=payload["phase"],
                 severity=spec.severity, technique=spec.mitre, title=f"Detected: {spec.name}",
                 message=f"{ctrl.name} raised an alert for {spec.name}"
                         + (f" on {tlabel}" if tlabel else "") + f" (dwell {dwell}s)",
                 asset_id=payload["target_id"], asset_label=tlabel,
                 data={"control": ctype, "dwell_s": dwell})
            score_event(t)
            if spec.containable and target is not None:
                rt = R.compute_response(spec, target, config, t)
                if rt is not None:
                    heapq.heappush(heap, (rt, _KIND_PRIORITY["response"], counter, {
                        "kind": "response", "spec_key": spec.key, "detect_t": t,
                        "target_id": target.id, "phase": payload["phase"],
                    }))
                    counter += 1

        elif kind == "response":
            spec = get_technique(payload["spec_key"])
            target = world.get(payload["target_id"])
            if target is None or target.security_state == SecurityState.CONTAINED:
                continue
            target.security_state = SecurityState.CONTAINED
            if target.id in world.attacker.footholds:
                world.attacker.footholds.remove(target.id)
            contained += 1
            mttr = t - payload["detect_t"]
            mttrs.append(mttr)
            blue_score += spec.score.blue_contain
            emit(t, EventType.RESPONSE, side=Side.SOC, actor="ir-team", phase=payload["phase"],
                 severity=Severity.MEDIUM, title=f"Contained: {target.name}",
                 message=f"{target.name} isolated / remediated (MTTR {mttr}s)",
                 asset_id=target.id, asset_label=target.name, data={"mttr_s": mttr})
            emit(t, EventType.STATE, side=Side.SYSTEM, actor="env", asset_id=target.id,
                 asset_label=target.name, title="State change",
                 message=f"{target.name}: {target.security_state.value} / {target.health.value}",
                 data={"security_state": target.security_state.value, "health": target.health.value})
            score_event(t)

    # ---- finalise ------------------------------------------------------------
    failed = attempts - successes - blocked
    backups_enabled = world.active_global_control("backups") is not None
    a = world.attacker
    final_assets = world.all_assets()
    milestones = {
        "foothold": a.has_foothold() or any(x.security_state == SecurityState.COMPROMISED
                                            for x in final_assets),
        "privilege": a.cred_scope.rank >= 2,
        "domain_admin": a.cred_scope.rank >= 3,
        "persistence": bool(a.flags.get("persistence") or a.flags.get("cloud_persistence")),
        "exfil": bool(a.flags.get("exfiltrated")),
        "ransomware": bool(a.flags.get("ransomware")),
        "ot": bool(a.flags.get("ot_impact")),
        "detect": detected > 0,
        "contain": contained > 0,
        "prevent": blocked > 0,
        "recover": backups_enabled,
        "notify": bool(a.flags.get("ransomware") or a.flags.get("exfiltrated")),
    }
    objectives = {
        "red": [ObjectiveStatus(text=o, met=_objective_met(o, milestones, _RED_KW))
                for o in scenario.objectives.red],
        "blue": [ObjectiveStatus(text=o, met=_objective_met(o, milestones, _BLUE_KW))
                 for o in scenario.objectives.blue],
    }

    kpis = compute_kpis(
        attempts=attempts, successes=successes, detected=detected, contained=contained,
        blocked=blocked, dwells=dwells, mttrs=mttrs, first_detection_t=first_detection_t,
    )

    summary = {
        "attempts": attempts, "succeeded": successes, "blocked": blocked, "failed": failed,
        "detected": detected, "contained": contained,
        "assets_total": len(final_assets),
        "assets_compromised": sum(1 for x in final_assets
                                  if x.security_state == SecurityState.COMPROMISED),
        "assets_contained": sum(1 for x in final_assets
                                if x.security_state == SecurityState.CONTAINED),
        "assets_down": sum(1 for x in final_assets if x.health.value == "down"),
        "attacker_max_creds": a.cred_scope.value,
        "exfiltrated": bool(a.flags.get("exfiltrated")),
        "ransomware": bool(a.flags.get("ransomware")),
        "ot_impact": bool(a.flags.get("ot_impact")),
        "backups_enabled": backups_enabled,
    }

    emit(duration_s, EventType.SYSTEM, side=Side.SYSTEM, actor="engine", title="Complete",
         message=f"Simulation complete — Red {red_score} / Blue {blue_score}")

    return RunResult(
        scenario_id=scenario.id,
        duration_s=duration_s,
        events=events,
        scores={"red": red_score, "blue": blue_score},
        kpis=kpis,
        summary=summary,
        objectives=objectives,
        environment=_asset_snapshot(build_world(env)),  # pristine initial snapshot
        final_assets=_asset_snapshot(world),
    )
