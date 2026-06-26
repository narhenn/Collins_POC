import { PanelHeader, Card } from '../components/ui/Card'
import MockBanner from '../components/ui/MockBanner'
import NoTwin from '../components/NoTwin'
import { useTwin } from '../context/TwinContext'

/** Compliance — MOCK. Illustrative standard coverage + gaps. A real version
 *  models standards/clauses as Document entities and maps Asset→SOP→Clause→
 *  Evidence in the graph (see PLACEHOLDERS.md → "Compliance twin"). */
const STANDARDS = [
  { name: 'AS9100 Rev D — Aerospace Quality Management', pct: 87, color: 'var(--accent-blue)' },
  { name: 'EASA Part 145 — MRO Organization Approval', pct: 74, color: 'var(--accent-amber)' },
  { name: 'FAA 14 CFR Part 145 — Repair Station', pct: 79, color: 'var(--accent-blue)' },
  { name: 'ARP4761 — Safety Assessment Process', pct: 91, color: 'var(--accent-green)' },
]
const GAPS = [
  { sev: 'red', t: 'AS9100 §8.5.1', d: 'Chiller preventive maintenance cycle not documented in MRO work order system' },
  { sev: 'amber', t: 'EASA Part 145.A.45', d: 'Avionics Bay 2 environmental monitoring log gap — 14 days overdue' },
  { sev: 'amber', t: 'FAA AC 145-9', d: 'Backup chiller not listed in approved equipment list (AEL) — add after twin expansion' },
]

export default function Compliance() {
  const { activeTenant } = useTwin()
  if (!activeTenant) return <NoTwin />
  return (
    <div className="panel">
      <PanelHeader title="Compliance Twin" subtitle="Standard coverage · gap detection · evidence mapping" />
      <MockBanner what="Coverage and gaps are illustrative; real compliance models clauses as Document entities and links Asset→SOP→Clause→Evidence in the graph." />
      <div className="grid-2">
        <Card title="Standard Coverage">
          {STANDARDS.map((s) => (
            <div key={s.name} className="bar-row">
              <div className="bar-label"><span>{s.name}</span><b style={{ color: s.color }}>{s.pct}%</b></div>
              <div className="bar-track"><div className="bar-fill" style={{ width: `${s.pct}%`, background: s.color }} /></div>
            </div>
          ))}
        </Card>
        <Card title={<>AI-Identified Gaps <span className="pill" style={{ background: 'rgba(226,86,78,.12)', color: 'var(--accent-red)' }}>{GAPS.length} open</span></>}>
          {GAPS.map((g) => (
            <div key={g.t} style={{ display: 'flex', gap: 8, padding: 8, marginBottom: 7, borderRadius: 6,
              background: g.sev === 'red' ? 'rgba(226,86,78,.05)' : 'rgba(224,150,47,.05)',
              border: `1px solid ${g.sev === 'red' ? 'rgba(226,86,78,.15)' : 'rgba(224,150,47,.15)'}` }}>
              <i className={`ti ti-alert-triangle`} style={{ color: g.sev === 'red' ? 'var(--accent-red)' : 'var(--accent-amber)', marginTop: 1 }} />
              <div style={{ fontSize: 11 }}><b>{g.t}</b><br /><span className="muted">{g.d}</span></div>
            </div>
          ))}
        </Card>
      </div>
    </div>
  )
}
