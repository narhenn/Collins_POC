import React, { useEffect, useState, useCallback, useRef } from 'react'
import api from './api'
import { Logo, Icon, SIG, TILE_ORDER, sevClass, fmt, pct } from './lib.jsx'
import Scenario from './Scenario.jsx'
import Intelligence from './Intelligence.jsx'
import BuildTwin from './BuildTwin.jsx'
import TurbineModel from './TurbineModel.jsx'

const NAV = [
  { id: 'dashboard', label: 'Live Dashboard', icon: 'ti-layout-dashboard' },
  { id: 'build', label: 'Build a Twin', icon: 'ti-sparkles' },
  { id: 'scenario', label: 'Scenario Builder', icon: 'ti-urgent' },
  { id: 'agents', label: 'Twin Intelligence', icon: 'ti-robot' },
]

export default function App() {
  const [route, setRoute] = useState('dashboard')
  const [health, setHealth] = useState(null)
  const [tenant, setTenant] = useState(null)
  const [machine, setMachine] = useState(null)
  const [twin, setTwin] = useState(null)        // live state (polled 1s)
  const [modelUrl, setModelUrl] = useState(null)  // Tripo-generated GLB
  const [building, setBuilding] = useState(false)
  const [err, setErr] = useState(null)
  const pollRef = useRef(null)

  useEffect(() => { api.health().then(setHealth).catch(() => {}) }, [])

  const poll = useCallback(async (tid) => {
    try { setTwin(await api.twinState(tid)) } catch { /* not ready */ }
  }, [])
  useEffect(() => {
    if (!tenant) return
    poll(tenant)
    pollRef.current = setInterval(() => poll(tenant), 1000)  // live, every second
    return () => clearInterval(pollRef.current)
  }, [tenant, poll])

  async function buildTwin() {
    setBuilding(true); setErr(null)
    try {
      const r = await api.build({ description: 'Gas turbine engine on MRO test rig', start_feed: false })
      setTenant(r.tenant); setMachine(r.machine); setModelUrl(null)
      poll(r.tenant)
    } catch (e) { setErr(String(e.message || e)) }
    setBuilding(false)
  }
  function onBuilt(t, m) { setTenant(t); setMachine(m); setModelUrl(null); poll(t) }
  async function stepLive(throttle) {
    if (!tenant) return
    try { await api.step({ tenant, throttle }) } catch {}
    poll(tenant)
  }

  const liveHealth = twin?.health
  const claudeOn = health?.claude?.enabled
  const machineName = machine?.name || 'Turbine Engine'
  const nFindings = (twin?.findings || []).length
  const nIncidents = (twin?.incidents || []).length

  const ctx = { tenant, machine, machineName, twin, claudeOn, stepLive, building, buildTwin, modelUrl, goBuild: () => setRoute('build') }

  return (
    <div className="app-root">
      {/* Topbar */}
      <div className="topbar">
        <span className="brand"><Logo size={32} />
          <span className="brand-word">
            <span className="brand-name">Goalcert</span>
            <span className="brand-tag">Turbine Digital Twin</span>
          </span>
        </span>
        <div className="crumb">{tenant
          ? <><b>{machineName}</b> · live aerospace MRO twin</>
          : 'No twin yet — build one to begin'}</div>
        <div className="topstat"><span className={`status-dot ${claudeOn ? 'live' : ''}`} style={{ background: claudeOn ? 'var(--brand)' : 'var(--hint)' }} />
          Agent <b>{claudeOn ? (health?.claude?.model || 'Claude') : 'stub'}</b></div>
        {tenant && <div className="topstat">
          <span className={`status-dot ${liveHealth == null ? '' : liveHealth > 0.7 ? 'green' : liveHealth > 0.4 ? 'amber' : 'red'}`} />
          Health <b>{liveHealth == null ? '—' : pct(liveHealth)}</b></div>}
        <div className="topstat"><span className="status-dot live" /> LIVE</div>
        <div className="acct"><span className="av">C</span>Collins MRO</div>
      </div>

      <div className="body">
        {/* Sidebar */}
        <div className="sidebar">
          <div className="sidebar-nav">
            <div className="sidebar-section">Operations</div>
            {NAV.map(it => (
              <a key={it.id} className={`nav-item ${route === it.id ? 'active' : ''}`} onClick={() => setRoute(it.id)}>
                <Icon n={it.icon} />{it.label}
                {it.id === 'dashboard' && nIncidents > 0 && <span className="nav-badge badge-red">{nIncidents}</span>}
                {it.id === 'agents' && <span className="nav-badge badge-blue">2</span>}
              </a>
            ))}
          </div>
          <div className="sidebar-foot">
            <div className="sidebar-help" onClick={() => setRoute('build')}>
              <Icon n="ti-sparkles" /> Build a Twin</div>
            <div className="sidebar-ver">Goalcert · NextXR core · demo</div>
          </div>
        </div>

        {/* Content */}
        <div className="content">
          {err && <div className="card" style={{ borderColor: 'rgba(225,29,72,.4)', color: 'var(--accent-red)', marginBottom: 16 }}>{err}</div>}
          {route === 'dashboard' && <Dashboard ctx={ctx} />}
          {route === 'build' && <BuildTwin tenant={tenant} machine={machine} twin={twin}
            modelUrl={modelUrl} onBuilt={onBuilt} setModelUrl={setModelUrl} />}
          {route === 'scenario' && (tenant ? <Scenario tenant={tenant} machineName={machineName} twin={twin} />
            : <NeedTwin onBuild={() => setRoute('build')} building={building} />)}
          {route === 'agents' && (tenant ? <Intelligence tenant={tenant} machineName={machineName} />
            : <NeedTwin onBuild={() => setRoute('build')} building={building} />)}
        </div>
      </div>
    </div>
  )
}

