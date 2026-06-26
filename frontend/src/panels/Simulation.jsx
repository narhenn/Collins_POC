import { useState } from 'react'
import { PanelHeader, Card } from '../components/ui/Card'
import MockBanner from '../components/ui/MockBanner'
import NoTwin from '../components/NoTwin'
import { useApi } from '../hooks/useApi'
import { useTwin } from '../context/TwinContext'
import { localName } from '../lib/format'
import api from '../api/client'

/** Simulation / Behaviour Engine.
 *  TOP (live): the generative dynamics archetypes + monitoring kinds that drive
 *  the twin — the real behaviour engine, from /schema/archetypes.
 *  BOTTOM (mock): what-if scenarios (still scripted — see PLACEHOLDERS.md). */
const SCENARIOS = {
  egt: { icon: 'ti-flame', label: 'Turbine hot-section distress', body: 'EGT ramps from 650°C to 780°C over 15 minutes. Tier-B baseline flags deviation at +2.5σ. Diagnosis: possible turbine blade erosion or fuel nozzle coking. Immediate action: reduce thrust, inspect hot section.', tags: ['Critical', 'EGT 780°C', 'Ground engine'] },
  hydraulic: { icon: 'ti-droplet', label: 'Hydraulic system leak', body: 'Pressure drops from 3000 PSI to 1800 PSI. Tier-C threshold fires at 2000 PSI. Downstream actuators lose authority. Diagnosis: seal failure in actuator HYD-02.', tags: ['Critical', '<2000 PSI', 'Isolate line'] },
  cooling: { icon: 'ti-snowflake-off', label: 'Avionics bay cooling loss', body: 'Chiller COP degrades from 5.2 to 3.5. Avionics bay temp rises past 28°C in ~12 min. Cascade: Tier-B COP drift triggers, then Tier-C bay overtemp. Diagnosis recommends backup chiller.', tags: ['Warning→Critical', 'COP 3.5', 'Add backup'] },
  gpu: { icon: 'ti-plug-x', label: 'Ground power unit failure', body: 'GPU transformer oil temp exceeds 85°C. UPS takes load. SoC drops. Recommend switching to backup GPU and scheduling oil change.', tags: ['High', 'Oil 85°C+', 'Switch GPU'] },
}

export default function Simulation() {
  const { activeTenant } = useTwin()
  const [key, setKey] = useState('cooling')
  const { data: cat } = useApi(() => api.archetypes(), [])
  if (!activeTenant) return <NoTwin />
  const s = SCENARIOS[key]
  const dyn = cat?.dynamics || []
  const kinds = cat?.monitoring_kinds || []

  return (
    <div className="panel">
      <PanelHeader title="Behaviour Engine & Simulation"
                   subtitle="The generative dynamics + monitoring archetypes that drive every twin" />

      {/* ── LIVE: the real behaviour engine catalog ── */}
      <Card title={<><i className="ti ti-engine" style={{ marginRight: 6 }} />Dynamics Archetypes ({dyn.length})</>}>
        <div className="muted" style={{ fontSize: 12, marginBottom: 10 }}>
          Each ontology class binds to one of these parameterized physics archetypes.
          The engine resolves them per entity and couples them through the graph.
        </div>
        <div className="grid-2">
          {dyn.map((a) => (
            <div key={a.archetype} style={{ border: '1px solid var(--border)', borderRadius: 8, padding: '8px 10px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                <span className="pill pill-blue">{a.archetype}</span>
              </div>
              {a.produces?.length > 0 && (
                <div style={{ fontSize: 10.5, color: 'var(--muted)' }}>
                  produces: {a.produces.map(localName).join(', ')}
                </div>
              )}
              {a.consumes?.length > 0 && (
                <div style={{ fontSize: 10.5, color: 'var(--hint)' }}>
                  consumes: {a.consumes.join(' · ')}
                </div>
              )}
            </div>
          ))}
        </div>
        <div style={{ marginTop: 12 }}>
          <span style={{ fontSize: 12, color: 'var(--muted)' }}>Monitoring rule kinds: </span>
          {kinds.map((k) => <span key={k} className="pill pill-surface" style={{ marginRight: 4 }}>{k}</span>)}
        </div>
      </Card>

      {/* ── MOCK: what-if scenarios ── */}
      <div className="section-gap">
        <MockBanner what="Impact analyses below are scripted; a real engine forks the twin into a scenario tenant and replays behaviours over injected conditions." />
      </div>
      <div className="grid-2 section-gap">
        {Object.entries(SCENARIOS).map(([k, v]) => (
          <button key={k} className="btn" style={{
            justifyContent: 'flex-start', padding: '10px 12px',
            borderColor: k === key ? 'var(--accent-amber)' : 'var(--border)',
            background: k === key ? 'rgba(224,150,47,.06)' : 'var(--surface)',
          }} onClick={() => setKey(k)}>
            <i className={`ti ${v.icon}`} /> {v.label}
          </button>
        ))}
      </div>
      <Card title={`Scenario: ${s.label}`}>
        <div style={{ fontSize: 12, lineHeight: 1.7, color: 'var(--muted)' }}>{s.body}</div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 12 }}>
          {s.tags.map((t) => <span key={t} className="pill pill-surface">{t}</span>)}
          <span className="pill pill-surface">Confidence ~74%</span>
        </div>
      </Card>
    </div>
  )
}
