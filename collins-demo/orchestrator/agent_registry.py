"""
agent_registry.py — Agent registry with vertical scoping.

Each agent is tagged with:
  - capabilities it provides (diagnose, work_order, cascade, predict, etc.)
  - domains it applies to (all, or specific verticals)
  - product it belongs to (nextxr, automind, goalcert, droneforce)

The frontend queries GET /api/agents/registry?domain=mrt-line and gets back
only the agents relevant to that vertical.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ── Agent definition ────────────────────────────────────────────────

@dataclass
class AgentDef:
    id: str
    name: str
    capability: str          # diagnose, work_order, cascade, predict, narrate, etc.
    product: str             # nextxr, automind, goalcert, droneforce
    icon: str                # tabler icon class
    description: str
    domains: list[str]       # ['all'] or specific domain keys
    category: str = "shared" # shared, vertical-specific, droneforce


# ── Full agent registry ─────────────────────────────────────────────

AGENTS: list[AgentDef] = [
    # -- Shared platform agents (work on ALL domains) --
    AgentDef("ag-p01", "Twin Builder", "build_twin", "nextxr", "ti-sparkles",
             "Conversational intake to provision a live physics twin from a photo or spec.",
             ["all"], "shared"),
    AgentDef("ag-p02", "Vision Agent", "vision", "nextxr", "ti-eye",
             "Interprets images/video from any sensor or drone to detect anomalies.",
             ["all"], "shared"),
    AgentDef("ag-p03", "Narration Agent", "narrate", "nextxr", "ti-message-chatbot",
             "Plain-English real-time operational observations from live sensor stream.",
             ["all"], "shared"),
    AgentDef("ag-p04", "Diagnosis Agent", "diagnose", "nextxr", "ti-stethoscope",
             "Layered root cause analysis from component health and sensor anomalies. Searches fault library for similar patterns.",
             ["all"], "shared"),
    AgentDef("ag-p05", "Prediction Agent", "predict", "nextxr", "ti-chart-line",
             "Runs physics prediction forward producing RUL and trajectory forecasts.",
             ["all"], "shared"),
    AgentDef("ag-p06", "Work Order Agent", "work_order", "automind", "ti-file-certificate",
             "Generates compliant maintenance work orders with step-by-step procedures. Cites domain-specific standards.",
             ["all"], "shared"),
    AgentDef("ag-p07", "Incident Report Agent", "incident_report", "automind", "ti-report",
             "Formal incident reports for regulatory submission with classification and evidence.",
             ["all"], "shared"),
    AgentDef("ag-p08", "Compliance Monitor", "compliance", "automind", "ti-shield-check",
             "Checks operations against applicable regulatory framework (EASA, LTA, NFPA, JCI, MIL-STD).",
             ["all"], "shared"),
    AgentDef("ag-p09", "Copilot", "chat", "automind", "ti-robot",
             "Answers operator questions using live telemetry as grounding context.",
             ["all"], "shared"),
    AgentDef("ag-p10", "Cascade Analysis", "cascade", "automind", "ti-affiliate",
             "Multi-system failure propagation reasoning across subsystems.",
             ["all"], "shared"),
    AgentDef("ag-p11", "Parts Procurement", "procurement", "automind", "ti-shopping-cart",
             "Identifies parts from work orders with lead times and sourcing channels.",
             ["all"], "shared"),
    AgentDef("ag-p14", "Alert Triage", "triage", "nextxr", "ti-filter",
             "Filters and correlates raw findings to prevent alert fatigue.",
             ["all"], "shared"),
    AgentDef("ag-p18", "Anomaly Detector", "anomaly", "nextxr", "ti-alert-triangle",
             "Statistical and physics-residual anomaly detection on live sensor streams.",
             ["all"], "shared"),
    AgentDef("ag-p19", "Energy Optimizer", "energy", "automind", "ti-bolt",
             "Optimal operating setpoints to minimise energy consumption across the facility.",
             ["all"], "shared"),

    # -- Railway (MRT) specific agents --
    AgentDef("ag-r01", "Train Dispatch", "dispatch", "automind", "ti-route",
             "Optimises real-time train dispatch decisions for headway adherence and delay minimisation.",
             ["mrt-line", "tram-network"], "vertical-specific"),
    AgentDef("ag-r02", "Signalling Health Monitor", "signalling", "nextxr", "ti-traffic-lights",
             "Monitors CBTC/ATP signalling subsystem for faults and degraded modes.",
             ["mrt-line"], "vertical-specific"),
    AgentDef("ag-r03", "Passenger Flow Predictor", "passenger_flow", "automind", "ti-users",
             "Forecasts passenger demand per station using historical and real-time data.",
             ["mrt-line", "tram-network"], "vertical-specific"),
    AgentDef("ag-r04", "Track Geometry Analyser", "track_geometry", "nextxr", "ti-ruler-measure",
             "Analyses track geometry measurements to identify deterioration and predict maintenance.",
             ["mrt-line", "tram-network"], "vertical-specific"),
    AgentDef("ag-r05", "Rolling Stock Maintenance", "rolling_stock", "nextxr", "ti-train",
             "RUL prediction on rolling stock components (traction motors, bogies, brakes, doors).",
             ["mrt-line", "tram-network"], "vertical-specific"),
    AgentDef("ag-r06", "Station Environment Controller", "station_env", "automind", "ti-air-conditioning",
             "Manages station HVAC and lighting based on passenger load and energy tariff.",
             ["mrt-line"], "vertical-specific"),
    AgentDef("ag-r07", "Depot Resource Allocator", "depot", "automind", "ti-building-warehouse",
             "Optimises depot bay and crew assignments across the maintenance window.",
             ["mrt-line", "tram-network"], "vertical-specific"),
    AgentDef("ag-r08", "Rail Grinding Scheduler", "grinding", "automind", "ti-tool",
             "Determines optimal rail grinding schedule from geometry trends and traffic tonnage.",
             ["mrt-line", "tram-network"], "vertical-specific"),
    AgentDef("ag-r09", "Platform Door Sync Monitor", "psd", "nextxr", "ti-door",
             "Monitors PSD operation timing and alignment with train doors.",
             ["mrt-line"], "vertical-specific"),
    AgentDef("ag-r10", "Traction Power Optimiser", "traction_power", "automind", "ti-bolt",
             "Maximises regenerative braking energy recovery across the network.",
             ["mrt-line", "tram-network"], "vertical-specific"),

    # -- EV specific agents --
    AgentDef("ag-e01", "Smart Charging Scheduler", "charging", "automind", "ti-plug-connected",
             "Optimises fleet charging schedule for cost, battery health, and grid constraints.",
             ["ev-network"], "vertical-specific"),
    AgentDef("ag-e02", "Battery Health Predictor", "battery_health", "nextxr", "ti-heart",
             "Estimates SoH and RUL using electrochemical degradation models and cycle data.",
             ["ev-network"], "vertical-specific"),
    AgentDef("ag-e03", "Fleet Route Optimiser", "fleet_route", "automind", "ti-map-pin",
             "Plans charge-aware routes for EV fleets to prevent range anxiety.",
             ["ev-network"], "vertical-specific"),
    AgentDef("ag-e04", "Grid Demand Response", "demand_response", "automind", "ti-building-factory",
             "Coordinates EV charging loads in response to grid operator demand signals.",
             ["ev-network"], "vertical-specific"),
    AgentDef("ag-e05", "Charger Fault Diagnostician", "charger_fault", "nextxr", "ti-plug-connected-x",
             "Monitors EVSE health via OCPP telemetry, diagnoses faults, generates maintenance actions.",
             ["ev-network"], "vertical-specific"),
    AgentDef("ag-e06", "V2G Arbitrage Optimiser", "v2g", "automind", "ti-arrows-exchange",
             "Manages bidirectional power flow for energy price arbitrage while protecting battery health.",
             ["ev-network"], "vertical-specific"),
    AgentDef("ag-e07", "Range Anxiety Mitigator", "range", "nextxr", "ti-battery-2",
             "Monitors vehicles and alerts when SoC vs remaining distance is critical.",
             ["ev-network"], "vertical-specific"),
    AgentDef("ag-e10", "Thermal Management Optimiser", "thermal", "nextxr", "ti-temperature",
             "Optimises battery cooling system for performance and longevity.",
             ["ev-network"], "vertical-specific"),
    AgentDef("ag-e11", "SitePredict Location Analyst", "sitepredict", "automind", "ti-map-search",
             "Ranks candidate charging sites by predicted ROI from traffic, demographics, EV density and grid capacity.",
             ["ev-network"], "vertical-specific"),
    AgentDef("ag-e12", "Dynamic Tariff & Load Optimiser", "tariff_ems", "automind", "ti-adjustments-bolt",
             "Automates time-of-use pricing and EMS load balancing to lift utilisation and shave peak demand.",
             ["ev-network"], "vertical-specific"),

    # -- Hospital specific agents --
    AgentDef("ag-h01", "Bed Management Optimiser", "bed_mgmt", "automind", "ti-bed",
             "Optimises real-time bed allocation across wards based on acuity and discharge predictions.",
             ["hospital"], "vertical-specific"),
    AgentDef("ag-h02", "OR Scheduling Agent", "or_scheduling", "automind", "ti-calendar-event",
             "Schedules surgical cases across operating theatres to maximise utilisation.",
             ["hospital"], "vertical-specific"),
    AgentDef("ag-h03", "Infection Prevention", "infection", "nextxr", "ti-virus",
             "Monitors environmental parameters and models outbreak propagation risk.",
             ["hospital"], "vertical-specific"),
    AgentDef("ag-h04", "Clinical Alarm Management", "alarm_mgmt", "nextxr", "ti-bell",
             "Deduplicates and prioritises clinical patient monitoring alarms to reduce alarm fatigue.",
             ["hospital"], "vertical-specific"),
    AgentDef("ag-h05", "Cold Chain Watchdog", "cold_chain", "nextxr", "ti-temperature-snow",
             "Monitors temperature for all cold-chain assets with predictive excursion alerting.",
             ["hospital"], "vertical-specific"),
    AgentDef("ag-h06", "Patient Flow Predictor", "patient_flow", "automind", "ti-users",
             "Forecasts ED arrival rates and admission demand over 4-24 hour horizons.",
             ["hospital"], "vertical-specific"),
    AgentDef("ag-h11", "Code Team Dispatcher", "code_team", "automind", "ti-urgent",
             "Identifies and pages correct team members for code blue/red events based on location and skills.",
             ["hospital"], "vertical-specific"),
    AgentDef("ag-h12", "Regulatory Readiness", "regulatory", "automind", "ti-certificate",
             "Continuously assesses compliance against JCI accreditation and MOH Singapore standards.",
             ["hospital"], "vertical-specific"),

    # -- Defence specific agents --
    AgentDef("ag-d01", "Threat Assessment", "threat", "automind", "ti-shield-star",
             "Fuses multi-source intelligence for threat classification and prioritisation.",
             ["defence-base"], "vertical-specific"),
    AgentDef("ag-d02", "Mission Planning Optimiser", "mission", "automind", "ti-map",
             "Generates and evaluates COAs against constraints, assets, and risk thresholds.",
             ["defence-base"], "vertical-specific"),
    AgentDef("ag-d07", "C4ISR Fusion", "c4isr", "nextxr", "ti-radar-2",
             "Fuses multi-sensor data (radar, EO/IR, AIS, SIGINT) into coherent operational picture.",
             ["defence-base"], "vertical-specific"),
    AgentDef("ag-d08", "Damage Control (Naval)", "damage_control", "nextxr", "ti-anchor",
             "Real-time ship stability and flooding management with counterflooding recommendations.",
             ["defence-base"], "vertical-specific"),
    AgentDef("ag-d09", "Force Protection", "force_protection", "automind", "ti-shield-lock",
             "Assesses and manages physical security posture of base or platform.",
             ["defence-base"], "vertical-specific"),
    AgentDef("ag-d11", "Counter-UAS", "counter_uas", "nextxr", "ti-drone",
             "Detects, identifies and tracks hostile UAS threats. Recommends engagement options.",
             ["defence-base"], "vertical-specific"),

    # -- DroneForce agents --
    AgentDef("ag-df01", "Drone Mission Planner", "drone_mission", "automind", "ti-map-pin",
             "Plans complete drone missions from inspection objectives to waypoint files.",
             ["all"], "droneforce"),
    AgentDef("ag-df03", "Aerial Anomaly Detector", "aerial_anomaly", "nextxr", "ti-camera",
             "Processes drone imagery in real time to detect infrastructure anomalies.",
             ["all"], "droneforce"),
    AgentDef("ag-df04", "Battery & Range Manager", "drone_battery", "nextxr", "ti-battery-charging",
             "Monitors drone battery and predicts remaining flight time. Manages RTB decisions.",
             ["all"], "droneforce"),
    AgentDef("ag-df05", "Airspace Deconfliction", "deconfliction", "automind", "ti-arrows-split",
             "4D trajectory deconfliction for multi-drone operations within facility airspace.",
             ["all"], "droneforce"),
    AgentDef("ag-df10", "Inspection Report Generator", "inspection_report", "automind", "ti-report-analytics",
             "Compiles drone inspection findings into formal reports with linked work orders.",
             ["all"], "droneforce"),
]


# ── Query functions ─────────────────────────────────────────────────

def agents_for_domain(domain: str) -> list[dict]:
    """Return agents applicable to a specific domain."""
    results = []
    for a in AGENTS:
        if "all" in a.domains or domain in a.domains:
            results.append({
                "id": a.id, "name": a.name, "capability": a.capability,
                "product": a.product, "icon": a.icon,
                "description": a.description, "category": a.category,
            })
    return results


def agents_by_category(domain: str) -> dict[str, list[dict]]:
    """Return agents grouped by category for a domain."""
    all_agents = agents_for_domain(domain)
    grouped = {"shared": [], "vertical-specific": [], "droneforce": []}
    for a in all_agents:
        cat = a.get("category", "shared")
        if cat not in grouped:
            grouped[cat] = []
        grouped[cat].append(a)
    return grouped


def agent_count() -> dict:
    """Return total agent counts by category."""
    shared = len([a for a in AGENTS if a.category == "shared"])
    vertical = len([a for a in AGENTS if a.category == "vertical-specific"])
    drone = len([a for a in AGENTS if a.category == "droneforce"])
    return {"shared": shared, "vertical_specific": vertical, "droneforce": drone,
            "total": shared + vertical + drone}
