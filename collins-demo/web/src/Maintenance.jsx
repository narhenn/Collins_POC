// Maintenance.jsx — the "AI Maintenance Director": a full-screen, cinematic
// autonomous-maintenance takeover. The AI is no longer in a chat box — it takes
// control of the digital twin, flies the camera to the fault, explains the root
// cause, and walks the repair step-by-step while telemetry recovers in real time.
//
// Design note (per brief): no flying-bot gimmick. The AI presence is a fixed
// holographic "core", and everything is screen-space animation, component
// highlights, and method panels beside the machine — all GPU-cheap and smooth.
import React, { useEffect, useMemo, useRef, useState } from 'react'
import { createViewer } from './scene/engine.js'
import { SIG, sevClass, fmt } from './lib.jsx'
import './Maintenance.css'

const I = ({ n }) => <i className={`ti ${n}`} />

// ── map a signal → the EDM subsystem (3-D asset) that owns it ─────────
const SUB_META = {
  'EDM-1':   { label: 'Wire EDM Machine',    icon: 'ti-grill' },
  'GEN-1':   { label: 'Discharge Generator', icon: 'ti-bolt' },
  'DIE-1':   { label: 'Dielectric & Flushing', icon: 'ti-droplet' },
  'WIRE-1':  { label: 'Wire Transport',      icon: 'ti-line-dashed' },
  'GUIDE-1': { label: 'Guides & Axes',       icon: 'ti-square' },
}
const SUB_ORDER = ['GEN-1', 'DIE-1', 'WIRE-1', 'GUIDE-1']

function subForSignal(sig = '') {
  if (/dielectric|Flow|Pressure/i.test(sig)) return 'DIE-1'
  if (/wireBreak|wireTension|wireFeed/i.test(sig)) return 'WIRE-1'
  if (/short|gapVoltage|peakCurrent|Energy|pulse|spark(?!Gap)/i.test(sig)) return 'GEN-1'
  if (/wireWear|surfaceRough|sparkGap/i.test(sig)) return 'GUIDE-1'
  return 'EDM-1'
}

// Degraded fallbacks so the telemetry has a dramatic "before" even offline.
const DEGRADED = {
  'edm:dielectricTemperature': 33, 'edm:dielectricConductivity': 24, 'edm:dielectricFlow': 2.4,
  'edm:dielectricPressure': 2.6, 'edm:shortCircuitRate': 22, 'edm:cuttingSpeed': 96,
  'edm:gapVoltage': 23, 'edm:peakCurrent': 27, 'edm:wireBreakRisk': 76, 'edm:wireTension': 5.4,
  'edm:wireFeedRate': 5, 'edm:wireWear': 88, 'edm:surfaceRoughnessRa': 3.4,
}

