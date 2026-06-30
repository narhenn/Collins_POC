import React, { useState } from 'react'
import api from './api'
import Markdown from './Markdown.jsx'
import { Icon, pct, hColor, statusColor, fmt, sevClass, SIG, domainMeta } from './lib.jsx'

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

// Build a diagnostics-shaped object from a simulated twin's snapshot.
function simDiagnostics(domain, twin) {
  const meta = domainMeta(domain)
  const latest = twin?.latest || {}
  const components = (meta.assets || []).map(([id, st]) => ({
    name: id, type: 'asset', status: st, health: st === 'crit' ? 0.3 : st === 'warn' ? 0.62 : 0.92,
  }))
  const sensors = (meta.all || []).map(k => ({ name: SIG[k]?.label || k, value: latest[k], status: sevClass(k, latest[k]) || 'ok' }))
  return { overall_health: twin?.health, components, sensors }
}

export default function Intelligence({ tenant, machineName, domain, isLive = true, twin }) {
  const [diag, setDiag] = useState(null)
  const [analysis, setAnalysis] = useState(null)
  const [busy, setBusy] = useState(null)
  const [err, setErr] = useState(null)

  async function runDiag() {
    setBusy('diag'); setErr(null)
    try {
      if (isLive) { setDiag(await api.runDiagnosis({ tenant, machine: machineName })) }
      else {
        const dg = simDiagnostics(domain, twin)
        const r = await api.diagnoseSnapshot({ machine: machineName, domain, latest: twin?.latest || {}, findings: twin?.findings || [], components: dg.components })
        setDiag({ report: r.report, diagnostics: dg })
      }
    } catch (e) { setErr(String(e.message || e)) }
    setBusy(null)
  }
  async function runAnalysis() {
    setBusy('analysis'); setErr(null)
    try {
      if (isLive) {
        const a = await api.runAnalysis({ tenant, machine: machineName, horizon_label: '6 hours' })
        setAnalysis({ report: a.report })
      } else {
        const r = await api.forecastSnapshot({ machine: machineName, domain, latest: twin?.latest || {}, horizon_label: '6 hours' })
        setAnalysis({ report: r.report })
      }
    } catch (e) { setErr(String(e.message || e)) }
    setBusy(null)
  }

  const d = diag?.diagnostics

  return (
    <div className="panel">
      <div className="panel-header">
        <div><div className="panel-title">Twin Intelligence</div>
          <div className="panel-subtitle">On-demand agents over {machineName}: a present-state diagnosis and an analysis of where it's heading. Graphs live in the Prediction tab.</div></div>
      </div>

      <div className="grid-2 section-gap">
        <div className="agent-row">
          <div className="agent-icon"><Icon n="ti-stethoscope" /></div>
          <div style={{ flex: 1 }}><div className="agent-name">Diagnosis Agent</div>
            <div className="agent-desc">Per-component & per-sensor health report from the live telemetry.</div></div>
          <button className="btn btn-primary" onClick={runDiag} disabled={busy}>
            {busy === 'diag' ? <><span className="spinner" />&nbsp; Running…</> : 'Run Diagnosis'}</button>
        </div>
        <div className="agent-row">
          <div className="agent-icon"><Icon n="ti-trending-up" /></div>
          <div style={{ flex: 1 }}><div className="agent-name">Analysis Agent</div>
            <div className="agent-desc">Where the machine is heading and what to pre-empt.</div></div>
          <button className="btn btn-teal" onClick={runAnalysis} disabled={busy}>
            {busy === 'analysis' ? <><span className="spinner" />&nbsp; Running…</> : 'Run Analysis'}</button>
        </div>
      </div>
      {err && <div className="card" style={{ borderColor: 'rgba(225,29,72,.4)', color: 'var(--accent-red)', marginBottom: 16 }}>{err}</div>}

      {d && (
        <div className="card section-gap">
          <div className="card-title"><Icon n="ti-stethoscope" /> Diagnosis Report
            <span className={`pill ${d.overall_health >= 0.6 ? 'pill-green' : d.overall_health >= 0.4 ? 'pill-amber' : 'pill-red'}`}>overall {pct(d.overall_health)}</span></div>
          <div className="grid-2">
            <div>
              <div className="card-label">{isLive ? 'Component Health' : 'Assets'}</div>
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
          <div style={{ marginTop: 14, borderLeft: '3px solid var(--accent-blue)', paddingLeft: 12 }}><Markdown text={diag.report} /></div>
        </div>
      )}

      {analysis && (
        <div className="card">
          <div className="card-title"><Icon n="ti-trending-up" /> Analysis <span className="pill pill-purple">Claude</span></div>
          <Markdown text={analysis.report} />
        </div>
      )}
    </div>
  )
}
