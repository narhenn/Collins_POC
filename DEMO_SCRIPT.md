# NextXR Demo Script — For Prem

**URL:** http://localhost:5176
**Duration:** ~15 minutes
**Before starting:** Make sure backend + frontend are running. Select "GoalCert Melbourne HQ" from the twin switcher in the top bar.

---

## Opening (30 seconds)

> "Prem, I want to show you where NextXR is at. The platform now does something no competitor does — not Azure Digital Twins, not Bentley iTwin, not Autodesk Tandem. None of them can generate a 3D building from a description. They all require pre-made models from Revit. We don't."

---

## Scene 1 — The AI Twin Builder (3 min)

**Where:** Click "Build a Twin" in the sidebar

> "You showed me the BIM workflow — AutoCAD to Revit to Fuzor. Three tools, weeks of manual work. Watch what happens when we just describe a building."

1. Click **Start**
2. Type: `a 2-floor data center with server rooms, an HVAC plant room, UPS room, and a security office`
3. Wait for the agent pipeline to run (watch the right panel light up: Concierge → Classifier → Composer → Validator → Graph Writer)

> "Five AI agents just ran — the Concierge understood the facility, the Classifier identified the domain, the Composer loaded the right capability bundle, the Validator ran SHACL ontology validation, and the Graph Writer committed real entities to Neo4j. All through the same validated write path."

4. After "Twin committed" appears, the **Scene Generator** runs automatically
5. A **"View 3D Model"** button appears in the pipeline panel

> "And now the Scene Generator just procedurally created a 3D building model from those graph entities. No IFC file, no Revit, no manual step. Thirty seconds from description to 3D."

6. Click **"View 3D Model"** → BIM Viewer opens with the 3D building

> "This is the generated building. Orbit around it, click any room or equipment — the side panel shows the real entity data from the graph."

7. Click a room/equipment piece, show the properties panel

---

## Scene 2 — The Living Twin (3 min)

**Where:** Click "Dashboard" in the sidebar. Switch to "GoalCert Melbourne HQ" from the twin switcher (this one has the full facility + dynamics data).

> "Now let me show you what makes this a LIVING twin, not just a model."

1. Show the **Dashboard** — KPI cards (Risk Score, Entities, Findings, Change Log events)

> "236 entities across 12 building systems. Everything validated through the ontology gate."

2. Click **"Live Ops"** in the sidebar

> "This is the real-time operations centre."

3. Click the **Start Feed** button (select "dynamics" mode)
4. Watch the sensor grid come alive — Air Temperature, UPS SoC, Transformer Oil Temp, Filter Delta P, Chiller COP

> "The dynamics engine is running coupled physics simulations right now. The chiller feeds the AHU which cools the zone which contains the servers. The servers generate heat load back into the zone. It's a real feedback loop — Carnot-bounded COP, IEEE transformer thermal model, Peukert battery discharge. Not scripted values."

5. Watch the SSE event stream on the left — real-time graph mutations flowing in
6. Watch Incidents appear on the right

> "And the behavior rules are running in parallel — 17 rules across three tiers. Tier C threshold rules, Tier B statistical baselines, Tier A physics models. When they fire, they create Findings, which get grouped into Incidents, diagnosed, and actioned — all through the same graph."

---

## Scene 3 — BIM 3D Viewer (2 min)

**Where:** Click "BIM Viewer" in the sidebar

> "And here's the 3D model. We can also import real BIM files — IFC, the industry standard."

1. Show the 3D model (if the GoalCert twin has the IFC-imported model, it shows the building)
2. Click elements, show the properties panel
3. Point out the color legend — green/amber/red by entity status

> "Every element in this 3D model is linked to a live entity in the graph. Click a room, see its sensor data. The colors change in real-time as the dynamics engine runs — green for healthy, amber for degraded, red for fault."

4. If the feed is running, show colors changing

> "This is what Snaptrude can't do. Snaptrude stops at design. We go all the way to live operations."

---

## Scene 4 — Asset Graph Deep Dive (2 min)

**Where:** Click "Asset Graph" in the sidebar

> "Every entity went through the validated write path."

1. Browse the entity list (12 physical assets, 200+ locations)
2. Click an entity (e.g., "AHU-01") — show properties, relationships, behavior profile
3. Click **Add Asset** — show the type dropdown (113 ontology classes across 11 systems)
4. Try creating an invalid entity (e.g., AirHandler without servesSpace) — the SHACL gate rejects it

