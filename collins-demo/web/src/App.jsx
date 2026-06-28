import React, { useEffect, useState, useCallback, useRef } from 'react'
import api from './api'
import Chart from './Chart.jsx'
import Intelligence from './Intelligence.jsx'

// Signal display metadata + redlines (mirror turbine/physics.py).
const SIG = {
  'aero:exhaustGasTemp': { label: 'EGT', unit: '°C', warn: 700, crit: 780 },
  'aero:shaftSpeedN1': { label: 'N1', unit: 'RPM', warn: 5450, crit: 5500 },
  'aero:shaftSpeedN2': { label: 'N2', unit: 'RPM', warn: 10700, crit: 10800 },
  'aero:fuelFlow': { label: 'Fuel', unit: 'kg/h' },
  'aero:vibrationG': { label: 'Vibration', unit: 'g', warn: 1.5, crit: 2.0 },
  'aero:oilTemperature': { label: 'Oil Temp', unit: '°C', warn: 80, crit: 85 },
  'aero:oilPressure': { label: 'Oil Press', unit: 'PSI', warnLow: 45, critLow: 40 },
  'aero:enginePressureRatio': { label: 'EPR', unit: '' },
}
const TILE_ORDER = ['aero:exhaustGasTemp', 'aero:shaftSpeedN1', 'aero:vibrationG',
  'aero:oilTemperature', 'aero:oilPressure', 'aero:fuelFlow', 'aero:shaftSpeedN2',
  'aero:enginePressureRatio']
const ICONS = { Thermal: '🔥', Lubrication: '🛢️', Mechanical: '⚙️', Aerodynamic: '🌀',
  Combustion: '⛽', Instrumentation: '📟', Authored: '✨' }

function sevClass(sig, v) {
  const m = SIG[sig]; if (!m || v == null) return ''
  if (m.crit != null && v >= m.crit) return 'crit'
  if (m.critLow != null && v <= m.critLow) return 'crit'
  if (m.warn != null && v >= m.warn) return 'warn'
  if (m.warnLow != null && v <= m.warnLow) return 'warn'
  return ''
}
const fmt = (v) => (v == null ? '—' : (Math.abs(v) >= 100 ? Math.round(v) : v.toFixed(Math.abs(v) < 10 ? 2 : 1)))

