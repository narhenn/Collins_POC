import React, { useEffect, useState } from 'react'
import api from './api'
import Chart from './Chart.jsx'
import { Icon, fmt } from './lib.jsx'

const ICONS = { Thermal: 'ti-flame', Lubrication: 'ti-oil', Mechanical: 'ti-settings',
  Aerodynamic: 'ti-wind', Combustion: 'ti-flame', Instrumentation: 'ti-device-analytics',
  Authored: 'ti-sparkles' }

export default function Scenario({ tenant, machineName }) {
  const [lib, setLib] = useState([])
  const [selected, setSelected] = useState(null)
  const [prompt, setPrompt] = useState('')
  const [authoring, setAuthoring] = useState(false)
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState(null)
  const [err, setErr] = useState(null)

  useEffect(() => { api.scenarioLibrary().then(d => setLib(d.scenarios || [])).catch(() => {}) }, [])

  async function author() {
    if (!prompt.trim()) return
    setAuthoring(true); setErr(null)
    try {
      const r = await api.authorScenario({ prompt, machine: machineName, sensors: [] })
      setLib(l => [r.scenario, ...l]); setSelected(r.scenario.id); setPrompt('')
    } catch (e) { setErr(String(e.message || e)) }
    setAuthoring(false)
  }
  async function run() {
    if (!selected) return
    setRunning(true); setErr(null); setResult(null)
    try {
      setResult(await api.runScenario({ tenant, scenario_id: selected, machine: machineName, analyze: true }))
    } catch (e) { setErr(String(e.message || e)) }
    setRunning(false)
  }

  const o = result?.projection?.outcome
  const traj = result?.projection?.trajectory || []
  const events = result?.projection?.events || []
  const selScn = lib.find(s => s.id === selected)

  return (
    <div className="panel">
      <div className="panel-header">
        <div><div className="panel-title">Scenario Builder</div>
          <div className="panel-subtitle">Author what-if scenarios and simulate them forward from the live twin's present state — side by side with reality.</div></div>
      </div>
      {err && <div className="card" style={{ borderColor: 'rgba(225,29,72,.4)', color: 'var(--accent-red)', marginBottom: 16 }}>{err}</div>}

      <div className="grid-2">
        {/* Builder */}
        <div className="card" style={{ alignSelf: 'start' }}>
          <div className="card-title"><Icon n="ti-sparkles" /> Author with agent <span className="pill pill-purple">agent</span></div>
          <textarea className="input" rows={2} value={prompt} onChange={e => setPrompt(e.target.value)}
            placeholder="Describe a what-if… e.g. 'oil starts leaking at full throttle' or 'EGT sensor fails during a hot run'" />
          <div className="row" style={{ marginTop: 8 }}>
            <button className="btn btn-teal" onClick={author} disabled={authoring || !prompt.trim()}>
              {authoring ? <><span className="spinner" />&nbsp; Authoring…</> : <><Icon n="ti-wand" /> Author scenario</>}</button>
            <span className="hint">or pick a built scenario</span>
          </div>
          <div style={{ marginTop: 14, maxHeight: 380, overflowY: 'auto' }}>
            {lib.map(s => (
              <div key={s.id} className={`scn ${selected === s.id ? 'sel' : ''}`} onClick={() => setSelected(s.id)}>
                <div className="ic"><Icon n={ICONS[s.category] || 'ti-alert-triangle'} /></div>
                <div style={{ flex: 1 }}>
                  <div className="nm">{s.name} {s.authored && <span className="pill pill-purple">authored</span>}</div>
                  <div className="ds">{s.description}</div>
                </div>
              </div>
            ))}
          </div>
          <button className="btn btn-primary" onClick={run} disabled={running || !selected} style={{ width: '100%', marginTop: 12, justifyContent: 'center' }}>
            {running ? <><span className="spinner" />&nbsp; Simulating…</> : <><Icon n="ti-player-play" /> Run simulation{selScn ? ` — ${selScn.name}` : ''}</>}
          </button>
        </div>

        {/* Results */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {!result ? (
            <div className="card"><div className="empty" style={{ padding: '50px 20px' }}>
              <Icon n="ti-chart-line" /><div style={{ marginTop: 8 }}>Pick a scenario and run it to see the predicted outcome.</div></div></div>
          ) : (
            <>
              <div className="card">
                <div className="card-title"><Icon n="ti-flame" /> Projected EGT
                  <span className={`pill ${o?.severity === 'critical' ? 'pill-red' : o?.severity === 'warning' ? 'pill-amber' : 'pill-green'}`}>{o?.severity}</span></div>
                <Chart data={traj} redline={780} series={[
                  { key: 'egt', label: 'EGT (true)', color: '#e11d48' },
                  { key: 'egt_reported', label: 'EGT (reported)', color: '#2563eb' }]} />
                <div style={{ marginTop: 10 }}>
                  <Chart data={traj} height={140} series={[
                    { key: 'vib', label: 'Vibration (g)', color: '#d97706' },
                    { key: 'health', label: 'Health', color: '#0d9488' }]} />
                </div>
              </div>

              <div className="card">
                <div className="card-title"><Icon n="ti-report-medical" /> Predicted Outcome</div>
                <div className="kpis">
                  <div className="kpibox"><div className="l">Time to redline</div>
                    <div className="v" style={{ color: o?.time_to_redline_min != null ? 'var(--accent-red)' : 'var(--text)' }}>
                      {o?.time_to_redline_min != null ? `${o.time_to_redline_min} min` : '—'}</div></div>
                  <div className="kpibox"><div className="l">Peak EGT</div><div className="v">{fmt(o?.peak_egt)}°C</div></div>
                  <div className="kpibox"><div className="l">Peak vibration</div><div className="v">{fmt(o?.peak_vibration)} g</div></div>
                  <div className="kpibox"><div className="l">Min oil pressure</div><div className="v">{fmt(o?.min_oil_pressure)} PSI</div></div>
                </div>
                {o?.blind_spot && <div style={{ marginTop: 10, padding: '8px 11px', borderRadius: 10, fontSize: 11.5,
                  background: 'rgba(225,29,72,.06)', border: '1px solid rgba(225,29,72,.3)', color: 'var(--accent-red)' }}>
                  <Icon n="ti-eye-off" /> Blind spot — the EGT reading freezes while the engine truly overheats; only the physics residual catches it.</div>}
              </div>

              <div className="card">
                <div className="card-title"><Icon n="ti-timeline" /> Predicted Event Timeline</div>
                {events.length === 0 ? <div className="empty">No detections in this horizon.</div>
                  : events.map((e, i) => (
                    <div key={i} className="evt"><div className="t">{e.t_min}m</div>
                      <span className={`sev ${e.severity}`}>{e.severity}</span>
                      <div className="m">{e.message}</div></div>))}
              </div>

              {result.analysis && (
                <div className="card">
                  <div className="card-title"><Icon n="ti-message-chatbot" /> Agent Analysis & Precautions</div>
                  <div className="analysis">{result.analysis}</div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
