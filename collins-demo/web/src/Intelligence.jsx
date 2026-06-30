import React, { useState, useRef } from 'react'
import api from './api'
import { Icon, pct, hColor, statusColor, fmt, sevClass, SIG, domainMeta } from './lib.jsx'

/* ── tiny helpers ──────────────────────────────────────────────────── */
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

function simDiagnostics(domain, twin) {
  const meta = domainMeta(domain)
  const latest = twin?.latest || {}
  const components = (meta.assets || []).map(([id, st]) => ({
    name: id, type: 'asset', status: st, health: st === 'crit' ? 0.3 : st === 'warn' ? 0.62 : 0.92,
  }))
  const sensors = (meta.all || []).map(k => ({ name: SIG[k]?.label || k, value: latest[k], status: sevClass(k, latest[k]) || 'ok' }))
  return { overall_health: twin?.health, components, sensors }
}

/* ── reusable visual components ───────────────────────────────────── */
function StepFlow({ steps }) {
  if (!steps?.length) return null
  return (
    <div style={{ position: 'relative', paddingLeft: 28 }}>
      {/* vertical connector line */}
      <div style={{ position: 'absolute', left: 13, top: 4, bottom: 4, width: 2, background: 'var(--border2)', borderRadius: 2 }} />
      {steps.map((s, i) => (
        <div key={i} style={{ position: 'relative', paddingBottom: i < steps.length - 1 ? 16 : 0 }}>
          {/* step circle */}
          <div style={{ position: 'absolute', left: -28, top: 0, width: 26, height: 26, borderRadius: '50%',
            background: 'var(--gradient)', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 11, fontWeight: 700, fontFamily: 'var(--mono)', zIndex: 2, boxShadow: 'var(--shadow-brand)' }}>{s.step || i + 1}</div>
          {/* step body */}
          <div style={{ background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 12, padding: '12px 14px' }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>{s.action}</div>
            {s.criteria && <div style={{ fontSize: 11.5, color: 'var(--muted)', display: 'flex', alignItems: 'center', gap: 5 }}>
              <Icon n="ti-check" /> <span>Criteria: {s.criteria}</span></div>}
            {s.safety && <div style={{ fontSize: 11.5, color: 'var(--accent-amber)', display: 'flex', alignItems: 'center', gap: 5, marginTop: 4,
              background: 'rgba(217,119,6,.08)', padding: '5px 8px', borderRadius: 8 }}>
              <Icon n="ti-alert-triangle" /> {s.safety}</div>}
          </div>
        </div>
      ))}
    </div>
  )
}

function ConfidenceGauge({ value, label }) {
  const pctVal = Math.round((value || 0) * 100)
  const color = pctVal >= 70 ? 'var(--accent-green)' : pctVal >= 40 ? 'var(--accent-amber)' : 'var(--accent-red)'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <span style={{ fontSize: 11, color: 'var(--muted)', minWidth: 60 }}>{label || 'Confidence'}</span>
      <div style={{ flex: 1, height: 8, borderRadius: 99, background: 'var(--surface2)', overflow: 'hidden' }}>
        <div style={{ width: pctVal + '%', height: '100%', borderRadius: 99, background: color, transition: 'width .4s ease' }} />
      </div>
      <span className="mono" style={{ fontSize: 11, fontWeight: 700, color, minWidth: 32 }}>{pctVal}%</span>
    </div>
  )
}

function AgentCard({ icon, name, desc, pill, children, onRun, running, runLabel, runColor }) {
  return (
    <div className="card section-gap" style={{ overflow: 'hidden' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: children ? 14 : 0 }}>
        <div className="agent-icon" style={runColor ? { background: runColor + '18', color: runColor } : {}}><Icon n={icon} /></div>
        <div style={{ flex: 1 }}>
          <div className="agent-name">{name} {pill && <span className="pill pill-purple" style={{ fontSize: 9, marginLeft: 6 }}>{pill}</span>}</div>
          <div className="agent-desc">{desc}</div>
        </div>
        {onRun && <button className="btn btn-primary" onClick={onRun} disabled={running} style={runColor ? { background: runColor } : {}}>
          {running ? <><span className="spinner" /> Running...</> : <><Icon n="ti-player-play" /> {runLabel || 'Run'}</>}
        </button>}
      </div>
      {children}
    </div>
  )
}