// Per-subsystem repair plans (root cause + telemetry targets + ordered steps).
const PLANS = {
  'DIE-1': {
    title: 'Dielectric & Flushing — Overheat & Flushing Loss',
    rootCause: [
      { icon: 'ti-temperature', text: '<b>Dielectric temperature high</b> — chiller under-performing' },
      { icon: 'ti-droplet', text: '<b>Flushing efficiency falls</b> — debris not cleared from the gap' },
      { icon: 'ti-plug-connected-x', text: '<b>Discharge turns unstable</b> — short-circuit rate climbs' },
      { icon: 'ti-alert-triangle', text: '<b>Wire-break risk & poor surface finish</b>' },
      { icon: 'ti-player-stop', text: '<b>Cut aborts / wire snap</b> if left untreated' },
    ],
    signals: [['edm:dielectricTemperature', 24], ['edm:dielectricConductivity', 10],
      ['edm:dielectricFlow', 6], ['edm:shortCircuitRate', 5], ['edm:cuttingSpeed', 150]],
    steps: [
      { t: 'Diagnose dielectric loop', d: 'Read chiller, conductivity and flow sensors to localise the loss.', f: 'DIE-1', tool: 'Sensor suite', time: 18, diff: 'Low' },
      { t: 'Lockout / isolate machine power', d: 'Apply LOTO before opening the dielectric housing.', f: 'EDM-1', tool: 'LOTO kit', time: 30, diff: 'Low', safety: true },
      { t: 'Inspect chiller & filter housing', d: 'Check pump pressure and the filter differential.', f: 'DIE-1', tool: 'Inspection', time: 40, diff: 'Low' },
      { t: 'Replace dielectric filter cartridge', d: 'Swap the clogged cartridge; reseat the O-ring seal.', f: 'DIE-1', tool: '8 mm hex · filter wrench', time: 90, diff: 'Medium' },
      { t: 'Recharge fluid & de-ioniser resin', d: 'Top up dielectric and restore resin to drop conductivity.', f: 'DIE-1', tool: 'Resin · fluid', time: 70, diff: 'Medium' },
      { t: 'Re-prime flushing & set pressure', d: 'Purge air and set upper/lower flush to spec.', f: 'EDM-1', tool: 'Pressure gauge', time: 45, diff: 'Low' },
      { t: 'Test cut & verify stability', d: 'Run a coupon; confirm temp, flow and gap are nominal.', f: 'EDM-1', tool: 'Test coupon', time: 60, diff: 'Low' },
    ],
  },
  'GEN-1': {
    title: 'Discharge Generator — Short-Circuiting',
    rootCause: [
      { icon: 'ti-plug-connected-x', text: '<b>Short-circuit rate rising</b> — contaminated power feed' },
      { icon: 'ti-bolt-off', text: '<b>Gap voltage collapses</b> — discharge cannot ionise cleanly' },
      { icon: 'ti-slice', text: '<b>Material-removal rate drops</b> — cutting speed falls' },
      { icon: 'ti-alert-triangle', text: '<b>Heat & wire-break risk climb</b>' },
      { icon: 'ti-player-stop', text: '<b>Generator fault / wire snap</b> if untreated' },
    ],
    signals: [['edm:shortCircuitRate', 4], ['edm:gapVoltage', 52], ['edm:peakCurrent', 18],
      ['edm:wireBreakRisk', 15], ['edm:cuttingSpeed', 150]],
    steps: [
      { t: 'Diagnose discharge circuit', d: 'Inspect short-circuit telemetry and gap voltage trace.', f: 'GEN-1', tool: 'Sensor suite', time: 18, diff: 'Low' },
      { t: 'Lockout / isolate machine power', d: 'Apply LOTO before touching the power feed.', f: 'EDM-1', tool: 'LOTO kit', time: 30, diff: 'Low', safety: true },
      { t: 'Inspect power-feed contacts', d: 'Check the feed contacts and bus connections for burn.', f: 'GEN-1', tool: 'Inspection', time: 40, diff: 'Medium' },
      { t: 'Clean / replace feed contacts', d: 'Dress or swap pitted contacts; clean the gap path.', f: 'GEN-1', tool: 'Contact kit', time: 80, diff: 'Medium' },
      { t: 'Re-tune pulse parameters', d: 'Reset Ton/Toff and peak current to a stable regime.', f: 'GEN-1', tool: 'CNC pendant', time: 60, diff: 'Medium' },
      { t: 'Verify gap stability', d: 'Confirm voltage and short-circuit rate are nominal.', f: 'EDM-1', tool: 'Scope', time: 45, diff: 'Low' },
      { t: 'Test cut & sign off', d: 'Run a coupon and confirm cutting speed recovered.', f: 'EDM-1', tool: 'Test coupon', time: 60, diff: 'Low' },
    ],
  },
  'WIRE-1': {
    title: 'Wire Transport — Tension Loss & Break Risk',
    rootCause: [
      { icon: 'ti-line-dashed', text: '<b>Wire tension below spec</b> — servo / brake slipping' },
      { icon: 'ti-wave-sine', text: '<b>Wire vibrates in the gap</b> — geometry error grows' },
      { icon: 'ti-plug-connected-x', text: '<b>Short-circuits increase</b> — unstable contact' },
      { icon: 'ti-alert-triangle', text: '<b>Wire-break risk climbs sharply</b>' },
      { icon: 'ti-player-stop', text: '<b>Wire snap & re-thread</b> if untreated' },
    ],
    signals: [['edm:wireTension', 15], ['edm:wireBreakRisk', 12], ['edm:wireFeedRate', 9],
      ['edm:shortCircuitRate', 5], ['edm:cuttingSpeed', 150]],
    steps: [
      { t: 'Diagnose wire path', d: 'Read tension, feed-rate and break-risk telemetry.', f: 'WIRE-1', tool: 'Sensor suite', time: 18, diff: 'Low' },
      { t: 'Lockout / isolate machine power', d: 'Apply LOTO before opening the wire path.', f: 'EDM-1', tool: 'LOTO kit', time: 30, diff: 'Low', safety: true },
      { t: 'Inspect spool & tension servo', d: 'Check brake, spool drag and the tension roller.', f: 'WIRE-1', tool: 'Inspection', time: 40, diff: 'Medium' },
      { t: 'Re-thread / replace wire', d: 'Load fresh brass wire and re-thread the guides.', f: 'WIRE-1', tool: 'Threader', time: 85, diff: 'Medium' },
      { t: 'Calibrate tension & feed', d: 'Set tension to spec and verify feed-rate tracking.', f: 'WIRE-1', tool: 'Tension meter', time: 60, diff: 'Medium' },
      { t: 'Verify gap stability', d: 'Confirm break-risk and short-circuit rate dropped.', f: 'EDM-1', tool: 'Scope', time: 45, diff: 'Low' },
      { t: 'Test cut & sign off', d: 'Run a coupon; confirm a clean, stable cut.', f: 'EDM-1', tool: 'Test coupon', time: 60, diff: 'Low' },
    ],
  },
  'GUIDE-1': {
    title: 'Guides & Axes — Guide Wear',
    rootCause: [
      { icon: 'ti-circle-dashed', text: '<b>Diamond guide wear high</b> — wire positioning drifts' },
      { icon: 'ti-wave-saw-tool', text: '<b>Surface roughness rises</b> — finish out of tolerance' },
      { icon: 'ti-ruler-measure', text: '<b>Geometry error grows</b> on the cut profile' },
      { icon: 'ti-alert-triangle', text: '<b>Scrap risk & rework</b> increase' },
      { icon: 'ti-player-stop', text: '<b>Part rejection</b> if untreated' },
    ],
    signals: [['edm:wireWear', 5], ['edm:surfaceRoughnessRa', 1.4], ['edm:cuttingSpeed', 150]],
    steps: [
      { t: 'Diagnose guides & axes', d: 'Read wire-wear and surface-roughness telemetry.', f: 'GUIDE-1', tool: 'Sensor suite', time: 18, diff: 'Low' },
      { t: 'Lockout / isolate machine power', d: 'Apply LOTO before accessing the guide head.', f: 'EDM-1', tool: 'LOTO kit', time: 30, diff: 'Low', safety: true },
      { t: 'Inspect diamond guides', d: 'Check upper/lower guides for grooving and wear.', f: 'GUIDE-1', tool: 'Loupe', time: 40, diff: 'Medium' },
      { t: 'Replace worn guide inserts', d: 'Swap the worn diamond inserts; clean the seats.', f: 'GUIDE-1', tool: 'Guide kit', time: 80, diff: 'Medium' },
      { t: 'Re-align U/V axes', d: 'Square the wire and re-reference the axes.', f: 'GUIDE-1', tool: 'Alignment jig', time: 65, diff: 'High' },
      { t: 'Verify squareness', d: 'Confirm geometry and roughness are in tolerance.', f: 'EDM-1', tool: 'Gauge', time: 45, diff: 'Low' },
      { t: 'Test cut & sign off', d: 'Run a coupon; confirm finish recovered.', f: 'EDM-1', tool: 'Test coupon', time: 60, diff: 'Low' },
    ],
  },
}