export default function App() {
  const [health, setHealth] = useState(null)
  const [tenant, setTenant] = useState(null)
  const [machine, setMachine] = useState(null)
  const [twin, setTwin] = useState(null)        // live turbine state
  const [building, setBuilding] = useState(false)
  const [running, setRunning] = useState(false)
  const [authoring, setAuthoring] = useState(false)

  const [lib, setLib] = useState([])
  const [selected, setSelected] = useState(null)
  const [prompt, setPrompt] = useState('')
  const [result, setResult] = useState(null)      // projection result
  const [err, setErr] = useState(null)
  const pollRef = useRef(null)

  // ── boot ──
  useEffect(() => {
    api.health().then(setHealth).catch(() => {})
    api.scenarioLibrary().then(d => setLib(d.scenarios || [])).catch(() => {})
  }, [])

  // ── poll live twin ──
  const poll = useCallback(async (tid) => {
    try { setTwin(await api.twinState(tid)) } catch { /* not ready */ }
  }, [])
  useEffect(() => {
    if (!tenant) return
    poll(tenant)
    pollRef.current = setInterval(() => poll(tenant), 2000)
    return () => clearInterval(pollRef.current)
  }, [tenant, poll])

  async function buildTwin() {
    setBuilding(true); setErr(null)
    try {
      const r = await api.build({ description: 'Gas turbine engine on MRO test rig', start_feed: false })
      setTenant(r.tenant); setMachine(r.machine)
      // prime the real-time twin with a few healthy steps
      for (let i = 0; i < 3; i++) await api.step({ tenant: r.tenant, throttle: 0.9 })
      poll(r.tenant)
    } catch (e) { setErr(String(e.message || e)) }
    setBuilding(false)
  }

  async function stepLive(throttle) {
    if (!tenant) return
    for (let i = 0; i < 2; i++) await api.step({ tenant, throttle })
    poll(tenant)
  }

  async function authored() {
    if (!prompt.trim()) return
    setAuthoring(true); setErr(null)
    try {
      const r = await api.authorScenario({ prompt, machine: machine?.name || 'Turbine Engine',
        sensors: Object.keys(SIG) })
      setLib(l => [r.scenario, ...l])
      setSelected(r.scenario.id)
      setPrompt('')
    } catch (e) { setErr(String(e.message || e)) }
    setAuthoring(false)
  }

  async function run() {
    if (!tenant || !selected) return
    setRunning(true); setErr(null); setResult(null)
    try {
      setResult(await api.runScenario({ tenant, scenario_id: selected,
        machine: machine?.name || 'Turbine Engine', analyze: true }))
    } catch (e) { setErr(String(e.message || e)) }
    setRunning(false)
  }

  const live = twin?.latest || {}
  const liveHealth = twin?.health
  const claudeOn = health?.claude?.enabled
  const o = result?.projection?.outcome
  const traj = result?.projection?.trajectory || []
  const events = result?.projection?.events || []
  const selScn = lib.find(s => s.id === selected)

  return (
    <div className="app">
      {/* Topbar */}
      <div className="topbar">
        <div className="logo">NEXT<span>XR</span></div>
        <div className="crumb">Collins MRO · <b>Scenario Builder</b></div>
        <div className="spacer" />
        <div className="topstat"><span className={`dot ${claudeOn ? 'blue' : ''}`} />
          Agent: <b>{claudeOn ? (health?.claude?.model || 'Claude') : 'stub'}</b></div>
        <div className="topstat">
          <span className={`dot ${liveHealth == null ? '' : liveHealth > 0.7 ? 'green' : liveHealth > 0.4 ? 'amber' : 'red'}`} />
          Twin Health: <b>{liveHealth == null ? '—' : `${Math.round(liveHealth * 100)}%`}</b>
        </div>
      </div>

      <div className="content">
        {err && <div className="card" style={{ borderColor: 'rgba(226,86,78,.4)', color: 'var(--accent-red)', marginBottom: 16 }}>{err}</div>}

        <div className="grid cols-2">
          {/* LEFT: 3D + live twin */}
          <div className="grid" style={{ gridTemplateColumns: '1fr', alignContent: 'start' }}>
            <div className="card">
              <div className="card-h">Live Digital Twin
                <span className="pill teal">real-time</span>
              </div>
              {/* 3D layer goes here (next step) */}
              <div className="viz">
                <div className="viz-label">
                  <div className="big">⬡ 3D Turbine Visualization</div>
                  <div>Reserved for the 3D model + sensor hotspots (next step).</div>
                  {machine && <div style={{ marginTop: 6 }} className="mono hint">{machine.name}</div>}
                </div>
              </div>

              {!tenant ? (
                <div className="row" style={{ marginTop: 14, justifyContent: 'center' }}>
                  <button className="btn primary" onClick={buildTwin} disabled={building}>
                    {building ? <><span className="spinner" /> &nbsp;Building twin…</> : 'Build Turbine Twin'}
                  </button>
                </div>
              ) : (
                <>
                  <div className="sensors">
                    {TILE_ORDER.filter(s => live[s] != null).map(s => (
                      <div key={s} className={`sensor ${sevClass(s, live[s])}`}>
                        <span className="live-dot" />
                        <div className="lbl">{SIG[s].label}</div>
                        <div className="val">{fmt(live[s])}<span className="u">{SIG[s].unit}</span></div>
                      </div>
                    ))}
                  </div>
                  <div className="row" style={{ marginTop: 12 }}>
                    <span className="hint">Drive the live engine (3D stand-in):</span>
                    <button className="btn" onClick={() => stepLive(0.6)}>Idle</button>
                    <button className="btn" onClick={() => stepLive(0.9)}>Cruise</button>
                    <button className="btn" onClick={() => stepLive(1.0)}>Full</button>
                  </div>
                </>
              )}
            </div>
          </div>

          {/* RIGHT: scenario builder */}
          <div className="grid" style={{ gridTemplateColumns: '1fr', alignContent: 'start' }}>
            <div className="card">
              <div className="card-h">Scenario Builder <span className="pill purple" style={{ background: 'rgba(139,109,240,.14)', color: 'var(--accent-purple)' }}>agent</span></div>
              <textarea className="input" rows={2} value={prompt} onChange={e => setPrompt(e.target.value)}
                placeholder="Describe a what-if… e.g. 'oil starts leaking at full throttle' or 'EGT sensor fails during a hot run'" />
              <div className="row" style={{ marginTop: 8 }}>
                <button className="btn teal" onClick={authored} disabled={authoring || !prompt.trim()}>
                  {authoring ? <><span className="spinner" />&nbsp; Authoring…</> : '✨ Author scenario'}
                </button>
                <span className="hint">or pick a built scenario below</span>
              </div>

              <div style={{ marginTop: 14, maxHeight: 260, overflowY: 'auto' }}>
                {lib.map(s => (
                  <div key={s.id} className={`scn ${selected === s.id ? 'sel' : ''}`} onClick={() => setSelected(s.id)}>
                    <div className="ic">{ICONS[s.category] || '⚠️'}</div>
                    <div style={{ flex: 1 }}>
                      <div className="nm">{s.name} {s.authored && <span className="pill purple" style={{ background: 'rgba(139,109,240,.14)', color: 'var(--accent-purple)' }}>authored</span>}</div>
                      <div className="ds">{s.description}</div>
                    </div>
                  </div>
                ))}
              </div>

              <div className="row" style={{ marginTop: 12 }}>
                <button className="btn primary" onClick={run} disabled={running || !tenant || !selected} style={{ flex: 1 }}>
                  {running ? <><span className="spinner" />&nbsp; Simulating…</>
                    : `▶ Run simulation${selScn ? ` — ${selScn.name}` : ''}`}
                </button>
              </div>
              {!tenant && <div className="hint" style={{ marginTop: 8 }}>Build the twin first to run a simulation from its present state.</div>}
            </div>
          </div>
        </div>

        {/* Twin intelligence: analysis + diagnosis agents + prediction */}
        {tenant && <Intelligence tenant={tenant} machine={machine} />}

        {/* Results: real-time vs simulated, side by side */}
        {result && (
          <div className="grid cols-2" style={{ marginTop: 16 }}>
            <div className="card">
              <div className="card-h">Projected Trajectory
                <span className={`pill ${o?.severity === 'critical' ? 'red' : o?.severity === 'warning' ? 'amber' : 'green'}`}>{o?.severity}</span>
              </div>
              <Chart data={traj} redline={780}
                series={[
                  { key: 'egt', label: 'EGT (true)', color: '#e2564e' },
                  { key: 'egt_reported', label: 'EGT (reported)', color: '#4b8bf5' },
                ]} />
              <div style={{ marginTop: 12 }}>
                <Chart data={traj} height={140}
                  series={[
                    { key: 'vib', label: 'Vibration (g)', color: '#e0962f' },
                    { key: 'health', label: 'Health', color: '#18a999' },
                  ]} />
              </div>
            </div>

            <div className="grid" style={{ gridTemplateColumns: '1fr', alignContent: 'start' }}>
              <div className="card">
                <div className="card-h">Predicted Outcome</div>
                <div className="kpis">
                  <div className="kpi"><div className="lbl">Time to redline</div>
                    <div className="val" style={{ color: o?.time_to_redline_min != null ? 'var(--accent-red)' : 'var(--text)' }}>
                      {o?.time_to_redline_min != null ? `${o.time_to_redline_min} min` : '—'}</div></div>
                  <div className="kpi"><div className="lbl">Peak EGT</div><div className="val">{fmt(o?.peak_egt)}°C</div></div>
                  <div className="kpi"><div className="lbl">Peak vibration</div><div className="val">{fmt(o?.peak_vibration)} g</div></div>
                  <div className="kpi"><div className="lbl">Min oil pressure</div><div className="val">{fmt(o?.min_oil_pressure)} PSI</div></div>
                  <div className="kpi"><div className="lbl">Min health</div>
                    <div className="val" style={{ color: o?.min_health < 0.4 ? 'var(--accent-red)' : 'var(--text)' }}>{o?.min_health != null ? `${Math.round(o.min_health * 100)}%` : '—'}</div></div>
                  <div className="kpi"><div className="lbl">Detections</div><div className="val">{o?.events_predicted ?? 0}</div></div>
                </div>
                {o?.blind_spot && (
                  <div style={{ marginTop: 10, padding: '8px 11px', borderRadius: 8, fontSize: 11.5,
                    background: 'rgba(226,86,78,.07)', border: '1px solid rgba(226,86,78,.3)', color: 'var(--accent-red)' }}>
                    ⚠ Blind spot — the EGT reading freezes while the engine truly overheats; only the physics residual catches it.
                  </div>
                )}
              </div>

              <div className="card">
                <div className="card-h">Predicted Event Timeline</div>
                {events.length === 0 ? <div className="empty">No detections in this horizon — the engine stays within limits.</div> :
                  events.map((e, i) => (
                    <div key={i} className="evt">
                      <div className="t">{e.t_min}m</div>
                      <span className={`sev ${e.severity}`}>{e.severity}</span>
                      <div className="m">{e.message}</div>
                    </div>
                  ))}
              </div>

              {result.analysis && (
                <div className="card">
                  <div className="card-h">Agent Analysis & Precautions
                    <span className="pill" style={{ background: 'rgba(139,109,240,.14)', color: 'var(--accent-purple)' }}>{claudeOn ? 'Claude' : 'rule-based'}</span>
                  </div>
                  <div className="analysis">{result.analysis}</div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
