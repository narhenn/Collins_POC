"""
knowledge.py — Agent knowledge layer for the GoalCert digital twin platform.

Three capabilities that make agents smarter:
  1. Fault library    — semantic search over known fault patterns + resolutions
  2. Compliance rules — domain-specific regulatory requirements agents can cite
  3. Incident memory  — resolved incidents stored and retrieved for future diagnosis

Uses numpy cosine similarity for retrieval (zero external deps).
Embeddings are generated via the Anthropic API's message parsing (small model)
or fall back to TF-IDF-style keyword vectors when no API key is set.

In production on AWS: swap the in-process store for Qdrant + BGE-M3 embeddings.
The agent interface (search_faults, search_compliance, remember, recall) stays identical.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger("orchestrator.knowledge")

# ── Lightweight keyword-based vectors (no ML model needed) ──────────

# Build a simple vocabulary from all text in the knowledge base, then
# represent each entry as a sparse TF vector. Cosine similarity over
# these vectors gives decent retrieval for domain-specific technical text.

_vocab: dict[str, int] = {}
_vocab_lock = False


def _tokenize(text: str) -> list[str]:
    """Simple whitespace + punctuation tokenizer."""
    return re.findall(r'[a-z0-9]+', text.lower())


def _build_vocab(corpus: list[str], max_terms: int = 2000):
    """Build vocabulary from corpus. Call once after loading all entries."""
    global _vocab, _vocab_lock
    if _vocab_lock:
        return
    tf = {}
    for doc in corpus:
        for token in set(_tokenize(doc)):
            tf[token] = tf.get(token, 0) + 1
    # Keep terms that appear in >1 doc but <80% of docs (IDF-like filtering)
    n = len(corpus) or 1
    terms = sorted(
        [(t, c) for t, c in tf.items() if 1 < c < n * 0.8],
        key=lambda x: -x[1]
    )[:max_terms]
    _vocab = {t: i for i, (t, _) in enumerate(terms)}
    _vocab_lock = True
    logger.info("knowledge: built vocab with %d terms from %d docs", len(_vocab), len(corpus))


def _vectorize(text: str) -> np.ndarray:
    """Convert text to a sparse TF vector using the global vocabulary."""
    if not _vocab:
        return np.zeros(1)
    vec = np.zeros(len(_vocab), dtype=np.float32)
    tokens = _tokenize(text)
    for token in tokens:
        if token in _vocab:
            vec[_vocab[token]] += 1.0
    # L2 normalize
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec /= norm
    return vec


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors."""
    if a.shape != b.shape or np.linalg.norm(a) == 0 or np.linalg.norm(b) == 0:
        return 0.0
    return float(np.dot(a, b))


# ── Knowledge entries ───────────────────────────────────────────────

@dataclass
class KnowledgeEntry:
    id: str
    domain: str          # edm-machine, turbine-engine, mrt-line, etc.
    category: str        # fault, compliance, incident, procedure
    title: str
    content: str
    metadata: dict = field(default_factory=dict)
    vector: np.ndarray = field(default_factory=lambda: np.zeros(1), repr=False)
    timestamp: float = field(default_factory=time.time)