function NeedTwin({ onBuild, building }) {
  return (
    <div className="panel">
      <div className="empty" style={{ padding: '60px 20px' }}>
        <div style={{ fontSize: 15, color: 'var(--text)', fontWeight: 600, marginBottom: 8 }}>No turbine twin yet</div>
        Build the digital twin first, then run scenarios and agents on it.
        <div style={{ marginTop: 16 }}>
          <button className="btn btn-primary" onClick={onBuild} disabled={building}>
            {building ? <><span className="spinner" />&nbsp; Building…</> : <><Icon n="ti-sparkles" /> Build Turbine Twin</>}
          </button>
        </div>
      </div>
    </div>
  )
}

function Dashboard({ ctx }) {
  const { tenant, machineName, twin, stepLive, building, buildTwin, modelUrl, goBuild } = ctx
  const live = twin?.latest || {}
  const h = twin?.health
  const findings = twin?.findings || []
  const incidents = twin?.incidents || []
  const egt = live['aero:exhaustGasTemp']
  const risk = h == null ? null : Math.round((1 - h) * 100)

  return (
    <div className="panel">
      <div className="panel-header">
        <div>
          <div className="panel-title">Live Operations</div>
          <div className="panel-subtitle">{tenant ? `${machineName} · streaming sensor telemetry in real time` : 'Build a turbine twin to start the live stream'}</div>
        </div>
        <div className="panel-actions">
          {tenant && <>
            <span className="hint" style={{ alignSelf: 'center' }}>Throttle:</span>
            <button className="btn" onClick={() => stepLive(0.55)}>Idle</button>
            <button className="btn" onClick={() => stepLive(0.9)}>Cruise</button>
            <button className="btn btn-primary" onClick={() => stepLive(1.0)}>Full</button>
          </>}
        </div>
      </div>

      {/* 3D hero — live model when generated, else placeholder */}
      <div className="section-gap">
        {modelUrl
          ? <TurbineModel url={modelUrl} latest={twin?.latest || {}} height={320} />
          : <div className="hero3d">
              <div className="v-chip"><Icon n="ti-cube" /> <b>3D Twin</b> · {machineName}</div>
              <div className="lbl">
                <div className="big">⬡ 3D Turbine Visualization</div>
                {tenant ? <>Build the 3D model from a 2D image — <a style={{ color: '#c4b5fd', cursor: 'pointer' }} onClick={goBuild}>open Build a Twin</a>.</>
                  : 'Build a twin to start the live stream and 3D model.'}
              </div>
            </div>}
      </div>

      {!tenant ? (
        <div className="empty" style={{ padding: '40px' }}>
          <button className="btn btn-primary" onClick={buildTwin} disabled={building}>
            {building ? <><span className="spinner" />&nbsp; Building…</> : <><Icon n="ti-sparkles" /> Build Turbine Twin</>}
          </button>
        </div>
      ) : (
        <>
          {/* KPIs */}
          <div className="grid-4 section-gap">
            <div className="card kpi"><div className="card-label">Twin Health</div>
              <div className="card-value" style={{ color: h > .7 ? 'var(--accent-green)' : h > .4 ? 'var(--accent-amber)' : 'var(--accent-red)' }}>{pct(h)}</div>
              <div className="card-change">physics health index</div></div>
            <div className="card kpi"><div className="card-label">Risk</div>
              <div className="card-value">{risk == null ? '—' : risk}</div>
              <div className="card-change">{risk >= 60 ? 'HIGH' : risk >= 30 ? 'ELEVATED' : 'LOW'}</div></div>
            <div className="card kpi"><div className="card-label">Active Findings</div>
              <div className="card-value" style={{ color: 'var(--accent-amber)' }}>{findings.length}</div>
              <div className="card-change">{incidents.length} incident(s)</div></div>
            <div className="card kpi"><div className="card-label">EGT</div>
              <div className="card-value" style={{ color: egt >= 780 ? 'var(--accent-red)' : 'var(--text)' }}>{fmt(egt)}<span style={{ fontSize: 14 }}>°C</span></div>
              <div className="card-change">redline 780 °C</div></div>
          </div>

          {/* Live telemetry */}
          <div className="card section-gap">
            <div className="card-title"><Icon n="ti-activity" /> Live Telemetry
              <span className="pill pill-green">● streaming</span></div>
            <div className="sensor-grid">
              {TILE_ORDER.filter(s => live[s] != null).map(s => (
                <div key={s} className={`sensor-card ${sevClass(s, live[s])}`}>
                  <span className="live-indicator" />
                  <div className="sensor-label">{SIG[s].label}</div>
                  <div><span className="sensor-value">{fmt(live[s])}</span><span className="sensor-unit">{SIG[s].unit}</span></div>
                </div>
              ))}
            </div>
          </div>

          {/* Findings + incidents */}
          <div className="grid-2">
            <div className="card">
              <div className="card-title"><Icon n="ti-alert-triangle" /> Active Findings
                <span className="pill pill-surface">{findings.length}</span></div>
              {findings.length === 0
                ? <div className="empty">No findings — engine within limits.</div>
                : <div className="event-list">{findings.slice(0, 6).map((f, i) => (
                    <div key={i} className="event-item">
                      <div className={`event-icon ${f.severity === 'critical' ? 'ev-crit' : 'ev-warn'}`}><Icon n="ti-alert-triangle" /></div>
                      <div className="event-body"><div className="event-title">{f.behaviorId || 'finding'}</div>
                        <div className="event-meta">{f.message}</div></div>
                    </div>))}</div>}
            </div>
            <div className="card">
              <div className="card-title"><Icon n="ti-git-merge" /> Incidents
                <span className="pill pill-surface">{incidents.length}</span></div>
              {incidents.length === 0
                ? <div className="empty">No incidents grouped yet.</div>
                : <div className="event-list">{incidents.map((inc, i) => (
                    <div key={i} className="event-item" style={{ borderColor: 'rgba(225,29,72,.25)' }}>
                      <div className="event-icon ev-crit"><Icon n="ti-urgent" /></div>
                      <div className="event-body"><div className="event-title">{inc.displayName || 'Incident'}</div>
                        <div className="event-meta">{inc.severity} · {inc.status}</div></div>
                    </div>))}</div>}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
