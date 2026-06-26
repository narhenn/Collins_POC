import { useState, useRef, useEffect } from 'react'
import { PanelHeader, Card } from '../components/ui/Card'
import MockBanner from '../components/ui/MockBanner'
import NoTwin from '../components/NoTwin'
import { useTwin } from '../context/TwinContext'
import { usePolling } from '../hooks/useApi'
import api from '../api/client'

/**
 * Operational Copilot — MOCK (with a touch of real grounding).
 *  The chat is canned/rule-based. It DOES read the live stats so a couple of
 *  answers reflect the real twin. A real copilot needs an LLM wired to the
 *  Graph Query API + schema service as tools (see PLACEHOLDERS.md → "Copilot").
 */
const QUICK = [
  'How many findings are open?',
  'What is the turbine EGT trend?',
  'Show me the diagnosis chain',
  'Is this facility AS9100 compliant?',
  'Any cross-tenant intelligence?',
  'What assets does this twin have?',
]

export default function Copilot() {
  const { activeTenant, activeTwin } = useTwin()
  const { data: stats } = usePolling(
    () => api.stats(activeTenant), 4000, [activeTenant], { skip: !activeTenant },
  )
  const [messages, setMessages] = useState([{
    role: 'ai',
    text: 'I can answer questions about this twin. The platform exposes a schema-query API and the graph read API — a full LLM copilot would use those as tools. For now I answer from live stats and a small playbook.',
  }])
  const [input, setInput] = useState('')
  const endRef = useRef(null)
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  if (!activeTenant) return <NoTwin />

  const answer = (q) => {
    const l = q.toLowerCase()
    if (l.includes('finding')) return `This twin has ${stats?.total_findings ?? 0} findings recorded (${stats?.finding_severity?.critical || 0} critical).`
    if (l.includes('asset') || l.includes('have')) {
      const c = stats?.entity_counts || {}
      return `Entities: ${Object.entries(c).map(([k, v]) => `${v} ${k}`).join(', ') || 'none yet'}. Total ${stats?.total_entities || 0}.`
    }
    if (l.includes('change log') || l.includes('changelog')) return 'The change log is an append-only, SHA-256 hash-chained ledger. Every mutation that passes the Graph Writer is recorded; altering any past event breaks the chain from that point on.'
    if (l.includes('sensor') || l.includes('add')) return 'Go to Asset Graph → Add Asset, pick a type (e.g. aero:TurbineTestRig), name it, and optionally relate it to an existing entity. It is validated by the SHACL gate before it is written.'
    if (l.includes('egt') || l.includes('turbine') || l.includes('exhaust')) return 'Turbine Rig TR-01 EGT is monitored by a Tier-B z-score baseline (warmup: 15 samples, threshold: 2.5 sigma). Normal EGT for this CFM56-class engine is ~650C at stabilized ground run. The behaviour model flags sustained high-side deviations as potential hot-section distress — blade erosion, nozzle coking, or compressor degradation.'
    if (l.includes('diagnosis') || l.includes('chain')) return 'The diagnosis chain follows the ontology path: Finding → Incident → Diagnosis → Recommendation → Action. Each node is SHACL-validated and hash-chained in the changelog. The operational agent creates this chain automatically when findings are grouped. Click any Incident in the Assets panel to traverse the full chain.'
    if (l.includes('as9100') || l.includes('compliance') || l.includes('easa') || l.includes('faa')) return 'This twin maps to AS9100 Rev D §8.5.1 (production/service provision) and EASA Part 145.A.45 (maintenance data). The hash-chained changelog provides tamper-evident audit trails that satisfy both standards. Currently 3 compliance gaps are flagged — see the Compliance panel for details.'
    if (l.includes('cross') || l.includes('melbourne') || l.includes('intel')) return 'Melbourne HQ (collins-melb-hq) resolved a similar chiller COP degradation incident 2 weeks ago. Resolution: condenser coil chemical wash + R-410A refrigerant recharge. Downtime: 2.5 hours. COP restored from 3.2 to 5.0. The operational diagnosis agent surfaces this cross-tenant intelligence automatically when matching behaviour patterns are detected.'
    if (l.includes('hydraulic') || l.includes('pressure')) return 'Hydraulic Actuator HYD-01 is monitored by a Tier-C threshold rule at 2000 PSI (nominal: 3000 PSI). Pressure below this limit indicates seal failure or internal leakage. Downstream actuators may lose flight control authority — this is a safety-critical alert.'
    return `I don't have a grounded answer for that yet. A full copilot would query the graph and ontology to respond. Current twin: ${activeTwin?.name}.`
  }

  const send = (q) => {
    const text = (q ?? input).trim()
    if (!text) return
    setInput('')
    setMessages((m) => [...m, { role: 'user', text }])
    setTimeout(() => setMessages((m) => [...m, { role: 'ai', text: answer(text) }]), 400)
  }

  return (
    <div className="panel">
      <PanelHeader title="Operational Copilot" subtitle="Natural-language access to your twin" />
      <MockBanner what="Replies are rule-based with live-stat grounding; a real copilot wires an LLM to the graph + schema APIs as tools." />
      <Card>
        <div className="chat-quick">
          {QUICK.map((q) => <div key={q} className="quick-chip" onClick={() => send(q)}>{q}</div>)}
        </div>
        <div className="chat-wrap">
          <div className="chat-messages">
            {messages.map((m, i) => (
              <div key={i} className={`chat-bubble ${m.role === 'user' ? 'bubble-user' : 'bubble-ai'}`}>
                {m.role === 'ai' && <div className="bubble-label">NextXR Copilot</div>}
                {m.text}
              </div>
            ))}
            <div ref={endRef} />
          </div>
          <div className="chat-input-row">
            <input className="input" value={input} placeholder="Ask about this twin…"
                   onChange={(e) => setInput(e.target.value)}
                   onKeyDown={(e) => e.key === 'Enter' && send()} />
            <button className="btn btn-primary" onClick={() => send()}><i className="ti ti-send" /></button>
          </div>
        </div>
      </Card>
    </div>
  )
}
