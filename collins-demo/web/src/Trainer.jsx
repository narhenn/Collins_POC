// Trainer.jsx — interactive maintenance training simulator.
// Loads a full repair procedure (with per-step consequences) for a scenario/fault,
// then lets the trainee perform / skip / reorder steps and SEE what happens —
// a recovering machine-health gauge, safety/order violations, scoring, and a
// live coach chat that explains any decision they explore.
import React, { useEffect, useMemo, useRef, useState } from 'react'
import api from './api'
import { Icon, hColor, pct } from './lib.jsx'
import { stubProcedure } from './aiStubs.js'
import Markdown from './Markdown.jsx'
import Chat from './Chat.jsx'

const START_HEALTH = 0.42

export default function Trainer({ machine, domain, fault, title, context, aiMode = 'stub' }) {
  const stub = aiMode !== 'agent'
  const [proc, setProc] = useState(null)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState(null)
  const [applied, setApplied] = useState([])     // step ids in the order performed
  const [health, setHealth] = useState(START_HEALTH)
  const [log, setLog] = useState([])             // {ok, severe, skip, text, step}
  const [violations, setViolations] = useState(0)
  const [skips, setSkips] = useState(0)
  const logRef = useRef(null)

  useEffect(() => { load() /* eslint-disable-next-line */ }, [fault, title])
  useEffect(() => { if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight }, [log])

  async function load() {
    setErr(null); reset()
    // stub mode: build a full interactive procedure locally — instant, works for
    // EVERY domain (the backend procedure agent was EDM-centric).
    if (stub) {
      setProc(stubProcedure({ domain, machineName: machine, fault, title })); setLoading(false); return
    }
    setLoading(true)
    try {
      const r = await api.procedure({ machine, domain, fault: fault || 'none', title, context })
      setProc(r.procedure)
    } catch (e) {
      // fall back to the local procedure so the teach flow never dead-ends
      setProc(stubProcedure({ domain, machineName: machine, fault, title }))
    }
    setLoading(false)
  }
  function reset() { setApplied([]); setHealth(START_HEALTH); setLog([]); setViolations(0); setSkips(0) }

  const steps = proc?.steps || []
  const total = steps.length
  const done = applied.length === total && total > 0
  const recovery = total ? (0.97 - START_HEALTH) / total : 0

  const statusOf = (s) => {
    if (applied.includes(s.id)) return 'done'
    if ((s.requires || []).every(r => applied.includes(r))) return 'next'
    return 'blocked'
  }
  const nextId = useMemo(() => steps.find(s => statusOf(s) === 'next')?.id, [steps, applied])

  function addLog(entry) { setLog(l => [...l, entry]) }

  function perform(s) {
    if (applied.includes(s.id)) return
    const reqMet = (s.requires || []).every(r => applied.includes(r))
    if (reqMet) {
      setApplied(a => [...a, s.id])
      setHealth(h => Math.min(0.99, h + recovery))
      addLog({ ok: true, step: s.id, text: `**${s.title}** done — ${s.criteria}` })
    } else {
      const missingSafety = (s.requires || []).some(r => steps.find(x => x.id === r)?.safety && !applied.includes(r))
      const pen = missingSafety ? 0.2 : 0.09
      setHealth(h => Math.max(0.05, h - pen))
      setViolations(v => v + 1)
      addLog({ ok: false, severe: missingSafety, step: s.id,
        text: (missingSafety ? '⛔ SAFETY VIOLATION — ' : '⚠ Out of order — ') + s.wrong_order_consequence })
    }
  }
  function skip(s) {
    if (applied.includes(s.id)) return
    setHealth(h => Math.max(0.05, h - 0.06))
    setSkips(n => n + 1)
    addLog({ ok: false, skip: true, step: s.id, text: '⏭ Skipped — ' + s.skip_consequence })
  }

  const score = Math.max(0, 100 - violations * 12 - skips * 8)
  const grade = score >= 90 ? 'A' : score >= 75 ? 'B' : score >= 60 ? 'C' : 'D'

  const coachContext = {
    scenario: title, fault, machine,
    procedure_summary: proc?.summary,
    steps: steps.map(s => ({ id: s.id, title: s.title, requires: s.requires, safety: s.safety })),
    completed_steps: applied, machine_health: Math.round(health * 100) + '%',
  }
  const coachSend = (messages) => {
    if (stub) {
      const q = ([...messages].reverse().find(m => m.role === 'user')?.content || '').toLowerCase()
      const safetyStep = steps.find(s => s.safety)
      let reply
      if (/skip|isolation|loto|safety/.test(q))
        reply = `Skipping the safety isolation${safetyStep ? ` (**${safetyStep.title}**)` : ''} is the riskiest mistake here — you'd be working on a live machine, risking injury and secondary damage. Always isolate before any physical work.`
      else if (/order|why|sequence|before|after/.test(q))
        reply = `The order matters: diagnose first so you target the right part, isolate before you open anything, inspect to confirm the failure mode, then repair → recalibrate → test → sign off. Each step depends on the one before it.`
      else if (/riskiest|worst|dangerous|mistake/.test(q))
        reply = `The two costly mistakes are (1) opening the machine before lockout/tagout, and (2) replacing a part before inspection confirms the actual failure mode — you fix the wrong thing and the fault returns.`
      else
        reply = `Work the steps top-to-bottom for **${proc?.title || 'this repair'}**. Perform the safety isolation early, confirm the failure by inspection before replacing anything, and finish with a functional test. Ask me "what if I skip X?" to explore consequences. _(Local coach — switch to Agent for full Claude coaching.)_`
      return Promise.resolve(reply)
    }
    return api.scenarioChat({ machine, messages, context: coachContext }).then(r => r.reply)
  }

  if (loading) return (
    <div className="card"><div className="empty" style={{ padding: '50px 20px' }}>
      <span className="spinner" style={{ width: 26, height: 26 }} />
      <div style={{ marginTop: 12 }}>The trainer is authoring the full repair procedure for this fault…</div>
      <div className="hint" style={{ marginTop: 4 }}>(a detailed, step-by-step plan — takes a moment)</div>
    </div></div>
  )
  if (err) return <div className="card" style={{ borderColor: 'rgba(225,29,72,.4)', color: 'var(--accent-red)' }}>{err}
    <div><button className="btn" style={{ marginTop: 10 }} onClick={load}><Icon n="ti-refresh" /> Retry</button></div></div>
  if (!proc) return null

  return (
    <div>
      {/* header + gauge + score */}
      <div className="card section-gap">
        <div className="card-title"><Icon n="ti-school" /> {proc.title}
          <span className="pill pill-purple">training</span>
          <button className="btn" style={{ marginLeft: 'auto' }} onClick={reset}><Icon n="ti-restore" /> Reset</button>
        </div>
        <Markdown text={proc.summary} />
        <div className="grid-3" style={{ marginTop: 12, gap: 12 }}>
          <div>
            <div className="row" style={{ justifyContent: 'space-between', fontSize: 12, marginBottom: 5 }}>
              <span className="hint">Machine health</span><b style={{ color: hColor(health) }}>{pct(health)}</b></div>
            <div className="tr-gauge"><i style={{ width: pct(health), background: hColor(health) }} /></div>
          </div>
          <div>
            <div className="row" style={{ justifyContent: 'space-between', fontSize: 12, marginBottom: 5 }}>
              <span className="hint">Progress</span><b>{applied.length}/{total}</b></div>
            <div className="tr-gauge"><i style={{ width: `${total ? (applied.length / total) * 100 : 0}%`, background: 'var(--brand)' }} /></div>
          </div>
          <div style={{ textAlign: 'center' }}>
            <div className="hint" style={{ fontSize: 12 }}>Score</div>
            <div style={{ fontFamily: 'var(--display)', fontSize: 22, fontWeight: 700, color: hColor(score / 100) }}>{score} · {grade}</div>
            <div className="hint" style={{ fontSize: 10 }}>{violations} order/safety · {skips} skipped</div>
          </div>
        </div>
        {/* flow mini-map */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginTop: 14, flexWrap: 'wrap' }}>
          {steps.map((s, i) => {
            const st = statusOf(s)
            const c = st === 'done' ? 'var(--accent-green)' : s.id === nextId ? 'var(--brand)' : 'var(--border2)'
            return <React.Fragment key={s.id}>
              {i > 0 && <span style={{ width: 10, height: 2, background: 'var(--border2)' }} />}
              <span title={s.title} style={{ width: 16, height: 16, borderRadius: '50%', background: c, color: '#fff',
                fontSize: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'var(--mono)',
                boxShadow: s.id === nextId ? '0 0 0 3px var(--brand-ring)' : 'none' }}>{s.safety ? '!' : i + 1}</span>
            </React.Fragment>
          })}
        </div>
        {done && (
          <div className="card" style={{ marginTop: 14, borderColor: 'rgba(22,163,74,.4)', background: 'rgba(22,163,74,.06)' }}>
            <div style={{ fontWeight: 700, color: 'var(--accent-green)' }}><Icon n="ti-circle-check" /> Machine restored — procedure complete!</div>
            <div style={{ fontSize: 12.5, marginTop: 4 }}>{proc.success_criteria}</div>
            <div style={{ fontSize: 12, marginTop: 6 }}>Final score <b>{score} ({grade})</b> — {violations === 0 && skips === 0 ? 'flawless run, textbook flow.' : `${violations} order/safety slip(s), ${skips} skip(s). Reset and try a cleaner run.`}</div>
          </div>
        )}
      </div>

      <div className="grid-2">
        {/* steps */}
        <div className="card" style={{ alignSelf: 'start' }}>
          <div className="card-title"><Icon n="ti-list-check" /> Repair steps <span className="hint" style={{ fontWeight: 400 }}>perform in the right order — or experiment</span></div>
          {steps.map((s, i) => {
            const st = statusOf(s)
            const cls = st === 'done' ? 'done' : s.id === nextId ? 'next' : st === 'blocked' ? 'blocked' : ''
            return (
              <div key={s.id} className={`tr-step ${cls}`}>
                <div className="tr-num">{st === 'done' ? '✓' : s.safety ? '!' : i + 1}</div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 600, fontSize: 12.5 }}>{s.title}
                    {s.safety && <span className="pill pill-red" style={{ marginLeft: 6, fontSize: 9 }}>safety</span>}
                    {s.requires?.length > 0 && <span className="hint" style={{ fontSize: 10, marginLeft: 6 }}>after {s.requires.join(', ')}</span>}
                  </div>
                  <div style={{ fontSize: 11.5, color: 'var(--muted)', marginTop: 2 }}>{s.action}</div>
                  {st !== 'done' && (
                    <div className="row" style={{ gap: 6, marginTop: 7 }}>
                      <button className="btn btn-primary" style={{ fontSize: 11, padding: '5px 10px' }} onClick={() => perform(s)}><Icon n="ti-player-play" /> Perform</button>
                      <button className="btn" style={{ fontSize: 11, padding: '5px 10px' }} onClick={() => skip(s)}><Icon n="ti-player-skip-forward" /> Skip</button>
                    </div>
                  )}
                </div>
              </div>
            )
          })}
          {proc.common_mistakes?.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <div className="card-label">Common mistakes</div>
              <ul className="md-ul" style={{ marginTop: 6, fontSize: 12 }}>
                {proc.common_mistakes.map((m, i) => <li key={i} style={{ color: 'var(--muted)' }}>{m}</li>)}
              </ul>
            </div>
          )}
        </div>

        {/* decision log + coach */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div className="card">
            <div className="card-title"><Icon n="ti-history" /> Decision outcomes</div>
            <div ref={logRef} style={{ maxHeight: 180, overflowY: 'auto' }}>
              {log.length === 0 ? <div className="empty">Perform or skip a step to see what happens.</div>
                : log.map((e, i) => (
                  <div key={i} style={{ display: 'flex', gap: 8, padding: '6px 0', borderBottom: '1px solid var(--border)' }}>
                    <span className="mono hint" style={{ minWidth: 26 }}>{e.step}</span>
                    <span style={{ fontSize: 12, color: e.ok ? 'var(--accent-green)' : e.severe ? 'var(--accent-red)' : 'var(--accent-amber)' }}>
                      <Markdown text={e.text} />
                    </span>
                  </div>))}
            </div>
          </div>
          <div className="card" style={{ display: 'flex', flexDirection: 'column' }}>
            <div className="card-title"><Icon n="ti-message-chatbot" /> Training coach <span className="pill pill-purple">Claude</span></div>
            <Chat send={coachSend} height={300}
              greeting={`I'm your coach for **${proc.title}**. Perform the steps on the left, or ask me anything — e.g. *"what if I skip the isolation step?"* or *"why does cleaning come before refilling?"*`}
              suggestions={['What if I skip the safety isolation?', 'Why this step order?', "What's the riskiest mistake here?"]}
              placeholder="Ask the coach, or explore a what-if…" />
          </div>
        </div>
      </div>
    </div>
  )
}
