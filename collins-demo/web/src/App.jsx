import React, { useEffect, useState, useCallback, useRef } from 'react'
import api from './api'
import { Logo, Icon, SIG, sevClass, fmt, pct, hColor, statusColor,
  DOMAINS, domainMeta, tilesFor, simTwin,
  useCountUp, HealthRing, Sparkline } from './lib.jsx'
import { stubNarration, stubChatReply } from './aiStubs.js'
import Scenario from './Scenario.jsx'
import Intelligence, { StepFlow } from './Intelligence.jsx'
import Prediction from './Prediction.jsx'
import BuildTwin from './BuildTwin.jsx'
import TurbineModel from './TurbineModel.jsx'
import Scene3D from './Scene3D.jsx'
import ModelViewer from './ModelViewer.jsx'
import NetworkMap from './NetworkMap.jsx'
import BimViewer from './BimViewer.jsx'
import Chat from './Chat.jsx'
import Markdown from './Markdown.jsx'
import Maintenance from './Maintenance.jsx'
import CascadeGraph from './CascadeGraph.jsx'
import Heatmap from './Heatmap.jsx'
import CommandPalette from './CommandPalette.jsx'
import AuditLog from './AuditLog.jsx'

const NAV = [
  { id: 'twins', label: 'Twins', icon: 'ti-stack-2' },
  { id: 'dashboard', label: 'Live Dashboard', icon: 'ti-layout-dashboard' },
  { id: 'build', label: 'Build a Twin', icon: 'ti-sparkles' },
  { id: 'scenario', label: 'Scenario & Faults', icon: 'ti-urgent' },
  { id: 'predict', label: 'Prediction', icon: 'ti-chart-histogram' },
  { id: 'agents', label: 'Twin Intelligence', icon: 'ti-robot' },
  { id: 'audit', label: 'Audit Trail', icon: 'ti-history' },
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
  const [maint, setMaint] = useState(false)          // AI Maintenance Director overlay
  const [running, setRunning] = useState(true)        // live twin start/stop
  // AI mode: 'stub' runs everything locally (no tokens, instant) — 'agent' calls Claude.
  // Default stub so the always-on co-pilot doesn't burn tokens while monitoring.
  const [aiMode, setAiMode] = useState(() => localStorage.getItem('gc_ai_mode') || 'stub')
  const toggleAiMode = () => setAiMode(m => { const n = m === 'agent' ? 'stub' : 'agent'; try { localStorage.setItem('gc_ai_mode', n) } catch {} return n })
  const [saved, setSaved] = useState(() => {          // user-saved twins (localStorage)
    try { return JSON.parse(localStorage.getItem('gc_saved_twins') || '[]') } catch { return [] } })
  const persistSaved = (list) => { setSaved(list); try { localStorage.setItem('gc_saved_twins', JSON.stringify(list)) } catch {} }
  const saveTwin = (entry) => persistSaved([entry, ...saved.filter(s => s.id !== entry.id)].slice(0, 24))
  const removeSaved = (id) => persistSaved(saved.filter(s => s.id !== id))
  const [cmdPalette, setCmdPalette] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [auditEntries, setAuditEntries] = useState([])
  const addAudit = (type, summary, detail, agent) => setAuditEntries(prev => [...prev,
    { id: Date.now() + '-' + Math.random().toString(36).slice(2, 6), timestamp: Date.now(),
      type, summary, detail: typeof detail === 'string' ? detail : JSON.stringify(detail, null, 2),
      agent, domain, machine: machine?.name || '' }])
  const pollRef = useRef(null)
  const simPhase = useRef(0)
  const simFaultRef = useRef(null); simFaultRef.current = simFault
  const faultMag = useRef(0)

  useEffect(() => { api.health().then(setHealth).catch(() => {}) }, [])
  // restore theme on mount
  useEffect(() => { const t = localStorage.getItem('theme'); if (t) document.documentElement.setAttribute('data-theme', t) }, [])
  // -- apply domain accent as CSS variable when domain changes --
  useEffect(() => {
    const meta = DOMAINS[domain]
    if (meta?.accent) {
      document.documentElement.style.setProperty('--brand', meta.accent)
      document.documentElement.style.setProperty('--brand-2', meta.accent)
      document.documentElement.style.setProperty('--brand-strong', meta.accent)
    }
  }, [domain])
  // Cmd+K command palette
  useEffect(() => {
    const handler = (e) => { if ((e.metaKey || e.ctrlKey) && e.key === 'k') { e.preventDefault(); setCmdPalette(p => !p) } }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  const poll = useCallback(async (tid) => {
    try { setTwin(await api.twinState(tid)) } catch { /* not ready */ }
  }, [])

  // Live polling (backend) or local simulation, depending on the active twin.
  // Paused when `running` is false (start/stop the twin).
  useEffect(() => {
    if (pollRef.current) clearInterval(pollRef.current)
    if (source === 'live' && tenant) {
      poll(tenant)                                    // always read current state once
      if (running) pollRef.current = setInterval(() => poll(tenant), 1000)
    } else if (source === 'sim') {
      if (running) {
        const tick = () => {
          simPhase.current = Math.min(1, simPhase.current + 0.02)
          // ramp an injected fault in (and back out when cleared)
          faultMag.current = Math.max(0, Math.min(1, faultMag.current + (simFaultRef.current ? 0.15 : -0.3)))
          setTwin(simTwin(domain, simPhase.current, simFaultRef.current, faultMag.current))
        }
        tick()
        pollRef.current = setInterval(tick, 1500)
      }
    }
    return () => pollRef.current && clearInterval(pollRef.current)
  }, [tenant, source, domain, poll, running])

  // Start/stop the live twin — freezes the backend ticker too, for live twins.
  async function toggleRunning() {
    const next = !running
    setRunning(next)
    if (source === 'live' && tenant) { try { await api.setTwinRunning(tenant, next) } catch {} }
  }

  // Open a real backend twin (seeds the graph; physics + agents come alive).
  // `mUrl` attaches a previously-reconstructed GLB (saved twins).
  async function openLive(dom, name, mUrl = null) {
    setBuilding(dom); setErr(null); setSimFault(null)
    try {
      const r = await api.createTwin({ name: name || domainMeta(dom).label, domain: dom })
      setTenant(r.tenant); setDomain(dom); setSource('live')
      setMachine(r.machine || { name: domainMeta(dom).label }); setModelUrl(mUrl)
      setTwin(null); setRunning(true); setRoute('dashboard')
    } catch (e) { setErr(String(e.message || e)) }
    setBuilding(null)
  }

  // Open a frontend-simulated facility twin.
  function openSim(dom) {
    setTenant(null); setDomain(dom); setSource('sim'); setSimFault(null)
    setMachine({ name: domainMeta(dom).label }); setModelUrl(null)
    simPhase.current = 0; faultMag.current = 0
    setTwin(simTwin(dom, 0)); setRunning(true); setRoute('dashboard')
  }

  // Build-a-Twin "confirm" lands here — set the active live twin + its 3D model,
  // WITHOUT navigating (Build-a-Twin shows a success card with "Open dashboard").
  function onBuilt(t, m, dom, mUrl) {
    setTenant(t); setDomain(dom || 'turbine-engine'); setSource('live')
    setMachine(m); setModelUrl(mUrl || null); setTwin(null); setRunning(true)
  }

  // Reopen a saved twin: recreate a fresh live twin and reattach its saved model.
  function openSaved(s) { openLive(s.domain, s.name, s.modelUrl || null) }

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
    stepLive, modelUrl, simFault, setSimFault, openMaint: () => setMaint(true),
    running, toggleRunning, saveTwin, aiMode, setAiMode, toggleAiMode,
    goBuild: () => setRoute('build'), goTwins: () => setRoute('twins') }

  return (
    <div className="app-root">
      <div className="topbar">
        <button className="btn btn-ghost mobile-menu" onClick={() => setSidebarOpen(!sidebarOpen)}>
          <Icon n="ti-menu-2" />
        </button>
        <span className="brand"><Logo size={32} />
          <span className="brand-word">
            <span className="brand-name">Goalcert</span>
            <span className="brand-tag">Digital Twin Platform</span>
          </span>
        </span>
        <div className="vertical-switcher">
          {Object.entries(DOMAINS).filter(([,d]) => d.library !== false).map(([key, d]) => (
            <button key={key} className={`v-pill ${domain === key ? 'active' : ''}`}
              style={domain === key ? { background: d.accent, color: '#fff' } : {}}
              onClick={() => { setDomain(key); setRoute('twins'); setSidebarOpen(false) }}>
              <Icon n={d.icon} /><span className="v-pill-label">{d.tag?.split(' ')[0] || d.label.split(' ')[0]}</span>
            </button>
          ))}
        </div>
        <div className="crumb">{source
          ? <><b>{machineName}</b> · {meta.tag} · live twin</>
          : 'Pick a twin from the Twins library to begin'}</div>
        <div className="topstat" onClick={toggleAiMode} title="Toggle between local Stub (no tokens, instant) and the Claude Agent"
          style={{ cursor: 'pointer', userSelect: 'none' }}>
          <span className={`status-dot ${aiMode === 'agent' && claudeOn ? 'live' : ''}`} style={{ background: aiMode === 'agent' && claudeOn ? 'var(--brand)' : 'var(--hint)' }} />
          AI <b>{aiMode === 'agent' ? (claudeOn ? (health?.claude?.model || 'Claude') : 'Claude (off)') : 'Stub'}</b>
          <span style={{ marginLeft: 4, fontSize: 12, opacity: 0.6 }}><Icon n="ti-switch-horizontal" /></span>
        </div>
        {source && <div className="topstat">
          <span className={`status-dot ${liveHealth == null ? '' : liveHealth > 0.7 ? 'green' : liveHealth > 0.4 ? 'amber' : 'red'}`} />
          Health <b>{liveHealth == null ? '—' : pct(liveHealth)}</b></div>}
        <div className="topstat"><span className="status-dot live" /> LIVE</div>
        <button className="btn btn-ghost" style={{ padding: '5px 8px', fontSize: 14 }} title="Toggle dark mode"
          onClick={() => { const t = document.documentElement.getAttribute('data-theme') === 'dark' ? '' : 'dark';
            document.documentElement.setAttribute('data-theme', t); localStorage.setItem('theme', t) }}>
          <Icon n={typeof window !== 'undefined' && document.documentElement.getAttribute('data-theme') === 'dark' ? 'ti-sun' : 'ti-moon'} />
        </button>
        <button className="btn btn-ghost" style={{ padding: '5px 8px', fontSize: 14 }} title="Command palette (Cmd+K)"
          onClick={() => setCmdPalette(true)}>
          <Icon n="ti-command" />
        </button>
        <div className="acct"><span className="av" style={{ background: domainMeta(domain).accent }}>{domainMeta(domain).label[0]}</span>{domainMeta(domain).tag}</div>
      </div>

      <div className="body">
        {sidebarOpen && <div className="sidebar-overlay" onClick={() => setSidebarOpen(false)} />}
        <div className={`sidebar ${sidebarOpen ? 'open' : ''}`}>
          <div className="sidebar-nav">
            <div className="sidebar-section">Operations</div>
            {NAV.map(it => (
              <a key={it.id} className={`nav-item ${route === it.id ? 'active' : ''}`} onClick={() => { setRoute(it.id); setSidebarOpen(false) }}>
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
            onLive={openLive} onSim={openSim} goBuild={() => setRoute('build')}
            saved={saved} onOpenSaved={openSaved} onRemoveSaved={removeSaved} />}
          {route === 'dashboard' && (source
            ? <Dashboard key={domain + ':' + (tenant || 'sim')} ctx={ctx} />
            : <NeedTwin onPick={() => setRoute('twins')} />)}
          {route === 'build' && <BuildTwin machine={machine} domain={domain}
            onBuilt={onBuilt} onSave={saveTwin} goDashboard={() => setRoute('dashboard')} />}
          {route === 'scenario' && (source ? <Scenario tenant={tenant} machineName={machineName} domain={domain} isLive={isLive} twin={twin} setSimFault={setSimFault} simFault={simFault} aiMode={aiMode} />
            : <NeedTwin onPick={() => setRoute('twins')} />)}
          {route === 'predict' && (source ? <Prediction tenant={tenant} machineName={machineName} domain={domain} isLive={isLive} twin={twin} />
            : <NeedTwin onPick={() => setRoute('twins')} />)}
          {route === 'agents' && (source ? <Intelligence tenant={tenant} machineName={machineName} domain={domain} isLive={isLive} twin={twin} aiMode={aiMode} />
            : <NeedTwin onPick={() => setRoute('twins')} />)}
          {route === 'bim' && <BimViewer />}
          {route === 'audit' && <AuditLog entries={auditEntries} />}
        </div>
      </div>

      {maint && source && (
        <Maintenance domain={domain} machineName={machineName} twin={twin} modelUrl={modelUrl}
          claudeOn={claudeOn} onExit={() => setMaint(false)} />
      )}

      {cmdPalette && <CommandPalette onClose={() => setCmdPalette(false)} commands={[
        { label: 'Twins Library', icon: 'ti-stack-2', group: 'Navigate', action: () => setRoute('twins') },
        { label: 'Live Dashboard', icon: 'ti-layout-dashboard', group: 'Navigate', action: () => setRoute('dashboard'), shortcut: 'D' },
        { label: 'Build a Twin', icon: 'ti-sparkles', group: 'Navigate', action: () => setRoute('build') },
        { label: 'Scenario & Faults', icon: 'ti-urgent', group: 'Navigate', action: () => setRoute('scenario') },
        { label: 'Prediction', icon: 'ti-chart-histogram', group: 'Navigate', action: () => setRoute('predict') },
        { label: 'Twin Intelligence', icon: 'ti-robot', group: 'Navigate', action: () => setRoute('agents') },
        { label: 'Audit Trail', icon: 'ti-history', group: 'Navigate', action: () => setRoute('audit') },
        { label: 'AI Maintenance Director', icon: 'ti-tool', group: 'Action', action: () => { setMaint(true); setCmdPalette(false) }, hint: 'Cinematic guided repair' },
        ...Object.keys(DOMAINS).filter(k => DOMAINS[k].library !== false).map(k => ({
          label: `Open ${DOMAINS[k].label}`, icon: DOMAINS[k].icon || 'ti-cube', group: 'Twin',
          action: () => { setRoute('twins') }, hint: DOMAINS[k].tag,
        })),
      ]} />}
    </div>
  )
}

function NeedTwin({ onPick }) {
  return (
    <div className="panel">
      <div style={{ padding: '60px 30px', textAlign: 'center' }}>
        <div style={{ width: 64, height: 64, borderRadius: '50%', background: 'var(--brand-soft)', margin: '0 auto 16px',
          display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 28, color: 'var(--brand)' }}>
          <Icon n="ti-stack-2" /></div>
        <div style={{ fontSize: 17, color: 'var(--text)', fontWeight: 700, marginBottom: 8 }}>Select a Digital Twin</div>
        <div style={{ fontSize: 13, color: 'var(--muted)', maxWidth: 360, margin: '0 auto 20px', lineHeight: 1.6 }}>
          Pick a machine or facility from the Twins library to bring its live dashboard, AI agents, and physics engine online.</div>
        <button className="btn btn-primary" onClick={onPick} style={{ padding: '10px 24px' }}>
          <Icon n="ti-stack-2" /> Open Twins Library</button>
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
function TwinsLibrary({ building, active, onLive, onSim, goBuild, saved = [], onOpenSaved, onRemoveSaved }) {
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

      {/* My saved twins (built from photos) */}
      {saved.length > 0 && (
        <div className="section-gap">
          <div className="card-label" style={{ marginBottom: 10 }}><Icon n="ti-device-floppy" /> My Twins</div>
          <div className="grid-3">
            {saved.map(s => {
              const d = DOMAINS[s.domain] || {}
              const busy = building === s.domain
              return (
                <div key={s.id} className="card twin-card" style={{ position: 'relative' }}>
                  <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 3, borderRadius: '16px 16px 0 0',
                    background: `linear-gradient(90deg, ${d.accent || '#7c3aed'}, ${d.accent || '#2563eb'}88)` }} />
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10, marginTop: 4 }}>
                    <div className="agent-icon" style={{ background: `${d.accent || '#7c3aed'}18`, color: d.accent || 'var(--brand)' }}>
                      <Icon n={d.icon || 'ti-cube'} /></div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 14, fontWeight: 700, fontFamily: 'var(--display)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.name}</div>
                      <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 1 }}>{d.label || s.domain}</div>
                    </div>
                    <span title="Remove" onClick={() => onRemoveSaved(s.id)}
                      style={{ cursor: 'pointer', color: 'var(--hint)', fontSize: 15 }}><Icon n="ti-trash" /></span>
                  </div>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 12 }}>
                    {s.modelUrl && <span className="pill pill-blue">3D model</span>}
                    <span className="pill pill-surface">saved {new Date(s.createdAt).toLocaleDateString()}</span>
                  </div>
                  <button className="btn btn-primary" style={{ width: '100%' }} disabled={!!building}
                    onClick={() => onOpenSaved(s)}>
                    {busy ? <><span className="spinner" /> Opening…</> : <><Icon n="ti-bolt" /> Open twin</>}
                  </button>
                </div>
              )
            })}
          </div>
        </div>
      )}
      <div className="grid-3 section-gap">
        {keys.map(k => {
          const d = DOMAINS[k]
          const live = d.source === 'live'
          const busy = building === k
          return (
            <div key={k} className="card twin-card" style={{ position: 'relative',
              borderColor: active === k ? d.accent || 'var(--brand)' : undefined,
              boxShadow: active === k ? `0 0 0 2px ${d.accent || 'var(--brand)'}22, 0 8px 24px ${d.accent || '#7c3aed'}18` : undefined }}>
              {/* accent stripe top */}
              <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 3, borderRadius: '16px 16px 0 0',
                background: `linear-gradient(90deg, ${d.accent || '#7c3aed'}, ${d.accent || '#2563eb'}88)` }} />
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10, marginTop: 4 }}>
                <div className="agent-icon" style={{ background: `${d.accent || '#7c3aed'}18`, color: d.accent || 'var(--brand)' }}>
                  <Icon n={d.icon} /></div>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 700, fontFamily: 'var(--display)' }}>{d.label}</div>
                  <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 1 }}>{d.tag}</div>
                </div>
                {active === k && <span className="pill pill-green" style={{ marginLeft: 'auto', fontSize: 9 }}>ACTIVE</span>}
              </div>
              <div style={{ fontSize: 12, color: 'var(--muted)', lineHeight: 1.55, marginBottom: 12, minHeight: 44 }}>{d.blurb}</div>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 14 }}>
                <span className="pill pill-green">● live</span>
                {d.detailed && <span className="pill pill-blue">full physics</span>}
                <span className="pill pill-surface">{d.tiles.length} signals</span>
                {d.assets && <span className="pill pill-surface">{d.assets.length} assets</span>}
              </div>
              <button className="btn btn-primary" style={{ width: '100%', background: d.accent || undefined,
                borderColor: 'transparent', boxShadow: `0 4px 14px ${d.accent || '#7c3aed'}33` }}
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


