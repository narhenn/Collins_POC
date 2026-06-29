import React, { useEffect, useState } from 'react'
import api from './api'
import Chart from './Chart.jsx'
import { Icon, pct, hColor, statusColor, fmt } from './lib.jsx'

function HealthBar({ name, type, health, status }) {
  return (
    <div style={{ marginBottom: 10 }}>
      <div className="row" style={{ justifyContent: 'space-between', marginBottom: 4 }}>
        <span style={{ fontSize: 12.5 }}>{name}{type === 'subsystem' && <span className="hint" style={{ fontSize: 10 }}> · subsystem</span>}</span>
        <span className="mono" style={{ fontSize: 11.5, color: hColor(health) }}>{pct(health)} · {status}</span>
      </div>
      <div className="bar-track"><div className="bar-fill" style={{ width: pct(health), background: hColor(health) }} /></div>
    </div>
  )
}

export default function Intelligence({ tenant, machineName }) {
  const [horizons, setHorizons] = useState([])
  const [horizon, setHorizon] = useState('2 hours')
  const [diag, setDiag] = useState(null)
  const [analysis, setAnalysis] = useState(null)
  const [busy, setBusy] = useState(null)
  const [err, setErr] = useState(null)

  useEffect(() => { api.horizons().then(d => setHorizons(d.horizons || [])).catch(() => {}) }, [])

  async function runDiag() {
    setBusy('diag'); setErr(null)
    try { setDiag(await api.runDiagnosis({ tenant, machine: machineName })) }   // string, not object
    catch (e) { setErr(String(e.message || e)) }
    setBusy(null)
  }
  async function runAnalysis() {
    setBusy('analysis'); setErr(null)
    try { setAnalysis(await api.runAnalysis({ tenant, machine: machineName, horizon_label: horizon })) }
    catch (e) { setErr(String(e.message || e)) }
    setBusy(null)
  }

  const d = diag?.diagnostics
  const a = analysis, pred = a?.prediction, rul = pred?.rul || []

  return (
    <div className="panel">
      <div className="panel-header">
        <div><div className="panel-title">Twin Intelligence</div>
          <div className="panel-subtitle">On-demand agents over {machineName}: a present-state diagnosis and a predictive analysis (present + future).</div></div>
      </div>

      {/* Agent launchers */}
      <div className="grid-2 section-gap">
        <div className="agent-row">
          <div className="agent-icon"><Icon n="ti-stethoscope" /></div>
          <div style={{ flex: 1 }}><div className="agent-name">Diagnosis Agent</div>
            <div className="agent-desc">Detailed per-component & per-sensor health report of the live twin.</div></div>
          <button className="btn btn-primary" onClick={runDiag} disabled={busy}>
            {busy === 'diag' ? <><span className="spinner" />&nbsp; Running…</> : 'Run Diagnosis'}</button>
        </div>
        <div className="agent-row">
          <div className="agent-icon"><Icon n="ti-trending-up" /></div>
          <div style={{ flex: 1 }}><div className="agent-name">Analysis Agent + Prediction</div>
            <div className="agent-desc">Present state plus a forecast over the chosen horizon.</div>
            <div className="row" style={{ marginTop: 6 }}>
              <select className="select" style={{ width: 'auto', padding: '6px 9px' }} value={horizon} onChange={e => setHorizon(e.target.value)}>
                {horizons.map(h => <option key={h.label} value={h.label}>{h.label}</option>)}
              </select>
            </div>
          </div>
          <button className="btn btn-teal" onClick={runAnalysis} disabled={busy}>
            {busy === 'analysis' ? <><span className="spinner" />&nbsp; Running…</> : 'Run Analysis'}</button>
        </div>
      </div>
      {err && <div className="card" style={{ borderColor: 'rgba(225,29,72,.4)', color: 'var(--accent-red)', marginBottom: 16 }}>{err}</div>}

      {/* Diagnosis */}
      {d && (
        <div className="card section-gap">
          <div className="card-title"><Icon n="ti-stethoscope" /> Diagnosis Report
            <span className={`pill ${d.overall_health >= 0.6 ? 'pill-green' : d.overall_health >= 0.4 ? 'pill-amber' : 'pill-red'}`}>overall {pct(d.overall_health)}</span></div>
          <div className="grid-2">
            <div>
              <div className="card-label">Component Health</div>
              <div style={{ marginTop: 8 }}>{(d.components || []).map((c, i) => <HealthBar key={i} {...c} />)}</div>
            </div>
            <div>
              <div className="card-label">Sensors</div>
              <table className="tbl" style={{ marginTop: 8 }}><tbody>
                {(d.sensors || []).map((s, i) => (
                  <tr key={i}><td style={{ color: 'var(--muted)' }}>{s.name}</td>
                    <td className="mono" style={{ textAlign: 'right' }}>{fmt(s.value)}</td>
                    <td style={{ textAlign: 'right', width: 70 }}><span style={{ color: statusColor(s.status), fontWeight: 600 }}>{s.status}</span></td></tr>
                ))}
              </tbody></table>
            </div>
          </div>
          <div className="analysis" style={{ marginTop: 14, borderLeftColor: 'var(--accent-blue)' }}>{diag.report}</div>
        </div>
      )}

      {/* Analysis (present + future) */}
      {a && (
        <div className="card">
          <div className="card-title"><Icon n="ti-trending-up" /> Predictive Analysis — next {a.horizon_label}
            <span className={`pill ${pred?.severity === 'critical' ? 'pill-red' : pred?.severity === 'warning' ? 'pill-amber' : 'pill-green'}`}>{pred?.severity}</span></div>
          <div className="grid-2">
            <div>
              <Chart data={pred?.trajectory || []} height={170} redline={780}
                series={[{ key: 'egt', label: 'EGT forecast', color: '#e11d48' }]} />
              <div style={{ marginTop: 10 }}>
                <Chart data={pred?.trajectory || []} height={150} series={[
                  { key: 'health', label: 'Overall', color: '#0d9488' },
                  { key: 'turbine_h', label: 'Turbine', color: '#e11d48' },
                  { key: 'bearings_h', label: 'Bearings', color: '#d97706' },
                  { key: 'lubrication_h', label: 'Lubrication', color: '#2563eb' }]} />
              </div>
            </div>
            <div>
              <div className="card-label">Remaining Useful Life / Time-to-Limit</div>
              <div style={{ marginTop: 8 }}>
                {rul.map((r, i) => (
                  <div key={i} className="row" style={{ justifyContent: 'space-between', padding: '7px 0', borderBottom: '1px solid var(--border)' }}>
                    <span style={{ fontSize: 12.5 }}>{r.mode}</span>
                    <span className="mono" style={{ fontSize: 12, color: r.within_horizon ? 'var(--accent-red)' : 'var(--accent-green)' }}>
                      {r.within_horizon ? `~${Math.round(r.time_to_limit_min)} min` : `> ${a.horizon_label}`}</span>
                  </div>
                ))}
              </div>
              <div className="card-label" style={{ marginTop: 14 }}>Component health: now → +{a.horizon_label}</div>
              <div style={{ marginTop: 6 }}>
                {['compressor', 'turbine', 'bearings', 'lubrication'].map(k => {
                  const now = pred?.component_health_now?.[k]?.health, fut = pred?.component_health_horizon?.[k]?.health
                  return (
                    <div key={k} className="row" style={{ justifyContent: 'space-between', padding: '5px 0', fontSize: 12.5 }}>
                      <span style={{ textTransform: 'capitalize' }}>{k}</span>
                      <span className="mono"><span style={{ color: hColor(now) }}>{pct(now)}</span>
                        <span className="hint"> → </span><span style={{ color: hColor(fut) }}>{pct(fut)}</span></span>
                    </div>
                  )
                })}
              </div>
            </div>
          </div>
          <div className="analysis" style={{ marginTop: 14 }}>{a.report}</div>
        </div>
      )}
    </div>
  )
}
