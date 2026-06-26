"""Generate a deterministic After-Action Report from a completed run's data.

Sections mirror the PDF's "Final Executive Report": executive summary, attack timeline,
MITRE mapping, scorecard, regulatory & financial impact, recommendations, maturity score,
and a prioritised corrective-action plan. Pure function of the run data.
"""
from __future__ import annotations

_TIMELINE_TYPES = {"attack", "block", "fail", "detection", "response", "inject", "phase"}


def _fmt(t: int) -> str:
    return f"{t // 60:02d}:{t % 60:02d}"


def _exec_summary(run: dict) -> str:
    s, kp = run["summary"], run["kpis"]
    sc = run["scores"]
    outcome = []
    if s.get("ot_impact"):
        outcome.append("the attacker manipulated safety-critical OT processes")
    if s.get("ransomware"):
        outcome.append("ransomware was deployed against enterprise systems")
    if s.get("exfiltrated"):
        outcome.append("sensitive data was exfiltrated")
    if not outcome:
        outcome.append("the intrusion was contained before material impact")
    det = f"{kp.get('detection_rate', 0) * 100:.0f}% of successful actions were detected"
    mttd = kp.get("mttd_s", 0)
    winner = "Blue" if sc.get("blue", 0) >= sc.get("red", 0) else "Red"
    return (
        f"Over a {run['duration_s'] // 60}-minute exercise, "
        + ", ".join(outcome)
        + f". {det}, with a mean time-to-detect of {mttd / 60:.1f} min and "
        f"{s.get('contained', 0)} host(s) contained. {s.get('blocked', 0)} attacker action(s) "
        f"were prevented outright. Overall advantage: {winner} team "
        f"(Red {sc.get('red', 0)} / Blue {sc.get('blue', 0)})."
    )


def _timeline(run: dict) -> list[dict]:
    out = []
    for e in run["events"]:
        if e.get("type") in _TIMELINE_TYPES:
            out.append({
                "t": e["t"], "clock": _fmt(e["t"]), "phase": e.get("phase"),
                "type": e["type"], "severity": e.get("severity"),
                "title": e.get("title"), "message": e.get("message"),
                "technique": e.get("technique"),
            })
    return out


def _mitre_map(run: dict) -> list[dict]:
    detected = {e.get("technique") for e in run["events"] if e.get("type") == "detection"}
    seen: dict[str, dict] = {}
    for e in run["events"]:
        if e.get("type") == "attack" and e.get("technique"):
            key = e["technique"]
            if key not in seen:
                seen[key] = {
                    "technique": key, "name": e.get("title"), "tactic": e.get("phase"),
                    "detected": key in detected,
                }
    return [seen[k] for k in sorted(seen)]


def _scorecard(run: dict) -> dict:
    s, kp, sc = run["summary"], run["kpis"], run["scores"]
    obj = run.get("objectives", {})
    return {
        "red_score": sc.get("red", 0),
        "blue_score": sc.get("blue", 0),
        "winner": "Blue" if sc.get("blue", 0) >= sc.get("red", 0) else "Red",
        "mttd_min": round(kp.get("mttd_s", 0) / 60, 1),
        "mttr_min": round(kp.get("mttr_s", 0) / 60, 1),
        "detection_rate": kp.get("detection_rate", 0),
        "containment_rate": kp.get("containment_rate", 0),
        "prevention_rate": kp.get("prevention_rate", 0),
        "fp_rate": kp.get("fp_rate", 0),
        "attacker_actions": s.get("attempts", 0),
        "succeeded": s.get("succeeded", 0),
        "blocked": s.get("blocked", 0),
        "detected": s.get("detected", 0),
        "contained": s.get("contained", 0),
        "red_objectives_met": sum(1 for o in obj.get("red", []) if o.get("met")),
        "red_objectives_total": len(obj.get("red", [])),
        "blue_objectives_met": sum(1 for o in obj.get("blue", []) if o.get("met")),
        "blue_objectives_total": len(obj.get("blue", [])),
    }


def _regulatory_impact(run: dict) -> list[str]:
    s = run["summary"]
    industry = run.get("industry", "generic")
    items: list[str] = []
    if s.get("exfiltrated"):
        items.append("Personal/IP data breach — breach-notification obligations likely triggered "
                     "(e.g. GDPR 72-hour notice; sector regulators).")
    if s.get("ransomware"):
        items.append("Material operational disruption — may require disclosure to regulators and, "
                     "for listed entities, securities filings.")
    if s.get("ot_impact"):
        items.append("Safety-critical / critical-infrastructure impact — mandatory reporting to "
                     "national CERT / sector authority; potential safety investigation.")
    if industry in ("finance", "manufacturing", "energy", "healthcare") and items:
        items.append(f"Sector-specific obligations apply for {industry}.")
    if not items:
        items.append("No reportable regulatory impact identified — incident contained pre-impact.")
    return items


