import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Canvas, useThree } from '@react-three/fiber'
import { OrbitControls, useGLTF, Environment, Bounds } from '@react-three/drei'
import * as THREE from 'three'
import { PanelHeader, Card } from '../components/ui/Card'
import { Loading, Empty } from '../components/ui/States'
import { useToast } from '../context/ToastContext'
import { useTwin } from '../context/TwinContext'
import { useApi, usePolling } from '../hooks/useApi'
import { localName, shortId, timeOf } from '../lib/format'
import NoTwin from '../components/NoTwin'
import api from '../api/client'

/**
 * BIM 3D Viewer — upload an IFC file, see the building in 3D,
 * click elements to view their NextXR entity data, color-coded by status.
 */
export default function BimViewer() {
  const toast = useToast()
  const { activeTenant, activeTwin } = useTwin()
  const [uploading, setUploading] = useState(false)
  const [selected, setSelected] = useState(null)
  const [dragover, setDragover] = useState(false)
  const fileRef = useRef(null)

  const { data: status, refetch: refetchStatus } = useApi(
    () => api.bimStatus(activeTenant),
    [activeTenant],
    { skip: !activeTenant },
  )

  const hasModel = status?.has_model

  const upload = useCallback(async (file) => {
    if (!file || !activeTenant) return
    setUploading(true)
    try {
      const res = await api.bimUpload(activeTenant, file)
      toast.ok('BIM imported', `${res.entity_count} entities from ${res.filename}`)
      refetchStatus()
    } catch (e) {
      toast.err('Import failed', e.message)
    } finally {
      setUploading(false)
    }
  }, [activeTenant, toast, refetchStatus])

  const onDrop = useCallback((e) => {
    e.preventDefault()
    setDragover(false)
    const file = e.dataTransfer?.files?.[0]
    if (file) upload(file)
  }, [upload])

  if (!activeTwin) return <NoTwin />

  return (
    <div className="panel">
      <PanelHeader title="BIM 3D Viewer" subtitle={hasModel
        ? `${status.entity_count} entities · ${status.glb_size_mb} MB`
        : 'Upload an IFC file to visualize the building'
      }>
        {hasModel && (
          <button className="btn" onClick={() => { fileRef.current?.click() }}>
            <i className="ti ti-replace" /> Replace model
          </button>
        )}
      </PanelHeader>

      <input ref={fileRef} type="file" accept=".ifc" style={{ display: 'none' }}
        onChange={e => { if (e.target.files?.[0]) upload(e.target.files[0]) }} />

      {!hasModel ? (
        <Card>
          <div
            className={`bim-dropzone ${dragover ? 'dragover' : ''}`}
            onDragOver={e => { e.preventDefault(); setDragover(true) }}
            onDragLeave={() => setDragover(false)}
            onDrop={onDrop}
            onClick={() => fileRef.current?.click()}
          >
            {uploading ? (
              <Loading label="Parsing IFC and importing entities..." />
            ) : (
              <>
                <i className="ti ti-3d-cube-sphere" style={{ fontSize: 48, display: 'block', marginBottom: 12, color: 'var(--accent-blue)' }} />
                <div style={{ fontSize: 16, fontWeight: 500, marginBottom: 6 }}>
                  Drop an IFC file here or click to browse
                </div>
                <div style={{ fontSize: 13, color: 'var(--muted)' }}>
                  The file will be parsed, entities imported into the graph, and geometry converted for 3D viewing
                </div>
              </>
            )}
          </div>
        </Card>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 300px', gap: 12, height: 'calc(100vh - 160px)' }}>
          <div className="bim-canvas">
            <Suspense fallback={<Loading label="Loading 3D model..." />}>
              <Canvas
                gl={{ antialias: true, alpha: false }}
                camera={{ position: [30, 20, 30], fov: 50 }}
                style={{ background: '#0d1017' }}
              >
                <ambientLight intensity={0.4} />
                <directionalLight position={[10, 20, 10]} intensity={0.8} />
                <Bounds fit clip observe margin={1.4}>
                  <BimModel
                    tenant={activeTenant}
                    onSelect={setSelected}
                    selectedId={selected?.entityId}
                  />
                </Bounds>
                <OrbitControls makeDefault enableDamping dampingFactor={0.1} />
                <Environment preset="city" background={false} />
              </Canvas>
            </Suspense>
          </div>
          <BimSidePanel tenant={activeTenant} selected={selected} />
        </div>
      )}
    </div>
  )
}