function healthyTarget(key) {
  const m = SIG[key] || {}
  if (m.warn != null) return +(m.warn * 0.62).toFixed(2)
  if (m.warnLow != null) return +(m.warnLow * 1.5).toFixed(2)
  if (m.crit != null) return +(m.crit * 0.5).toFixed(2)
  if (m.critLow != null) return +(m.critLow * 1.8).toFixed(2)
  return 0
}

// Build the active plan from the live fault (EDM) or generic findings (others).
function buildPlan(domain, twin) {
  const findings = (twin?.findings || []).slice()
    .sort((a, b) => (b.severity === 'critical') - (a.severity === 'critical'))
  const worst = findings[0]
  const faultSig = worst?.signal
  if (domain === 'edm-machine') {
    let sub = subForSignal(faultSig || '')
    if (!PLANS[sub]) sub = 'DIE-1'           // EDM-1 / unknown → default to the dielectric plan
    return { ...PLANS[sub], sub, focusSub: sub }
  }
  // generic plan for the facility / turbine twins
  const sigs = findings.slice(0, 5).map(f => f.signal).filter(Boolean)
  const signals = (sigs.length ? sigs : Object.keys(twin?.latest || {}).slice(0, 4))
    .map(k => [k, healthyTarget(k)])
  return {
    sub: 'EDM-1', focusSub: null,
    title: worst?.displayName || 'Restore machine to nominal',
    rootCause: [
      { icon: 'ti-alert-triangle', text: `<b>${worst?.displayName || 'Out-of-band signal'}</b>` },
      { icon: 'ti-activity', text: 'Degradation spreads to coupled subsystems' },
      { icon: 'ti-trending-down', text: 'Overall health falls below target' },
      { icon: 'ti-player-stop', text: '<b>Unplanned downtime</b> if untreated' },
    ],
    signals,
    steps: [
      { t: 'Diagnose the fault', d: 'Read the affected telemetry and localise the cause.', f: null, tool: 'Sensor suite', time: 20, diff: 'Low' },
      { t: 'Isolate / make safe', d: 'Apply lockout before any intervention.', f: null, tool: 'LOTO kit', time: 30, diff: 'Low', safety: true },
      { t: 'Inspect the component', d: 'Confirm the failure mode on the affected asset.', f: null, tool: 'Inspection', time: 45, diff: 'Medium' },
      { t: 'Repair / replace', d: 'Restore the failed part to serviceable condition.', f: null, tool: 'Tooling', time: 90, diff: 'Medium' },
      { t: 'Recalibrate', d: 'Bring the subsystem back to its set-point.', f: null, tool: 'Calibration', time: 60, diff: 'Medium' },
      { t: 'Functional test', d: 'Run the asset and confirm signals are nominal.', f: null, tool: 'Test', time: 50, diff: 'Low' },
      { t: 'Verify & sign off', d: 'Confirm health is restored and close the work order.', f: null, tool: '—', time: 30, diff: 'Low' },
    ],
  }
}

