import React, { useEffect, useState, useCallback, useRef } from 'react'
import api from './api'
import { Logo, Icon, SIG, sevClass, fmt, pct, hColor, statusColor,
  DOMAINS, domainMeta, tilesFor, simTwin } from './lib.jsx'
import Scenario from './Scenario.jsx'
import Intelligence, { StepFlow } from './Intelligence.jsx'
import Prediction from './Prediction.jsx'
import BuildTwin from './BuildTwin.jsx'
import TurbineModel from './TurbineModel.jsx'
import Scene3D from './Scene3D.jsx'

const NAV = [
  { id: 'twins', label: 'Twins', icon: 'ti-stack-2' },
  { id: 'dashboard', label: 'Live Dashboard', icon: 'ti-layout-dashboard' },
  { id: 'build', label: 'Build a Twin', icon: 'ti-sparkles' },
  { id: 'scenario', label: 'Scenario & Faults', icon: 'ti-urgent' },
  { id: 'predict', label: 'Prediction', icon: 'ti-chart-histogram' },
  { id: 'agents', label: 'Twin Intelligence', icon: 'ti-robot' },
]

export default function App() {
  const [route, setRoute] = useState('twins')
  const [health, setHealth] = useState(null)
  const [tenant, setTenant] = useState(null)
  const [domain, setDomain] = useState('turbine-engine')
  const [source, setSource] = useState(null)          // 'live' | 'sim' | null
  const [machine, setMachine] = useState(null)
  const [twin, setTwin] = useState(null)              // live state (polled) or sim
  const [modelUrl, setModelUrl] = useState(null)      // Tripo-generated GLB (turbine)
  const [building, setBuilding] = useState(null)      // domain key currently seeding
  const [err, setErr] = useState(null)
  const [simFault, setSimFault] = useState(null)      // active fault on a simulated twin
  const pollRef = useRef(null)
  const simPhase = useRef(0)
  const simFaultRef = useRef(null); simFaultRef.current = simFault
  const faultMag = useRef(0)

  useEffect(() => { api.health().then(setHealth).catch(() => {}) }, [])

  const poll = useCallback(async (tid) => {
    try { setTwin(await api.twinState(tid)) } catch { /* not ready */ }
  }, [])

  // Live polling (backend) or local simulation, depending on the active twin.
  useEffect(() => {
    if (pollRef.current) clearInterval(pollRef.current)
    if (source === 'live' && tenant) {
      poll(tenant)
      pollRef.current = setInterval(() => poll(tenant), 1000)
    } else if (source === 'sim') {
      simPhase.current = 0; faultMag.current = 0
      const tick = () => {
        simPhase.current = Math.min(1, simPhase.current + 0.02)
        // ramp an injected fault in (and back out when cleared)
        faultMag.current = Math.max(0, Math.min(1, faultMag.current + (simFaultRef.current ? 0.15 : -0.3)))
        setTwin(simTwin(domain, simPhase.current, simFaultRef.current, faultMag.current))
      }
      tick()
      pollRef.current = setInterval(tick, 1500)
    }
    return () => pollRef.current && clearInterval(pollRef.current)
  }, [tenant, source, domain, poll])

  // Open a real backend twin (seeds the graph; physics + agents come alive).
  async function openLive(dom, name) {
    setBuilding(dom); setErr(null); setSimFault(null)
    try {
      const r = await api.createTwin({ name: name || domainMeta(dom).label, domain: dom })
      setTenant(r.tenant); setDomain(dom); setSource('live')
      setMachine(r.machine || { name: domainMeta(dom).label }); setModelUrl(null)
      setTwin(null); setRoute('dashboard')
    } catch (e) { setErr(String(e.message || e)) }
    setBuilding(null)
  }

  // Open a frontend-simulated facility twin.
  function openSim(dom) {
    setTenant(null); setDomain(dom); setSource('sim'); setSimFault(null)
    setMachine({ name: domainMeta(dom).label }); setModelUrl(null)
    setTwin(simTwin(dom, 0)); setRoute('dashboard')
  }

  // The turbine "Build a Twin" image→3D flow lands here.
  function onBuilt(t, m) {
    setTenant(t); setDomain('turbine-engine'); setSource('live')
    setMachine(m); setModelUrl(null); setRoute('dashboard')
  }

  async function stepLive(throttle) {
    if (source !== 'live' || !tenant) return
    try { await api.step({ tenant, throttle }) } catch {}
    poll(tenant)
  }

  const liveHealth = twin?.health
  const claudeOn = health?.claude?.enabled
  const meta = domainMeta(domain)
  const machineName = machine?.name || meta.label
  const isLive = source === 'live' && !!tenant
  const nFindings = (twin?.findings || []).length
  const nIncidents = (twin?.incidents || []).length

  const ctx = { tenant, domain, source, isLive, meta, machine, machineName, twin, claudeOn,
    stepLive, modelUrl, simFault, setSimFault, goBuild: () => setRoute('build'), goTwins: () => setRoute('twins') }

  return (
    <div className="app-root">
      <div className="topbar">
        <span className="brand"><Logo size={32} />
          <span className="brand-word">
            <span className="brand-name">Goalcert</span>
            <span className="brand-tag">Digital Twin Platform</span>
          </span>
        </span>
        <div className="crumb">{source
          ? <><b>{machineName}</b> · {meta.tag} · live twin</>
          : 'Pick a twin from the Twins library to begin'}</div>
        <div className="topstat"><span className={`status-dot ${claudeOn ? 'live' : ''}`} style={{ background: claudeOn ? 'var(--brand)' : 'var(--hint)' }} />
          Agent <b>{claudeOn ? (health?.claude?.model || 'Claude') : 'stub'}</b></div>
        {source && <div className="topstat">
          <span className={`status-dot ${liveHealth == null ? '' : liveHealth > 0.7 ? 'green' : liveHealth > 0.4 ? 'amber' : 'red'}`} />
          Health <b>{liveHealth == null ? '—' : pct(liveHealth)}</b></div>}
        <div className="topstat"><span className="status-dot live" /> LIVE</div>
        <div className="acct"><span className="av">C</span>Collins MRO</div>
      </div>

      <div className="body">
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
            <div className="sidebar-help" onClick={() => setRoute('twins')}>
              <Icon n="ti-stack-2" /> Twins library</div>
            <div className="sidebar-ver">Goalcert · NextXR core · demo</div>
          </div>
        </div>

        <div className="content">
          {err && <div className="card" style={{ borderColor: 'rgba(225,29,72,.4)', color: 'var(--accent-red)', marginBottom: 16 }}>{err}</div>}
          {route === 'twins' && <TwinsLibrary building={building} active={source ? domain : null}
            onLive={openLive} onSim={openSim} goBuild={() => setRoute('build')} />}
          {route === 'dashboard' && (source
            ? <Dashboard key={domain + ':' + (tenant || 'sim')} ctx={ctx} />
            : <NeedTwin onPick={() => setRoute('twins')} />)}
          {route === 'build' && <BuildTwin tenant={tenant} machine={machine} twin={twin}
            modelUrl={modelUrl} onBuilt={onBuilt} setModelUrl={setModelUrl} />}
          {route === 'scenario' && (source ? <Scenario tenant={tenant} machineName={machineName} domain={domain} isLive={isLive} twin={twin} setSimFault={setSimFault} simFault={simFault} />
            : <NeedTwin onPick={() => setRoute('twins')} />)}
          {route === 'predict' && (source ? <Prediction tenant={tenant} machineName={machineName} domain={domain} isLive={isLive} twin={twin} />
            : <NeedTwin onPick={() => setRoute('twins')} />)}
          {route === 'agents' && (source ? <Intelligence tenant={tenant} machineName={machineName} domain={domain} isLive={isLive} twin={twin} />
            : <NeedTwin onPick={() => setRoute('twins')} />)}
        </div>
      </div>
    </div>
  )
}

