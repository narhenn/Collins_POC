"""
hospital/equipment.py — the hospital's physical asset roster, with live health.

This is the data behind the Equipment gallery ("every asset in the twin, in 3-D").
Each entry names a prop `key` from the frontend 3-D catalog (three/catalog.js), so
the gallery can mount a real model for it, plus the asset-management fields the
info panel shows (manufacturer / model / serial / install + warranty / criticality
/ conditionIndex).

The roster is derived from the v3 hospital-campus layout recipes: an acute /
diagnostics ground floor (reception, emergency, imaging, theatres, sterile supply,
pharmacy, blood bank, gas store) and an inpatient upper floor (ICU, wards,
isolation, nurse stations).

`equipment_state(state, frame, SIGNALS)` grades every asset live: each asset
watches the campus signal that actually governs it (a blood-bank fridge watches
the cold-chain temperature, a gas manifold watches O2 outlet pressure, an OR
laminar-flow canopy watches theatre pressure...), so injecting a fault lights up
exactly the assets that fault touches — and nothing else.
"""
from __future__ import annotations

# ── Per-asset-type metadata ──────────────────────────────────────────
# key -> (manufacturer, model prefix, warranty years, base conditionIndex,
#         criticality)
_ASSET_META = {
    "mri":             ("Siemens Healthineers", "MAGNETOM", 7, 0.93, "high"),
    "ctscanner":       ("GE HealthCare", "Revolution", 6, 0.90, "high"),
    "xray":            ("Philips", "DigitalDiagnost", 6, 0.94, "medium"),
    "ultrasound":      ("Canon Medical", "Aplio", 5, 0.95, "medium"),
    "ventilator":      ("Draeger", "Evita", 5, 0.90, "high"),
    "infusionpump":    ("B. Braun", "Infusomat", 4, 0.92, "high"),
    "patientmonitor":  ("Philips", "IntelliVue", 5, 0.94, "high"),
    "autoclave":       ("Getinge", "HS66", 6, 0.90, "high"),
    "bloodbank":       ("Helmer Scientific", "iB", 8, 0.95, "high"),
    "fridge":          ("Follett", "REF", 6, 0.93, "high"),
    "gascylinderbank": ("BeaconMedaes", "Manifold", 10, 0.96, "high"),
    "gas":             ("BeaconMedaes", "Outlet", 10, 0.96, "high"),
    "nurse":           ("Hillrom", "NaviCare", 6, 0.95, "medium"),
    "hospitalbed":     ("Hillrom", "Progressa", 8, 0.92, "medium"),
    "bed":             ("Stryker", "SV2", 8, 0.94, "medium"),
    "operatingtable":  ("Maquet", "Magnus", 10, 0.93, "high"),
    "anesthesia":      ("Draeger", "Perseus", 8, 0.92, "high"),
    "surgicallight":   ("Trumpf Medical", "TruLight", 8, 0.95, "medium"),
    "laf":             ("Halton", "Vita", 10, 0.93, "high"),
    "mayostand":       ("Pedigo", "MS", 12, 0.97, "low"),
    "crashcart":       ("Armstrong Medical", "Lifeline", 8, 0.95, "high"),
    "medcart":         ("Omnicell", "XT", 6, 0.94, "medium"),
    "dialysis":        ("Fresenius", "5008", 7, 0.91, "high"),
    "examtable":       ("Midmark", "625", 10, 0.96, "low"),
    "ivstand":         ("Provita", "IVP", 10, 0.98, "low"),
    "stretcher":       ("Stryker", "Prime", 9, 0.95, "medium"),
    "wheelchair":      ("Invacare", "Tracer", 8, 0.96, "low"),
    "ups":             ("Schneider Electric", "Galaxy", 6, 0.93, "high"),
    "generator":       ("Cummins", "C-Series", 12, 0.94, "high"),
    "chiller":         ("Carrier", "AquaEdge", 12, 0.91, "high"),
    "ahu":             ("Trane", "Performa", 12, 0.90, "high"),
    "cabinet":         ("Bristol Maid", "STC", 12, 0.97, "low"),
    "reception":       ("Interior Fitout", "RCP", 12, 0.98, "low"),
}

