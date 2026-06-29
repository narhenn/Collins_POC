import React, { Suspense, useMemo, useState } from 'react'
import { Canvas } from '@react-three/fiber'
import { OrbitControls, useGLTF, Html, Bounds, ContactShadows } from '@react-three/drei'
import * as THREE from 'three'
import { SIG, sevClass, fmt } from './lib.jsx'

const HOT_COLOR = { '': '#16a34a', warn: '#d97706', crit: '#e11d48' }

// Where each sensor hotspot sits relative to the model's normalized bounds.
const HOTSPOTS = [
  ['aero:exhaustGasTemp', [1.1, 0.2, 0]],
  ['aero:shaftSpeedN1', [-1.1, 0, 0]],
  ['aero:vibrationG', [0, 1.1, 0.2]],
  ['aero:oilTemperature', [0.2, -0.9, 0.4]],
  ['aero:oilPressure', [-0.4, -0.4, -1.0]],
  ['aero:fuelFlow', [0.4, 0.3, 1.0]],
]

function Model({ url }) {
  const { scene } = useGLTF(url)
  // center + scale to a ~3-unit box
  const cloned = useMemo(() => {
    const s = scene.clone(true)
    const box = new THREE.Box3().setFromObject(s)
    const size = new THREE.Vector3(); box.getSize(size)
    const center = new THREE.Vector3(); box.getCenter(center)
    const scale = 3 / (Math.max(size.x, size.y, size.z) || 1)
    s.position.sub(center)
    s.scale.setScalar(scale)
    s.traverse(o => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true } })
    return s
  }, [scene])
  return <primitive object={cloned} />
}

function Hotspot({ pos, sig, value }) {
  const [open, setOpen] = useState(false)
  const sev = sevClass(sig, value)
  const color = HOT_COLOR[sev]
  const m = SIG[sig] || { label: sig, unit: '' }
  return (
    <group position={pos}>
      <Html center distanceFactor={8}>
        <div onClick={() => setOpen(o => !o)} style={{ cursor: 'pointer', transform: 'translateZ(0)' }}>
          <div style={{ width: 14, height: 14, borderRadius: '50%', background: color,
            border: '2px solid #fff', boxShadow: `0 0 0 4px ${color}44`, margin: '0 auto' }} />
          {open && (
            <div style={{ marginTop: 6, background: 'rgba(12,14,28,.92)', color: '#fff',
              border: `1px solid ${color}`, borderRadius: 8, padding: '5px 9px',
              fontFamily: 'JetBrains Mono, monospace', fontSize: 11, whiteSpace: 'nowrap' }}>
              {m.label}: <b>{fmt(value)}</b> {m.unit}
            </div>
          )}
        </div>
      </Html>
    </group>
  )
}

function Fallback({ label }) {
  return <Html center><div style={{ color: '#aab0e0', fontFamily: 'JetBrains Mono, monospace', fontSize: 12 }}>{label}</div></Html>
}

export default function TurbineModel({ url, latest = {}, height = 300 }) {
  return (
    <div style={{ height, borderRadius: 18, overflow: 'hidden', background: '#0b0d18', position: 'relative' }}>
      <Canvas shadows camera={{ position: [4, 2.5, 4.5], fov: 48 }} dpr={[1, 2]}>
        <color attach="background" args={['#0b0d18']} />
        <ambientLight intensity={0.7} />
        <directionalLight position={[5, 8, 5]} intensity={1.4} castShadow />
        <directionalLight position={[-5, 3, -4]} intensity={0.5} color="#9ec9ff" />
        <Suspense fallback={<Fallback label="Loading 3D model…" />}>
          <Bounds fit clip observe margin={1.2}>
            <Model url={url} />
          </Bounds>
          {HOTSPOTS.filter(([s]) => latest[s] != null).map(([s, pos]) => (
            <Hotspot key={s} pos={pos} sig={s} value={latest[s]} />
          ))}
        </Suspense>
        <ContactShadows position={[0, -1.6, 0]} opacity={0.5} scale={10} blur={2.4} far={4} />
        <OrbitControls enablePan={false} autoRotate autoRotateSpeed={0.6} minDistance={3} maxDistance={12} />
      </Canvas>
      <div style={{ position: 'absolute', top: 12, left: 12, background: 'rgba(12,14,28,.72)',
        border: '1px solid rgba(124,58,237,.4)', color: '#dfe3ff', fontFamily: 'JetBrains Mono, monospace',
        fontSize: 11, padding: '6px 12px', borderRadius: 999 }}>
        ⬡ 3D Twin · click a hotspot for live value
      </div>
    </div>
  )
}
