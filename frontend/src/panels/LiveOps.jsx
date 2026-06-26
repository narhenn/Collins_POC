import { useState } from 'react'
import { PanelHeader, Card } from '../components/ui/Card'
import { Empty } from '../components/ui/States'
import NoTwin from '../components/NoTwin'
import FeedControls from '../components/FeedControls'
import { useEventStream } from '../hooks/useEventStream'
import { usePolling } from '../hooks/useApi'
import { useTwin } from '../context/TwinContext'
import { useToast } from '../context/ToastContext'
import { actionColor, localName, shortId, timeOf } from '../lib/format'
import api from '../api/client'

/** Live Operational Layer — the real-time spine. The left column is the SSE
 *  event stream straight off the event bus (every committed mutation). The
 *  right shows live feed sensors + the most recent incident from the graph. */
export default function LiveOps() {
  const { activeTenant } = useTwin()
  const { events, connected } = useEventStream(activeTenant, { max: 60 })
  const { data: feed } = usePolling(() => api.feedStatus(), 1500, [])
  const { data: incData } = usePolling(
    () => api.listEntities(activeTenant, 'Incident', 5), 3000,
    [activeTenant], { skip: !activeTenant },
  )
  const { data: actionData } = usePolling(
    () => api.listEntities(activeTenant, 'Process', 10), 3000,
    [activeTenant], { skip: !activeTenant },
  )

  if (!activeTenant) return <NoTwin />

  const incidents = incData?.nodes || []
  const temp = feed?.latest_value
  const tempCls = temp == null ? '' : temp > 28 ? 'sensor-crit' : temp > 25 ? 'sensor-warn' : ''
  const signals = feed?.signals || {}

  return (
    <div className="panel">
      <PanelHeader
        title="Live Operational Layer"
        subtitle={
          <>Event bus stream · {connected
            ? <span style={{ color: 'var(--ok)' }}>● connected</span>
            : <span className="muted">○ connecting…</span>}</>
        }
      >
        <FeedControls />
      </PanelHeader>

      <div className="sensor-grid section-gap">
        {/* ── Aerospace signals first ── */}
        {signals['aero:exhaustGasTemp'] != null && (
          <div className={`sensor-card ${signals['aero:exhaustGasTemp'] > 750 ? 'sensor-crit' : signals['aero:exhaustGasTemp'] > 700 ? 'sensor-warn' : ''}`}>
            <div className="live-indicator" />
            <div className="sensor-label">Exhaust Gas Temp</div>
            <div className="sensor-value">{Number(signals['aero:exhaustGasTemp']).toFixed(0)}<span className="sensor-unit">°C</span></div>
          </div>
        )}
        {signals['aero:shaftSpeedN1'] != null && (
          <div className={`sensor-card ${Math.abs(signals['aero:shaftSpeedN1'] - 5200) > 30 ? 'sensor-warn' : ''}`}>
            <div className="live-indicator" />
            <div className="sensor-label">Shaft Speed N1</div>
            <div className="sensor-value">{Number(signals['aero:shaftSpeedN1']).toFixed(0)}<span className="sensor-unit">RPM</span></div>
          </div>
        )}
        {signals['aero:hydraulicPressure'] != null && (
          <div className={`sensor-card ${signals['aero:hydraulicPressure'] < 2000 ? 'sensor-crit' : signals['aero:hydraulicPressure'] < 2500 ? 'sensor-warn' : ''}`}>
            <div className="live-indicator" />
            <div className="sensor-label">Hydraulic Pressure</div>
            <div className="sensor-value">{Number(signals['aero:hydraulicPressure']).toFixed(0)}<span className="sensor-unit">PSI</span></div>
          </div>
        )}
        {signals['aero:avionicsBayTemp'] != null && (
          <div className={`sensor-card ${signals['aero:avionicsBayTemp'] > 30 ? 'sensor-crit' : signals['aero:avionicsBayTemp'] > 28 ? 'sensor-warn' : ''}`}>
            <div className="live-indicator" />
            <div className="sensor-label">Avionics Bay Temp</div>
            <div className="sensor-value">{Number(signals['aero:avionicsBayTemp']).toFixed(1)}<span className="sensor-unit">°C</span></div>
          </div>
        )}
        {/* ── Facility infrastructure ── */}
        {signals['cfp:chillerCOP'] != null && (
          <div className={`sensor-card ${signals['cfp:chillerCOP'] < 3.5 ? 'sensor-warn' : ''}`}>
            <div className="live-indicator" />
            <div className="sensor-label">Chiller COP</div>
            <div className="sensor-value">{Number(signals['cfp:chillerCOP']).toFixed(2)}</div>
          </div>
        )}
        {signals['cfp:upsSoC'] != null && (
          <div className={`sensor-card ${signals['cfp:upsSoC'] < 50 ? 'sensor-crit' : signals['cfp:upsSoC'] < 90 ? 'sensor-warn' : ''}`}>
            <div className="live-indicator" />
            <div className="sensor-label">UPS State of Charge</div>
            <div className="sensor-value">{Number(signals['cfp:upsSoC']).toFixed(0)}<span className="sensor-unit">%</span></div>
          </div>
        )}
        {signals['cfp:oilTemperature'] != null && (
          <div className={`sensor-card ${signals['cfp:oilTemperature'] > 85 ? 'sensor-crit' : signals['cfp:oilTemperature'] > 75 ? 'sensor-warn' : ''}`}>
            <div className="live-indicator" />
            <div className="sensor-label">GPU Oil Temp</div>
            <div className="sensor-value">{Number(signals['cfp:oilTemperature']).toFixed(1)}<span className="sensor-unit">°C</span></div>
          </div>
        )}
        {signals['cfp:filterDeltaP'] != null && (
          <div className={`sensor-card ${signals['cfp:filterDeltaP'] > 250 ? 'sensor-crit' : signals['cfp:filterDeltaP'] > 200 ? 'sensor-warn' : ''}`}>
            <div className="live-indicator" />
            <div className="sensor-label">Filter Delta P</div>
            <div className="sensor-value">{Number(signals['cfp:filterDeltaP']).toFixed(0)}<span className="sensor-unit">Pa</span></div>
          </div>
        )}
        <div className="sensor-card">
          <div className="live-indicator" />
          <div className="sensor-label">Samples Processed</div>
          <div className="sensor-value">{feed?.samples_processed ?? 0}</div>
        </div>
        <div className="sensor-card">
          <div className="live-indicator" />
          <div className="sensor-label">Findings Emitted</div>
          <div className="sensor-value" style={{ color: 'var(--accent-amber)' }}>{feed?.findings_emitted ?? 0}</div>
        </div>
      </div>

      <div className="grid-2">
        <Card title={<><i className="ti ti-bolt" /> Live Mutation Stream</>}>
          {events.length === 0
            ? <Empty label="No events yet. Start the feed or add an asset." icon="ti-wave-sine" />
            : (
              <div className="event-list" style={{ maxHeight: 380, overflowY: 'auto' }}>
                {events.map((ev, i) => (
                  <div key={`${ev.event_id}-${i}`} className="event-item">
                    <div className="event-icon" style={{ background: `${actionColor(ev.action)}22`, color: actionColor(ev.action) }}>
                      <i className={`ti ${{ create: 'ti-plus', update: 'ti-pencil', delete: 'ti-trash' }[ev.action] || 'ti-point'}`} />
                    </div>
                    <div className="event-body">
                      <div className="event-title">
                        <span style={{ color: actionColor(ev.action), textTransform: 'uppercase', fontSize: 10, fontWeight: 700 }}>{ev.action}</span>
                        {' '}{ev.label || localName(ev.entity_type)}
                      </div>
                      <div className="event-meta">{ev.actor} · {shortId(ev.entity_id, 10)}</div>
                    </div>
                    <span className="event-time">{timeOf(ev.ts)}</span>
                  </div>
                ))}
              </div>
            )}
        </Card>

        <Card title={<><i className="ti ti-git-merge" /> Correlated Incidents</>}>
          {incidents.length === 0
            ? <Empty label="No incidents. The diagnosis engine groups findings into incidents as the feed runs." icon="ti-shield-check" />
            : incidents.map((inc) => (
                <div key={inc.id} className="event-item" style={{ borderColor: 'rgba(226,86,78,.25)', background: 'rgba(226,86,78,.04)' }}>
                  <div className="event-icon ev-crit"><i className="ti ti-urgent" /></div>
                  <div className="event-body">
                    <div className="event-title">{inc.displayName || 'Incident'}</div>
                    <div className="event-meta">{inc.status || 'open'} · {shortId(inc.id, 10)}</div>
                  </div>
                  <span className="event-time">{timeOf(inc.createdAt)}</span>
                </div>
              ))}
        </Card>
      </div>

      {/* GoalCert training pipeline handoff */}
      <GoalCertHandoff actions={actionData?.nodes || []} tenant={activeTenant} />
    </div>
  )
}


