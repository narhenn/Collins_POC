import React, { useEffect, useState } from 'react'
import api from './api'
import Chart from './Chart.jsx'
import Markdown from './Markdown.jsx'
import Trainer from './Trainer.jsx'
import { Icon, fmt, pct, hColor, predictCharts, simTrajectory, signalsAtRisk } from './lib.jsx'

const HORIZONS = ['1 hour', '2 hours', '6 hours', '24 hours', '3 days', '1 week']
const HMIN = { '1 hour': 60, '2 hours': 120, '6 hours': 360, '24 hours': 1440, '3 days': 4320, '1 week': 10080 }

export default function Scenario({ tenant, machineName, domain, isLive = true, twin, setSimFault }) {
  const [tab, setTab] = useState('scenario')           // 'scenario' | 'fault'
  const [scenarios, setScenarios] = useState([])
  const [faults, setFaults] = useState([])
  const [desc, setDesc] = useState('')
  const [horizon, setHorizon] = useState('2 hours')
  const [spec, setSpec] = useState(null)
  const [authoring, setAuthoring] = useState(false)
  const [running, setRunning] = useState(false)
  const [injecting, setInjecting] = useState(false)
  const [result, setResult] = useState(null)
  const [mode, setMode] = useState('outcome')          // 'outcome' | 'train'
  const [err, setErr] = useState(null)

  useEffect(() => {
    api.twinScenarios(domain).then(r => setScenarios(r.scenarios || [])).catch(() => {})
    api.twinFaults(domain).then(r => setFaults(r.faults || [])).catch(() => {})
    setSpec(null); setResult(null); setDesc('')
  }, [domain])

  const switchTab = (t) => { setTab(t); setSpec(null); setResult(null); setDesc(''); setErr(null) }

  async function author() {
    if (!desc.trim()) return
    setAuthoring(true); setErr(null); setResult(null)
    try {
      const r = await api.simAuthor({ tenant, machine: machineName, domain, kind: tab, description: desc, horizon_label: horizon })
      setSpec(r.spec)
    } catch (e) { setErr(String(e.message || e)) }
    setAuthoring(false)
  }
  function pickScenario(s) { setDesc(s.description); setSpec(null); setResult(null) }
  function pickFault(f) {
    setSpec({ title: f.label, fault: f.id, severity: 0.85, control: 0.85, horizon_min: HMIN[horizon] || 120,
      rationale: 'Default fault preset for this machine.', expected_outcome: '' })
    setResult(null); setDesc('')
  }
  async function simulate() {
    if (!spec) return
    setRunning(true); setErr(null); setResult(null)
    try {
      if (isLive) {
        const r = await api.simRun({ tenant, machine: machineName, domain, fault: spec.fault, severity: spec.severity,
          control: spec.control, horizon_min: spec.horizon_min, title: spec.title })
        setResult({ ...r, sim: false })
      } else {
        // simulated twin: frontend trajectory + AI outcome (no physics engine)
        const fault = spec.fault === 'none' ? null : spec.fault
        const traj = simTrajectory(domain, spec.horizon_min, 60, fault, spec.severity ?? 1)
        const last = traj[traj.length - 1]
        const severity = last.health < 0.4 ? 'critical' : last.health < 0.7 ? 'warning' : 'nominal'
        const context = `Assume this situation is in effect: ${spec.title}. ${spec.rationale || ''} Severity ~${Math.round((spec.severity || 0) * 100)}%.`
        let narrative = null
        try { const f = await api.forecastSnapshot({ machine: machineName, domain, latest: last, horizon_label: `${Math.round(spec.horizon_min)} min`, context }); narrative = f?.report } catch {}
        setResult({ projection: { trajectory: traj, severity, rul: [], events: [] }, narrative, sim: true, atRisk: signalsAtRisk(domain, last) })
      }
    } catch (e) { setErr(String(e.message || e)) }
    setRunning(false)
  }
  async function injectLive() {
    if (!spec || spec.fault === 'none') return
    setInjecting(true); setErr(null)
    try {
      if (isLive) await api.step({ tenant, fault: spec.fault, severity: spec.severity || 0.9 })
      else if (setSimFault) setSimFault(spec.fault)   // bias the running simulated twin
    } catch (e) { setErr(String(e.message || e)) }
    setInjecting(false)
  }

  const p = result?.projection
  const traj = p?.trajectory || []
  const rul = p?.rul || []
  const events = p?.events || []
  const sev = p?.severity
  const charts = predictCharts(domain)
  const isFault = tab === 'fault'

  return (
    <div className="panel">
      <div className="panel-header">
        <div>
          <div className="panel-title">Scenario & Fault Engine</div>
          <div className="panel-subtitle">Describe a situation or a fault and the agent authors a runnable spec for {machineName}, then simulates it forward on the live physics — without touching the running twin.</div>
        </div>
      </div>

      {/* tabs */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        <button className={`btn ${tab === 'scenario' ? 'btn-primary' : ''}`} onClick={() => switchTab('scenario')}>
          <Icon n="ti-cloud-storm" /> Scenarios <span className="hint" style={{ marginLeft: 4 }}>external factors</span>
        </button>
        <button className={`btn ${tab === 'fault' ? 'btn-primary' : ''}`} onClick={() => switchTab('fault')}>
          <Icon n="ti-alert-triangle" /> Faults <span className="hint" style={{ marginLeft: 4 }}>degraded components</span>
        </button>
      </div>

      {err && <div className="card" style={{ borderColor: 'rgba(225,29,72,.4)', color: 'var(--accent-red)', marginBottom: 16 }}>{err}</div>}

      <div className="grid-2">
        {/* ── Builder ── */}
        <div className="card" style={{ alignSelf: 'start' }}>
          <div className="card-title"><Icon n="ti-sparkles" /> Author with agent <span className="pill pill-purple">Claude</span></div>
          <textarea className="input" rows={3} value={desc} onChange={e => setDesc(e.target.value)}
            placeholder={isFault
              ? "Describe a fault… e.g. 'the flushing pump is failing and debris is building up in the kerf'"
              : "Describe a situation… e.g. 'a summer heatwave pushes the shop to 40°C during a long production run'"} />
          <div className="row" style={{ marginTop: 8, gap: 8, alignItems: 'center' }}>
            <select className="select" style={{ width: 'auto', padding: '7px 9px' }} value={horizon} onChange={e => setHorizon(e.target.value)}>
              {HORIZONS.map(h => <option key={h} value={h}>{h}</option>)}
            </select>
            <button className="btn btn-teal" onClick={author} disabled={authoring || !desc.trim()}>
              {authoring ? <><span className="spinner" /> Authoring…</> : <><Icon n="ti-wand" /> Author spec</>}
            </button>
          </div>

          <div className="card-label" style={{ marginTop: 16 }}>{isFault ? 'Or pick a known fault' : 'Or start from a preset'}</div>
          <div style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 7 }}>
            {isFault
              ? faults.map(f => <button key={f.id} className="btn" style={{ fontSize: 11 }} onClick={() => pickFault(f)}>⚠ {f.label}</button>)
              : scenarios.map((s, i) => <button key={i} className="btn" style={{ fontSize: 11 }} onClick={() => pickScenario(s)}>{s.title}</button>)}
          </div>

          {/* authored / selected spec */}
          {spec && (
            <div className="card section-gap" style={{ background: 'var(--surface2)', marginTop: 16 }}>
              <div style={{ fontWeight: 600, marginBottom: 8 }}>{spec.title}</div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, fontSize: 12 }}>
                <div><span className="hint">Effect:</span> <b>{spec.fault === 'none' ? 'operating condition' : spec.fault}</b></div>
                <div><span className="hint">Severity:</span> {Math.round((spec.severity ?? 0) * 100)}%</div>
                <div><span className="hint">Load:</span> {Math.round((spec.control ?? 0) * 100)}%</div>
                <div><span className="hint">Horizon:</span> {spec.horizon_min} min</div>
              </div>
              {spec.rationale && <div style={{ fontSize: 11.5, color: 'var(--muted)', marginTop: 8 }}>{spec.rationale}</div>}
              {spec.expected_outcome && <div style={{ fontSize: 11.5, marginTop: 6 }}><span className="hint">Expected:</span> {spec.expected_outcome}</div>}
              <div className="row" style={{ marginTop: 12, gap: 8 }}>
                <button className="btn btn-primary" onClick={() => { setMode('outcome'); simulate() }} disabled={running} style={{ flex: 1, justifyContent: 'center' }}>
                  {running ? <><span className="spinner" /> Simulating…</> : <><Icon n="ti-chart-line" /> Outcome</>}
                </button>
                {spec.fault && spec.fault !== 'none' && (
                  <button className="btn btn-teal" onClick={() => setMode('train')} style={{ flex: 1, justifyContent: 'center' }}>
                    <Icon n="ti-school" /> Train
                  </button>
                )}
              </div>
              {isFault && spec.fault !== 'none' && (
                <button className="btn btn-danger" onClick={injectLive} disabled={injecting} style={{ width: '100%', marginTop: 8, justifyContent: 'center' }} title="Apply this fault to the running twin">
                  {injecting ? <><span className="spinner" /> Injecting…</> : <><Icon n="ti-bolt" /> Inject into live twin</>}
                </button>
              )}
            </div>
          )}
        </div>

        {/* ── Results ── */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {!result ? (
            <div className="card"><div className="empty" style={{ padding: '50px 20px' }}>
              <Icon n="ti-chart-line" /><div style={{ marginTop: 8 }}>Author or pick a {isFault ? 'fault' : 'scenario'}, then Simulate to project it forward.</div></div></div>
          ) : (
            <>
              <div className="card">
                <div className="card-title"><Icon n="ti-chart-line" /> Projected behaviour
                  <span className={`pill ${sev === 'critical' ? 'pill-red' : sev === 'warning' ? 'pill-amber' : 'pill-green'}`}>{sev || 'nominal'}</span></div>
                {charts.map((c, i) => (
                  <div key={i} style={{ marginTop: i ? 14 : 4 }}>
                    <div className="card-label" style={{ marginBottom: 4 }}>{c.title}</div>
                    <Chart data={traj} height={c.series.length > 2 ? 150 : 130} redline={c.redline} series={c.series} />
                  </div>
                ))}
              </div>

              {result.sim ? (
                <div className="card">
                  <div className="card-title"><Icon n="ti-alert-triangle" /> Signals projected out of band</div>
                  {(result.atRisk || []).length === 0 ? <div className="empty">All signals stay within limits across this horizon.</div>
                    : (result.atRisk || []).map((r, i) => (
                      <div key={i} className="row" style={{ justifyContent: 'space-between', padding: '7px 0', borderBottom: '1px solid var(--border)' }}>
                        <span style={{ fontSize: 12.5 }}>{r.meta?.label || r.key}</span>
                        <span className="mono" style={{ fontSize: 12, color: r.sev === 'crit' ? 'var(--accent-red)' : 'var(--accent-amber)' }}>
                          {fmt(r.value)}{r.meta?.unit ? ' ' + r.meta.unit : ''} · {r.sev === 'crit' ? 'critical' : 'warning'}</span>
                      </div>))}
                </div>
              ) : (
                <>
                  <div className="card">
                    <div className="card-title"><Icon n="ti-clock-bolt" /> Time-to-limit (RUL)</div>
                    {rul.map((r, i) => (
                      <div key={i} className="row" style={{ justifyContent: 'space-between', padding: '7px 0', borderBottom: '1px solid var(--border)' }}>
                        <span style={{ fontSize: 12.5 }}>{r.mode}</span>
                        <span className="mono" style={{ fontSize: 12, color: r.within_horizon ? 'var(--accent-red)' : 'var(--accent-green)' }}>
                          {r.within_horizon ? `~${Math.round(r.time_to_limit_min)} min` : 'beyond horizon'}</span>
                      </div>
                    ))}
                  </div>
                  <div className="card">
                    <div className="card-title"><Icon n="ti-timeline" /> Predicted detection timeline</div>
                    {events.length === 0 ? <div className="empty">No detections within this horizon.</div>
                      : events.map((e, i) => (
                        <div key={i} className="row" style={{ alignItems: 'flex-start', gap: 10, padding: '7px 0', borderBottom: '1px solid var(--border)' }}>
                          <span className="mono" style={{ color: 'var(--hint)', minWidth: 48 }}>t+{Math.round(e.t_min)}m</span>
                          <span className={`pill ${e.severity === 'critical' ? 'pill-red' : 'pill-amber'}`} style={{ flexShrink: 0 }}>{e.severity}</span>
                          <span style={{ fontSize: 12 }}>{e.message || e.behavior_id}</span>
                        </div>))}
                  </div>
                </>
              )}

              {result.narrative && (
                <div className="card">
                  <div className="card-title"><Icon n="ti-message-chatbot" /> Agent analysis & precautions <span className="pill pill-purple">Claude</span></div>
                  <Markdown text={result.narrative} />
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* Interactive maintenance trainer (full width) */}
      {mode === 'train' && spec && spec.fault && spec.fault !== 'none' && (
        <div className="section-gap" style={{ marginTop: 16 }}>
          <Trainer machine={machineName} domain={domain} fault={spec.fault} title={spec.title}
            context={[spec.rationale, spec.expected_outcome].filter(Boolean).join(' ')} />
        </div>
      )}
    </div>
  )
}