> "The ontology gate is real. 113 classes, 30+ predicates, SHACL shape validation on every write. You can't put bad data in."

---

## Scene 5 — Bundle Author (2 min)

**Where:** Click "Bundle Author" in the sidebar

> "Here's the closed loop — the reason this platform is domain-agnostic."

1. Click **Start**, type domain: `maritime`, bundle name: `vessel-systems`
2. Describe: `cargo ship with engine room, ballast tanks, navigation bridge, and fuel systems`
3. Watch the 9-stage pipeline: Interviewer → Ontology Drafter → Behavior Modeler → Rule Author → Elicitation Designer → Asset Curator → Linter → Approval Gate → Publisher

> "The Bundle Author just created a new vertical — maritime. It drafted an ontology fragment, authored behavior rules, designed elicitation questions for the Concierge, and it's waiting for human approval. Once approved, the Concierge will know how to build maritime twins. That's the closed loop — Team 3 feeds Team 1."

---

## Scene 6 — Change Log + Governance (1 min)

**Where:** Click "Change Log" in the sidebar

> "Every mutation is hash-chained. SHA-256, append-only, tamper-evident."

1. Show the change log entries — CREATE, UPDATE actions flowing
2. Scroll through recent entries

> "If anyone edits a past entry, the chain breaks. This is the audit trail for compliance."

---

## Scene 7 — Twin Health (30 sec)

**Where:** Click "Twin Health" in the sidebar

1. Show Structural Coverage (should be 100% — assets, locations, findings, reasoning)
2. Show Data Freshness — BIM model shows real import date, telemetry is "Live"

> "Twin Health now shows real data. The BIM row isn't a placeholder anymore — it shows when the model was actually imported."

---

## Closing (1 min)

> "Let me put this in perspective. The traditional BIM pipeline — AutoCAD, Revit, Fuzor — takes weeks and produces a static model. NextXR takes 30 seconds and produces a living digital twin with real physics, real anomaly detection, and a real 3D model. No competitor can do this.
>
> The platform has 20 AI agents, 113 ontology classes, 47 API endpoints, a hash-chained audit trail, and a dynamics engine with 14 coupled physics models. And we can extend to any new domain — maritime, data centers, hospitals — through the Bundle Author's closed loop.
>
> The next step is the cybersecurity simulation layer on top of this — red team, blue team, SOC scenarios running on the digital twin. The architecture is ready for it."

---

## If Prem Asks Tough Questions

**"How is this different from Snaptrude?"**
> "Snaptrude is a design tool — it helps architects go from brief to BIM. It stops there. NextXR goes from brief to a living, operational digital twin with real physics simulation, anomaly detection, and a hash-chained audit trail. Snaptrude is the design phase. We're the operations phase — and we automated the design phase too."

**"Can we import real BIM models from Revit?"**
> "Yes. The BIM Viewer accepts IFC files — the universal BIM standard. Upload an IFC exported from Revit, and it imports the spatial hierarchy and equipment into the graph through the same validated write path, then renders the 3D model."

**"What about the cyber sim?"**
> "The architecture is ready. The dynamics engine simulates the physical systems. Cyber scenarios would run on top — a phishing attack compromises the edge node, the attacker moves laterally to the HVAC controller, the AHU setpoint changes, the physics engine shows the temperature rising, the behavior rules detect the anomaly. The graph already models all these relationships."

**"Is this production-ready?"**
> "The core is solid — validated write path, hash-chained changelog, graceful degradation when services are down. Some panels are still placeholders (Predict, Copilot, Compliance, Marketplace). The dynamics engine and 3D generation are new. For a GoalCert demo it's ready. For production we'd need auth hardening, WebSocket migration, and the full cyber sim scenarios."

---

## Pre-Demo Checklist

- [ ] Docker running (`docker compose up -d`)
- [ ] Backend running (`cd nextxr-ontology && python -m server.main`)
- [ ] Frontend running (`cd frontend && npx vite --port 5176`)
- [ ] Open http://localhost:5176
- [ ] Select "GoalCert Melbourne HQ" in twin switcher
- [ ] Verify Dashboard loads with entity counts
- [ ] Verify BIM Viewer shows the 3D model
- [ ] Close any other tabs/apps to avoid performance issues
