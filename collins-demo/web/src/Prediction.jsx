import React, { useEffect, useState, useCallback } from 'react'
import api from './api'
import Chart from './Chart.jsx'
import { Icon, pct, hColor, predictCharts, subsysFor, SUBSYS, simTrajectory, signalsAtRisk, fmt } from './lib.jsx'

const HORIZONS = ['1 hour', '2 hours', '6 hours', '24 hours', '3 days', '1 week', '2 weeks']
const HMIN = { '1 hour': 60, '2 hours': 120, '6 hours': 360, '24 hours': 1440, '3 days': 4320, '1 week': 10080, '2 weeks': 20160 }

export default function Prediction({ tenant, machineName, domain, isLive = true }) {
  const [horizon, setHorizon] = useState('6 hours')
  const [proj, setProj] = useState(null)
  const [narrative, setNarrative] = useState(null)
  const [loading, setLoading] = useState(false)
  const [explaining, setExplaining] = useState(false)
  const [err, setErr] = useState(null)
  const charts = predictCharts(domain)
  const hasSubsys = !!SUBSYS[domain]
  const subs = subsysFor(domain)

  const runForecast = useCallback(async () => {
    setLoading(true); setErr(null); setNarrative(null)
    try {
      if (isLive) {
        const r = await api.simRun({ tenant, machine: machineName, domain, fault: null, control: null, horizon_min: HMIN[horizon] || 360, analyze: false })
        setProj(r.projection)
      } else {
        const traj = simTrajectory(domain, HMIN[horizon] || 360, 60, null, 0)
        const last = traj[traj.length - 1]
        setProj({ trajectory: traj, severity: last.health < 0.4 ? 'critical' : last.health < 0.7 ? 'warning' : 'nominal', rul: [], atRisk: signalsAtRisk(domain, last), sim: true })
      }
    } catch (e) { setErr(String(e.message || e)) }
    setLoading(false)
  }, [tenant, machineName, domain, horizon, isLive])
  useEffect(() => { runForecast() }, [runForecast])

  async function explain() {
    setExplaining(true); setErr(null)
    try {
      if (isLive) {
        const r = await api.simRun({ tenant, machine: machineName, domain, fault: null, control: null, horizon_min: HMIN[horizon] || 360, analyze: true })
        setNarrative(r.narrative)
      } else {
        const last = (proj?.trajectory || []).slice(-1)[0] || {}
        const r = await api.forecastSnapshot({ machine: machineName, domain, latest: last, horizon_label: horizon })
        setNarrative(r?.report)
      }
    } catch (e) { setErr(String(e.message || e)) }
    setExplaining(false)
  }

  const traj = proj?.trajectory || []
  const rul = proj?.rul || []
  const atRisk = proj?.atRisk || []
  const chn = proj?.component_health_now || {}
  const chh = proj?.component_health_horizon || {}
  const sev = proj?.severity

  return (
    <div className="panel">
      <div className="panel-header">
        <div>
          <div className="panel-title">Prediction</div>
          <div className="panel-subtitle">Forecast of {machineName} — where each signal and subsystem is heading over the next hours to weeks.</div>
        </div>
        <div className="panel-actions">
          <span className="hint" style={{ alignSelf: 'center' }}>Horizon:</span>
          <select className="select" style={{ width: 'auto', padding: '7px 10px' }} value={horizon} onChange={e => setHorizon(e.target.value)}>
            {HORIZONS.map(h => <option key={h} value={h}>{h}</option>)}
          </select>
          <button className="btn" onClick={runForecast} disabled={loading}>
            {loading ? <><span className="spinner" /> Forecasting…</> : <><Icon n="ti-refresh" /> Refresh</>}
          </button>
          {sev && <span className={`pill ${sev === 'critical' ? 'pill-red' : sev === 'warning' ? 'pill-amber' : 'pill-green'}`} style={{ alignSelf: 'center' }}>{sev}</span>}
        </div>
      </div>

      {err && <div className="card" style={{ borderColor: 'rgba(225,29,72,.4)', color: 'var(--accent-red)', marginBottom: 16 }}>{err}</div>}

      <div className="grid-2 section-gap">
        {charts.map((c, i) => (
          <div key={i} className="card">
            <div className="card-title" style={{ fontSize: 13 }}><Icon n="ti-chart-line" /> {c.title}</div>
            <Chart data={traj} height={160} redline={c.redline} series={c.series} />
          </div>
        ))}
      </div>

      <div className="grid-2">
        {hasSubsys ? (
          <div className="card">
            <div className="card-title"><Icon n="ti-heartbeat" /> Subsystem health · now → +{horizon}</div>
            {subs.map(s => {
              const now = chn?.[s.key]?.health, fut = chh?.[s.key]?.health
              return (
                <div key={s.key} style={{ marginBottom: 12 }}>
                  <div className="row" style={{ justifyContent: 'space-between', marginBottom: 4, fontSize: 12.5 }}>
                    <span>{s.label}</span>
                    <span className="mono" style={{ fontSize: 11.5 }}>
                      <span style={{ color: hColor(now) }}>{pct(now)}</span>
                      <span className="hint"> → </span><span style={{ color: hColor(fut) }}>{pct(fut)}</span>
                    </span>
                  </div>
                  <div className="bar-track"><div className="bar-fill" style={{ width: pct(fut), background: hColor(fut) }} /></div>
                </div>
              )
            })}
          </div>
        ) : (
          <div className="card">
            <div className="card-title"><Icon n="ti-alert-triangle" /> Signals projected out of band · +{horizon}</div>
            {atRisk.length === 0 ? <div className="empty">All signals stay within limits across this horizon.</div>
              : atRisk.map((r, i) => (
                <div key={i} className="row" style={{ justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid var(--border)' }}>
                  <span style={{ fontSize: 12.5 }}>{r.meta?.label || r.key}</span>
                  <span className="mono" style={{ fontSize: 12, color: r.sev === 'crit' ? 'var(--accent-red)' : 'var(--accent-amber)' }}>
                    {fmt(r.value)}{r.meta?.unit ? ' ' + r.meta.unit : ''} · {r.sev === 'crit' ? 'critical' : 'warning'}</span>
                </div>))}
          </div>
        )}

        <div className="card">
          <div className="card-title"><Icon n="ti-clock-bolt" /> {isLive ? 'Time-to-limit (RUL)' : 'Forecast'}</div>
          {isLive
            ? (rul.length === 0 ? <div className="empty">No forecast yet.</div>
              : rul.map((r, i) => (
                <div key={i} className="row" style={{ justifyContent: 'space-between', padding: '9px 0', borderBottom: '1px solid var(--border)' }}>
                  <span style={{ fontSize: 12.5 }}>{r.mode}</span>
                  <span className="mono" style={{ fontSize: 12, color: r.within_horizon ? 'var(--accent-red)' : 'var(--accent-green)' }}>
                    {r.within_horizon ? `~${Math.round(r.time_to_limit_min)} min` : `> ${horizon}`}</span>
                </div>)))
            : <div className="empty" style={{ padding: '20px' }}>Run the AI forecast for a narrative outlook over the next {horizon}.</div>}
          <button className="btn btn-primary" onClick={explain} disabled={explaining} style={{ width: '100%', marginTop: 14, justifyContent: 'center' }}>
            {explaining ? <><span className="spinner" /> Analysing…</> : <><Icon n="ti-message-chatbot" /> Explain forecast with AI</>}
          </button>
        </div>
      </div>

      {narrative && (
        <div className="card section-gap">
          <div className="card-title"><Icon n="ti-message-chatbot" /> AI forecast summary <span className="pill pill-purple">Claude</span></div>
          <div style={{ fontSize: 13, lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>{narrative}</div>
        </div>
      )}
    </div>
  )
}