function BimModel({ tenant, onSelect, selectedId }) {
  const url = api.bimModelUrl(tenant)
  const { scene } = useGLTF(url)

  const { data: mapping } = useApi(() => api.bimMapping(tenant), [tenant])
  const { data: entities } = usePolling(
    () => api.listEntities(tenant, 'PhysicalAsset', 100),
    4000, [tenant], { skip: !tenant },
  )

  // Build a reverse map: entityId -> status for color coding
  const statusMap = useMemo(() => {
    const map = {}
    if (entities?.nodes) {
      for (const n of entities.nodes) {
        map[n.id] = n.status || 'unknown'
      }
    }
    return map
  }, [entities])

  // Reverse mapping: meshName (globalId) -> entityId
  const reverseMap = useMemo(() => {
    if (!mapping) return {}
    const rm = {}
    for (const [gid, eid] of Object.entries(mapping)) {
      rm[gid] = eid
    }
    return rm
  }, [mapping])

  // Apply materials based on status
  useEffect(() => {
    if (!scene || !mapping) return
    scene.traverse((child) => {
      if (!child.isMesh) return
      const entityId = reverseMap[child.name]
      const isSelected = entityId === selectedId

      child.material = child.material.clone()
      child.material.transparent = true

      if (isSelected) {
        child.material.color = new THREE.Color('#7aa2f7')
        child.material.emissive = new THREE.Color('#7aa2f7')
        child.material.emissiveIntensity = 0.3
        child.material.opacity = 1.0
      } else if (entityId) {
        const status = statusMap[entityId]
        if (status === 'fault') {
          child.material.color = new THREE.Color('#e2564e')
          child.material.opacity = 0.9
        } else if (status === 'degraded') {
          child.material.color = new THREE.Color('#e0962f')
          child.material.opacity = 0.9
        } else if (status === 'running') {
          child.material.color = new THREE.Color('#4fae3a')
          child.material.opacity = 0.85
        } else {
          child.material.color = new THREE.Color('#4b8bf5')
          child.material.opacity = 0.8
        }
        child.material.emissive = new THREE.Color('#000000')
        child.material.emissiveIntensity = 0
      } else {
        // Unmapped structural element
        child.material.color = new THREE.Color('#232c3d')
        child.material.opacity = 0.35
        child.material.emissive = new THREE.Color('#000000')
      }
    })
  }, [scene, mapping, reverseMap, statusMap, selectedId])

  const handleClick = useCallback((e) => {
    e.stopPropagation()
    const mesh = e.object
    const entityId = reverseMap[mesh.name]
    if (entityId) {
      onSelect({ entityId, meshName: mesh.name })
    }
  }, [reverseMap, onSelect])

  return <primitive object={scene} onPointerDown={handleClick} />
}


function BimSidePanel({ tenant, selected }) {
  const { data: entity } = useApi(
    () => api.getEntity(selected?.entityId, tenant),
    [selected?.entityId, tenant],
    { skip: !selected?.entityId },
  )
  const node = entity?.node

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, overflowY: 'auto' }}>
      <Card title="Selected Element">
        {!selected ? (
          <Empty label="Click a building element to inspect it" icon="ti-pointer" />
        ) : !node ? (
          <Loading label="Loading entity..." />
        ) : (
          <div style={{ fontSize: 13 }}>
            <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 8 }}>{node.displayName}</div>
            <div style={{ color: 'var(--muted)', marginBottom: 12 }}>
              {localName(node.canonicalType)}
            </div>
            <div className="grid-2" style={{ gap: '6px 12px', fontSize: 12 }}>
              <div><span className="muted">Status</span></div>
              <div><StatusPill status={node.status} /></div>
              <div><span className="muted">ID</span></div>
              <div className="mono">{shortId(node.id, 12)}</div>
              {node.bimGlobalId && <>
                <div><span className="muted">IFC GUID</span></div>
                <div className="mono">{shortId(node.bimGlobalId, 12)}</div>
              </>}
              {node.setpoint != null && <>
                <div><span className="muted">Setpoint</span></div>
                <div>{node.setpoint} C</div>
              </>}
              {node.levelIndex != null && <>
                <div><span className="muted">Level</span></div>
                <div>{node.levelIndex}</div>
              </>}
            </div>
            {entity?.relationships?.length > 0 && (
              <div style={{ marginTop: 12 }}>
                <div style={{ fontSize: 11, fontFamily: 'var(--mono)', color: 'var(--muted)', marginBottom: 4 }}>
                  Relationships
                </div>
                {entity.relationships.map((r, i) => (
                  <div key={i} style={{ fontSize: 12, marginBottom: 2 }}>
                    <span style={{ color: 'var(--accent-blue)' }}>{localName(r.predicate || r.type)}</span>
                    {' -> '}{shortId(r.target || r.target_id, 10)}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </Card>

      <Card title="Legend">
        <div style={{ fontSize: 12, display: 'flex', flexDirection: 'column', gap: 4 }}>
          <LegendRow color="#4fae3a" label="Running / Healthy" />
          <LegendRow color="#e0962f" label="Degraded / Warning" />
          <LegendRow color="#e2564e" label="Fault / Critical" />
          <LegendRow color="#4b8bf5" label="Mapped entity" />
          <LegendRow color="#232c3d" label="Structural (no entity)" />
          <LegendRow color="#7aa2f7" label="Selected" glow />
        </div>
      </Card>
    </div>
  )
}


function StatusPill({ status }) {
  const colors = {
    running: 'var(--accent-green)',
    degraded: 'var(--accent-amber)',
    fault: 'var(--accent-red)',
    off: 'var(--muted)',
  }
  const c = colors[status] || 'var(--hint)'
  return (
    <span style={{
      padding: '1px 8px', borderRadius: 10, fontSize: 11, fontFamily: 'var(--mono)',
      color: c, border: `1px solid ${c}`,
    }}>{status || 'unknown'}</span>
  )
}


function LegendRow({ color, label, glow }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div style={{
        width: 12, height: 12, borderRadius: 3, background: color,
        boxShadow: glow ? `0 0 6px ${color}` : 'none',
      }} />
      <span className="muted">{label}</span>
    </div>
  )
}