# ── The roster ───────────────────────────────────────────────────────
# (id, label, prop key, room, sector, zone) — `zone` ties the asset to a campus
# zone id from physics._ZONES so a localised fault can target it.
_ROSTER = [
    # ══ Ground floor — Emergency ══
    ("ED-MON-1",  "Triage Monitor",           "patientmonitor", "ED — Triage",          "Emergency",         "ED"),
    ("ED-BED-1",  "Triage Bay 1",             "bed",            "ED — Triage",          "Emergency",         "ED"),
    ("ED-BED-2",  "Triage Bay 2",             "bed",            "ED — Triage",          "Emergency",         "ED"),
    ("ED-IV-1",   "IV Stand",                 "ivstand",        "ED — Triage",          "Emergency",         "ED"),
    ("ED-TBED-1", "Trauma Bay Bed",           "hospitalbed",    "ED — Trauma Bay",      "Emergency",         "ED"),
    ("ED-TMON-1", "Trauma Vitals Monitor",    "patientmonitor", "ED — Trauma Bay",      "Emergency",         "ED"),
    ("ED-PUMP-1", "Trauma Infusion Pump",     "infusionpump",   "ED — Trauma Bay",      "Emergency",         "ED"),
    ("ED-RBED-1", "Resus Bed 1",              "hospitalbed",    "ED — Resuscitation",   "Emergency",         "ED"),
    ("ED-RBED-2", "Resus Bed 2",              "hospitalbed",    "ED — Resuscitation",   "Emergency",         "ED"),
    ("ED-VENT-1", "Transport Ventilator",     "ventilator",     "ED — Resuscitation",   "Emergency",         "ED"),
    ("ED-CART-1", "Crash Cart",               "crashcart",      "ED — Resuscitation",   "Emergency",         "ED"),
    ("ED-STR-1",  "Transport Stretcher",      "stretcher",      "ED — Resuscitation",   "Emergency",         "ED"),

    # ══ Ground floor — Diagnostic Imaging ══
    ("RAD-MRI-1", "MRI Scanner",              "mri",            "MRI Suite",            "Diagnostic Imaging", "RAD"),
    ("RAD-MMON-1", "MR-safe Monitor",         "patientmonitor", "MRI Suite",            "Diagnostic Imaging", "RAD"),
    ("RAD-CT-1",  "CT Scanner",               "ctscanner",      "CT Suite",             "Diagnostic Imaging", "RAD"),
    ("RAD-CMON-1", "CT Vitals Monitor",       "patientmonitor", "CT Suite",             "Diagnostic Imaging", "RAD"),
    ("RAD-XR-1",  "Digital X-Ray",            "xray",           "X-Ray Room",           "Diagnostic Imaging", "RAD"),
    ("RAD-US-1",  "Ultrasound",               "ultrasound",     "Ultrasound",           "Diagnostic Imaging", "RAD"),
    ("RAD-EXT-1", "Exam Couch",               "examtable",      "Ultrasound",           "Diagnostic Imaging", "RAD"),

    # ══ Ground floor — Laboratory ══
    ("LAB-FRG-1", "Reagent Fridge",           "fridge",         "Laboratory",           "Support Services",  "LAB"),
    ("LAB-BEN-1", "Analyser Bench",           "cabinet",        "Laboratory",           "Support Services",  "LAB"),
    ("LAB-AN-1",  "Bench Analyser",           "patientmonitor", "Laboratory",           "Support Services",  "LAB"),

    # ══ Ground floor — Surgical ══
    ("OR1-TBL-1", "Operating Table 1",        "operatingtable", "Operating Room 1",     "Surgical",          "OR1"),
    ("OR1-ANA-1", "Anaesthesia Machine 1",    "anesthesia",     "Operating Room 1",     "Surgical",          "OR1"),
    ("OR1-LGT-1", "Surgical Light 1",         "surgicallight",  "Operating Room 1",     "Surgical",          "OR1"),
    ("OR1-LAF-1", "Laminar Flow Canopy 1",    "laf",            "Operating Room 1",     "Surgical",          "OR1"),
    ("OR1-MAY-1", "Mayo Stand 1",             "mayostand",      "Operating Room 1",     "Surgical",          "OR1"),
    ("OR1-MON-1", "Anaesthetic Monitor 1",    "patientmonitor", "Operating Room 1",     "Surgical",          "OR1"),
    ("OR1-GAS-1", "OR1 Medical Gas Panel",    "gas",            "Operating Room 1",     "Surgical",          "OR1"),
    ("OR2-TBL-1", "Operating Table 2",        "operatingtable", "Operating Room 2",     "Surgical",          "OR2"),
    ("OR2-ANA-1", "Anaesthesia Machine 2",    "anesthesia",     "Operating Room 2",     "Surgical",          "OR2"),
    ("OR2-LGT-1", "Surgical Light 2",         "surgicallight",  "Operating Room 2",     "Surgical",          "OR2"),
    ("OR2-LAF-1", "Laminar Flow Canopy 2",    "laf",            "Operating Room 2",     "Surgical",          "OR2"),
    ("OR2-MON-1", "Anaesthetic Monitor 2",    "patientmonitor", "Operating Room 2",     "Surgical",          "OR2"),
    ("OR2-GAS-1", "OR2 Medical Gas Panel",    "gas",            "Operating Room 2",     "Surgical",          "OR2"),
    ("SCR-STO-1", "Sterile Store",            "cabinet",        "Scrub & Prep",         "Surgical",          "OR1"),

    # ══ Ground floor — Support Services ══
    ("CSD-AUT-1", "Steam Autoclave 1",        "autoclave",      "Central Sterile Supply", "Support Services", "LAB"),
    ("CSD-AUT-2", "Steam Autoclave 2",        "autoclave",      "Central Sterile Supply", "Support Services", "LAB"),
    ("CSD-INS-1", "Instrument Store",         "cabinet",        "Central Sterile Supply", "Support Services", "LAB"),
    ("PHM-CRT-1", "Medication Cart",          "medcart",        "Pharmacy",             "Support Services",  "PHARM"),
    ("PHM-FRG-1", "Cold-Chain Fridge",        "fridge",         "Pharmacy",             "Support Services",  "PHARM"),
    ("PHM-STO-1", "Drug Store",               "cabinet",        "Pharmacy",             "Support Services",  "PHARM"),
    ("BLD-BNK-1", "Blood Bank Fridge 1",      "bloodbank",      "Blood Bank",           "Support Services",  "PHARM"),
    ("BLD-BNK-2", "Blood Bank Fridge 2",      "bloodbank",      "Blood Bank",           "Support Services",  "PHARM"),
    ("GAS-MAN-1", "Medical Gas Manifold",     "gascylinderbank", "Medical Gas Store",   "Support Services",  "OR1"),

    # ══ Ground floor — Admin ══
    ("ADM-RCP-1", "Reception Desk",           "reception",      "Reception & Admin",    "Admin",             "ED"),

    # ══ Plant — Power & HVAC ══
    ("PLT-UPS-1", "Critical UPS",             "ups",            "Plant Room",           "Facilities",        "ED"),
    ("PLT-GEN-1", "Standby Generator",        "generator",      "Plant Room",           "Facilities",        "ED"),
    ("PLT-AHU-1", "Clinical AHU",             "ahu",            "Plant Room",           "Facilities",        "OR1"),
    ("PLT-CHL-1", "Chiller",                  "chiller",        "Plant Room",           "Facilities",        "OR1"),

    # ══ Upper floor — Critical Care ══
    ("ICU-BED-1", "ICU Bed 1",                "hospitalbed",    "Intensive Care Unit",  "Critical Care",     "ICU"),
    ("ICU-VNT-1", "ICU Ventilator 1",         "ventilator",     "Intensive Care Unit",  "Critical Care",     "ICU"),
    ("ICU-MON-1", "Multiparameter Monitor 1", "patientmonitor", "Intensive Care Unit",  "Critical Care",     "ICU"),
    ("ICU-PMP-1", "Infusion Pump 1",          "infusionpump",   "Intensive Care Unit",  "Critical Care",     "ICU"),
    ("ICU-BED-2", "ICU Bed 2",                "hospitalbed",    "Intensive Care Unit",  "Critical Care",     "ICU"),
    ("ICU-VNT-2", "ICU Ventilator 2",         "ventilator",     "Intensive Care Unit",  "Critical Care",     "ICU"),
    ("ICU-MON-2", "Multiparameter Monitor 2", "patientmonitor", "Intensive Care Unit",  "Critical Care",     "ICU"),
    ("ICU-PMP-2", "Infusion Pump 2",          "infusionpump",   "Intensive Care Unit",  "Critical Care",     "ICU"),
    ("ICU-DIA-1", "Dialysis Machine",         "dialysis",       "Intensive Care Unit",  "Critical Care",     "ICU"),
    ("ICU-IV-1",  "IV Stand",                 "ivstand",        "Intensive Care Unit",  "Critical Care",     "ICU"),
    ("ICU-NRS-1", "ICU Nurse Station",        "nurse",          "ICU Nurse Station",    "Critical Care",     "ICU"),
    ("ICU-CRT-1", "ICU Med Cart",             "medcart",        "ICU Nurse Station",    "Critical Care",     "ICU"),
    ("ISO-BED-1", "Isolation Bed 1",          "bed",            "Isolation Room 1",     "Critical Care",     "ISO"),
    ("ISO-MON-1", "Isolation Monitor 1",      "patientmonitor", "Isolation Room 1",     "Critical Care",     "ISO"),
    ("ISO-VNT-1", "Isolation Ventilator 1",   "ventilator",     "Isolation Room 1",     "Critical Care",     "ISO"),
    ("ISO-BED-2", "Isolation Bed 2",          "bed",            "Isolation Room 2",     "Critical Care",     "ISO"),
    ("ISO-MON-2", "Isolation Monitor 2",      "patientmonitor", "Isolation Room 2",     "Critical Care",     "ISO"),

    # ══ Upper floor — Wards ══
    ("WA-BED-1",  "Ward A Bed 1",             "bed",            "General Ward A",       "Wards",             "WA"),
    ("WA-BED-2",  "Ward A Bed 2",             "bed",            "General Ward A",       "Wards",             "WA"),
    ("WA-BED-3",  "Ward A Bed 3",             "bed",            "General Ward A",       "Wards",             "WA"),
    ("WA-MON-1",  "Ward A Bedside Monitor",   "patientmonitor", "General Ward A",       "Wards",             "WA"),
    ("WA-IV-1",   "Ward A IV Stand",          "ivstand",        "General Ward A",       "Wards",             "WA"),
    ("WA-NRS-1",  "Ward A Nurse Station",     "nurse",          "Ward A Nurse Station", "Wards",             "WA"),
    ("WB-BED-1",  "Ward B Bed 1",             "bed",            "General Ward B",       "Wards",             "WB"),
    ("WB-BED-2",  "Ward B Bed 2",             "bed",            "General Ward B",       "Wards",             "WB"),
    ("WB-BED-3",  "Ward B Bed 3",             "bed",            "General Ward B",       "Wards",             "WB"),
    ("WB-MON-1",  "Ward B Bedside Monitor",   "patientmonitor", "General Ward B",       "Wards",             "WB"),
    ("WB-WCH-1",  "Ward B Wheelchair",        "wheelchair",     "General Ward B",       "Wards",             "WB"),
    ("WB-NRS-1",  "Ward B Nurse Station",     "nurse",          "Ward B Nurse Station", "Wards",             "WB"),
]


