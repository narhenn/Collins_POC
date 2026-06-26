import { useState } from 'react'
import { PanelHeader, Card } from '../components/ui/Card'
import { Empty } from '../components/ui/States'
import { DemoNote } from '../components/ui/Modal'
import NoTwin from '../components/NoTwin'
import { usePolling } from '../hooks/useApi'
import { useTwin } from '../context/TwinContext'
import { shortId, timeOf } from '../lib/format'
import api from '../api/client'

/**
 * AI Agents — powered by AUTOMIND workflow engine.
 *  - REAL: the diagnosis pipeline runs server-side as the feed loops and writes
 *    Diagnosis / Recommendation / Action / Incident entities. We surface those
 *    as live "agent output" from the graph.
 *  - Agent workflows are built and orchestrated by the AUTOMIND visual builder.
 */
const AGENTS = [
  { name: 'Diagnosis Agent', icon: 'ti-stethoscope', color: 'var(--accent-blue)', real: true,
    status: 'Correlates findings → incident → diagnosis (runs with the feed)' },
  { name: 'Correlation Agent', icon: 'ti-git-merge', color: 'var(--accent-purple)', real: true,
    status: 'Groups related findings into incidents via the write path' },
  { name: 'Cross-Tenant Intel', icon: 'ti-world', color: 'var(--accent-teal)', real: true,
    status: 'Surfaces resolved incidents from other Collins facilities' },
  { name: 'MRO Safety Agent', icon: 'ti-shield', color: 'var(--accent-red)', real: false,
    status: 'Would watch safety-critical findings and escalate per ARP4761' },
  { name: 'GoalCert Handoff', icon: 'ti-school', color: 'var(--accent-green)', real: false,
    status: 'Would route Action nodes to GoalCert for training video generation' },
]

export default function Agents() {
  const { activeTenant } = useTwin()
  const [toggles, setToggles] = useState(() => AGENTS.map(() => true))

  const { data: diagData } = usePolling(
    () => api.listEntities(activeTenant, 'Document', 20), 3000,
    [activeTenant], { skip: !activeTenant },
  )
  const { data: procData } = usePolling(
    () => api.listEntities(activeTenant, 'Process', 20), 3000,
    [activeTenant], { skip: !activeTenant },
  )

  if (!activeTenant) return <NoTwin />

  // Diagnoses + recommendations are Document-category; actions are Process.
  const docs = diagData?.nodes || []
  const actions = (procData?.nodes || []).filter((n) => /action/i.test(n.canonicalType || ''))

  return (
    <div className="panel">
      <PanelHeader
        title={<>Autonomous Operations Agents <span className="pill pill-surface" style={{fontSize:10,verticalAlign:'middle',marginLeft:6}}>Powered by AUTOMIND</span></>}
        subtitle="Agent workflows orchestrated by the AUTOMIND visual builder. The reasoning chain runs as the feed loops."
      />

      <Card title={<>Agent Roster <DemoNote>roster toggles are mock</DemoNote></>} className="section-gap">
        {AGENTS.map((a, i) => (
          <div className="agent-row" key={a.name}>
            <div className="agent-icon" style={{ background: `${a.color}22`, color: a.color }}>
              <i className={`ti ${a.icon}`} />
            </div>
            <div>
              <div className="agent-name">
                {a.name}{' '}
                {a.real
                  ? <span className="pill" style={{ background: 'rgba(79,174,58,.14)', color: 'var(--accent-green)' }}>LIVE</span>
                  : <span className="pill pill-surface">PLANNED</span>}
              </div>
              <div className="agent-status">{a.status}</div>
            </div>
            <div className={`agent-toggle ${toggles[i] ? 'on' : ''}`}
                 onClick={() => setToggles((t) => t.map((v, j) => j === i ? !v : v))} />
          </div>
        ))}
      </Card>

      <div className="grid-2">
        <Card title={<><i className="ti ti-stethoscope" /> Diagnoses & Recommendations <span className="pill" style={{ background: 'rgba(79,174,58,.14)', color: 'var(--accent-green)' }}>LIVE</span></>}>
          {docs.length === 0
            ? <Empty label="No diagnoses yet. Run the feed — the engine produces them after findings accumulate." icon="ti-stethoscope" />
            : docs.map((d) => (
                <div key={d.id} className="event-item">
                  <div className="event-icon ev-info"><i className="ti ti-file-text" /></div>
                  <div className="event-body">
                    <div className="event-title">{d.displayName || 'Diagnosis'}</div>
                    <div className="event-meta">{d.message || d.status || shortId(d.id, 10)}</div>
                  </div>
                  <span className="event-time">{timeOf(d.createdAt)}</span>
                </div>
              ))}
        </Card>

        <Card title={<><i className="ti ti-checklist" /> Recommended Actions <span className="pill" style={{ background: 'rgba(79,174,58,.14)', color: 'var(--accent-green)' }}>LIVE</span></>}>
          {actions.length === 0
            ? <Empty label="No actions yet." icon="ti-checklist" />
            : actions.map((a) => (
                <div key={a.id} className="event-item">
                  <div className="event-icon ev-ok"><i className="ti ti-arrow-right-circle" /></div>
                  <div className="event-body">
                    <div className="event-title">{a.displayName || 'Action'}</div>
                    <div className="event-meta">{a.status || 'proposed'} · {shortId(a.id, 10)}</div>
                  </div>
                  <span className="event-time">{timeOf(a.createdAt)}</span>
                </div>
              ))}
        </Card>
      </div>
    </div>
  )
}
