// Chat.jsx — a reusable chatbot panel. The parent supplies `send(messages)` which
// returns the assistant's reply text; AI replies render as markdown.
import React, { useEffect, useRef, useState } from 'react'
import { Icon } from './lib.jsx'
import Markdown from './Markdown.jsx'

export default function Chat({ send, greeting, suggestions = [], placeholder = 'Ask the agent…', height = 360 }) {
  const [msgs, setMsgs] = useState([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const logRef = useRef(null)
  useEffect(() => { if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight }, [msgs, busy])

  async function submit(text) {
    const q = (text ?? input).trim()
    if (!q || busy) return
    const next = [...msgs, { role: 'user', content: q }]
    setMsgs(next); setInput(''); setBusy(true)
    try {
      const reply = await send(next)
      setMsgs([...next, { role: 'assistant', content: reply || '(no reply)' }])
    } catch {
      setMsgs([...next, { role: 'assistant', content: 'Sorry — I could not reach the agent. Try again.' }])
    }
    setBusy(false)
  }

  return (
    <div className="chatbox" style={{ height }}>
      <div className="chat-log" ref={logRef}>
        {greeting && msgs.length === 0 && (
          <div className="chat-row ai"><div className="chat-av ai"><Icon n="ti-robot" /></div>
            <div className="chat-bub ai"><Markdown text={greeting} /></div></div>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={`chat-row ${m.role === 'user' ? 'user' : 'ai'}`}>
            <div className={`chat-av ${m.role === 'user' ? 'user' : 'ai'}`}><Icon n={m.role === 'user' ? 'ti-user' : 'ti-robot'} /></div>
            <div className={`chat-bub ${m.role === 'user' ? 'user' : 'ai'}`}>
              {m.role === 'user' ? m.content : <Markdown text={m.content} />}
            </div>
          </div>
        ))}
        {busy && <div className="chat-row ai"><div className="chat-av ai"><Icon n="ti-robot" /></div>
          <div className="chat-bub ai"><span className="spinner" /></div></div>}
      </div>
      {suggestions.length > 0 && msgs.length === 0 && (
        <div className="chat-chips">{suggestions.map((s, i) => <div key={i} className="chat-chip" onClick={() => submit(s)}>{s}</div>)}</div>
      )}
      <div className="chat-input">
        <input className="input" value={input} onChange={e => setInput(e.target.value)} placeholder={placeholder}
          onKeyDown={e => { if (e.key === 'Enter') submit() }} />
        <button className="btn btn-primary" onClick={() => submit()} disabled={busy}><Icon n="ti-send" /></button>
      </div>
    </div>
  )
}
