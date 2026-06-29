import React, { useEffect, useRef, useState } from 'react'
import api from './api'
import { Icon } from './lib.jsx'
import TurbineModel from './TurbineModel.jsx'

export default function BuildTwin({ tenant, machine, twin, modelUrl, onBuilt, setModelUrl }) {
  const [history, setHistory] = useState([])
  const [input, setInput] = useState('')
  const [thinking, setThinking] = useState(false)
  const [machineName, setMachineName] = useState('')
  const [ready, setReady] = useState(false)
  const [image, setImage] = useState(null)         // {b64, name, preview}
  const [drag, setDrag] = useState(false)
  const [building, setBuilding] = useState(false)
  const [log, setLog] = useState([])
  const [err, setErr] = useState(null)
  const fileRef = useRef(null)
  const pollRef = useRef(null)
  const msgsRef = useRef(null)

  // greet on mount
  useEffect(() => {
    api.buildTwinMessage({ history: [], message: '' }).then(r => {
      setHistory([{ role: 'assistant', content: r.reply }])
    }).catch(() => setHistory([{ role: 'assistant', content:
      "Hi! I'm the Twin Builder. What machine are we twinning?" }]))
  }, [])
  useEffect(() => { if (msgsRef.current) msgsRef.current.scrollTop = msgsRef.current.scrollHeight }, [history, thinking])
  useEffect(() => () => clearInterval(pollRef.current), [])

  async function send() {
    const m = input.trim(); if (!m) return
    const h = [...history, { role: 'user', content: m }]
    setHistory(h); setInput(''); setThinking(true)
    try {
      const r = await api.buildTwinMessage({ history, message: m })
      setHistory([...h, { role: 'assistant', content: r.reply }])
      if (r.ready) setReady(true)
      if (r.machine_name) setMachineName(r.machine_name)
    } catch (e) { setHistory([...h, { role: 'assistant', content: 'Error: ' + e.message }]) }
    setThinking(false)
  }

  function loadFile(f) {
    if (!f) return
    const r = new FileReader()
    r.onload = () => setImage({ b64: r.result, name: f.name, preview: r.result })
    r.readAsDataURL(f)
  }

  async function build() {
    if (!image) { setErr('Drop a 2D image of the machine first.'); return }
    setBuilding(true); setErr(null); setLog([{ t: '> uploading image…' }])
    try {
      const r = await api.buildTwinGenerate({
        machine: machineName || machine?.name || 'Turbine Engine',
        image_b64: image.b64, filename: image.name || 'machine.png',
      })
      onBuilt(r.tenant, r.machine)                       // live twin is up immediately
      setLog(l => [...l, { t: '✓ live twin built — sensors streaming', ok: true }])
      if (r.tripo === 'running' && r.task_id) {
        setLog(l => [...l, { t: 'Tripo: reconstructing 3D from the image…', acc: true }])
        pollStatus(r.task_id, r.tenant)
      } else if (r.tripo === 'no_key') {
        setLog(l => [...l, { t: '⚠ TRIPO_API_KEY not set — add it to orchestrator/.env to generate the 3D model. The live twin still works.', warn: true }])
        setBuilding(false)
      } else {
        setLog(l => [...l, { t: 'Tripo unavailable: ' + r.tripo, warn: true }]); setBuilding(false)
      }
    } catch (e) { setErr(String(e.message || e)); setBuilding(false) }
  }

  function pollStatus(taskId, tnt) {
    let n = 0
    pollRef.current = setInterval(async () => {
      n++
      try {
        const s = await api.buildTwinStatus(taskId)
        if (s.progress != null && n % 2 === 0)
          setLog(l => [...l, { t: `Tripo: ${s.status} ${s.progress || 0}%` }])
        if (s.status === 'success' && s.model_url) {
          clearInterval(pollRef.current)
          setModelUrl(api.modelUrl(tnt))
          setLog(l => [...l, { t: '✓ 3D model ready', ok: true }])
          setBuilding(false)
        } else if (s.status === 'failed' || s.status === 'error') {
          clearInterval(pollRef.current)
          setLog(l => [...l, { t: 'Tripo failed: ' + (s.detail || s.status), warn: true }])
          setBuilding(false)
        }
      } catch (e) { /* keep polling */ }
      if (n > 120) { clearInterval(pollRef.current); setBuilding(false) }
    }, 2500)
  }

  return (
    <div className="panel">
      <div className="panel-header">
        <div><div className="panel-title">Build a Twin</div>
          <div className="panel-subtitle">Talk to the agent, drop a 2D image of your machine, and it reconstructs a 3D twin (Tripo) wired to live sensors & physics.</div></div>
      </div>
      {err && <div className="card" style={{ borderColor: 'rgba(225,29,72,.4)', color: 'var(--accent-red)', marginBottom: 16 }}>{err}</div>}

      <div className="grid-2">
        {/* Left: chat + upload */}
        <div className="card" style={{ display: 'flex', flexDirection: 'column' }}>
          <div className="card-title"><Icon n="ti-sparkles" /> Twin Builder <span className="pill pill-purple">agent</span></div>
          <div ref={msgsRef} style={{ flex: 1, minHeight: 220, maxHeight: 300, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 10, padding: '2px' }}>
            {history.map((m, i) => (
              <div key={i} style={{ alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start', maxWidth: '85%',
                padding: '10px 13px', borderRadius: 14, fontSize: 12.5, lineHeight: 1.55,
                background: m.role === 'user' ? 'var(--gradient)' : 'var(--surface2)',
                color: m.role === 'user' ? '#fff' : 'var(--text)',
                border: m.role === 'user' ? 'none' : '1px solid var(--border)' }}>
                {m.role === 'assistant' && <div style={{ fontSize: 10, color: 'var(--muted)', marginBottom: 3, fontWeight: 600 }}>Twin Builder · AI</div>}
                {m.content}
              </div>
            ))}
            {thinking && <div style={{ alignSelf: 'flex-start' }}><span className="spinner" /></div>}
          </div>
          <div className="row" style={{ marginTop: 10 }}>
            <input className="input" value={input} placeholder="Type your answer…"
              onChange={e => setInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && send()} />
            <button className="btn btn-primary" onClick={send}><Icon n="ti-send" /></button>
          </div>

          {/* image dropzone */}
          <div style={{ marginTop: 12,
            border: `2px dashed ${drag ? 'var(--brand)' : 'var(--border2)'}`, borderRadius: 14,
            background: drag ? 'var(--brand-soft)' : 'var(--brand-softer)', padding: 16, textAlign: 'center', cursor: 'pointer' }}
            onClick={() => fileRef.current?.click()}
            onDragOver={e => { e.preventDefault(); setDrag(true) }}
            onDragLeave={() => setDrag(false)}
            onDrop={e => { e.preventDefault(); setDrag(false); loadFile(e.dataTransfer.files[0]) }}>
            <input ref={fileRef} type="file" accept="image/*" style={{ display: 'none' }}
              onChange={e => loadFile(e.target.files[0])} />
            {image
              ? <img src={image.preview} alt="machine" style={{ maxHeight: 120, borderRadius: 10 }} />
              : <><div style={{ fontSize: 22 }}><Icon n="ti-cloud-upload" /></div>
                  <div style={{ fontWeight: 600, marginTop: 4 }}>Drop a 2D image of the machine</div>
                  <div className="hint" style={{ fontSize: 11 }}>PNG / JPG · or click to browse</div></>}
          </div>
          <button className="btn btn-primary" style={{ marginTop: 12, justifyContent: 'center' }}
            onClick={build} disabled={building || !image}>
            {building ? <><span className="spinner" />&nbsp; Building…</> : <><Icon n="ti-wand" /> Build 3D Twin</>}
          </button>
        </div>

        {/* Right: 3D result + log */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div className="card">
            <div className="card-title"><Icon n="ti-cube" /> Reconstructed 3D Twin
              {tenant && <span className="pill pill-green">live</span>}</div>
            {modelUrl
              ? <TurbineModel url={modelUrl} latest={twin?.latest || {}} height={300} />
              : <div className="hero3d" style={{ height: 300 }}>
                  <div className="lbl"><div className="big">⬡ 3D model appears here</div>
                    {building ? 'Tripo is reconstructing the model from your image…' : 'Chat, drop an image, and hit Build.'}</div>
                </div>}
          </div>
          {log.length > 0 && (
            <div className="card">
              <div className="card-title"><Icon n="ti-terminal-2" /> Build Log</div>
              <div className="mono" style={{ fontSize: 11.5, maxHeight: 160, overflowY: 'auto', lineHeight: 1.7 }}>
                {log.map((l, i) => (
                  <div key={i} style={{ color: l.ok ? 'var(--accent-green)' : l.warn ? 'var(--accent-amber)' : l.acc ? 'var(--brand)' : 'var(--muted)' }}>{l.t}</div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
