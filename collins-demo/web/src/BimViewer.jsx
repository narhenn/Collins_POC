// BimViewer.jsx — the BIM X-Ray page: IFC buildings as overlaid discipline
// layers (architecture / structure / plumbing / HVAC / electrical), rendered
// from the per-discipline GLBs the orchestrator's bim_ifc pipeline produces.
//
//   • layer toggles + per-layer opacity
//   • X-RAY mode — the shell goes glassy, the systems glow through the walls
//   • horizontal section cut (slice the building at any height)
//   • storey filter
//   • WALK mode — pointer-lock + WASD, walk inside and look through walls
//   • click any element → inspector (class, storey, discipline, GUID)
import React, { Suspense, useEffect, useMemo, useRef, useState } from 'react'
import { Canvas, useThree, useFrame } from '@react-three/fiber'
import { OrbitControls, PointerLockControls, useGLTF, Html } from '@react-three/drei'
import * as THREE from 'three'
import { Icon } from './lib.jsx'
import api from './api.js'

const SHELL = new Set(['architecture', 'structure', 'site'])

// A mesh material may be a single Material or an array (multi-material); this
// normalises both to an array so we never call .clone() on a bare Array.
const asMats = (m) => (Array.isArray(m) ? m : [m]).filter(Boolean)

// Error boundary so a bad GLB / three.js hiccup shows a message instead of
// white-screening the whole app.
class SceneBoundary extends React.Component {
  constructor(p) { super(p); this.state = { err: null } }
  static getDerivedStateFromError(err) { return { err } }
  componentDidCatch(err) { console.warn('BIM scene error:', err) }
  render() {
    if (this.state.err) {
      return <div style={{ height: '100%', display: 'flex', alignItems: 'center',
        justifyContent: 'center', color: '#aab0e0', fontSize: 13, textAlign: 'center', padding: 24 }}>
        <div><div style={{ fontSize: 22, marginBottom: 8 }}>⬡</div>
          Couldn't render this building's 3D layers.<br />
          <span style={{ fontSize: 11, color: '#7a80a8' }}>{String(this.state.err?.message || this.state.err)}</span>
        </div></div>
    }
    return this.props.children
  }
}

// ── one discipline layer ──────────────────────────────────────────────
function Layer({ url, disc, color, visible, opacity, xray, storey, storeyOf, onPick }) {
  const { scene } = useGLTF(url)
  const root = useMemo(() => {
    const s = scene.clone(true)
    s.traverse(o => {
      if (!o.isMesh) return
      o.material = asMats(o.material).map(mm => {
        const c = mm.clone()
        c.side = THREE.DoubleSide
        return c
      })
      if (o.material.length === 1) o.material = o.material[0]  // keep single-mat meshes simple
      o.userData.disc = disc
    })
    return s
  }, [scene, disc])

  // material mode: xray fades the shell, systems get a slight glow
  useEffect(() => {
    const shell = SHELL.has(disc)
    root.traverse(o => {
      if (!o.isMesh) return
      for (const m of asMats(o.material)) {
        if (xray && shell) {
          m.transparent = true
          m.opacity = 0.13 * opacity
          m.depthWrite = false
        } else {
          m.transparent = opacity < 0.999
          m.opacity = opacity
          m.depthWrite = opacity > 0.35
        }
        if (xray && !shell) {
          if (!m.emissive) m.emissive = new THREE.Color()
          m.emissive.setRGB(color[0], color[1], color[2])
          m.emissiveIntensity = 0.35
        } else if (m.emissive) {
          m.emissiveIntensity = 0
        }
        m.needsUpdate = true
      }
    })
  }, [root, xray, opacity, disc, color])

  // storey filter: node names carry "<guid>|<class>|<name>"
  useEffect(() => {
    root.traverse(o => {
      if (!o.isMesh) return
      const guid = (o.name || o.parent?.name || '').split('|')[0]
      o.visible = !storey || !storeyOf[guid] || storeyOf[guid] === storey
    })
  }, [root, storey, storeyOf])

  if (!visible) return null
  return <primitive object={root}
    onPointerDown={e => { e.stopPropagation(); onPick(e.object, e.point) }} />
}