function NeedTwin({ onPick }) {
  return (
    <div className="panel">
      <div className="empty" style={{ padding: '60px 20px' }}>
        <div style={{ fontSize: 15, color: 'var(--text)', fontWeight: 600, marginBottom: 8 }}>No twin selected</div>
        Open the Twins library and pick a machine or facility to bring its live dashboard up.
        <div style={{ marginTop: 16 }}>
          <button className="btn btn-primary" onClick={onPick}><Icon n="ti-stack-2" /> Open Twins library</button>
        </div>
      </div>
    </div>
  )
}

function NeedLive({ onPick, feature }) {
  return (
    <div className="panel">
      <div className="empty" style={{ padding: '60px 20px' }}>
        <div style={{ fontSize: 15, color: 'var(--text)', fontWeight: 600, marginBottom: 8 }}>{feature}</div>
        Open the <b>Wire EDM</b> or <b>Gas Turbine</b> twin to run the on-demand diagnosis,
        prediction and scenario engines on its live physics.
        <div style={{ marginTop: 16 }}>
          <button className="btn btn-primary" onClick={onPick}><Icon n="ti-stack-2" /> Open Twins library</button>
        </div>
      </div>
    </div>
  )
}

// ── Twins library ────────────────────────────────────────────────────
function TwinsLibrary({ building, active, onLive, onSim, goBuild }) {
  const keys = Object.keys(DOMAINS).filter(k => DOMAINS[k].library !== false)
  return (
    <div className="panel">
      <div className="panel-header">
        <div>
          <div className="panel-title">Twins</div>
          <div className="panel-subtitle">Open a live digital twin, or build a new one from a 2-D image.</div>
        </div>
        <div className="panel-actions">
          <button className="btn btn-primary" onClick={goBuild}><Icon n="ti-sparkles" /> Build from image</button>
        </div>
      </div>
      <div className="grid-3 section-gap">
        {keys.map(k => {
          const d = DOMAINS[k]
          const live = d.source === 'live'
          const busy = building === k
          return (
            <div key={k} className="card twin-card" style={{ position: 'relative', borderColor: active === k ? 'var(--brand)' : undefined }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
                <div className="agent-icon" style={{ color: d.accent }}><Icon n={d.icon} /></div>
                <div>
                  <div className="twin-name">{d.label}</div>
                  <div className="twin-domain">{d.tag}</div>
                </div>
              </div>
              <div className="twin-desc">{d.blurb}</div>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 14 }}>
                <span className="pill pill-green">● live</span>
                {d.detailed && <span className="pill pill-blue">full physics</span>}
                <span className="pill pill-surface">{d.tiles.length} signals</span>
              </div>
              <button className="btn btn-primary" style={{ width: '100%' }}
                disabled={!!building}
                onClick={() => live ? onLive(k, d.label) : onSim(k)}>
                {busy ? <><span className="spinner" /> Opening twin…</>
                  : <><Icon n="ti-bolt" /> Open twin</>}
              </button>
            </div>
          )
        })}
      </div>
      <div className="cta-band" style={{ marginTop: 4 }}>
        <h3>One backbone, any twin</h3>
        <p>Every twin runs on the same NextXR ontology + behaviour engine: live telemetry, a 3-tier
          findings pipeline, predictive RUL, and the Claude agent layer — diagnosis, scenarios,
          work orders and cascade analysis — all grounded in each machine's own data.</p>
      </div>
    </div>
  )
}