# ── Which campus signal governs each asset type ──────────────────────
# prop key -> (signal key in physics.SIGNALS, limit, direction, metric label, unit)
# direction 'below' = value under the limit is bad; 'above' = over is bad.
_WATCH = {
    "bloodbank":       ("bloodbank_temp", 6.0,   "above", "Storage temp",   "°C"),
    "fridge":          ("bloodbank_temp", 6.0,   "above", "Storage temp",   "°C"),
    "gascylinderbank": ("o2_pressure",    350.0, "below", "O2 outlet",      "kPa"),
    "gas":             ("o2_pressure",    350.0, "below", "O2 outlet",      "kPa"),
    "anesthesia":      ("o2_pressure",    350.0, "below", "O2 supply",      "kPa"),
    "laf":             ("or_pressure",    8.0,   "below", "OR pressure",    "Pa"),
    "ahu":             ("air_changes",    15.0,  "below", "Air changes",    "ACH"),
    "chiller":         ("air_changes",    15.0,  "below", "Air changes",    "ACH"),
    "surgicallight":   ("or_pressure",    8.0,   "below", "OR pressure",    "Pa"),
    "operatingtable":  ("or_pressure",    8.0,   "below", "OR pressure",    "Pa"),
    "autoclave":       ("autoclave_f0",   15.0,  "below", "Cycle F0",       "min"),
    "ups":             ("ups_runtime",    15.0,  "below", "Runtime left",   "min"),
    "generator":       ("gen_ready",      0.5,   "below", "Ready state",    ""),
    "ventilator":      ("ups_runtime",    15.0,  "below", "Backup runtime", "min"),
    "infusionpump":    ("ups_runtime",    15.0,  "below", "Backup runtime", "min"),
    "dialysis":        ("ups_runtime",    15.0,  "below", "Backup runtime", "min"),
    "patientmonitor":  ("infection_risk", 5.0,   "above", "Infection risk", "%"),
    "nurse":           ("ed_wait",        240.0, "above", "ED wait",        "min"),
    "bed":             ("bed_occ",        92.0,  "above", "Bed occupancy",  "%"),
    "hospitalbed":     ("bed_occ",        92.0,  "above", "Bed occupancy",  "%"),
    "stretcher":       ("ed_wait",        240.0, "above", "ED wait",        "min"),
    "medcart":         ("bloodbank_temp", 6.0,   "above", "Cold-chain temp", "°C"),
    "mri":             ("power_load",     90.0,  "above", "Critical load",  "%"),
    "ctscanner":       ("power_load",     90.0,  "above", "Critical load",  "%"),
    "xray":            ("power_load",     90.0,  "above", "Critical load",  "%"),
    "ultrasound":      ("power_load",     90.0,  "above", "Critical load",  "%"),
}