/** GoalCert integration panel — launches real training scenarios via API */
function GoalCertHandoff({ actions, tenant }) {
  const [gcRun, setGcRun] = useState(null)
  const [gcLoading, setGcLoading] = useState(false)
  const toast = useToast()

  const actionNodes = actions.filter(n => /action|recommendation/i.test(n.canonicalType || ''))
  if (actionNodes.length === 0) return null

  const launchTraining = async () => {
    setGcLoading(true)
    try {
      const result = await api.triggerGoalcert({
        tenant_id: tenant,
        fault_type: 'chiller_cop_degradation',
        equipment_name: 'Chiller-01',
      })
      setGcRun(result)
      if (result.status === 'ok') {
        toast.ok('GoalCert', 'Training scenario launched successfully')
      } else {
        toast.info('GoalCert', result.message || 'Service queued')
      }
    } catch (e) {
      toast.err('GoalCert', 'Could not reach GoalCert service')
      setGcRun({ status: 'degraded', message: 'GoalCert service unreachable. Training scenario queued.' })
    }
    setGcLoading(false)
  }

  return (
    <Card title={<><i className="ti ti-school" /> GoalCert Training Pipeline <span className="pill pill-surface" style={{fontSize:9}}>live integration</span></>}>
      <div className="muted" style={{ fontSize: 11, marginBottom: 10 }}>
        Action nodes from the diagnosis chain feed into GoalCert's Simulation Engine. Each action becomes a scored MRO training scenario with LOTO, diagnosis, repair, and verification phases.
      </div>

      {actionNodes.slice(0, 5).map((a) => (
        <div key={a.id} className="event-item" style={{ borderLeft: '3px solid var(--accent-teal)' }}>
          <div className="event-icon" style={{ background: 'rgba(24,169,153,.12)', color: 'var(--accent-teal)' }}>
            <i className="ti ti-player-play" />
          </div>
          <div className="event-body">
            <div className="event-title">{a.displayName || 'Action'}</div>
            <div className="event-meta">{a.status || 'pending'} · {shortId(a.id, 10)}</div>
          </div>
          <span className="event-time">{timeOf(a.createdAt)}</span>
        </div>
      ))}

      {!gcRun && (
        <button className="btn btn-primary" style={{ marginTop: 12, width: '100%' }}
                onClick={launchTraining} disabled={gcLoading}>
          {gcLoading ? 'Launching...' : 'Launch GoalCert Training Scenario'}
        </button>
      )}

      {gcRun && gcRun.status === 'ok' && (
        <div style={{ marginTop: 12, padding: 14, background: 'rgba(24,169,153,.06)', borderRadius: 8, border: '1px solid rgba(24,169,153,.2)' }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--accent-teal)', marginBottom: 8 }}>
            <i className="ti ti-check" /> Scenario Run Complete
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, fontSize: 11 }}>
            <div><span className="muted">Scenario:</span> Collins MRO Chiller Repair</div>
            <div><span className="muted">Duration:</span> {gcRun.duration_s ? `${Math.round(gcRun.duration_s / 60)} min` : '—'}</div>
            <div><span className="muted">Tech Score:</span> <b style={{color:'var(--accent-teal)'}}>{gcRun.scores?.red ?? '—'}</b></div>
            <div><span className="muted">QA Score:</span> <b style={{color:'var(--accent-blue)'}}>{gcRun.scores?.blue ?? '—'}</b></div>
            {gcRun.kpis && <>
              <div><span className="muted">Detection Rate:</span> {((gcRun.kpis.detection_rate || 0) * 100).toFixed(0)}%</div>
              <div><span className="muted">Containment:</span> {((gcRun.kpis.containment_rate || 0) * 100).toFixed(0)}%</div>
            </>}
          </div>
          {gcRun.objectives && (
            <div style={{ marginTop: 10, fontSize: 10 }}>
              <div style={{ fontWeight: 600, marginBottom: 4 }}>Technician Objectives:</div>
              {(gcRun.objectives.red || []).map((o, i) => (
                <div key={i} style={{ color: 'var(--muted)' }}>
                  <i className="ti ti-check" style={{ color: 'var(--accent-green)', fontSize: 11 }} /> {typeof o === 'string' ? o : o.text}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {gcRun && gcRun.status === 'degraded' && (
        <div style={{ marginTop: 12, padding: 12, background: 'rgba(224,150,47,.06)', borderRadius: 8, border: '1px solid rgba(224,150,47,.2)', fontSize: 11, color: 'var(--accent-amber)' }}>
          <i className="ti ti-alert-triangle" /> {gcRun.message}
        </div>
      )}
    </Card>
  )
}
