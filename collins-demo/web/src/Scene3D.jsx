// Scene3D.jsx — React wrapper that mounts the procedural Three.js engine
// (scene/engine.js), wires the inspector's "Ask AI" to the orchestrator, and
// (for the live Wire-EDM twin) streams real telemetry onto the 3-D subsystems.
import React, { useEffect, useRef } from 'react'
import { createViewer } from './scene/engine.js'
import { SIG, sevClass, fmt } from './lib.jsx'
import api from './api'

// Map the EDM twin's live signals onto the subsystem assets in the scene.
function metric(sig, live) { const m = SIG[sig]; return [m?.label || sig, m?.unit || '', fmt(live[sig])] }
function worst(sigs, live) {
  let s = 'ok'
  for (const sig of sigs) { const c = sevClass(sig, live[sig]); if (c === 'crit') return 'crit'; if (c === 'warn') s = 'warn' }
  return s
}
function edmUpdates(live) {
  if (!live || live['edm:cuttingSpeed'] == null) return null
  return {
    'EDM-1': { status: worst(['edm:shortCircuitRate', 'edm:wireBreakRisk', 'edm:dielectricTemperature'], live),
      metrics: [metric('edm:cuttingSpeed', live), metric('edm:gapVoltage', live), metric('edm:shortCircuitRate', live)] },
    'GEN-1': { status: worst(['edm:shortCircuitRate', 'edm:gapVoltage'], live),
      metrics: [metric('edm:peakCurrent', live), metric('edm:shortCircuitRate', live), metric('edm:gapVoltage', live)] },
    'DIE-1': { status: worst(['edm:dielectricConductivity', 'edm:dielectricTemperature', 'edm:dielectricPressure', 'edm:dielectricFlow'], live),
      metrics: [metric('edm:dielectricConductivity', live), metric('edm:dielectricTemperature', live), metric('edm:dielectricFlow', live)] },
    'WIRE-1': { status: worst(['edm:wireBreakRisk', 'edm:wireTension'], live),
      metrics: [metric('edm:wireTension', live), metric('edm:wireBreakRisk', live), metric('edm:wireFeedRate', live)] },
    'GUIDE-1': { status: worst(['edm:wireWear', 'edm:surfaceRoughnessRa'], live),
      metrics: [metric('edm:wireWear', live), metric('edm:surfaceRoughnessRa', live)] },
  }
}

export default function Scene3D({ domain, machine, live, height = 380 }) {
  const hostRef = useRef(null)
  const viewerRef = useRef(null)

  useEffect(() => {
    if (!hostRef.current) return
    const onAskAI = async (asset) => {
      const r = await api.assetStatus({ machine: machine || domain, domain, asset })
      return r?.status || 'No AI status returned.'
    }
    let viewer
    try { viewer = createViewer(hostRef.current, { domain, machine, onAskAI }) } catch (e) { console.error('3D scene failed', e) }
    viewerRef.current = viewer
    return () => { try { viewer && viewer.dispose() } catch {} viewerRef.current = null }
  }, [domain, machine])

  // Stream live telemetry onto the EDM subsystems (status pins + inspector).
  useEffect(() => {
    const v = viewerRef.current
    if (!v || !v.updateAssets || domain !== 'edm-machine') return
    v.updateAssets(edmUpdates(live))
  }, [live, domain])

  return <div ref={hostRef} className="hero3d scene3d-host" style={{ height, position: 'relative', padding: 0, overflow: 'hidden' }} />
}