// ── walk-mode movement (pointer lock + WASD) ─────────────────────────
function WalkRig({ speed = 3.2, eye }) {
  const keys = useRef({})
  const { camera } = useThree()
  useEffect(() => {
    camera.position.set(eye[0], eye[1], eye[2])
    const dn = e => { keys.current[e.code] = true }
    const up = e => { keys.current[e.code] = false }
    window.addEventListener('keydown', dn); window.addEventListener('keyup', up)
    return () => { window.removeEventListener('keydown', dn); window.removeEventListener('keyup', up) }
  }, [camera, eye])
  useFrame((_, dt) => {
    const k = keys.current
    const v = (k.ShiftLeft || k.ShiftRight ? 2.2 : 1) * speed * Math.min(dt, 0.1)
    const fwd = new THREE.Vector3(); camera.getWorldDirection(fwd)
    fwd.y = 0; fwd.normalize()
    const right = new THREE.Vector3().crossVectors(fwd, new THREE.Vector3(0, 1, 0))
    if (k.KeyW || k.ArrowUp) camera.position.addScaledVector(fwd, v)
    if (k.KeyS || k.ArrowDown) camera.position.addScaledVector(fwd, -v)
    if (k.KeyD || k.ArrowRight) camera.position.addScaledVector(right, v)
    if (k.KeyA || k.ArrowLeft) camera.position.addScaledVector(right, -v)
    if (k.KeyE || k.Space) camera.position.y += v
    if (k.KeyQ || k.KeyC) camera.position.y -= v
  })
  return <PointerLockControls />
}

// global horizontal section cut
function SectionCut({ enabled, height }) {
  const { gl } = useThree()
  useEffect(() => {
    gl.localClippingEnabled = true
    gl.clippingPlanes = enabled
      ? [new THREE.Plane(new THREE.Vector3(0, -1, 0), height)]
      : []
    return () => { gl.clippingPlanes = [] }
  }, [gl, enabled, height])
  return null
}

function Loading() {
  return <Html center><div style={{ color: '#aab0e0', fontFamily: 'var(--mono)', fontSize: 12 }}>
    Loading building layers…</div></Html>
}

