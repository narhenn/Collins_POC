import React, { useEffect, useState } from 'react'
import api from './api'
import Chart from './Chart.jsx'

const pct = (h) => (h == null ? '—' : `${Math.round(h * 100)}%`)
const hColor = (h) => (h == null ? 'var(--hint)' : h >= 0.8 ? 'var(--accent-green)'
  : h >= 0.6 ? 'var(--accent-teal)' : h >= 0.4 ? 'var(--accent-amber)' : 'var(--accent-red)')
const sColor = (s) => ({ ok: 'var(--accent-green)', warning: 'var(--accent-amber)',
  critical: 'var(--accent-red)' }[s] || 'var(--hint)')

function HealthBar({ name, type, health, status }) {
  return (
    <div style={{ marginBottom: 9 }}>
      <div className="row" style={{ justifyContent: 'space-between', marginBottom: 4 }}>
        <span style={{ fontSize: 12 }}>{name}
          {type === 'subsystem' && <span className="hint" style={{ fontSize: 10 }}> · subsystem</span>}</span>
        <span className="mono" style={{ fontSize: 11, color: hColor(health) }}>{pct(health)} · {status}</span>
      </div>
      <div style={{ height: 6, borderRadius: 4, background: 'var(--surface2)', overflow: 'hidden' }}>
        <div style={{ height: '100%', width: pct(health), background: hColor(health), transition: 'width .4s' }} />
      </div>
    </div>
  )
}