def _financial_impact(run: dict) -> dict:
    s = run["summary"]
    backups = s.get("backups_enabled")
    low = high = 0
    drivers: list[str] = []
    if s.get("ransomware"):
        base = (300_000, 900_000) if backups else (1_500_000, 4_000_000)
        low += base[0]
        high += base[1]
        drivers.append("Ransomware recovery & downtime" + (" (mitigated by backups)" if backups else ""))
    if s.get("exfiltrated"):
        low += 500_000
        high += 2_000_000
        drivers.append("Data breach response, notification & legal")
    if s.get("ot_impact"):
        low += 1_000_000
        high += 5_000_000
        drivers.append("OT/physical process disruption & safety remediation")
    low += 75_000 * s.get("assets_down", 0)
    high += 200_000 * s.get("assets_down", 0)
    if s.get("assets_down"):
        drivers.append(f"{s.get('assets_down')} critical system(s) offline")
    if low == 0 and high == 0:
        drivers.append("Negligible — no material impact realised")
    return {"estimate_low_usd": low, "estimate_high_usd": high, "drivers": drivers}


def _recommendations(run: dict) -> list[str]:
    s, kp = run["summary"], run["kpis"]
    recs: list[str] = []
    if kp.get("detection_rate", 0) < 0.8:
        recs.append("Improve detection coverage — several attacker actions went unobserved; "
                    "expand SIEM log sources and tune correlation rules.")
    if kp.get("mttd_s", 0) > 600:
        recs.append("Reduce mean-time-to-detect — current dwell time is high; add behavioural "
                    "analytics and prioritise high-severity alert triage.")
    if s.get("exfiltrated"):
        recs.append("Deploy/strengthen DLP and egress filtering on sensitive data stores and cloud.")
    if s.get("ransomware"):
        recs.append("Harden against ransomware — enforce least privilege, application allow-listing, "
                    "and maintain tested offline backups.")
    if not s.get("backups_enabled"):
        recs.append("Implement and regularly test offline, immutable backups.")
    if s.get("ot_impact"):
        recs.append("Enforce strict IT/OT segmentation and deploy OT-aware monitoring at the boundary.")
    if s.get("contained", 0) == 0 and s.get("succeeded", 0) > 0:
        recs.append("Establish/automate containment playbooks (host isolation, credential reset).")
    if not recs:
        recs.append("Maintain current posture; continue periodic purple-team validation.")
    return recs


def _maturity_score(run: dict) -> dict:
    kp, s = run["kpis"], run["summary"]
    detection = kp.get("detection_rate", 0) * 30
    containment = kp.get("containment_rate", 0) * 25
    prevention = kp.get("prevention_rate", 0) * 20
    impact_penalty = 0
    impact_penalty += 15 if s.get("ransomware") else 0
    impact_penalty += 15 if s.get("ot_impact") else 0
    impact_penalty += 10 if s.get("exfiltrated") else 0
    recovery = 10 if s.get("backups_enabled") else 0
    raw = 15 + detection + containment + prevention + recovery - impact_penalty
    score = max(0, min(100, round(raw)))
    band = ("Initial" if score < 25 else "Developing" if score < 50
            else "Defined" if score < 70 else "Managed" if score < 88 else "Optimised")
    return {"score": score, "band": band}


def _corrective_actions(run: dict) -> list[dict]:
    recs = _recommendations(run)
    s = run["summary"]
    actions = []
    for i, r in enumerate(recs):
        # Priority by realised impact / position.
        if any(k in r.lower() for k in ("ot", "ransomware", "dlp", "backup")) and (
            s.get("ot_impact") or s.get("ransomware") or s.get("exfiltrated")
        ):
            prio = "P1"
        elif i < 3:
            prio = "P2"
        else:
            prio = "P3"
        actions.append({"priority": prio, "action": r})
    actions.sort(key=lambda a: a["priority"])
    return actions


def generate_report(run: dict) -> dict:
    """`run` is the serialised run data (scores, kpis, summary, objectives, events, ...)."""
    return {
        "scenario_name": run.get("scenario_name"),
        "duration_min": run["duration_s"] // 60,
        "exec_summary": _exec_summary(run),
        "timeline": _timeline(run),
        "mitre_map": _mitre_map(run),
        "scorecard": _scorecard(run),
        "regulatory_impact": _regulatory_impact(run),
        "financial_impact": _financial_impact(run),
        "recommendations": _recommendations(run),
        "maturity_score": _maturity_score(run),
        "corrective_actions": _corrective_actions(run),
    }