class KnowledgeStore:
    """In-process knowledge store with semantic search.

    Production: replace with Qdrant client, same interface.
    """

    def __init__(self, persist_dir: Optional[str] = None):
        self.entries: list[KnowledgeEntry] = []
        self._persist_dir = persist_dir
        if persist_dir:
            os.makedirs(persist_dir, exist_ok=True)
            self._load()

    # ── Add entries ──

    def add(self, domain: str, category: str, title: str, content: str,
            metadata: dict | None = None) -> str:
        """Add a knowledge entry. Returns the entry ID."""
        entry_id = hashlib.md5(f"{domain}:{title}:{content[:100]}".encode()).hexdigest()[:12]
        # Skip duplicates
        if any(e.id == entry_id for e in self.entries):
            return entry_id
        entry = KnowledgeEntry(
            id=entry_id, domain=domain, category=category,
            title=title, content=content,
            metadata=metadata or {},
        )
        self.entries.append(entry)
        return entry_id

    def rebuild_vectors(self):
        """Rebuild all vectors after adding entries. Call once after bulk load."""
        corpus = [f"{e.title} {e.content}" for e in self.entries]
        _build_vocab(corpus)
        for entry in self.entries:
            entry.vector = _vectorize(f"{entry.title} {entry.content}")
        logger.info("knowledge: vectorized %d entries", len(self.entries))
        if self._persist_dir:
            self._save()

    # ── Search ──

    def search(self, query: str, domain: str | None = None,
               category: str | None = None, top_k: int = 5) -> list[dict]:
        """Semantic search over knowledge entries.

        Returns list of {id, title, content, score, domain, category, metadata}.
        """
        if not self.entries:
            return []
        q_vec = _vectorize(query)
        results = []
        for entry in self.entries:
            # Filter by domain/category if specified
            if domain and entry.domain != domain:
                continue
            if category and entry.category != category:
                continue
            score = _cosine_sim(q_vec, entry.vector)
            if score > 0.05:  # minimum relevance threshold
                results.append({
                    "id": entry.id,
                    "title": entry.title,
                    "content": entry.content,
                    "score": round(score, 3),
                    "domain": entry.domain,
                    "category": entry.category,
                    "metadata": entry.metadata,
                })
        results.sort(key=lambda r: -r["score"])
        return results[:top_k]

    def search_faults(self, query: str, domain: str | None = None, top_k: int = 3) -> list[dict]:
        """Search fault library for similar fault patterns."""
        return self.search(query, domain=domain, category="fault", top_k=top_k)

    def search_compliance(self, query: str, domain: str | None = None, top_k: int = 3) -> list[dict]:
        """Search compliance rules relevant to a situation."""
        return self.search(query, domain=domain, category="compliance", top_k=top_k)

    def recall_incidents(self, query: str, domain: str | None = None, top_k: int = 3) -> list[dict]:
        """Recall similar past resolved incidents."""
        return self.search(query, domain=domain, category="incident", top_k=top_k)

    # ── Memory (write resolved incidents back) ──

    def remember_incident(self, domain: str, title: str, diagnosis: str,
                          resolution: str, metadata: dict | None = None) -> str:
        """Store a resolved incident for future retrieval."""
        content = f"DIAGNOSIS: {diagnosis}\nRESOLUTION: {resolution}"
        entry_id = self.add(domain, "incident", title, content, metadata)
        # Re-vectorize the new entry
        entry = next((e for e in self.entries if e.id == entry_id), None)
        if entry and _vocab:
            entry.vector = _vectorize(f"{entry.title} {entry.content}")
        if self._persist_dir:
            self._save()
        return entry_id

    # ── Persistence ──

    def _save(self):
        if not self._persist_dir:
            return
        data = []
        for e in self.entries:
            data.append({
                "id": e.id, "domain": e.domain, "category": e.category,
                "title": e.title, "content": e.content,
                "metadata": e.metadata, "timestamp": e.timestamp,
            })
        path = Path(self._persist_dir) / "knowledge.json"
        path.write_text(json.dumps(data, indent=2))

    def _load(self):
        path = Path(self._persist_dir) / "knowledge.json"
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text())
            for d in data:
                self.add(d["domain"], d["category"], d["title"], d["content"], d.get("metadata", {}))
            self.rebuild_vectors()
            logger.info("knowledge: loaded %d entries from disk", len(self.entries))
        except Exception as e:
            logger.warning("knowledge: failed to load (%s)", e)

    def stats(self) -> dict:
        """Return knowledge store statistics."""
        by_domain = {}
        by_category = {}
        for e in self.entries:
            by_domain[e.domain] = by_domain.get(e.domain, 0) + 1
            by_category[e.category] = by_category.get(e.category, 0) + 1
        return {
            "total_entries": len(self.entries),
            "by_domain": by_domain,
            "by_category": by_category,
            "vocab_size": len(_vocab),
        }


# ── Seed the knowledge store with domain fault libraries ────────────