export default function Intelligence({ tenant, machine }) {
  const [horizons, setHorizons] = useState([])
  const [horizon, setHorizon] = useState('2 hours')
  const [diag, setDiag] = useState(null)
  const [analysis, setAnalysis] = useState(null)
  const [busy, setBusy] = useState(null)   // 'diag' | 'analysis'
  const [err, setErr] = useState(null)

  useEffect(() => { api.horizons().then(d => setHorizons(d.horizons || [])).catch(() => {}) }, [])

  async function runDiag() {
    setBusy('diag'); setErr(null)
    try { setDiag(await api.runDiagnosis({ tenant, machine })) }
    catch (e) { setErr(String(e.message || e)) }
    setBusy(null)
  }
  async function runAnalysis() {
    setBusy('analysis'); setErr(null)
    try { setAnalysis(await api.runAnalysis({ tenant, machine, horizon_label: horizon })) }
    catch (e) { setErr(String(e.message || e)) }
    setBusy(null)
  }

  const d = diag?.diagnostics
  const a = analysis
  const pred = a?.prediction
  const rul = pred?.rul || []

  return (
    <div className="card" style={{ marginTop: 16 }}>
      <div className="card-h">Twin Intelligence
        <span className="pill" style={{ background: 'rgba(139,109,240,.14)', color: 'var(--accent-purple)' }}>agents</span>
      </div>
      <div className="row" style={{ flexWrap: 'wrap', gap: 10 }}>
        <button className="btn primary" onClick={runDiag} disabled={!tenant || busy}>
          {busy === 'diag' ? <><span className="spinner" />&nbsp; Diagnosing…</> : '🩺 Run Diagnosis (now)'}
        </button>
        <div className="row" style={{ gap: 6 }}>
          <button className="btn teal" onClick={runAnalysis} disabled={!tenant || busy}>
            {busy === 'analysis' ? <><span className="spinner" />&nbsp; Analyzing…</> : '🔮 Run Analysis'}
          </button>
          <span className="hint">horizon</span>
          <select className="input" style={{ width: 'auto', padding: '7px 9px' }}
            value={horizon} onChange={e => setHorizon(e.target.value)}>
            {horizons.map(h => <option key={h.label} value={h.label}>{h.label}</option>)}
          </select>
        </div>
        {!tenant && <span className="hint">Build the twin first.</span>}
      </div>
      {err && <div style={{ marginTop: 10, color: 'var(--accent-red)', fontSize: 12 }}>{err}</div>}

      {/* Diagnosis report */}
      {d && (
        <div className="grid cols-2" style={{ marginTop: 14 }}>
          <div>
            <div className="card-h" style={{ fontSize: 12 }}>Component Health
              <span className={`pill ${d.overall_health >= 0.6 ? 'green' : d.overall_health >= 0.4 ? 'amber' : 'red'}`}>
                overall {pct(d.overall_health)}</span>
            </div>
            {(d.components || []).map((c, i) => <HealthBar key={i} {...c} />)}
          </div>
          <div>
            <div className="card-h" style={{ fontSize: 12 }}>Sensors</div>
            <table style={{ width: '100%', fontSize: 11.5, borderCollapse: 'collapse' }}>
              <tbody>
                {(d.sensors || []).map((s, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid var(--border)' }}>
                    <td style={{ padding: '5px 0', color: 'var(--muted)' }}>{s.name}</td>
                    <td className="mono" style={{ textAlign: 'right' }}>{s.value == null ? '—' : (Math.abs(s.value) >= 100 ? Math.round(s.value) : s.value.toFixed(2))}</td>
                    <td style={{ textAlign: 'right', width: 64 }}>
                      <span style={{ color: sColor(s.status), fontWeight: 600 }}>{s.status}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div style={{ gridColumn: '1 / -1' }}>
            <div className="analysis" style={{ borderLeftColor: 'var(--accent-blue)', whiteSpace: 'pre-wrap' }}>{diag.report}</div>
          </div>
        </div>
      )}

      {/* Analysis (present + future) */}
      {a && (
        <div style={{ marginTop: 16, borderTop: '1px solid var(--border)', paddingTop: 14 }}>
          <div className="card-h" style={{ fontSize: 12 }}>Predictive Analysis — next {a.horizon_label}
            <span className={`pill ${pred?.severity === 'critical' ? 'red' : pred?.severity === 'warning' ? 'amber' : 'green'}`}>{pred?.severity}</span>
          </div>
          <div className="grid cols-2">
            <div>
              <Chart data={pred?.trajectory || []} height={170} redline={780}
                series={[{ key: 'egt', label: 'EGT forecast', color: '#e2564e' }]} />
              <div style={{ marginTop: 10 }}>
                <Chart data={pred?.trajectory || []} height={150}
                  series={[
                    { key: 'health', label: 'Overall', color: '#18a999' },
                    { key: 'turbine_h', label: 'Turbine', color: '#e2564e' },
                    { key: 'bearings_h', label: 'Bearings', color: '#e0962f' },
                    { key: 'lubrication_h', label: 'Lubrication', color: '#4b8bf5' },
                  ]} />
              </div>
            </div>
            <div>
              <div className="card-h" style={{ fontSize: 12 }}>Remaining Useful Life / Time-to-Limit</div>
              {rul.map((r, i) => (
                <div key={i} className="row" style={{ justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid var(--border)' }}>
                  <span style={{ fontSize: 12 }}>{r.mode}</span>
                  <span className="mono" style={{ fontSize: 12, color: r.within_horizon ? 'var(--accent-red)' : 'var(--accent-green)' }}>
                    {r.within_horizon ? `~${Math.round(r.time_to_limit_min)} min` : `> ${a.horizon_label}`}
                  </span>
                </div>
              ))}
              <div className="card-h" style={{ fontSize: 12, marginTop: 12 }}>Component health: now → +{a.horizon_label}</div>
              {['compressor', 'turbine', 'bearings', 'lubrication'].map(k => {
                const now = pred?.component_health_now?.[k]?.health
                const fut = pred?.component_health_horizon?.[k]?.health
                return (
                  <div key={k} className="row" style={{ justifyContent: 'space-between', padding: '4px 0', fontSize: 12 }}>
                    <span style={{ textTransform: 'capitalize' }}>{k}</span>
                    <span className="mono">
                      <span style={{ color: hColor(now) }}>{pct(now)}</span>
                      <span className="hint"> → </span>
                      <span style={{ color: hColor(fut) }}>{pct(fut)}</span>
                    </span>
                  </div>
                )
              })}
            </div>
          </div>
          <div className="analysis" style={{ marginTop: 12, whiteSpace: 'pre-wrap' }}>{a.report}</div>
        </div>
      )}
    </div>
  )
}