// ── Generic, domain-aware dashboard ──────────────────────────────────
function Dashboard({ ctx }) {
  const { tenant, domain, source, isLive, meta, machineName, twin, stepLive, modelUrl, claudeOn } = ctx
  const live = twin?.latest || {}
  const h = twin?.health
  const findings = twin?.findings || []
  const incidents = twin?.incidents || []
  const tiles = tilesFor(domain)
  const headlineSig = tiles[0]
  const headline = SIG[headlineSig]
  const risk = h == null ? null : Math.round((1 - h) * 100)

  // ── AI co-pilot (every twin, grounded in its own live telemetry) ──
  const twinRef = useRef(twin); twinRef.current = twin
  const [narration, setNarration] = useState([])
  const [narrating, setNarrating] = useState(false)
  useEffect(() => {
    if (!source) return
    const tick = async () => {
      const tw = twinRef.current
      if (!tw || !tw.latest) return
      setNarrating(true)
      try {
        const r = await api.narrateSnapshot({ machine: machineName, latest: tw.latest,
          findings: tw.findings || [], health: tw.health })
        if (r?.narration) setNarration(prev => [{ text: r.narration, ts: new Date().toLocaleTimeString() }, ...prev].slice(0, 12))
      } catch {}
      setNarrating(false)
    }
    tick()
    const t = setInterval(tick, 8000)
    return () => clearInterval(t)
  }, [source, domain, machineName])

  // snapshot body for the snapshot-based agents (work-order / cascade on sim twins)
  const snap = () => ({ machine: machineName, domain, latest: live, findings,
    components: (meta.assets || []).map(([id, st]) => ({ name: id, status: st })) })

  const [alert, setAlert] = useState(null)
  useEffect(() => {   // live: physics RUL alert
    if (!isLive) return
    const check = async () => {
      try { const r = await api.predictAlert({ tenant, machine: machineName, horizon_label: '2 hours' }); setAlert(r?.alert || null) } catch {}
    }
    check(); const t = setInterval(check, 30000); return () => clearInterval(t)
  }, [isLive, tenant, machineName])
  useEffect(() => {   // sim: surface the worst active finding as the alert
    if (isLive || !source) return
    const crit = (findings || []).find(f => f.severity === 'critical')
    setAlert(crit ? crit.message : null)
  }, [isLive, source, findings])

  const [wo, setWo] = useState(null)
  const [woLoading, setWoLoading] = useState(false)
  const generateWO = async () => {
    setWoLoading(true)
    try { const r = isLive ? await api.workOrder({ tenant, machine: machineName }) : await api.workOrderSnapshot(snap()); setWo(r?.work_order || null) } catch {}
    setWoLoading(false)
  }
  const printWO = () => window.print()

  const [cascade, setCascade] = useState(null)
  const [cascadeLoading, setCascadeLoading] = useState(false)
  const runCascade = async () => {
    setCascadeLoading(true)
    try { const r = isLive ? await api.cascade({ tenant, machine: machineName, horizon_label: '2 hours' }) : await api.cascadeSnapshot(snap()); setCascade(r?.cascade_analysis || null) } catch {}
    setCascadeLoading(false)
  }

  const throttleLabel = domain === 'edm-machine' ? 'Intensity' : 'Throttle'

  // Live fault injection (drive a fault into the running twin's physics)
  const [faults, setFaults] = useState([])
  const [fault, setFault] = useState('')
  useEffect(() => {
    if (!isLive) { setFaults([]); setFault(''); return }
    api.twinFaults(domain).then(r => setFaults(r?.faults || [])).catch(() => {})
  }, [isLive, domain])
  const injectFault = async (f) => {
    setFault(f === 'none' ? '' : f)
    try { await api.step({ tenant, fault: f || 'none', severity: 1.0 }) } catch {}
  }

  return (
    <div className="panel">
      <div className="panel-header">
        <div>
          <div className="panel-title">Live Operations</div>
          <div className="panel-subtitle">{machineName} · streaming sensor telemetry in real time</div>
        </div>
        <div className="panel-actions">
          {isLive && (domain === 'edm-machine' || domain === 'turbine-engine') && <>
            <span className="hint" style={{ alignSelf: 'center' }}>{throttleLabel}:</span>
            <button className="btn" onClick={() => stepLive(0.5)}>Low</button>
            <button className="btn" onClick={() => stepLive(0.75)}>Mid</button>
            <button className="btn btn-primary" onClick={() => stepLive(1.0)}>High</button>
            {faults.length > 0 && (
              <select className="select" style={{ width: 'auto', minWidth: 150 }}
                value={fault} onChange={e => injectFault(e.target.value)}>
                <option value="">Inject fault…</option>
                <option value="none">✓ Healthy (clear)</option>
                {faults.map(f => <option key={f.id} value={f.id}>⚠ {f.label}</option>)}
              </select>
            )}
          </>}
        </div>
      </div>

      {/* KPIs — the dashboard summary, on top */}
      <div className="grid-4 section-gap">
        <div className="card kpi"><div className="card-label">Twin Health</div>
          <div className="card-value" style={{ color: hColor(h) }}>{pct(h)}</div>
          <div className="card-change">physics health index</div></div>
        <div className="card kpi"><div className="card-label">Risk</div>
          <div className="card-value">{risk == null ? '—' : risk}</div>
          <div className="card-change">{risk >= 60 ? 'HIGH' : risk >= 30 ? 'ELEVATED' : 'LOW'}</div></div>
        <div className="card kpi"><div className="card-label">Active Findings</div>
          <div className="card-value" style={{ color: 'var(--accent-amber)' }}>{findings.length}</div>
          <div className="card-change">{incidents.length} incident(s)</div></div>
        {headline && <div className="card kpi"><div className="card-label">{headline.label}</div>
          <div className="card-value" style={{ color: sevClass(headlineSig, live[headlineSig]) === 'crit' ? 'var(--accent-red)' : 'var(--text)' }}>
            {fmt(live[headlineSig])}<span style={{ fontSize: 14 }}>{headline.unit ? ' ' + headline.unit : ''}</span></div>
          <div className="card-change">{headline.crit != null ? `limit ${headline.crit} ${headline.unit}` : headline.critLow != null ? `min ${headline.critLow} ${headline.unit}` : 'live'}</div></div>}
      </div>

      {/* 3D twin scene */}
      <div className="section-gap">
        {domain === 'turbine-engine'
          ? (modelUrl
              ? <TurbineModel url={modelUrl} latest={live} height={380} />
              : <div className="hero3d" style={{ height: 380 }}>
                  <div className="v-chip"><Icon n="ti-engine" /> <b>{machineName}</b></div>
                  <div className="lbl"><div className="big">⬡ Gas Turbine</div>
                    Generating the 3D model from your image — <a style={{ color: '#c4b5fd', cursor: 'pointer' }} onClick={ctx.goBuild}>open Build a Twin</a>.</div>
                </div>)
          : <Scene3D domain={domain} machine={machineName} live={live} height={380} />}
      </div>

      {/* Predictive alert banner (live) */}
      {isLive && alert && (
        <div className="card section-gap" style={{ borderColor: 'rgba(225,29,72,.4)', background: 'rgba(225,29,72,.06)' }}>
          <div className="card-title" style={{ color: 'var(--accent-red)' }}><Icon n="ti-alert-octagon" /> Predictive Alert</div>
          <div style={{ fontSize: 13, lineHeight: 1.7 }}>{alert}</div>
        </div>
      )}

      {/* AI co-pilot — narrates every twin from its own live telemetry */}
      {source && (
        <div className="card section-gap">
          <div className="card-title"><Icon n="ti-message-chatbot" /> AI Co-Pilot {narrating && <span className="spinner" style={{ marginLeft: 8 }} />}
            <span className="pill pill-green" style={{ fontSize: 9 }}>{claudeOn ? 'Claude' : 'stub'}</span>
          </div>
          {narration.length === 0
            ? <div className="empty">Waiting for sensor data to narrate…</div>
            : <div style={{ maxHeight: 140, overflowY: 'auto', fontSize: 12, lineHeight: 1.8 }}>
                {narration.map((n, i) => (
                  <div key={i} style={{ padding: '3px 0', borderBottom: '1px solid var(--border)', opacity: i === 0 ? 1 : 0.5 + (0.5 / (i + 1)) }}>
                    <span style={{ color: 'var(--hint)', fontFamily: 'var(--mono)', fontSize: 10, marginRight: 8 }}>{n.ts}</span>
                    {n.text}
                  </div>
                ))}
              </div>}
        </div>
      )}

      {/* Live telemetry (generic, domain-driven) */}
      <div className="card section-gap">
        <div className="card-title"><Icon n="ti-activity" /> Live Telemetry
          <span className="pill pill-green">● streaming</span></div>
        <div className="sensor-grid">
          {tiles.filter(s => live[s] != null).map(s => (
            <div key={s} className={`sensor-card ${sevClass(s, live[s])}`}>
              <span className="live-indicator" />
              <div className="sensor-label">{SIG[s]?.label || s}</div>
              <div><span className="sensor-value">{fmt(live[s])}</span><span className="sensor-unit">{SIG[s]?.unit}</span></div>
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
            ? <div className="empty">No findings — within limits.</div>
            : <div className="event-list">{findings.slice(0, 6).map((f, i) => (
                <div key={i} className="event-item">
                  <div className={`event-icon ${f.severity === 'critical' ? 'ev-crit' : 'ev-warn'}`}><Icon n="ti-alert-triangle" /></div>
                  <div className="event-body"><div className="event-title">{f.displayName || f.behaviorId || 'finding'}</div>
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
                    <div className="event-meta">{inc.severity || 'critical'}{inc.status ? ' · ' + inc.status : ''}</div></div>
                </div>))}</div>}
        </div>
      </div>

      {/* Work order (when findings exist) */}
      {source && findings.length > 0 && (
        <div className="card section-gap">
          <div className="card-title"><Icon n="ti-file-certificate" /> Maintenance Work Order
            <span className="pill pill-surface" style={{ fontSize: 9 }}>AS9100 / EASA Part 145</span>
          </div>
          {!wo ? (
            <div>
              <div className="empty" style={{ marginBottom: 12 }}>Generate a compliant maintenance work order from the current diagnosis.</div>
              <button className="btn btn-primary" onClick={generateWO} disabled={woLoading} style={{ width: '100%' }}>
                {woLoading ? <><span className="spinner" /> Generating…</> : <><Icon n="ti-file-certificate" /> Generate Work Order</>}
              </button>
            </div>
          ) : (
            <div>
              {/* WO header KPIs */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10, marginBottom: 16 }}>
                <div className="kpibox"><div className="l">WO Number</div><div className="v" style={{ fontSize: 15 }}>{wo.wo_number}</div></div>
                <div className="kpibox"><div className="l">ATA Chapter</div><div className="v" style={{ fontSize: 13 }}>{wo.ata_chapter}</div></div>
                <div className="kpibox"><div className="l">Priority</div><div className="v">
                  <span className={`pill ${wo.priority === 'AOG' ? 'pill-red' : wo.priority === 'Critical' ? 'pill-amber' : 'pill-surface'}`}>{wo.priority}</span></div></div>
                <div className="kpibox"><div className="l">Est. Hours</div><div className="v">{wo.estimated_hours}h</div></div>
              </div>

              {/* fault + root cause */}
              <div className="grid-2" style={{ marginBottom: 16, gap: 10 }}>
                <div style={{ background: 'rgba(225,29,72,.04)', border: '1px solid rgba(225,29,72,.12)', borderRadius: 12, padding: '12px 14px' }}>
                  <div className="card-label" style={{ color: 'var(--accent-red)' }}>Fault Description</div>
                  <div style={{ fontSize: 12.5, lineHeight: 1.6, marginTop: 6 }}>{wo.fault_description}</div>
                </div>
                <div style={{ background: 'rgba(217,119,6,.04)', border: '1px solid rgba(217,119,6,.12)', borderRadius: 12, padding: '12px 14px' }}>
                  <div className="card-label" style={{ color: 'var(--accent-amber)' }}>Root Cause</div>
                  <div style={{ fontSize: 12.5, lineHeight: 1.6, marginTop: 6 }}>{wo.root_cause}</div>
                </div>
              </div>

              {/* compliance */}
              <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 14, display: 'flex', alignItems: 'center', gap: 6 }}>
                <Icon n="ti-certificate" /> Compliance: {wo.compliance_ref}
              </div>

              {/* repair steps as visual flow */}
              <div className="card-label" style={{ marginBottom: 10 }}>Repair Procedure</div>
              <StepFlow steps={wo.steps || []} />

              {/* parts as chips */}
              {wo.parts_required?.length > 0 && (
                <div style={{ marginTop: 16 }}>
                  <div className="card-label" style={{ marginBottom: 8 }}>Parts Required</div>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                    {wo.parts_required.map((p, i) => (
                      <span key={i} className="pill pill-blue" style={{ fontSize: 11, padding: '4px 10px' }}>{p}</span>
                    ))}
                  </div>
                </div>
              )}

              {/* sign-off + print */}
              <div style={{ marginTop: 16, padding: '12px 14px', background: 'rgba(22,163,74,.04)', border: '1px solid rgba(22,163,74,.12)',
                borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div>
                  <div className="card-label" style={{ color: 'var(--accent-green)' }}>Sign-off</div>
                  <div style={{ fontSize: 12, marginTop: 4 }}>{wo.sign_off}</div>
                </div>
                <button className="btn" onClick={printWO}><Icon n="ti-printer" /> Print</button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Cascade analysis */}
      {source && (
        <div className="card section-gap">
          <div className="card-title"><Icon n="ti-affiliate" /> Cascade Analysis
            <span className="pill pill-purple" style={{ fontSize: 9 }}>Claude</span>
          </div>
          {!cascade ? (
            <div>
              <div className="empty" style={{ marginBottom: 12 }}>Reason about how degradation in one subsystem propagates to others over the forecast horizon.</div>
              <button className="btn btn-primary" onClick={runCascade} disabled={cascadeLoading} style={{ width: '100%' }}>
                {cascadeLoading ? <><span className="spinner" /> Analyzing…</> : <><Icon n="ti-affiliate" /> Run Cascade Analysis</>}
              </button>
            </div>
          ) : (
            <div>
              <div style={{ fontSize: 13, lineHeight: 1.8, whiteSpace: 'pre-wrap',
                borderLeft: '3px solid var(--brand-2)', padding: '14px 16px',
                background: 'var(--brand-softer)', borderRadius: '0 12px 12px 0' }}>
                {cascade}
              </div>
              <button className="btn" onClick={runCascade} disabled={cascadeLoading} style={{ marginTop: 12 }}>
                {cascadeLoading ? <><span className="spinner" /> Analyzing…</> : <><Icon n="ti-refresh" /> Re-run</>}
              </button>
            </div>
          )}
        </div>
      )}

    </div>
  )
}