# Asset types that are passive furniture — always nominal, no live signal.
_PASSIVE = {"cabinet", "reception", "ivstand", "mayostand", "examtable",
            "wheelchair", "crashcart"}


def _meta_for(key: str, index: int) -> dict:
    """Deterministic, plausible asset-management metadata for one instance."""
    mfr, model_prefix, warranty_years, cond, criticality = _ASSET_META.get(
        key, ("Generic", "GEN", 5, 0.95, "low"))
    age = index % 6                                   # 0..5 years old
    install_year = 2026 - age
    month = 1 + (index % 12)
    return {
        "manufacturer": mfr,
        "modelNumber": f"{model_prefix}-{100 + (index % 900)}",
        "serialNumber": f"{key[:3].upper()}{install_year}{1000 + index:04d}",
        "installDate": f"{install_year}-{month:02d}-15",
        "warrantyExpiry": f"{install_year + warranty_years}-{month:02d}-15",
        "runtimeHours": 1800 * age + (index % 1800),
        "criticality": criticality,
        "conditionIndex": round(max(0.4, cond - 0.02 * age), 3),
    }


# Pre-compute the static part of the roster once (metadata never changes).
EQUIPMENT = []
for _i, (_id, _label, _prop, _room, _sector, _zone) in enumerate(_ROSTER):
    EQUIPMENT.append({
        "id": _id, "label": _label, "prop": _prop, "room": _room,
        "sector": _sector, "zone": _zone, **_meta_for(_prop, _i),
    })