function ChatBubble({ from, text }) {
  const isAI = from === 'ai'
  return (
    <div style={{ display: 'flex', justifyContent: isAI ? 'flex-start' : 'flex-end', marginBottom: 10 }}>
      <div style={{ maxWidth: '85%', padding: '10px 14px', borderRadius: isAI ? '4px 14px 14px 14px' : '14px 4px 14px 14px',
        background: isAI ? 'var(--surface2)' : 'var(--brand-soft)', fontSize: 12.5, lineHeight: 1.7,
        border: '1px solid ' + (isAI ? 'var(--border)' : 'var(--brand-ring)') }}>
        {text}
      </div>
    </div>
  )
}

/* ── main component ───────────────────────────────────────────────── */
export default function Intelligence({ tenant, machineName, domain, isLive = true, twin }) {
  const [tab, setTab] = useState('diagnosis')
  const [diag, setDiag] = useState(null)
  const [analysis, setAnalysis] = useState(null)
  const [procurement, setProcurement] = useState(null)
  const [incident, setIncident] = useState(null)
  const [tsHistory, setTsHistory] = useState([])
  const [tsInput, setTsInput] = useState('')
  const [tsResult, setTsResult] = useState(null)
  const [busy, setBusy] = useState(null)
  const [err, setErr] = useState(null)
  const chatEndRef = useRef(null)

  const TABS = [
    { id: 'diagnosis', icon: 'ti-stethoscope', label: 'Diagnosis' },
    { id: 'troubleshoot', icon: 'ti-messages', label: 'AI Mechanic' },
    { id: 'procurement', icon: 'ti-package', label: 'Parts' },
    { id: 'incident', icon: 'ti-report', label: 'Incident Report' },
  ]

  /* ── agent runners ──────────────────────────────────────────────── */
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
      if (isLive) { const a = await api.runAnalysis({ tenant, machine: machineName, horizon_label: '6 hours' }); setAnalysis({ report: a.report }) }
      else { const r = await api.forecastSnapshot({ machine: machineName, domain, latest: twin?.latest || {}, horizon_label: '6 hours' }); setAnalysis({ report: r.report }) }
    } catch (e) { setErr(String(e.message || e)) }
    setBusy(null)
  }

  async function sendTroubleshoot() {
    if (!tsInput.trim()) return
    const msg = tsInput.trim()
    const newHistory = [...tsHistory, { role: 'user', content: msg }]
    setTsHistory(newHistory); setTsInput(''); setBusy('ts'); setErr(null)
    try {
      const r = await api.troubleshoot({ tenant, machine: machineName, history: newHistory, message: msg })
      setTsResult(r)
      setTsHistory(prev => [...prev, { role: 'assistant', content: r.reply || r.message }])
      setTimeout(() => chatEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 100)
    } catch (e) { setErr(String(e.message || e)) }
    setBusy(null)
  }

  async function runProcurement() {
    setBusy('proc'); setErr(null)
    try { setProcurement(await api.procurement({ tenant, machine: machineName })) }
    catch (e) { setErr(String(e.message || e)) }
    setBusy(null)
  }

  async function runIncident() {
    setBusy('inc'); setErr(null)
    try { setIncident(await api.incidentReport({ tenant, machine: machineName })) }
    catch (e) { setErr(String(e.message || e)) }
    setBusy(null)
  }

  const d = diag?.diagnostics
  const wo = procurement?.work_order
  const parts = procurement?.procurement
  const rep = incident?.report

  return (
    <div className="panel">
      <div className="panel-header">
        <div><div className="panel-title">Twin Intelligence</div>
          <div className="panel-subtitle">AI agents for {machineName} — diagnosis, troubleshooting, procurement, and compliance reporting.</div></div>
      </div>

      {/* ── agent pipeline tabs ─────────────────────────────────────── */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 18, flexWrap: 'wrap' }}>
        {TABS.map(t => (
          <button key={t.id} className={`btn ${tab === t.id ? 'btn-primary' : ''}`} onClick={() => setTab(t.id)}
            style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12.5 }}>
            <Icon n={t.icon} /> {t.label}
          </button>
        ))}
      </div>

      {err && <div className="card" style={{ borderColor: 'rgba(225,29,72,.4)', color: 'var(--accent-red)', marginBottom: 16 }}>{err}</div>}

      {/* ═══ DIAGNOSIS TAB ═══════════════════════════════════════════ */}
      {tab === 'diagnosis' && <>
        <div className="grid-2 section-gap">
          <AgentCard icon="ti-stethoscope" name="Diagnosis Agent" desc="Per-component & per-sensor health report." pill="Claude"
            onRun={runDiag} running={busy === 'diag'} runLabel="Diagnose" />
          <AgentCard icon="ti-trending-up" name="Analysis Agent" desc="Where the machine is heading over the next 6 hours." pill="Claude"
            onRun={runAnalysis} running={busy === 'analysis'} runLabel="Analyze" runColor="#0d9488" />
        </div>

        {d && (
          <div className="card section-gap">
            <div className="card-title"><Icon n="ti-stethoscope" /> Diagnosis Report
              <span className={`pill ${d.overall_health >= 0.6 ? 'pill-green' : d.overall_health >= 0.4 ? 'pill-amber' : 'pill-red'}`}>
                overall {pct(d.overall_health)}</span></div>
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
            <div style={{ marginTop: 14, fontSize: 13, lineHeight: 1.7, whiteSpace: 'pre-wrap',
              borderLeft: '3px solid var(--accent-blue)', paddingLeft: 12, background: 'var(--brand-softer)',
              borderRadius: '0 10px 10px 0', padding: '12px 14px 12px 14px', borderLeftWidth: 3, borderLeftStyle: 'solid',
              borderLeftColor: 'var(--accent-blue)' }}>{diag.report}</div>
          </div>
        )}

        {analysis && (
          <div className="card">
            <div className="card-title"><Icon n="ti-trending-up" /> Analysis <span className="pill pill-purple">Claude</span></div>
            <div style={{ fontSize: 13, lineHeight: 1.7, whiteSpace: 'pre-wrap',
              borderLeft: '3px solid var(--accent-teal)', padding: '12px 14px',
              background: 'rgba(13,148,136,.04)', borderRadius: '0 10px 10px 0' }}>{analysis.report}</div>
          </div>
        )}
      </>}

      {/* ═══ TROUBLESHOOT TAB (AI Mechanic) ══════════════════════════ */}
      {tab === 'troubleshoot' && (
        <div className="card">
          <div className="card-title"><Icon n="ti-messages" /> AI Mechanic <span className="pill pill-purple">Claude</span></div>
          <div className="card-label">Describe what you see or ask a diagnostic question</div>

          {/* chat history */}
          <div style={{ maxHeight: 340, overflowY: 'auto', marginTop: 12, marginBottom: 12, padding: '4px 0' }}>
            {tsHistory.length === 0 && <div className="empty" style={{ margin: '20px 0' }}>
              Start a conversation — describe the symptom and the AI Mechanic will walk you through diagnosis.</div>}
            {tsHistory.map((m, i) => <ChatBubble key={i} from={m.role === 'user' ? 'user' : 'ai'} text={m.content} />)}
            {busy === 'ts' && <div style={{ padding: 8 }}><span className="spinner" /> Thinking...</div>}
            <div ref={chatEndRef} />
          </div>

          {/* hypothesis + confidence */}
          {tsResult && (
            <div style={{ background: 'var(--surface2)', borderRadius: 12, padding: '12px 14px', marginBottom: 12, border: '1px solid var(--border)' }}>
              <div style={{ display: 'flex', gap: 12, marginBottom: 8 }}>
                <div style={{ flex: 1 }}>
                  <div className="card-label">Leading Hypothesis</div>
                  <div style={{ fontSize: 13, fontWeight: 600, marginTop: 4 }}>{tsResult.hypothesis || 'Gathering information...'}</div>
                </div>
                {tsResult.resolved && <span className="pill pill-green" style={{ alignSelf: 'flex-start' }}>Resolved</span>}
              </div>
              <ConfidenceGauge value={tsResult.confidence} />
            </div>
          )}

          {/* input */}
          <div style={{ display: 'flex', gap: 8 }}>
            <input type="text" value={tsInput} onChange={e => setTsInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && sendTroubleshoot()}
              placeholder="e.g. EGT is reading 660C and climbing..."
              style={{ flex: 1, padding: '10px 14px', borderRadius: 10, border: '1px solid var(--border)',
                fontSize: 13, outline: 'none', background: 'var(--surface)' }} />
            <button className="btn btn-primary" onClick={sendTroubleshoot} disabled={busy === 'ts' || !tsInput.trim()}>
              <Icon n="ti-send" /> Send</button>
          </div>
        </div>
      )}

      {/* ═══ PROCUREMENT TAB ═════════════════════════════════════════ */}
      {tab === 'procurement' && (
        <AgentCard icon="ti-package" name="Parts Procurement Agent" pill="Claude"
          desc="Generate a work order, then identify every part needed with PN, cost, lead time, and source."
          onRun={runProcurement} running={busy === 'proc'} runLabel="Generate">

          {parts && <>
            {/* summary KPIs */}
            <div className="grid-4 section-gap" style={{ marginTop: 4 }}>
              <div className="card kpi"><div className="card-label">Parts Needed</div>
                <div className="card-value">{parts.parts?.length || 0}</div></div>
              <div className="card kpi"><div className="card-label">Est. Cost</div>
                <div className="card-value" style={{ fontSize: 22 }}>${parts.total_estimated_cost?.toLocaleString() || '—'}</div></div>
              <div className="card kpi"><div className="card-label">AOG Stock</div>
                <div className="card-value" style={{ color: parts.aog_available ? 'var(--accent-green)' : 'var(--accent-red)' }}>
                  {parts.aog_available ? 'Yes' : 'No'}</div></div>
              <div className="card kpi"><div className="card-label">WO Ref</div>
                <div className="card-value" style={{ fontSize: 16 }}>{parts.work_order_ref || wo?.wo_number || '—'}</div></div>
            </div>

            {/* parts table */}
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                <thead><tr style={{ borderBottom: '2px solid var(--border)', textAlign: 'left' }}>
                  <th style={{ padding: '8px 10px', color: 'var(--muted)', fontWeight: 700, fontSize: 10, textTransform: 'uppercase', letterSpacing: '.05em' }}>Part Number</th>
                  <th style={{ padding: '8px 10px', color: 'var(--muted)', fontWeight: 700, fontSize: 10, textTransform: 'uppercase', letterSpacing: '.05em' }}>Description</th>
                  <th style={{ padding: '8px 10px', color: 'var(--muted)', fontWeight: 700, fontSize: 10, textTransform: 'uppercase', letterSpacing: '.05em', textAlign: 'center' }}>Qty</th>
                  <th style={{ padding: '8px 10px', color: 'var(--muted)', fontWeight: 700, fontSize: 10, textTransform: 'uppercase', letterSpacing: '.05em', textAlign: 'right' }}>Cost</th>
                  <th style={{ padding: '8px 10px', color: 'var(--muted)', fontWeight: 700, fontSize: 10, textTransform: 'uppercase', letterSpacing: '.05em' }}>Lead Time</th>
                  <th style={{ padding: '8px 10px', color: 'var(--muted)', fontWeight: 700, fontSize: 10, textTransform: 'uppercase', letterSpacing: '.05em' }}>Source</th>
                </tr></thead>
                <tbody>
                  {(parts.parts || []).map((p, i) => (
                    <tr key={i} style={{ borderBottom: '1px solid var(--border)' }}>
                      <td style={{ padding: '10px', fontFamily: 'var(--mono)', fontWeight: 600, color: 'var(--accent-blue)' }}>{p.part_number}</td>
                      <td style={{ padding: '10px' }}>{p.description}</td>
                      <td style={{ padding: '10px', textAlign: 'center' }}><span className="pill pill-surface">{p.quantity}</span></td>
                      <td style={{ padding: '10px', textAlign: 'right', fontFamily: 'var(--mono)' }}>${p.estimated_cost_usd?.toLocaleString() || '—'}</td>
                      <td style={{ padding: '10px' }}>{p.lead_time || '—'}</td>
                      <td style={{ padding: '10px', fontSize: 11 }}>{p.source || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {parts.notes && <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 10, fontStyle: 'italic' }}>{parts.notes}</div>}
          </>}
        </AgentCard>
      )}

      {/* ═══ INCIDENT REPORT TAB ═════════════════════════════════════ */}
      {tab === 'incident' && (
        <AgentCard icon="ti-report" name="Incident Report Agent" pill="Claude"
          desc="Generate a formal MRO incident report with regulatory references and return-to-service closure."
          onRun={runIncident} running={busy === 'inc'} runLabel="Generate">

          {rep && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14, marginTop: 4 }}>
              {/* header row */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10 }}>
                <div className="kpibox"><div className="l">Report ID</div><div className="v" style={{ fontSize: 14 }}>{rep.report_id || '—'}</div></div>
                <div className="kpibox"><div className="l">Classification</div><div className="v" style={{ fontSize: 13 }}>{rep.classification || '—'}</div></div>
                <div className="kpibox"><div className="l">Timestamp</div><div className="v" style={{ fontSize: 13 }}>{rep.timestamp || new Date().toISOString().slice(0, 16)}</div></div>
              </div>

              {/* symptoms */}
              {rep.symptoms?.length > 0 && (
                <div style={{ background: 'rgba(225,29,72,.04)', border: '1px solid rgba(225,29,72,.15)', borderRadius: 12, padding: 14 }}>
                  <div className="card-label" style={{ color: 'var(--accent-red)' }}>Observed Symptoms</div>
                  <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 6 }}>
                    {rep.symptoms.map((s, i) => (
                      <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5 }}>
                        <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--accent-red)', flexShrink: 0 }} />
                        {s}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* evidence + cause */}
              <div className="grid-2">
                <div style={{ background: 'var(--surface2)', borderRadius: 12, padding: 14, border: '1px solid var(--border)' }}>
                  <div className="card-label">Physics Evidence</div>
                  <div style={{ fontSize: 12.5, lineHeight: 1.7, marginTop: 6 }}>{rep.physics_evidence || '—'}</div>
                </div>
                <div style={{ background: 'var(--surface2)', borderRadius: 12, padding: 14, border: '1px solid var(--border)' }}>
                  <div className="card-label">Probable Cause</div>
                  <div style={{ fontSize: 12.5, lineHeight: 1.7, marginTop: 6, fontWeight: 600 }}>{rep.probable_cause || '—'}</div>
                </div>
              </div>

              {/* corrective action */}
              <div style={{ borderLeft: '3px solid var(--accent-blue)', padding: '12px 14px', background: 'var(--brand-softer)', borderRadius: '0 10px 10px 0' }}>
                <div className="card-label">Corrective Action</div>
                <div style={{ fontSize: 12.5, lineHeight: 1.7, marginTop: 6 }}>{rep.corrective_action || '—'}</div>
              </div>

              {/* regulatory + return to service */}
              <div className="grid-2">
                <div style={{ background: 'rgba(37,99,235,.04)', border: '1px solid rgba(37,99,235,.15)', borderRadius: 12, padding: 14 }}>
                  <div className="card-label" style={{ color: 'var(--accent-blue)' }}>Regulatory Closure</div>
                  <div style={{ fontSize: 12.5, lineHeight: 1.7, marginTop: 6 }}>{rep.regulatory_closure || '—'}</div>
                </div>
                <div style={{ background: 'rgba(22,163,74,.04)', border: '1px solid rgba(22,163,74,.15)', borderRadius: 12, padding: 14 }}>
                  <div className="card-label" style={{ color: 'var(--accent-green)' }}>Return to Service</div>
                  <div style={{ fontSize: 12.5, lineHeight: 1.7, marginTop: 6 }}>{rep.return_to_service || '—'}</div>
                </div>
              </div>
            </div>
          )}
        </AgentCard>
      )}
    </div>
  )
}

export { StepFlow }