// ── the page ──────────────────────────────────────────────────────────
export default function BimViewer() {
  const [buildings, setBuildings] = useState([])
  const [samples, setSamples] = useState([])
  const [bid, setBid] = useState(null)
  const [job, setJob] = useState(null)              // ingest status while processing
  const [manifest, setManifest] = useState(null)
  const [elements, setElements] = useState([])
  const [layers, setLayers] = useState({})          // {disc: {visible, opacity}}
  const [xray, setXray] = useState(false)
  const [cut, setCut] = useState(false)
  const [cutH, setCutH] = useState(2)
  const [storey, setStorey] = useState('')
  const [walk, setWalk] = useState(false)
  const [picked, setPicked] = useState(null)
  const fileRef = useRef(null)

  const refresh = async () => {
    try {
      const r = await api.bimBuildings()
      setBuildings(r.buildings || []); setSamples(r.samples || [])
    } catch { }
  }
  useEffect(() => { refresh() }, [])

  // poll ingest status until ready
  useEffect(() => {
    if (!job || job.state === 'ready' || job.state === 'error') return
    const iv = setInterval(async () => {
      try {
        const s = await api.bimStatus(job.bid)
        setJob(s)
        if (s.state === 'ready') { clearInterval(iv); refresh(); openBuilding(s.bid) }
      } catch { }
    }, 1500)
    return () => clearInterval(iv)
  }, [job?.bid, job?.state])

  async function openBuilding(id) {
    const s = await api.bimStatus(id)
    if (s.state !== 'ready') { setJob(s); return }
    const man = s.manifest
    setBid(id); setManifest(man); setPicked(null); setStorey('')
    setLayers(Object.fromEntries(man.disciplines.map(d =>
      [d.id, { visible: true, opacity: 1 }])))
    setCutH(Math.round((man.bounds?.max?.[2] ?? 3) * 0.66))
    try { setElements(await api.bimFileJson(id, 'elements.json')) } catch { setElements([]) }
  }

  async function loadSample(id) { setJob(await api.bimSample(id)) }

  async function upload(e) {
    const f = e.target.files?.[0]
    if (!f) return
    const s = await api.bimUpload(f)
    setJob(s)
    e.target.value = ''
  }

  const byGuid = useMemo(() => Object.fromEntries(elements.map(el => [el.guid, el])), [elements])
  const storeyOf = useMemo(() => Object.fromEntries(
    elements.filter(el => el.storey).map(el => [el.guid, el.storey])), [elements])
  const storeys = manifest?.storeys || []

  // camera targets from IFC bounds (IFC is Z-up; the scene group rotates it Y-up)
  const b = manifest?.bounds
  const center = b ? [(b.min[0] + b.max[0]) / 2, (b.min[2] + b.max[2]) / 2, -(b.min[1] + b.max[1]) / 2] : [0, 1, 0]
  const size = b ? Math.max(b.max[0] - b.min[0], b.max[1] - b.min[1], b.max[2] - b.min[2]) : 12
  const eye = [center[0], (b?.min?.[2] ?? 0) + 1.6, center[2]]

  function onPick(obj, point) {
    const raw = obj.name || obj.parent?.name || ''
    const [guid, cls, name] = raw.split('|')
    const el = byGuid[guid]
    setPicked({ guid, cls: el?.class || cls, name: el?.name || name || '(unnamed)',
      storey: el?.storey, disc: el?.discipline || obj.userData?.disc })
  }

  const processing = job && job.state !== 'ready' && job.state !== 'error'

  return (
    <div className="panel">
      <div className="panel-header">
        <div>
          <div className="panel-title">BIM X-Ray</div>
          <div className="panel-subtitle">IFC → discipline layers · see the plumbing, HVAC and wiring through the walls</div>
        </div>
        <div className="panel-actions">
          <input ref={fileRef} type="file" accept=".ifc" style={{ display: 'none' }} onChange={upload} />
          <button className="btn" onClick={() => fileRef.current?.click()}>
            <Icon n="ti-upload" /> Upload IFC</button>
          {samples.map(s => (
            <button key={s.id} className="btn btn-primary" disabled={!s.available || processing}
              onClick={() => loadSample(s.id)}>
              <Icon n="ti-building" /> {s.name}</button>
          ))}
        </div>
      </div>

      {processing && (
        <div className="card section-gap">
          <div className="card-title"><span className="spinner" /> Processing {job.bid}…</div>
          <div style={{ fontSize: 12.5, color: 'var(--hint)' }}>{job.detail} · {job.progress ?? 0}%</div>
          <div style={{ height: 6, background: 'var(--surface2)', borderRadius: 99, marginTop: 8 }}>
            <div style={{ height: '100%', width: `${job.progress ?? 0}%`, background: 'var(--gradient)', borderRadius: 99, transition: 'width .8s' }} />
          </div>
        </div>
      )}
      {job?.state === 'error' && (
        <div className="card section-gap" style={{ borderColor: 'rgba(225,29,72,.4)' }}>
          <div className="card-title" style={{ color: 'var(--accent-red)' }}>Ingest failed</div>
          <div style={{ fontSize: 12.5 }}>{job.detail}</div>
        </div>
      )}

      {!manifest && !processing && (
        <div className="grid-3 section-gap">
          {buildings.map(bld => (
            <div key={bld.bid} className="card twin-card" style={{ cursor: 'pointer' }} onClick={() => openBuilding(bld.bid)}>
              <div className="card-title"><Icon n="ti-building" /> {bld.name || bld.bid}</div>
              <div style={{ fontSize: 12, color: 'var(--hint)' }}>{bld.elements} elements · {(bld.disciplines || []).join(' · ')}</div>
            </div>
          ))}
          {buildings.length === 0 && (
            <div className="empty" style={{ gridColumn: '1/-1' }}>
              No buildings ingested yet — upload an IFC file or load the Duplex sample.
              The pipeline splits it into architecture / structure / plumbing / HVAC / electrical
              layers you can overlay and X-ray.</div>
          )}
        </div>
      )}

      {manifest && (
        <div className="section-gap" style={{ display: 'grid', gridTemplateColumns: '250px 1fr', gap: 14 }}>
          {/* controls */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div className="card">
              <div className="card-title" style={{ marginBottom: 8 }}><Icon n="ti-stack-2" /> Layers</div>
              {manifest.disciplines.map(d => {
                const st = layers[d.id] || { visible: true, opacity: 1 }
                const cssColor = `rgb(${d.color.map(c => Math.round(c * 255)).join(',')})`
                return (
                  <div key={d.id} style={{ padding: '7px 0', borderTop: '1px dashed var(--border)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span style={{ width: 10, height: 10, borderRadius: 3, background: cssColor }} />
                      <b style={{ fontSize: 12.5, flex: 1 }}>{d.label}</b>
                      <span style={{ fontSize: 10.5, color: 'var(--hint)' }}>{d.count}</span>
                      <button className="btn" style={{ padding: '2px 8px' }} title={st.visible ? 'Hide' : 'Show'}
                        onClick={() => setLayers(l => ({ ...l, [d.id]: { ...st, visible: !st.visible } }))}>
                        <Icon n={st.visible ? 'ti-eye' : 'ti-eye-off'} /></button>
                    </div>
                    <input type="range" min={5} max={100} value={Math.round(st.opacity * 100)}
                      style={{ width: '100%' }} disabled={!st.visible}
                      onChange={e => setLayers(l => ({ ...l, [d.id]: { ...st, opacity: +e.target.value / 100 } }))} />
                  </div>
                )
              })}
            </div>

            <div className="card">
              <div className="card-title" style={{ marginBottom: 8 }}><Icon n="ti-adjustments" /> View</div>
              <button className={`btn ${xray ? 'btn-primary' : ''}`} style={{ width: '100%', marginBottom: 6 }}
                onClick={() => setXray(x => !x)}>
                <Icon n="ti-scan" /> X-Ray {xray ? 'ON' : 'off'}</button>
              <button className={`btn ${walk ? 'btn-primary' : ''}`} style={{ width: '100%', marginBottom: 6 }}
                onClick={() => setWalk(w => !w)}>
                <Icon n="ti-walk" /> Walk mode {walk ? 'ON' : 'off'}</button>
              {walk && <div style={{ fontSize: 10.5, color: 'var(--hint)', marginBottom: 6 }}>
                Click the scene to lock the mouse · WASD move · E/Q up/down · Shift run · Esc exit</div>}
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4 }}>
                <label style={{ fontSize: 12 }}><input type="checkbox" checked={cut}
                  onChange={e => setCut(e.target.checked)} /> Section cut</label>
                <input type="range" min={(b?.min?.[2] ?? 0) + 0.3} max={b?.max?.[2] ?? 8} step={0.1}
                  value={cutH} disabled={!cut} style={{ flex: 1 }}
                  onChange={e => setCutH(+e.target.value)} />
                <span style={{ fontSize: 10.5, fontFamily: 'var(--mono)' }}>{cutH.toFixed(1)}m</span>
              </div>
              {storeys.length > 0 && (
                <select className="select" style={{ width: '100%', marginTop: 8 }} value={storey}
                  onChange={e => setStorey(e.target.value)}>
                  <option value="">All storeys / spaces</option>
                  {storeys.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              )}
              <button className="btn" style={{ width: '100%', marginTop: 8 }} onClick={() => { setManifest(null); setBid(null); refresh() }}>
                <Icon n="ti-arrow-left" /> All buildings</button>
            </div>

            {picked && (
              <div className="card">
                <div className="card-title" style={{ marginBottom: 6 }}><Icon n="ti-focus-2" /> Element</div>
                <div style={{ fontSize: 12.5, fontWeight: 700 }}>{picked.name}</div>
                <div style={{ fontSize: 11.5, color: 'var(--hint)', marginTop: 4, lineHeight: 1.7 }}>
                  {picked.cls}<br />
                  {picked.disc && <>Layer: <b style={{ color: 'var(--text)' }}>{picked.disc}</b><br /></>}
                  {picked.storey && <>Storey: <b style={{ color: 'var(--text)' }}>{picked.storey}</b><br /></>}
                  <span style={{ fontFamily: 'var(--mono)', fontSize: 10 }}>{picked.guid}</span>
                </div>
              </div>
            )}
          </div>

          {/* scene */}
          <div style={{ height: 640, borderRadius: 16, overflow: 'hidden', background: '#0b0d18', position: 'relative' }}>
           <SceneBoundary>
            <Canvas camera={{ position: [center[0] + size * 0.9, center[1] + size * 0.7, center[2] + size * 0.9], fov: 50, near: 0.1, far: 500 }} dpr={[1, 2]}>
              <color attach="background" args={['#0b0d18']} />
              {/* local lights only — no CDN environment map, so the viewer is fully offline-safe */}
              <hemisphereLight args={['#dfe6ff', '#20263c', 0.9]} />
              <ambientLight intensity={0.35} />
              <directionalLight position={[20, 30, 15]} intensity={1.1} />
              <directionalLight position={[-15, 10, -10]} intensity={0.35} color="#9ec9ff" />
              <SectionCut enabled={cut} height={cutH} />
              <Suspense fallback={<Loading />}>
                {/* IFC is Z-up → rotate into three's Y-up world */}
                <group rotation={[-Math.PI / 2, 0, 0]}>
                  {manifest.disciplines.map(d => (
                    <Layer key={d.id} url={api.bimFileUrl(bid, d.glb)} disc={d.id}
                      color={d.color} visible={layers[d.id]?.visible !== false}
                      opacity={layers[d.id]?.opacity ?? 1} xray={xray}
                      storey={storey} storeyOf={storeyOf} onPick={onPick} />
                  ))}
                </group>
                <gridHelper args={[Math.ceil(size * 2.5), Math.ceil(size * 2.5), '#26305a', '#141a33']}
                  position={[center[0], (b?.min?.[2] ?? 0) - 0.02, center[2]]} />
              </Suspense>
              {walk
                ? <WalkRig eye={eye} />
                : <OrbitControls target={center} enableDamping makeDefault />}
            </Canvas>
           </SceneBoundary>
            <div style={{ position: 'absolute', top: 12, left: 12, background: 'rgba(12,14,28,.72)',
              border: '1px solid rgba(124,58,237,.4)', color: '#dfe3ff', fontFamily: 'var(--mono)',
              fontSize: 11, padding: '6px 12px', borderRadius: 999, display: 'flex', gap: 6, alignItems: 'center' }}>
              <Icon n="ti-building" /> <b>{manifest.name}</b> · {manifest.elements} elements
              {xray && <span style={{ color: '#8ff0c8' }}>· X-RAY</span>}
              {walk && <span style={{ color: '#ffd479' }}>· WALK</span>}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