def equipment_summary() -> dict:
    """Static roster shape: how many assets, and how many distinct types."""
    return {"count": len(EQUIPMENT),
            "types": sorted({e["prop"] for e in EQUIPMENT}),
            "sectors": sorted({e["sector"] for e in EQUIPMENT})}


def equipment_state(state, frame: dict, signals: dict) -> list:
    """Grade every asset against the live frame.

    Returns the roster with, per asset: `status` (ok / warn / crit), the live
    `metric` that drives it, and whether the active fault directly targets it.
    """
    out = []
    target = getattr(state, "fault_target", "") or ""
    for e in EQUIPMENT:
        prop = e["prop"]
        item = dict(e)
        watch = _WATCH.get(prop)

        if prop in _PASSIVE or watch is None:
            item["status"] = "ok"
            item["metric"] = None
        else:
            sig_key, limit, direction, m_label, m_unit = watch
            value = frame.get(signals[sig_key])
            if value is None:
                item["status"] = "ok"
                item["metric"] = None
            else:
                # distance past the limit, normalised — >=1.0 is a hard breach
                if direction == "above":
                    over = (value - limit) / max(abs(limit), 1e-6)
                else:
                    over = (limit - value) / max(abs(limit), 1e-6)
                if over >= 0.0:
                    status = "crit"
                elif over >= -0.12:      # within 12% of the limit
                    status = "warn"
                else:
                    status = "ok"
                item["status"] = status
                item["metric"] = {"label": m_label, "value": round(float(value), 2),
                                  "unit": m_unit, "limit": limit, "direction": direction}

        # a localised fault escalates the assets in the zone it hit
        item["targeted"] = bool(target) and e["zone"] == target
        if item["targeted"] and item["status"] == "ok":
            item["status"] = "warn"
        out.append(item)
    return out