// ── Workflow pipeline (horizontal flowchart) ──────────────────────────
function WorkflowPipeline({ findings, incidents, health, wo, cascade, onMaint }) {
  const hasFinding = findings.length > 0
  const hasIncident = incidents.length > 0
  const hasDiag = hasIncident
  const hasWO = !!wo
  const hasCascade = !!cascade
  const healthBad = health != null && health < 0.6

  const steps = [
    { id: 'sense', icon: 'ti-antenna-bars-5', label: 'Sensor\nIngestion', active: true, color: 'var(--accent-green)' },
    { id: 'detect', icon: 'ti-alert-triangle', label: 'Anomaly\nDetection', active: hasFinding, color: hasFinding ? 'var(--accent-amber)' : 'var(--hint)' },
    { id: 'classify', icon: 'ti-category', label: 'Incident\nClassification', active: hasIncident, color: hasIncident ? 'var(--accent-red)' : 'var(--hint)' },
    { id: 'diagnose', icon: 'ti-stethoscope', label: 'AI\nDiagnosis', active: hasDiag, color: hasDiag ? 'var(--accent-blue)' : 'var(--hint)' },
    { id: 'workorder', icon: 'ti-file-certificate', label: 'Work\nOrder', active: hasWO, color: hasWO ? 'var(--brand)' : 'var(--hint)' },
    { id: 'repair', icon: 'ti-tool', label: 'Guided\nRepair', active: false, color: 'var(--hint)', onClick: onMaint },
    { id: 'resolve', icon: 'ti-circle-check', label: 'Return to\nService', active: healthBad === false && hasFinding === false, color: !hasFinding ? 'var(--accent-green)' : 'var(--hint)' },
  ]

  return (
    <div className="card section-gap" style={{ padding: '14px 18px', overflow: 'hidden' }}>
      <div className="card-title" style={{ marginBottom: 10 }}><Icon n="ti-git-branch" /> Maintenance Workflow</div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 0, overflowX: 'auto', padding: '4px 0' }}>
        {steps.map((s, i) => (
          <React.Fragment key={s.id}>
            {i > 0 && (
              <div style={{ width: 32, height: 2, flexShrink: 0,
                background: steps[i - 1].active && s.active ? 'var(--brand)' : 'var(--border2)',
                transition: 'background .5s' }} />
            )}
            <div onClick={s.onClick} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6,
              minWidth: 72, cursor: s.onClick ? 'pointer' : 'default', transition: 'opacity .3s',
              opacity: s.active ? 1 : 0.4 }}>
              <div style={{ width: 40, height: 40, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 18, background: s.active ? s.color : 'var(--surface2)', color: s.active ? '#fff' : 'var(--hint)',
                border: s.active ? 'none' : '2px solid var(--border)', transition: 'all .5s',
                boxShadow: s.active ? `0 0 12px ${s.color}44` : 'none',
                animation: s.active && s.color === 'var(--accent-red)' ? 'pulse 1.5s infinite' : 'none' }}>
                <Icon n={s.icon} />
              </div>
              <div style={{ fontSize: 10, fontWeight: 600, textAlign: 'center', lineHeight: 1.3, whiteSpace: 'pre-line',
                color: s.active ? 'var(--text)' : 'var(--hint)' }}>{s.label}</div>
            </div>
          </React.Fragment>
        ))}
      </div>
    </div>
  )
}

