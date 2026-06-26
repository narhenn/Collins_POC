#!/usr/bin/env python3
"""
seed_melbourne_hq.py — Pre-seed the collins-melb-hq tenant for Act 6
(cross-tenant intelligence) of the Collins Aerospace PoC demo.

Creates a small Melbourne HQ facility with a Chiller that has a RESOLVED
incident: COP drift → diagnosed as condenser fouling → fixed by coil
cleaning + refrigerant recharge. This history lets the Singapore MRO
diagnosis agent surface cross-tenant intelligence.

Usage:
    cd nextxr-ontology
    python -m scripts.seed_melbourne_hq

Requires: Neo4j running (docker compose up -d)
"""
from __future__ import annotations

import sys
from pathlib import Path

# ensure the repo root is on sys.path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from graph.schema import apply_schema
from graph.writer import GraphWriter, Rel
from changelog.service import ChangeLog
from twins.service import TwinRegistry

CFP  = "https://ontology.nextxr.io/v3/cfp#"
CORE = "https://ontology.nextxr.io/v3/core#"

TENANT = "collins-melb-hq"
ACTOR  = "seed-script"


def main():
    print(f"[seed] Applying schema constraints...")
    try:
        apply_schema(dry_run=False, close=False)
    except Exception as e:
        print(f"[seed] Schema apply warning: {e}")

    registry = TwinRegistry()
    if registry.get(TENANT):
        print(f"[seed] Tenant '{TENANT}' already exists, skipping.")
        return

    cl = ChangeLog()
    writer = GraphWriter(changelog=cl)

    # Create twin via registry (seeds a generic-facility)
    print(f"[seed] Creating twin '{TENANT}'...")
    twin = registry.create(
        name="Collins Melbourne HQ",
        domain="generic-facility",
        writer=writer,
        actor=ACTOR,
        tenant_id=TENANT,
    )
    print(f"[seed] Twin created: {twin.tenant_id} (seed_asset={twin.seed_asset_id})")

    # Now add a resolved incident chain to the chiller
    # Find the chiller entity
    from graph.query import GraphQuery
    query = GraphQuery()
    entities = query.list_by_label(TENANT, "PhysicalAsset", limit=50)
    chiller_id = None
    for e in entities:
        if "Chiller" in e.get("displayName", ""):
            chiller_id = e["id"]
            break

    if not chiller_id:
        print("[seed] Warning: no chiller found to attach incident. Skipping incident chain.")
        return

    print(f"[seed] Found chiller: {chiller_id}")

    # Create all nodes first (no inter-node relationships yet — direction matters)
    finding = writer.create(
        tenant_id=TENANT,
        canonical_type=CORE + "Finding",
        actor=ACTOR,
        properties={
            "displayName": "Chiller COP drift — 3.2 (baseline 5.1)",
            "severity": "warning",
            "status": "resolved",
            "behaviorId": "cfp.chiller_cop_baseline",
        },
        relationships=[Rel("nxr:flags", chiller_id)],
    )
    print(f"[seed] Finding: {finding.node_id}")

    incident = writer.create(
        tenant_id=TENANT,
        canonical_type=CORE + "Incident",
        actor=ACTOR,
        properties={
            "displayName": "Chiller-01 COP degradation",
            "status": "resolved",
            "severity": "warning",
        },
    )
    print(f"[seed] Incident: {incident.node_id}")

    diagnosis = writer.create(
        tenant_id=TENANT,
        canonical_type=CORE + "Diagnosis",
        actor=ACTOR,
        properties={
            "displayName": "Condenser fouling confirmed",
            "status": "resolved",
            "diagnosisText": "Chiller COP dropped from 5.1 to 3.2 over 2 weeks. "
                             "Condenser coil inspection revealed heavy fouling. "
                             "Root cause: airborne debris accumulation from nearby "
                             "construction site.",
            "confidence": 0.95,
        },
    )
    print(f"[seed] Diagnosis: {diagnosis.node_id}")

    recommendation = writer.create(
        tenant_id=TENANT,
        canonical_type=CORE + "Recommendation",
        actor=ACTOR,
        properties={
            "displayName": "Clean condenser + recharge refrigerant",
            "status": "resolved",
            "recommendationText": "1. Clean condenser coils (chemical wash). "
                                  "2. Recharge R-410A refrigerant to spec. "
                                  "3. Verify COP recovery to >4.5. "
                                  "4. Schedule 60-day condenser inspection cycle.",
        },
    )
    print(f"[seed] Recommendation: {recommendation.node_id}")

    action = writer.create(
        tenant_id=TENANT,
        canonical_type=CORE + "Action",
        actor=ACTOR,
        properties={
            "displayName": "Condenser coil cleaning + R-410A recharge",
            "status": "resolved",
            "executionMode": "manual",
            "actionText": "Technician performed chemical wash on condenser coils. "
                          "Recharged R-410A to 12.5 kg (spec: 12.2-12.8 kg). "
                          "Post-maintenance COP measured at 5.0. "
                          "Total downtime: 2.5 hours.",
        },
    )
    print(f"[seed] Action: {action.node_id}")

    # Wire the chain with CORRECT relationship directions:
    # Finding --groupedInto--> Incident
    # Incident --diagnosedAs--> Diagnosis
    # Diagnosis --recommends--> Recommendation
    # Recommendation --proposesAction--> Action
    if finding.ok and incident.ok:
        writer.relate(tenant_id=TENANT, actor=ACTOR,
                      source_id=finding.node_id, predicate="nxr:groupedInto",
                      target_id=incident.node_id)
        print(f"[seed] Linked: Finding --groupedInto--> Incident")

    if incident.ok and diagnosis.ok:
        writer.relate(tenant_id=TENANT, actor=ACTOR,
                      source_id=incident.node_id, predicate="nxr:diagnosedAs",
                      target_id=diagnosis.node_id)
        print(f"[seed] Linked: Incident --diagnosedAs--> Diagnosis")

    if diagnosis.ok and recommendation.ok:
        writer.relate(tenant_id=TENANT, actor=ACTOR,
                      source_id=diagnosis.node_id, predicate="nxr:recommends",
                      target_id=recommendation.node_id)
        print(f"[seed] Linked: Diagnosis --recommends--> Recommendation")

    if recommendation.ok and action.ok:
        writer.relate(tenant_id=TENANT, actor=ACTOR,
                      source_id=recommendation.node_id, predicate="nxr:proposesAction",
                      target_id=action.node_id)
        print(f"[seed] Linked: Recommendation --proposesAction--> Action")

    print(f"\n[seed] Melbourne HQ seeded successfully!")
    print(f"[seed] Tenant: {TENANT}")
    print(f"[seed] Incident chain: Finding -> Incident -> Diagnosis -> Recommendation -> Action")
    print(f"[seed] Resolution: condenser cleaning, 2.5h downtime, COP restored to 5.0")


if __name__ == "__main__":
    main()