def seed_knowledge(store: KnowledgeStore):
    """Seed the knowledge store with fault patterns, compliance rules,
    and procedures across all verticals."""

    # -- Aerospace MRO faults --
    store.add("turbine-engine", "fault", "EGT exceedance — blade erosion",
        "Exhaust gas temperature exceeds baseline by 15-25°C at constant N1. Physics residual shows "
        "measured EGT cannot be explained by fuel flow alone. Root cause: HP turbine blade tip erosion "
        "reducing stage efficiency. Resolution: borescope per CMM 72-00-00, replace blade set if tip "
        "loss >0.5mm. Typical repair time: 4.5 hours.")
    store.add("turbine-engine", "fault", "Compressor surge — N1 collapse with EGT spike",
        "Sudden N1 drop 200+ RPM with simultaneous EGT spike 50-80°C. Characteristic of compressor "
        "stall/surge event. Causes: FOD ingestion, blade fouling, variable vane malfunction, "
        "inlet distortion. Immediate action: reduce throttle. Inspect compressor per CMM 72-30-00.")
    store.add("turbine-engine", "fault", "Oil system starvation — bearing distress",
        "Oil pressure drops below 40 PSI with oil temperature rising above 85°C. Vibration increases "
        "on bearing-related frequencies. Root cause: oil pump degradation, filter blockage, or leak. "
        "Resolution: immediate shutdown, inspect oil pump and filter, check bearing surfaces.")
    store.add("turbine-engine", "fault", "Nozzle coking — uneven combustion",
        "EGT spread between sectors exceeds 30°C. Indicates nozzle fouling from carbon deposits. "
        "Progressive degradation. Resolution: remove and clean nozzle guide vanes, chemical soak, "
        "verify spray pattern uniformity.")

    # -- Railway MRT faults --
    store.add("mrt-line", "fault", "CBTC zone controller failure — communications loss",
        "Zone controller hardware fault causes loss of train position data for 2-5 station section. "
        "ATS shows COMM LOSS for affected zone. Trains held at boundary. Resolution: switch to "
        "backup zone controller if available. If both failed: manual block working per OCC procedure. "
        "Recovery time: 15-45 minutes depending on fault type.")
    store.add("mrt-line", "fault", "Platform screen door desynchronization",
        "PSD opening time exceeds 6 seconds or fails to align with train doors. Causes: stopping "
        "position drift >200mm, PSD motor degradation, door enabling loop signal loss. Resolution: "
        "adjust ATO stopping accuracy, replace PSD motor if cycle count >500K.")
    store.add("mrt-line", "fault", "Third rail undervoltage — traction power loss",
        "Third rail voltage drops below 680V at train location. Causes: high simultaneous load "
        "(multiple trains accelerating), rectifier transformer fault at substation, rail bond failure "
        "increasing resistance. Resolution: check substation rectifier, inspect rail bonds in "
        "affected section, verify load balancing between substations.")
    store.add("mrt-line", "fault", "Station flooding — surface water ingress",
        "Heavy rainfall (>50mm/hr) overwhelms surface drainage. Water enters underground station via "
        "escalator shaft or entrance staircase. Sump pumps at capacity. Resolution: deploy flood "
        "barriers at station entrances (LTA mandatory post-2017), close escalators channeling water, "
        "activate emergency sump pump boost, consider service suspension for affected stations.")
    store.add("mrt-line", "fault", "Escalator motor overload — step chain tension",
        "Escalator motor current rising 15-20% above baseline at same passenger load. Causes: step "
        "chain elongation (>0.5% stretch triggers replacement), handrail drive bearing wear, "
        "comb plate interference. Resolution: measure chain pitch, replace if elongated, "
        "lubricate bearings, inspect comb plate clearance.")

    # -- EV faults --
    store.add("ev-network", "fault", "Cell voltage imbalance — dendrite growth precursor",
        "Individual cell voltage deviating >50mV from pack average at same SoC. Indicates internal "
        "resistance asymmetry from SEI non-uniformity or early dendrite formation. If temperature "
        "also elevated: thermal runaway precursor. Resolution: reduce charge rate to 0.5C max, "
        "schedule cell-level impedance test, consider pack retirement if SoH <80%.")
    store.add("ev-network", "fault", "Thermal runaway propagation — battery fire risk",
        "Cell temperature exceeding 55°C with positive dT/dt (>2°C/min). Stage 1: SEI decomposition. "
        "Stage 2: separator melting (>130°C for PE). Stage 3: electrolyte venting and ignition. "
        "NMC cells: onset at ~90°C. LFP cells: onset at ~180°C. Resolution: immediate BMS contactor "
        "open, activate cooling, establish 50m exclusion zone, notify fire brigade with HF gas warning.")
    store.add("ev-network", "fault", "EVSE communication fault — CP pilot signal loss",
        "OCPP session shows EVCommunicationError. Control Pilot signal lost between EVSE and vehicle. "
        "Causes: cable damage, connector corrosion, onboard charger fault. Vehicle automatically "
        "opens contactor on CP loss. Resolution: inspect cable and connector, measure CP signal "
        "with oscilloscope (should be 1kHz ±12V PWM), replace cable if damaged.")
    store.add("ev-network", "fault", "Transformer thermal aging — EV load spike",
        "Distribution transformer winding hot-spot exceeding 120°C under EV charging load. Normal "
        "aging rate doubles for every 6°C above 98°C (IEC 60076-7). At 140°C: rapid insulation "
        "degradation. Resolution: implement smart charging demand response, stagger vehicle "
        "departure times, consider transformer upgrade if sustained loading >90% nameplate.")

    # -- Hospital faults --
    store.add("hospital", "fault", "Operating room positive pressure loss",
        "OR differential pressure drops below +5 Pa relative to corridor. HEPA AHU fan failure or "
        "duct breach. Contamination ingress risk — airborne particles can enter sterile field. "
        "Resolution: immediately close OR doors, activate backup AHU if available, postpone elective "
        "cases until pressure restored. Check HEPA filter DP (replacement if >350 Pa), verify "
        "fan belt/motor. Comply with ASHRAE 170 minimum +8 Pa requirement.")
    store.add("hospital", "fault", "Medical gas O2 zone pressure drop",
        "Zone alarm panel shows O2 pressure below 345 kPa (50 PSI). Causes: manifold bank depletion "
        "with auto-switchover failure, pipeline leak, zone valve inadvertently closed, excessive "
        "simultaneous demand. Resolution: check manifold status (primary vs secondary bank), "
        "verify zone valve positions, switch to cylinder backup if pipeline fault, notify all "
        "clinical areas served by affected zone. Per NFPA 99 Chapter 5.")
    store.add("hospital", "fault", "Blood bank cold chain excursion — temperature above 6°C",
        "Blood bank refrigerator temperature exceeds 6°C for >30 minutes. Product integrity "
        "compromised for RBCs (1-6°C required). Causes: door left open, compressor failure, "
        "thermostat malfunction, power interruption. Resolution: transfer products to backup "
        "fridge, quarantine affected units pending quality review, investigate root cause, "
        "file deviation report per AABB standards. Do not use quarantined units without "
        "pathologist sign-off.")
    store.add("hospital", "fault", "Isolation room negative pressure lost — airborne pathogen risk",
        "AIIR room pressure rises above -2.5 Pa (approaches neutral or positive). Airborne "
        "pathogens (TB, measles, COVID) can escape to corridor. Causes: AHU exhaust fan failure, "
        "HEPA filter blockage, anteroom door propped open. Resolution: close all room doors "
        "immediately, staff wear N95 outside room, repair exhaust system within 2 hours or "
        "transfer patient to functioning isolation room. Per CDC/HICPAC and ASHRAE 170.")

    # -- Defence faults --
    store.add("defence-base", "fault", "Radar TX power degradation — detection range loss",
        "Surveillance radar transmit power dropping below 80% of rated output. Detection range "
        "shrinks proportionally (R_max proportional to P_tx^0.25). Causes: magnetron aging, "
        "waveguide arcing, modulator fault. Resolution: switch to backup transmitter if available, "
        "replace magnetron tube, check waveguide pressurization (SF6 or dry air). Combat "
        "effectiveness assessment required per MIL-STD-882.")
    store.add("defence-base", "fault", "Ship compartment flooding — stability risk",
        "Watertight compartment reporting water ingress. Free surface effect reduces metacentric "
        "height (GM). List angle increasing. Causes: hull breach (combat damage, corrosion), "
        "watertight door failure, piping failure. Resolution: set maximum watertight condition "
        "(Zebra), activate bilge pumps, compute counterflooding requirements to correct list, "
        "assess time-to-capsize from flooding rate. Per STANAG 4154.")

    # -- Compliance rules --
    store.add("turbine-engine", "compliance", "EASA Part 145.A.45 — Maintenance data",
        "All maintenance must be carried out using applicable maintenance data from the design "
        "approval holder. Maintenance data must be current and accessible to maintenance personnel. "
        "Digital twin diagnosis must reference specific CMM chapter numbers.")
    store.add("turbine-engine", "compliance", "AS9100D Clause 8.5.1 — Production and service provision",
        "Organisation must implement production and service provision under controlled conditions "
        "including monitoring and measurement at appropriate stages, use of suitable infrastructure, "
        "and competent personnel. Work orders must include acceptance criteria per step.")

    store.add("mrt-line", "compliance", "LTA Railway Safety Directive — incident reporting",
        "All safety incidents must be reported to LTA within defined timeframes. Category A incidents "
        "(serious injury/death): immediate verbal notification + written report within 24 hours. "
        "Category B (service disruption >30 min): written report within 48 hours.")
    store.add("mrt-line", "compliance", "SFSRTS 2000 — tunnel ventilation for smoke control",
        "Tunnel ventilation must maintain critical velocity >2.5 m/s face velocity for smoke "
        "control. Ventilation direction must push smoke away from evacuation path. Emergency "
        "ventilation mode must be activatable from OCC within 120 seconds of smoke detection.")
    store.add("mrt-line", "compliance", "EN 50126 — RAMS for railway applications",
        "All safety-critical systems (signalling, ATP, ATO) must demonstrate Reliability, "
        "Availability, Maintainability and Safety per EN 50126 lifecycle. Hazard log must be "
        "maintained throughout system life. SIL 4 required for ATP functions.")

    store.add("ev-network", "compliance", "IEC 61851-1 — EV conductive charging system",
        "Defines Mode 1-4 charging, CP pilot state machine (A through F), current rating encoding "
        "via PWM duty cycle. All EVSE must implement control pilot safety functions. Connector "
        "temperature must not exceed 90°C per IEC 62196.")
    store.add("ev-network", "compliance", "NFPA 855 — Energy storage systems",
        "Battery energy storage systems must comply with separation distances, suppression system "
        "requirements (water mist preferred for Li-ion), ventilation for off-gas management, "
        "and emergency response information signage. Maximum 50MWh per zone for utility scale.")
    store.add("ev-network", "compliance", "UN ECE R100 — EV battery safety",
        "No HV electrolyte leakage, fire, or explosion within 1 hour post-crash. Vibration, thermal "
        "stability (oven test to 130°C for 30min), external short circuit, overcharge tests required. "
        "BMS must open contactors within 10ms of crash sensor activation.")

    store.add("hospital", "compliance", "NFPA 99 Chapter 5 — Medical gas pipeline systems",
        "Area alarm panels required outside each zone served (OR, ICU, NICU, ED). Master alarm "
        "in at least 2 continuously staffed locations. O2 warning pressure: <345 kPa. Emergency "
        "pressure: <280 kPa. Zone valve boxes must be accessible for emergency isolation.")
    store.add("hospital", "compliance", "ASHRAE 170-2021 — Healthcare ventilation",
        "Operating room: minimum 20 ACH total, 4 ACH outdoor air, positive pressure. AIIR rooms: "
        "minimum 12 ACH, 2 ACH outdoor air, negative pressure. Burn unit: 10 ACH, positive, HEPA. "
        "Maximum 60% RH in all clinical spaces.")
    store.add("hospital", "compliance", "JCI FMS.7 — Utility systems",
        "Hospital must document and test all utility systems including water, electrical, HVAC. "
        "All utility failures must be reported, investigated, and corrective action documented. "
        "Generator testing required monthly with documented load verification.")

    store.add("defence-base", "compliance", "MIL-STD-882E — System safety",
        "Hazard severity categories: I (Catastrophic), II (Critical), III (Marginal), IV (Negligible). "
        "Digital twin must not take autonomous action in Categories I or II without human authorization. "
        "Software safety assessment required per Task 202.")
    store.add("defence-base", "compliance", "NIST SP 800-171 — CUI protection",
        "All 110 security requirements across 14 control families must be met for handling CUI. "
        "Includes access control, audit and accountability, configuration management, identification "
        "and authentication, incident response, media protection, and system integrity.")

    # Rebuild vectors after seeding
    store.rebuild_vectors()
    logger.info("knowledge: seeded %d entries across %d domains",
                len(store.entries), len(set(e.domain for e in store.entries)))


# ── Singleton store ─────────────────────────────────────────────────

_store: KnowledgeStore | None = None


def get_knowledge_store() -> KnowledgeStore:
    """Get or create the singleton knowledge store."""
    global _store
    if _store is None:
        persist_dir = os.environ.get("KNOWLEDGE_DIR", ".knowledge")
        _store = KnowledgeStore(persist_dir=persist_dir)
        if not _store.entries:
            seed_knowledge(_store)
    return _store