// ── Generic, domain-aware dashboard ──────────────────────────────────
// Preset hotspot anchor points around a normalized (~3-unit) model.
const HOTSPOT_POS = [[1.1, 0.2, 0], [-1.1, 0, 0], [0, 1.1, 0.2], [0.2, -0.9, 0.4], [-0.4, -0.4, -1.0], [0.4, 0.3, 1.0]]
const hotspotsFor = (domain) => tilesFor(domain).slice(0, 6).map((s, i) => [s, HOTSPOT_POS[i]])

function Dashboard({ ctx }) {
  const { tenant, domain, source, isLive, meta, machineName, twin, stepLive, modelUrl, claudeOn, openMaint, setSimFault,
    running, toggleRunning, aiMode, toggleAiMode } = ctx
  const live = twin?.latest || {}
  const h = twin?.health
  const backendFindings = twin?.findings || []
  const incidents = twin?.incidents || []
  const tiles = tilesFor(domain)
  // supplement backend findings with client-derived ones from live telemetry —
  // this ensures findings appear for live twins whose backend hasn't yet surfaced them,
  // and for sim twins at any health level when sensors breach warn/crit thresholds
  const existingSigs = new Set(backendFindings.map(f => f.signal).filter(Boolean))
  const findings = [
    ...backendFindings,
    ...tiles
      .filter(s => live[s] != null && !existingSigs.has(s))
      .map(s => {
        const sev = sevClass(s, live[s]); if (!sev) return null
        const m = SIG[s]
        return {
          displayName: `${m.label} ${sev === 'crit' ? 'out of limits' : 'drifting out of band'}`,
          severity: sev === 'crit' ? 'critical' : 'warning',
          message: `${m.label} at ${fmt(live[s])}${m.unit ? ' ' + m.unit : ''} — ${sev === 'crit' ? 'breached threshold' : 'approaching limit'}.`,
          signal: s,
        }
      })
      .filter(Boolean),
  ]
  const headlineSig = tiles[0]
  const headline = SIG[headlineSig]
  const risk = h == null ? null : Math.round((1 - h) * 100)

  // animated count-up for KPI values
  const animRisk = useCountUp(risk ?? 0)
  const animFindings = useCountUp(findings.length)

  // sensor history buffer for sparklines (last 30 readings per signal)
  const historyRef = useRef({})
  useEffect(() => {
    if (!live || Object.keys(live).length === 0) return
    const hist = historyRef.current
    for (const [k, v] of Object.entries(live)) {
      if (v == null) continue
      if (!hist[k]) hist[k] = []
      hist[k].push(v)
      if (hist[k].length > 30) hist[k].shift()
    }
  }, [live])

  // ── AI co-pilot: unified chat + auto-narration ─────────────────────
  const twinRef = useRef(twin); twinRef.current = twin
  const [copilotMsgs, setCopilotMsgs] = useState([])
  const [copilotInput, setCopilotInput] = useState('')
  const [copilotBusy, setCopilotBusy] = useState(false)
  const copilotEndRef = useRef(null)

  // auto-narrate — appears as AI messages in the chat. In stub mode this is a
  // local, zero-token observation (and runs less often); agent mode calls Claude.
  useEffect(() => {
    if (!source) return
    const stub = aiMode !== 'agent'
    const tick = async () => {
      const tw = twinRef.current
      if (!tw || !tw.latest) return
      if (stub) {
        const text = stubNarration({ domain, machineName, latest: tw.latest, findings: tw.findings || [], health: tw.health })
        setCopilotMsgs(prev => [...prev, { role: 'auto', text, ts: new Date().toLocaleTimeString() }].slice(-20))
        return
      }
      try {
        const r = await api.narrateSnapshot({ machine: machineName, latest: tw.latest,
          findings: tw.findings || [], health: tw.health })
        if (r?.narration) setCopilotMsgs(prev => [...prev, { role: 'auto', text: r.narration, ts: new Date().toLocaleTimeString() }].slice(-20))
      } catch {}
    }
    tick()
    const t = setInterval(tick, stub ? 20000 : 10000)
    return () => clearInterval(t)
  }, [source, domain, machineName, aiMode])

  // scroll within the chat container only — scrollIntoView scrolls the whole page
  useEffect(() => {
    const el = copilotEndRef.current?.parentElement
    if (el) el.scrollTop = el.scrollHeight
  }, [copilotMsgs])

  async function sendCopilotMsg() {
    const msg = copilotInput.trim()
    if (!msg) return
    setCopilotMsgs(prev => [...prev, { role: 'user', text: msg, ts: new Date().toLocaleTimeString() }])
    setCopilotInput('')
    // stub mode: instant local answer, no tokens
    if (aiMode !== 'agent') {
      const text = stubChatReply(msg, { domain, machineName, latest: live, findings, health: h })
      setCopilotMsgs(prev => [...prev, { role: 'assistant', text, ts: new Date().toLocaleTimeString() }])
      return
    }
    setCopilotBusy(true)
    try {
      const history = copilotMsgs.filter(m => m.role !== 'auto').map(m => ({
        role: m.role === 'user' ? 'user' : 'assistant', content: m.text
      }))
      history.push({ role: 'user', content: msg })
      const r = await api.dashboardChat({ machine: machineName, messages: history,
        snapshot: { latest: live, findings, health: h } })
      setCopilotMsgs(prev => [...prev, { role: 'assistant', text: r.reply, ts: new Date().toLocaleTimeString() }])
    } catch (e) {
      setCopilotMsgs(prev => [...prev, { role: 'assistant', text: 'Sorry, I could not process that.', ts: new Date().toLocaleTimeString() }])
    }
    setCopilotBusy(false)
  }

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
    // load fault catalogue for ALL domains (live and simulated)
    api.twinFaults(domain).then(r => setFaults(r?.faults || [])).catch(() => {})
  }, [domain])
  const injectFault = async (f) => {
    const faultId = f === 'none' ? '' : f
    setFault(faultId)
    if (isLive) {
      // live twin: push fault into the physics engine
      try { await api.step({ tenant, fault: f || 'none', severity: 1.0 }) } catch {}
    } else if (setSimFault) {
      // simulated twin: bias the frontend simulation
      setSimFault(faultId || null)
    }
  }

  return (
    <div className="panel">
      <div className="panel-header">
        <div>
          <div className="panel-title">Live Operations</div>
          <div className="panel-subtitle">{machineName} · streaming sensor telemetry in real time</div>
        </div>
        <div className="panel-actions">
          <button className={`btn ${running ? '' : 'btn-primary'}`} onClick={toggleRunning}
            title={running ? 'Stop the twin (freeze telemetry)' : 'Start the twin'}>
            <Icon n={running ? 'ti-player-pause' : 'ti-player-play'} /> {running ? 'Stop twin' : 'Start twin'}
          </button>
          <button className="btn btn-primary repair-cta" onClick={openMaint}
            title="Enter AI Maintenance Director">
            <Icon n="ti-robot" /> Repair with AI
          </button>
          {isLive && running && <>
            <span className="hint" style={{ alignSelf: 'center' }}>{throttleLabel}:</span>
            <button className="btn" onClick={() => stepLive(0.5)}>Low</button>
            <button className="btn" onClick={() => stepLive(0.75)}>Mid</button>
            <button className="btn btn-primary" onClick={() => stepLive(1.0)}>High</button>
          </>}
          {faults.length > 0 && (
            <select className="select" style={{ width: 'auto', minWidth: 150 }}
              value={fault} onChange={e => injectFault(e.target.value)}>
              <option value="">Inject fault…</option>
              <option value="none">✓ Healthy (clear)</option>
              {faults.map(f => <option key={f.id} value={f.id}>⚠ {f.label}</option>)}
            </select>
          )}
        </div>
      </div>

      {/* KPIs — the dashboard summary, on top */}
      <div className="grid-4 section-gap">
        <div className="card kpi"><div className="card-label">Twin Health</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <HealthRing value={h} size={56} stroke={5} />
            <div><div className="card-value" style={{ color: hColor(h), fontSize: 22 }}>{pct(h)}</div>
              <div className="card-change">physics index</div></div>
          </div></div>
        <div className="card kpi"><div className="card-label">Risk Score</div>
          <div className="card-value">{risk == null ? '—' : Math.round(animRisk)}</div>
          <div className="card-change" style={{ color: risk >= 60 ? 'var(--accent-red)' : risk >= 30 ? 'var(--accent-amber)' : 'var(--accent-green)', fontWeight: 600 }}>
            {risk >= 60 ? 'HIGH' : risk >= 30 ? 'ELEVATED' : 'LOW'}</div></div>
        <div className="card kpi"><div className="card-label">Active Findings</div>
          <div className="card-value" style={{ color: findings.length > 0 ? 'var(--accent-red)' : 'var(--accent-amber)' }}>{Math.round(animFindings)}</div>
          <div className="card-change">{incidents.length} incident(s)</div></div>
        {headline && <div className="card kpi"><div className="card-label">{headline.label}</div>
          <div className="card-value" style={{ color: sevClass(headlineSig, live[headlineSig]) === 'crit' ? 'var(--accent-red)' : 'var(--text)' }}>
            {fmt(live[headlineSig])}<span style={{ fontSize: 14 }}>{headline.unit ? ' ' + headline.unit : ''}</span></div>
          <div className="card-change">{headline.crit != null ? `limit ${headline.crit} ${headline.unit}` : headline.critLow != null ? `min ${headline.critLow} ${headline.unit}` : 'live'}</div></div>}
      </div>

      {/* Workflow pipeline — detection to resolution */}
      <WorkflowPipeline findings={findings} incidents={incidents} health={h}
        wo={wo} cascade={cascade} onMaint={openMaint} />

      {/* Twin scene — fleet twins get the live network map; otherwise the
          reconstructed GLB (Build-a-Twin) takes priority, else the turbine
          model, else the procedural domain scene. */}
      <div className="section-gap">
        {domain === 'tram-network' && isLive
          ? <NetworkMap tenant={tenant} height={460} running={running} />
          : modelUrl
          ? (domain === 'turbine-engine'
              ? <TurbineModel url={modelUrl} latest={live} height={380} health={h} />
              : <ModelViewer url={modelUrl} latest={live} hotspots={hotspotsFor(domain)} height={380}
                  badge={<><Icon n={meta.icon || 'ti-cube'} /> <b>{machineName}</b> · reconstructed</>} />)
          : domain === 'turbine-engine'
            ? <div className="hero3d" style={{ height: 380 }}>
                <div className="v-chip"><Icon n="ti-engine" /> <b>{machineName}</b></div>
                <div className="lbl"><div className="big">⬡ Gas Turbine</div>
                  Generating the 3D model from your image — <a style={{ color: '#c4b5fd', cursor: 'pointer' }} onClick={ctx.goBuild}>open Build a Twin</a>.</div>
              </div>
            : <Scene3D domain={domain} machine={machineName} live={live} height={380} />}
      </div>

      {/* Predictive alert banner (live) */}
      {isLive && alert && (
        <div className="card section-gap" style={{ borderColor: 'rgba(225,29,72,.4)', background: 'rgba(225,29,72,.06)' }}>
          <div className="card-title" style={{ color: 'var(--accent-red)' }}><Icon n="ti-alert-octagon" /> Predictive Alert</div>
          <div style={{ fontSize: 13, lineHeight: 1.7 }}>{alert}</div>
        </div>
      )}

      {/* AI Co-Pilot — unified chat: auto-narration + user Q&A */}
      {source && (
        <div className="card section-gap" style={{ display: 'flex', flexDirection: 'column' }}>
          <div className="card-title"><Icon n="ti-message-chatbot" /> AI Co-Pilot
            <span className="pill pill-green" style={{ fontSize: 9 }}>live</span>
            {/* Stub ↔ Agent toggle — stub never spends tokens while monitoring */}
            <div className="ai-toggle" style={{ marginLeft: 'auto' }} title="Stub = local, no tokens · Agent = Claude">
              <button className={aiMode !== 'agent' ? 'on' : ''} onClick={() => aiMode === 'agent' && toggleAiMode()}>
                <Icon n="ti-cpu" /> Stub</button>
              <button className={aiMode === 'agent' ? 'on' : ''} onClick={() => aiMode !== 'agent' && toggleAiMode()}>
                <Icon n="ti-sparkles" /> Agent</button>
            </div>
          </div>

          {/* chat messages */}
          <div style={{ maxHeight: 280, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 8, padding: '4px 0', marginBottom: 10 }}>
            {copilotMsgs.length === 0 && (
              <div className="empty" style={{ margin: '12px 0' }}>
                The co-pilot is observing {machineName} in real time. Auto-observations will appear here, or ask a question below.</div>
            )}
            {copilotMsgs.map((m, i) => (
              <div key={i} style={{ display: 'flex', justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start', gap: 8 }}>
                {m.role !== 'user' && (
                  <div style={{ width: 26, height: 26, borderRadius: 8, flexShrink: 0, display: 'flex', alignItems: 'center',
                    justifyContent: 'center', fontSize: 13,
                    background: m.role === 'auto' ? 'rgba(22,163,74,.12)' : 'var(--gradient)', color: m.role === 'auto' ? 'var(--accent-green)' : '#fff' }}>
                    <Icon n={m.role === 'auto' ? 'ti-antenna-bars-5' : 'ti-sparkles'} />
                  </div>
                )}
                <div style={{ maxWidth: '80%', padding: '9px 13px', fontSize: 12.5, lineHeight: 1.6,
                  borderRadius: m.role === 'user' ? '14px 4px 14px 14px' : '4px 14px 14px 14px',
                  background: m.role === 'user' ? 'var(--gradient)' : m.role === 'auto' ? 'var(--surface2)' : 'var(--surface2)',
                  color: m.role === 'user' ? '#fff' : 'var(--text)',
                  border: m.role === 'user' ? 'none' : '1px solid var(--border)' }}>
                  {m.role === 'auto' && <div style={{ fontSize: 9, color: 'var(--accent-green)', fontWeight: 700, marginBottom: 3, fontFamily: 'var(--mono)' }}>
                    OBSERVATION · {m.ts}</div>}
                  {m.role === 'assistant' && <div style={{ fontSize: 9, color: 'var(--brand)', fontWeight: 700, marginBottom: 3, fontFamily: 'var(--mono)' }}>
                    CO-PILOT · {m.ts}</div>}
                  {m.text}
                </div>
              </div>
            ))}
            {copilotBusy && <div style={{ padding: 6 }}><span className="spinner" /> Thinking...</div>}
            <div ref={copilotEndRef} />
          </div>

          {/* quick suggestions */}
          {copilotMsgs.filter(m => m.role === 'user').length === 0 && (
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 8 }}>
              {['How is the machine doing?', "What's the most concerning signal?", 'What should I check next?'].map(s => (
                <button key={s} className="chat-chip" onClick={() => { setCopilotInput(s); }}>{s}</button>
              ))}
            </div>
          )}

          {/* input */}
          <div style={{ display: 'flex', gap: 8 }}>
            <input value={copilotInput} onChange={e => setCopilotInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && sendCopilotMsg()}
              placeholder={`Ask about ${machineName}…`}
              style={{ flex: 1, padding: '10px 14px', borderRadius: 10, border: '1px solid var(--border)',
                fontSize: 13, outline: 'none', background: 'var(--surface)', fontFamily: 'var(--font)' }} />
            <button className="btn btn-primary" onClick={sendCopilotMsg} disabled={copilotBusy || !copilotInput.trim()}>
              <Icon n="ti-send" /></button>
          </div>
        </div>
      )}

      {/* Live telemetry (generic, domain-driven) */}
      <div className="card section-gap">
        <div className="card-title"><Icon n="ti-activity" /> Live Telemetry
          <span className="pill pill-green">● streaming</span></div>
        <div className="sensor-grid">
          {tiles.filter(s => live[s] != null).map(s => {
            const sev = sevClass(s, live[s])
            const sparkColor = sev === 'crit' ? '#e11d48' : sev === 'warn' ? '#d97706' : '#7c3aed'
            return (
              <div key={s} className={`sensor-card ${sev}`} style={{ position: 'relative' }}>
                <span className="live-indicator" />
                <div className="sensor-label">{SIG[s]?.label || s}</div>
                <div><span className="sensor-value">{fmt(live[s])}</span><span className="sensor-unit">{SIG[s]?.unit}</span></div>
                <Sparkline data={historyRef.current[s]} color={sparkColor} />
              </div>
            )
          })}
        </div>
      </div>

      {/* Signal anomaly heatmap */}
      {source && Object.keys(live).length > 0 && (
        <div className="card section-gap">
          <div className="card-title"><Icon n="ti-grid-dots" /> Signal Heatmap <span className="pill pill-surface">last 60s</span></div>
          <Heatmap signals={tiles.filter(s => live[s] != null)} live={live} />
        </div>
      )}

      {/* Findings + incidents */}
      <div className="grid-2">
        <div className="card">
          <div className="card-title"><Icon n="ti-alert-triangle" /> Active Findings
            <span className={`pill ${findings.length > 0 ? 'pill-red' : 'pill-surface'}`}>{findings.length}</span></div>
          {findings.length === 0
            ? <div className="empty">No findings — within limits.</div>
            : <>
                <div className="event-list">{findings.slice(0, 6).map((f, i) => (
                  <div key={i} className="event-item" style={{ '--i': i }}>
                    <div className={`event-icon ${f.severity === 'critical' ? 'ev-crit' : 'ev-warn'}`}><Icon n="ti-alert-triangle" /></div>
                    <div className="event-body"><div className="event-title">{f.displayName || f.behaviorId || 'finding'}</div>
                      <div className="event-meta">{f.message}</div></div>
                  </div>))}</div>
                <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid var(--border)' }}>
                  <button className="btn btn-primary repair-cta" style={{ width: '100%', justifyContent: 'center' }}
                    onClick={openMaint}>
                    <Icon n="ti-robot" /> Launch AI Repair Session
                  </button>
                </div>
              </>}
        </div>
        <div className="card">
          <div className="card-title"><Icon n="ti-git-merge" /> Incidents
            <span className="pill pill-surface">{incidents.length}</span></div>
          {incidents.length === 0
            ? <div className="empty">No incidents grouped yet.</div>
            : <div className="event-list">{incidents.map((inc, i) => (
                <div key={i} className="event-item" style={{ borderColor: 'rgba(225,29,72,.25)', '--i': i }}>
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
              <CascadeGraph text={cascade} findings={findings} />
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
