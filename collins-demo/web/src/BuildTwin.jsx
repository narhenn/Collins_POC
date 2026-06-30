import React, { useEffect, useRef, useState } from 'react'
import api from './api'
import { Icon, DOMAINS, domainMeta } from './lib.jsx'
import TurbineModel from './TurbineModel.jsx'
import Scene3D from './Scene3D.jsx'

// Domains available for "Build from image" — live-physics domains that make sense
const BUILD_DOMAINS = [
  { key: 'turbine-engine', icon: 'ti-engine', label: 'Gas Turbine', tag: 'Aerospace MRO', color: '#2563eb' },
  { key: 'edm-machine', icon: 'ti-grill', label: 'Wire EDM', tag: 'Precision Machining', color: '#7c3aed' },
  { key: 'datacenter', icon: 'ti-server-2', label: 'Data Center', tag: 'IT Infrastructure', color: '#0ea5e9' },
  { key: 'hospital', icon: 'ti-building-hospital', label: 'Hospital', tag: 'Healthcare', color: '#14b8a6' },
  { key: 'manufacturing', icon: 'ti-building-factory-2', label: 'Manufacturing', tag: 'Industrial', color: '#f59e0b' },
]

export default function BuildTwin({ tenant, machine, twin, modelUrl, onBuilt, setModelUrl }) {
  const [history, setHistory] = useState([])
  const [input, setInput] = useState('')
  const [thinking, setThinking] = useState(false)
  const [machineName, setMachineName] = useState('')
  const [ready, setReady] = useState(false)
  const [image, setImage] = useState(null)
  const [drag, setDrag] = useState(false)
  const [building, setBuilding] = useState(false)
  const [log, setLog] = useState([])
  const [err, setErr] = useState(null)
  const [domain, setDomain] = useState('turbine-engine')
  const [quality, setQuality] = useState('fast')
  const [provider, setProvider] = useState(null)
  const [builtDomain, setBuiltDomain] = useState(null)
  const fileRef = useRef(null)
  const pollRef = useRef(null)
  const msgsRef = useRef(null)

  useEffect(() => {
    api.buildTwinMessage({ history: [], message: '' }).then(r => {
      setHistory([{ role: 'assistant', content: r.reply }])
    }).catch(() => setHistory([{ role: 'assistant', content:
      "Hi! I'm the Twin Builder. Tell me about the machine or equipment you want to twin." }]))
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
    if (!image) { setErr('Drop a photo of the asset first.'); return }
    setBuilding(true); setErr(null)
    setLog([{ t: `> domain: ${domainMeta(domain).label}  quality: ${quality}`, acc: true }])
    setLog(l => [...l, { t: '> uploading image…' }])
    try {
      const r = await api.buildTwinGenerate({
        machine: machineName || machine?.name || domainMeta(domain).label,
        domain,
        image_b64: image.b64,
        filename: image.name || 'machine.png',
        quality,
      })
      setProvider(r.provider || null)
      setBuiltDomain(domain)
      onBuilt(r.tenant, r.machine)
      setLog(l => [...l,
        { t: `✓ live ${domainMeta(domain).label} twin built — sensors streaming`, ok: true },
        { t: `  provider: ${r.provider || 'none'}  quality: ${r.quality || quality}`, acc: true },
      ])
      if (r.tripo === 'running' && r.task_id) {
        const pName = r.provider === 'runpod' ? 'RunPod' : 'Tripo'
        setLog(l => [...l, { t: `${pName}: reconstructing 3D model from image…`, acc: true }])
        pollStatus(r.task_id, r.tenant, pName)
      } else if (r.tripo === 'no_key') {
        setLog(l => [...l, { t: '⚠ No 3D provider configured (set RUNPOD_API_KEY or TRIPO_API_KEY in .env)', warn: true }])
        setBuilding(false)
      } else {
        setLog(l => [...l, { t: '3D generation: ' + r.tripo, warn: true }]); setBuilding(false)
      }
    } catch (e) { setErr(String(e.message || e)); setBuilding(false) }
  }

  function pollStatus(taskId, tnt, pName) {
    let n = 0
    pollRef.current = setInterval(async () => {
      n++
      try {
        const s = await api.buildTwinStatus(taskId)
        if (s.progress != null && n % 2 === 0)
          setLog(l => [...l, { t: `${pName}: ${s.status} ${s.progress || 0}%` }])
        if (s.status === 'success' && s.model_url) {
          clearInterval(pollRef.current)
          setModelUrl(api.modelUrl(tnt))
          setLog(l => [...l, { t: `✓ 3D model ready (${pName})`, ok: true }])
          setBuilding(false)
        } else if (s.status === 'failed' || s.status === 'error') {
          clearInterval(pollRef.current)
          setLog(l => [...l, { t: `${pName} failed: ${s.detail || s.status}`, warn: true }])
          setBuilding(false)
        }
      } catch { /* keep polling */ }
      if (n > 120) { clearInterval(pollRef.current); setBuilding(false) }
    }, 2500)
  }

  const domInfo = BUILD_DOMAINS.find(d => d.key === domain) || BUILD_DOMAINS[0]

  return (
    <div className="panel">
      <div className="panel-header">
        <div><div className="panel-title">Build a Twin</div>
          <div className="panel-subtitle">Pick a domain, drop a photo of your asset, and the platform builds a live digital twin with 3D model, sensors, and AI agents.</div></div>
      </div>
      {err && <div className="card" style={{ borderColor: 'rgba(225,29,72,.4)', color: 'var(--accent-red)', marginBottom: 16 }}>{err}</div>}

      {/* ── Step 1: Domain selector ── */}
      <div className="card section-gap">
        <div className="card-title"><Icon n="ti-category" /> 1. Select Domain</div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {BUILD_DOMAINS.map(d => (
            <button key={d.key} className={`btn ${domain === d.key ? 'btn-primary' : ''}`}
              onClick={() => setDomain(d.key)}
              style={domain === d.key ? { background: d.color, borderColor: 'transparent', boxShadow: `0 4px 14px ${d.color}44` } : {}}>
              <Icon n={d.icon} /> {d.label}
              <span className="hint" style={{ marginLeft: 2, fontSize: 10, color: domain === d.key ? 'rgba(255,255,255,.7)' : undefined }}>{d.tag}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="grid-2">
        {/* ── Left: chat + upload + controls ── */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {/* Chat */}
          <div className="card" style={{ display: 'flex', flexDirection: 'column' }}>
            <div className="card-title"><Icon n="ti-sparkles" /> 2. Describe Your Asset <span className="pill pill-purple">agent</span></div>
            <div ref={msgsRef} style={{ flex: 1, minHeight: 180, maxHeight: 260, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 10, padding: '2px' }}>
              {history.map((m, i) => (
                <div key={i} style={{ alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start', maxWidth: '85%',
                  padding: '10px 13px', borderRadius: 14, fontSize: 12.5, lineHeight: 1.55,
                  background: m.role === 'user' ? 'var(--gradient)' : 'var(--surface2)',
                  color: m.role === 'user' ? '#fff' : 'var(--text)',
                  border: m.role === 'user' ? 'none' : '1px solid var(--border)' }}>
                  {m.role === 'assistant' && <div style={{ fontSize: 10, color: 'var(--muted)', marginBottom: 3, fontWeight: 600 }}>Twin Builder</div>}
                  {m.content}
                </div>
              ))}
              {thinking && <div style={{ alignSelf: 'flex-start' }}><span className="spinner" /></div>}
            </div>
            <div className="row" style={{ marginTop: 10 }}>
              <input className="input" value={input} placeholder="e.g. A Collins TFE731 turbofan on a test stand…"
                onChange={e => setInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && send()} />
              <button className="btn btn-primary" onClick={send}><Icon n="ti-send" /></button>
            </div>
          </div>

          {/* Image upload */}
          <div className="card">
            <div className="card-title"><Icon n="ti-photo" /> 3. Upload Asset Photo</div>
            <div style={{ border: `2px dashed ${drag ? domInfo.color : 'var(--border2)'}`,
              borderRadius: 14, background: drag ? `${domInfo.color}11` : 'var(--brand-softer)',
              padding: 18, textAlign: 'center', cursor: 'pointer', transition: 'all .2s' }}
              onClick={() => fileRef.current?.click()}
              onDragOver={e => { e.preventDefault(); setDrag(true) }}
              onDragLeave={() => setDrag(false)}
              onDrop={e => { e.preventDefault(); setDrag(false); loadFile(e.dataTransfer.files[0]) }}>
              <input ref={fileRef} type="file" accept="image/*" style={{ display: 'none' }}
                onChange={e => loadFile(e.target.files[0])} />
              {image
                ? <div style={{ position: 'relative', display: 'inline-block' }}>
                    <img src={image.preview} alt="asset" style={{ maxHeight: 130, borderRadius: 12, border: '2px solid var(--border)' }} />
                    <button onClick={e => { e.stopPropagation(); setImage(null) }}
                      style={{ position: 'absolute', top: -8, right: -8, width: 24, height: 24, borderRadius: '50%',
                        background: 'var(--accent-red)', color: '#fff', border: 'none', cursor: 'pointer',
                        display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 12 }}>✕</button>
                  </div>
                : <><div style={{ fontSize: 28, color: domInfo.color }}><Icon n="ti-cloud-upload" /></div>
                    <div style={{ fontWeight: 600, marginTop: 6, fontSize: 13 }}>Drop a photo of your {domInfo.label.toLowerCase()}</div>
                    <div className="hint" style={{ fontSize: 11, marginTop: 4 }}>PNG / JPG — any angle works, clean background is best</div></>}
            </div>
          </div>

          {/* Quality + Build */}
          <div className="card">
            <div className="card-title"><Icon n="ti-wand" /> 4. Generate 3D Twin</div>
            <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
              <div className="card-label" style={{ alignSelf: 'center', marginBottom: 0 }}>Quality:</div>
              <button className={`btn ${quality === 'fast' ? 'btn-primary' : ''}`} onClick={() => setQuality('fast')}
                style={{ fontSize: 11 }}>
                <Icon n="ti-bolt" /> Fast <span className="hint" style={{ fontSize: 9 }}>~20s</span>
              </button>
              <button className={`btn ${quality === 'high' ? 'btn-primary' : ''}`} onClick={() => setQuality('high')}
                style={{ fontSize: 11 }}>
                <Icon n="ti-diamond" /> High Quality <span className="hint" style={{ fontSize: 9 }}>~40s</span>
              </button>
            </div>
            <button className="btn btn-primary" style={{ width: '100%', justifyContent: 'center', padding: '12px 0' }}
              onClick={build} disabled={building || !image}>
              {building
                ? <><span className="spinner" /> Building {domInfo.label} Twin…</>
                : <><Icon n="ti-wand" /> Build 3D Twin — {domInfo.label}</>}
            </button>
          </div>
        </div>

        {/* ── Right: 3D result + log ── */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div className="card">
            <div className="card-title">
              <Icon n="ti-cube" /> Reconstructed 3D Model
              {tenant && <span className="pill pill-green">live</span>}
              {provider && <span className="pill pill-blue" style={{ fontSize: 9 }}>{provider === 'runpod' ? 'RunPod GPU' : provider}</span>}
            </div>
            {modelUrl
              ? (builtDomain === 'turbine-engine'
                  ? <TurbineModel url={modelUrl} latest={twin?.latest || {}} height={320} />
                  : <div style={{ height: 320, display: 'flex', alignItems: 'center', justifyContent: 'center',
                      background: 'var(--surface2)', borderRadius: 14, overflow: 'hidden' }}>
                      <TurbineModel url={modelUrl} latest={twin?.latest || {}} height={320} />
                    </div>)
              : <div className="hero3d" style={{ height: 320 }}>
                  <div className="lbl">
                    <div className="big" style={{ fontSize: 24 }}><Icon n={domInfo.icon} /></div>
                    <div className="big">{domInfo.label} Twin</div>
                    {building
                      ? <div style={{ marginTop: 8 }}>
                          <span className="spinner" style={{ borderTopColor: '#7c3aed' }} />
                          <span style={{ marginLeft: 8 }}>Generating 3D model from your photo…</span>
                        </div>
                      : <div style={{ marginTop: 6 }}>Select domain, upload photo, and hit Build</div>}
                  </div>
                </div>}
          </div>

          {/* Build log */}
          {log.length > 0 && (
            <div className="card">
              <div className="card-title"><Icon n="ti-terminal-2" /> Build Log
                {provider && <span className="pill pill-surface" style={{ fontSize: 9 }}>{provider}</span>}
              </div>
              <div className="mono" style={{ fontSize: 11, maxHeight: 200, overflowY: 'auto', lineHeight: 1.8 }}>
                {log.map((l, i) => (
                  <div key={i} style={{ color: l.ok ? 'var(--accent-green)' : l.warn ? 'var(--accent-amber)' : l.acc ? 'var(--brand)' : 'var(--muted)',
                    animation: 'fadeIn .3s ease', padding: '1px 0' }}>{l.t}</div>
                ))}
              </div>
            </div>
          )}

          {/* How it works */}
          {!building && !modelUrl && (
            <div className="card" style={{ background: 'var(--brand-softer)', border: '1px solid var(--brand-ring)' }}>
              <div className="card-title" style={{ fontSize: 12 }}><Icon n="ti-info-circle" /> How it works</div>
              <div style={{ fontSize: 11.5, lineHeight: 1.7, color: 'var(--muted)' }}>
                <div style={{ marginBottom: 6 }}><b>1.</b> Pick the domain type for your equipment</div>
                <div style={{ marginBottom: 6 }}><b>2.</b> Chat with the AI to describe the asset (optional)</div>
                <div style={{ marginBottom: 6 }}><b>3.</b> Upload a photo from any angle</div>
                <div><b>4.</b> The platform creates a live digital twin with the 3D model, wired to physics simulation, sensor telemetry, and 12 AI agents</div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