const mmss = (s) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')}`
const lerp = (a, b, t) => a + (b - a) * t

export default function Maintenance({ domain = 'edm-machine', machineName = 'Wire EDM Machine', twin, claudeOn, onExit }) {
  const hostRef = useRef(null)
  const viewerRef = useRef(null)
  const calloutRef = useRef(null)
  const startRef = useRef(Date.now())
  const eventsRef = useRef([])

  const plan = useMemo(() => buildPlan(domain, twin), [domain, twin?.findings?.length])
  const steps = plan.steps
  const total = steps.length

  const [stage, setStage] = useState('intro')          // intro | scan | diagnose | repair | complete
  const [introOut, setIntroOut] = useState(false)
  const [rcLit, setRcLit] = useState(0)                 // root-cause nodes lit
  const [step, setStep] = useState(0)                   // current repair step (0-based)
  const [playing, setPlaying] = useState(true)
  const [voice, setVoice] = useState(false)
  const [focusSub, setFocusSub] = useState(plan.focusSub)
  const [subtitle, setSubtitle] = useState('')
  const [typed, setTyped] = useState(0)
  const [scan, setScan] = useState(false)

  // before/after telemetry per signal
  const tele = useMemo(() => plan.signals.map(([key, after]) => {
    const before = twin?.latest?.[key] ?? DEGRADED[key] ?? after
    return { key, after, before, meta: SIG[key] || { label: key, unit: '' } }
  }), [plan, twin])

  // recovery fraction (drives telemetry + health)
  const frac = stage === 'complete' ? 1 : stage === 'repair' ? Math.min(1, (step + 1) / total) : 0
  const startHealth = twin?.health != null ? twin.health : 0.23
  const health = stage === 'complete' ? 1 : lerp(startHealth, 0.99, frac)

  // ── mount the cinematic 3-D viewer (scene loads behind the intro) ──
  useEffect(() => {
    if (!hostRef.current) return
    let v
    try { v = createViewer(hostRef.current, { domain, machine: machineName, cinematic: true }) }
    catch (e) { /* graceful: HUD still works without the 3-D */ }
    viewerRef.current = v
    return () => { try { v && v.dispose() } catch {} viewerRef.current = null }
  }, [domain, machineName])

  // keep the glued callout pinned to the focused subsystem every frame
  useEffect(() => {
    let raf
    const tick = () => {
      raf = requestAnimationFrame(tick)
      const node = calloutRef.current, v = viewerRef.current
      if (!node || !v || !focusSub || !(stage === 'diagnose' || stage === 'repair')) {
        if (node) node.style.opacity = '0'; return
      }
      const p = v.worldToScreen(focusSub)
      if (!p || !p.visible) { node.style.opacity = '0'; return }
      node.style.transform = `translate(${p.x}px, ${p.y}px) translate(-50%,-100%)`
      node.style.opacity = '1'
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [focusSub, stage])

  const focus = (id) => { setFocusSub(id); viewerRef.current && viewerRef.current.focusAsset(id) }
  const colorSubsystems = (allGood) => {
    const v = viewerRef.current; if (!v) return
    const up = {}
    SUB_ORDER.forEach(id => { up[id] = { status: allGood ? 'ok' : (id === plan.focusSub ? 'crit' : 'ok') } })
    up['EDM-1'] = { status: allGood ? 'ok' : (plan.focusSub ? 'warn' : 'crit') }
    v.updateAssets(up)
  }

  const say = (txt) => { setSubtitle(txt); eventsRef.current.push({ t: (Date.now() - startRef.current) / 1000, label: txt, stage, step }) }

  // ── stage choreography ──
  useEffect(() => {
    const timers = []
    const at = (ms, fn) => timers.push(setTimeout(fn, ms))
    if (stage === 'intro') {
      say('Maintenance mode activated. Taking control of the digital twin.')
      at(2300, () => setIntroOut(true))
      at(3100, () => setStage('scan'))
    } else if (stage === 'scan') {
      setScan(true)
      say(`Scanning ${machineName}. Generating a live health map across all subsystems.`)
      viewerRef.current && viewerRef.current.resetView(1.4)
      at(1500, () => colorSubsystems(false))
      at(3000, () => { setScan(false); setStage('diagnose') })
    } else if (stage === 'diagnose') {
      if (plan.focusSub) focus(plan.focusSub)
      const subLabel = SUB_META[plan.focusSub]?.label || 'the affected component'
      say(`Fault isolated to ${subLabel}. Projecting the root-cause chain.`)
      plan.rootCause.forEach((_, i) => at(700 + i * 650, () => setRcLit(i + 1)))
      at(900 + plan.rootCause.length * 650 + 900, () => { setStep(0); setStage('repair') })
    } else if (stage === 'repair') {
      // (per-step effect below drives camera + narration)
    } else if (stage === 'complete') {
      colorSubsystems(true)
      viewerRef.current && viewerRef.current.resetView(1.8)
      say('Diagnostic re-scan passed. All subsystems nominal. Maintenance complete.')
    }
    return () => timers.forEach(clearTimeout)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stage])

  // per-step choreography while repairing
  useEffect(() => {
    if (stage !== 'repair') return
    const s = steps[step]; if (!s) return
    focus(s.f || plan.focusSub || 'EDM-1')
    say(`Step ${step + 1} of ${total}: ${s.t}. ${s.d}`)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stage, step])

  // auto-advance the repair when playing
  useEffect(() => {
    if (stage !== 'repair' || !playing) return
    const s = steps[step]; if (!s) return
    const dur = Math.max(2600, Math.min(5200, s.time * 55))
    const t = setTimeout(() => {
      if (step + 1 >= total) setStage('complete')
      else setStep(step + 1)
    }, dur)
    return () => clearTimeout(t)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stage, step, playing])

  // typewriter for the subtitle
  useEffect(() => {
    setTyped(0)
    if (!subtitle) return
    let i = 0
    const id = setInterval(() => { i += 2; setTyped(i); if (i >= subtitle.length) clearInterval(id) }, 16)
    return () => clearInterval(id)
  }, [subtitle])

  // optional voice (opt-in; guarded)
  useEffect(() => {
    if (!voice || !subtitle || !('speechSynthesis' in window)) return
    try {
      window.speechSynthesis.cancel()
      const u = new SpeechSynthesisUtterance(subtitle)
      u.rate = 1.04; u.pitch = 1.0
      window.speechSynthesis.speak(u)
    } catch {}
    return () => { try { window.speechSynthesis.cancel() } catch {} }
  }, [subtitle, voice])

  // escape to exit
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onExit && onExit() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onExit])

  // remaining ETA
  const remaining = stage === 'complete' ? 0 : steps.slice(stage === 'repair' ? step : 0).reduce((a, s) => a + s.time, 0)
  const speaking = stage !== 'complete'

  const goStep = (i) => { setStage('repair'); setPlaying(false); setStep(Math.max(0, Math.min(total - 1, i))) }
  const subsysRows = SUB_ORDER.map(id => ({
    id, label: SUB_META[id].label,
    status: stage === 'complete' ? 'ok' : (id === plan.focusSub ? (stage === 'repair' || stage === 'diagnose' ? 'crit' : 'crit') : 'ok'),
  }))
  const statusColor = (s) => s === 'crit' ? 'var(--mx-red)' : s === 'warn' ? 'var(--mx-amber)' : 'var(--mx-green)'

  // focused subsystem live metrics (for the glued callout)
  const focusTele = tele.filter(x => subForSignal(x.key) === focusSub).slice(0, 2)
  const cur = (x) => lerp(x.before, x.after, frac)

  return (
    <div className="mx-root" style={{ '--mx-dim-level': (stage === 'diagnose' || stage === 'repair') ? 0.9 : 0.25 }}>
      <div className="mx-veil" />

      {/* ── intro takeover ── */}
      {stage === 'intro' && (
        <div className={`mx-intro ${introOut ? 'out' : ''}`}>
          <AICore size={150} speaking />
          <div>
            <div className="mx-intro-title">AI Maintenance Director</div>
          </div>
          <div className="mx-intro-sub">Taking control of digital twin</div>
          <div className="mx-intro-bar"><i /></div>
        </div>
      )}

      {/* ── main stage ── */}
      <div className="mx-stage">
        {/* top bar */}
        <div className="mx-top">
          <div className="mx-badge"><AICore size={32} speaking={speaking} />
            <div><b>AI Maintenance Director</b><br /><small>Autonomous mode</small></div>
          </div>
          <div className="mx-top-spacer" />
          <div className="mx-chip"><span className="dot" style={{ background: 'var(--mx-cyan)' }} />{machineName}</div>
          <div className="mx-chip">Agent <b>{claudeOn ? 'Claude' : 'on-board'}</b></div>
          <div className="mx-exit" onClick={onExit}><I n="ti-x" /> Exit</div>
        </div>

        {/* LEFT rail — flow / root cause */}
        <div className="mx-left">
          <div className="mx-card">
            <div className="mx-h"><I n="ti-affiliate" /> Root cause<span className="tag">{plan.sub}</span></div>
            <div className="mx-rc">
              {plan.rootCause.map((n, i) => (
                <React.Fragment key={i}>
                  {i > 0 && <div className={`mx-rcarrow ${rcLit > i ? 'lit' : ''}`} />}
                  <div className={`mx-rcn ${rcLit > i ? 'lit' : ''}`}>
                    <div className="ic"><I n={n.icon} /></div>
                    <div className="tx" dangerouslySetInnerHTML={{ __html: n.text }} />
                  </div>
                </React.Fragment>
              ))}
            </div>
          </div>

          <div className="mx-card flush">
            <div className="mx-h"><I n="ti-route" /> Repair plan<span className="tag">{total} steps</span></div>
            <div className="mx-flow">
              {steps.map((s, i) => {
                const st = stage === 'complete' || i < step ? 'done' : (stage === 'repair' && i === step) ? 'active' : ''
                return (
                  <div key={i} className={`mx-fnode ${st}`} onClick={() => goStep(i)}>
                    <div className="rail">
                      <div className="bead">{st === 'done' ? '✓' : s.safety ? '!' : i + 1}</div>
                      <div className="wire" />
                    </div>
                    <div className="body">
                      <div className="ftitle">{s.t}{s.safety && <span className="safety">SAFETY</span>}</div>
                      {st === 'active' ? (
                        <div className="mx-detail">
                          <div className="fsub" style={{ marginBottom: 8 }}>{s.d}</div>
                          <div className="mx-meta">
                            <div><span>Tool</span><br /><b>{s.tool}</b></div>
                            <div><span>Est. time</span><br /><b>{mmss(s.time)}</b></div>
                            <div><span>Difficulty</span><br /><b>{s.diff}</b></div>
                            <div><span>Component</span><br /><b>{SUB_META[s.f || plan.focusSub || 'EDM-1']?.label || '—'}</b></div>
                          </div>
                        </div>
                      ) : <div className="fsub">{s.d}</div>}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>

        {/* CENTER — the 3-D twin (AI controls the camera) */}
        <div className="mx-center">
          <div ref={hostRef} className="mx-canvas hero3d scene3d-host" />
          <div className={`mx-scan ${scan ? 'on' : ''}`}><i /><b /></div>
          {/* glued component callout */}
          <div ref={calloutRef} className={`mx-callout ${stage === 'repair' || stage === 'complete' ? 'repair' : ''}`} style={{ opacity: 0 }}>
            <div className="lab">
              <div className="nm"><I n={SUB_META[focusSub]?.icon || 'ti-cube'} /> {SUB_META[focusSub]?.label || ''}</div>
              {focusTele.length > 0 && <div className="mm">
                {focusTele.map(x => <span key={x.key}>{x.meta.label}<b>{fmt(cur(x))}{x.meta.unit ? ' ' + x.meta.unit : ''}</b></span>)}
              </div>}
            </div>
            <div className="stem" /><div className="ring" />
          </div>
        </div>

        {/* RIGHT rail — health + telemetry */}
        <div className="mx-right">
          <div className="mx-card">
            <div className="mx-h"><I n="ti-heartbeat" /> Twin health</div>
            <HealthRing value={health} />
            <div className="mx-sub-list">
              {subsysRows.map(r => (
                <div key={r.id} className="mx-subrow">
                  <span className="sd" style={{ background: statusColor(r.status), boxShadow: `0 0 10px ${statusColor(r.status)}` }} />
                  <span className="nm">{r.label}</span>
                  <span className="st" style={{ color: statusColor(r.status) }}>{r.status === 'crit' ? 'FAULT' : r.status === 'warn' ? 'WATCH' : 'OK'}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="mx-card flush">
            <div className="mx-h"><I n="ti-activity" /> Live telemetry<span className="tag">recovering</span></div>
            <div className="mx-tel">
              {tele.map(x => {
                const v = cur(x); const sev = sevClass(x.key, v)
                const col = sev === 'crit' ? 'var(--mx-red)' : sev === 'warn' ? 'var(--mx-amber)' : 'var(--mx-green)'
                const m = x.meta
                const fill = m.crit != null ? Math.min(100, (v / (m.crit * 1.15)) * 100)
                  : m.critLow != null ? Math.min(100, Math.max(6, (v / ((m.warnLow || m.critLow) * 2)) * 100))
                  : Math.max(8, Math.min(100, frac * 100))
                return (
                  <div key={x.key} className="mx-trow">
                    <div className="tt"><span className="nm">{m.label}</span>
                      <span className="vv" style={{ color: col }}>{fmt(v)}<u>{m.unit}</u></span></div>
                    <div className="mx-bar"><i style={{ width: `${fill}%`, background: col }} /></div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>

        {/* BOTTOM — AI voice / task / controls */}
        <div className="mx-bottom">
          <div className="mx-bar-wrap">
            <div className="mx-voice">
              <AICore size={46} speaking={speaking} />
              <div className={`mx-wave ${speaking ? '' : 'idle'}`}>{Array.from({ length: 7 }).map((_, i) => <i key={i} />)}</div>
              <div className="mx-said">
                <div className="who">AI Director {voice ? '· speaking' : ''}</div>
                <div className="txt">{subtitle.slice(0, typed)}{typed < subtitle.length && <span className="car">▍</span>}</div>
              </div>
            </div>

            <div className="mx-task">
              <div className="lbl">Current task</div>
              <div className="now">{stage === 'complete' ? 'Maintenance complete' : stage === 'repair' ? steps[step]?.t : stage === 'diagnose' ? 'Root-cause analysis' : stage === 'scan' ? 'Health scan' : 'Initialising'}</div>
              <div className="eta">{stage === 'complete' ? 'Done' : `~${mmss(remaining)} remaining`}</div>
              <div className="mx-prog"><i style={{ width: `${Math.round(frac * 100)}%` }} /></div>
            </div>

            <div className="mx-ctrls">
              <div className={`mx-btn ${voice ? 'on' : ''}`} title="Voice narration" onClick={() => setVoice(v => !v)}><I n={voice ? 'ti-volume' : 'ti-volume-off'} /></div>
              <div className="mx-btn" title="Previous step" onClick={() => goStep(step - 1)} disabled={stage !== 'repair' || step === 0}><I n="ti-player-track-prev" /></div>
              <div className="mx-btn play" title={playing ? 'Pause' : 'Play'} onClick={() => { if (stage === 'complete') return; if (stage !== 'repair') setStage('repair'); setPlaying(p => !p) }}>
                <I n={playing && stage === 'repair' ? 'ti-player-pause' : 'ti-player-play'} /></div>
              <div className="mx-btn" title="Next step" onClick={() => (step + 1 >= total ? setStage('complete') : goStep(step + 1))} disabled={stage === 'complete'}><I n="ti-player-track-next" /></div>
            </div>
          </div>
        </div>
      </div>

      {/* ── completion ── */}
      {stage === 'complete' && (
        <div className="mx-complete">
          <Confetti />
          <div className="ok"><I n="ti-check" /></div>
          <div className="big">Maintenance Complete</div>
          <div className="sub">{machineName} restored to nominal · health {Math.round(health * 100)}% · {total} steps verified</div>
          <div className="mx-play">
            <div className="mx-h" style={{ justifyContent: 'center', marginTop: 10 }}><I n="ti-history" /> Session playback</div>
            {steps.map((s, i) => (
              <div key={i} className="row" onClick={() => goStep(i)}>
                <span className="t">{mmss(steps.slice(0, i).reduce((a, x) => a + x.time, 0))}</span>
                <span className="l">{s.t}</span>
                <I n="ti-player-play" />
              </div>
            ))}
          </div>
          <div className="acts">
            <div className="mx-exit" style={{ background: 'rgba(124,150,255,.12)', borderColor: 'var(--mx-line2)', color: 'var(--mx-text)' }} onClick={() => { startRef.current = Date.now(); eventsRef.current = []; setRcLit(0); setStep(0); setPlaying(true); setStage('scan') }}>
              <I n="ti-refresh" /> Replay
            </div>
            <div className="mx-exit" onClick={onExit}><I n="ti-check" /> Done — exit</div>
          </div>
        </div>
      )}
    </div>
  )
}

// ── the stationary holographic AI core (no flying bot) ───────────────
function AICore({ size = 120, speaking = false }) {
  return (
    <div className={`mx-core ${speaking ? 'speaking' : ''}`} style={{ '--s': size + 'px' }}>
      <div className="ring r1" /><div className="ring r2" /><div className="ring r3" />
      <div className="pulse" /><div className="orb" />
    </div>
  )
}

// ── animated health ring ─────────────────────────────────────────────
function HealthRing({ value = 0 }) {
  const r = 40, c = 2 * Math.PI * r
  const off = c * (1 - Math.max(0, Math.min(1, value)))
  const col = value >= 0.8 ? 'var(--mx-green)' : value >= 0.55 ? 'var(--mx-cyan)' : value >= 0.4 ? 'var(--mx-amber)' : 'var(--mx-red)'
  return (
    <div className="mx-health">
      <svg className="mx-ring-svg" viewBox="0 0 96 96">
        <circle className="mx-ring-bg" cx="48" cy="48" r={r} />
        <circle className="mx-ring-fg" cx="48" cy="48" r={r} stroke={col}
          strokeDasharray={c} strokeDashoffset={off} />
      </svg>
      <div>
        <div className="mx-ring-num" style={{ color: col }}>{Math.round(value * 100)}%</div>
        <div className="mx-ring-lbl">Physics health</div>
      </div>
    </div>
  )
}

// ── holographic completion confetti (CSS-driven, GPU-cheap) ──────────
function Confetti() {
  const bits = useMemo(() => Array.from({ length: 64 }).map((_, i) => ({
    left: Math.random() * 100,
    delay: Math.random() * 0.8,
    dur: 2.4 + Math.random() * 1.8,
    col: ['#33e29b', '#36e3ff', '#9a7cff', '#5b8bff', '#ffc24b'][i % 5],
    rot: Math.random() * 360,
  })), [])
  return (
    <div className="mx-confetti">
      {bits.map((b, i) => (
        <i key={i} style={{ left: b.left + '%', background: b.col,
          transform: `rotate(${b.rot}deg)`, animationDuration: b.dur + 's', animationDelay: b.delay + 's' }} />
      ))}
    </div>
  )
}
