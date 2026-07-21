/**
 * EquipmentGallery — every asset in the hospital twin, as a 3-D asset catalog.
 *
 * ONE card per distinct asset TYPE (not per instance), grouped by catalog
 * category — each card a real, lazily-mounted 3-D model (AssetPreview). A type's
 * card rolls up the health of all its instances (worst status wins) and shows how
 * many there are; clicking opens an inspector on the least-healthy instance with
 * its live signal, condition and asset/warranty info.
 *
 * Fed by the campus twin's equipment roster (GET /api/twins/{tenant}/network ->
 * `equipment`), so a fault injected into the physics lights up exactly the assets
 * it touches.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import AssetPreview from './three/AssetPreview'
import { CATALOG, CATEGORIES } from './three/catalog'
import { Icon } from './lib.jsx'

const ENTRY = Object.fromEntries(CATALOG.map((c) => [c.key, c]))
const DOT = { crit: 'var(--accent-red)', warn: 'var(--accent-amber)', ok: 'var(--accent-green)' }
const RANK = { crit: 2, warn: 1, ok: 0 }

/** Mount the live 3-D preview only while (near) on-screen. */
function LazyThumb({ propKey }) {
  const ref = useRef(null)
  const [show, setShow] = useState(false)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const io = new IntersectionObserver(([e]) => setShow(e.isIntersecting), { rootMargin: '150px 0px' })
    io.observe(el)
    return () => io.disconnect()
  }, [])
  return (
    <div className="equip-card-thumb" ref={ref}>
      {show
        ? <AssetPreview assetKey={propKey} interactive={false} showHuman={false} showGrid={false} background="#0d1017" />
        : <Icon n="ti-loader" />}
    </div>
  )
}

export default function EquipmentGallery({ equipment }) {
  const [selected, setSelected] = useState(null)   // { type, instance }

  // Collapse instances -> one entry per asset type (prop key), worst status wins.
  const types = useMemo(() => {
    const byKey = {}
    for (const e of (equipment || [])) {
      const t = (byKey[e.prop] ||= { key: e.prop, instances: [], worst: 'ok', rep: e })
      t.instances.push(e)
      if ((RANK[e.status] ?? 0) > (RANK[t.worst] ?? 0)) { t.worst = e.status; t.rep = e }
    }
    return byKey
  }, [equipment])

  // Group types by catalog category, in catalog order.
  const groups = useMemo(() => {
    const byCat = {}
    for (const t of Object.values(types)) {
      const cat = ENTRY[t.key]?.cat || 'Other'
      ;(byCat[cat] ||= []).push(t)
    }
    for (const k of Object.keys(byCat)) {
      byCat[k].sort((a, b) => (ENTRY[a.key]?.label || a.key).localeCompare(ENTRY[b.key]?.label || b.key))
    }
    return [...CATEGORIES, 'Other'].filter((c) => byCat[c]?.length).map((c) => ({ cat: c, items: byCat[c] }))
  }, [types])

  const total = Object.keys(types).length
  const counts = useMemo(() => {
    const c = { ok: 0, warn: 0, crit: 0 }
    for (const e of (equipment || [])) c[e.status] = (c[e.status] || 0) + 1
    return c
  }, [equipment])

  if (!equipment || !equipment.length) {
    return <div className="empty">Loading equipment…</div>
  }

  return (
    <div className="equip-gallery">
      <div className="equip-summary">
        <span className="pill pill-surface">{equipment.length} assets · {total} types</span>
        {counts.crit > 0 && <span className="pill pill-red">{counts.crit} critical</span>}
        {counts.warn > 0 && <span className="pill pill-amber">{counts.warn} degraded</span>}
        <span className="pill pill-green">{counts.ok} nominal</span>
      </div>

      <div className="equip-gallery-scroll">
        {groups.map((g) => (
          <section key={g.cat} className="equip-sector">
            <div className="equip-sector-head">
              {g.cat}<span className="equip-sector-count">{g.items.length}</span>
            </div>
            <div className="equip-grid">
              {g.items.map((t) => (
                <TypeCard key={t.key} type={t} active={selected?.type?.key === t.key}
                  onClick={() => setSelected({ type: t, instance: t.rep })} />
              ))}
            </div>
          </section>
        ))}
      </div>

      {selected && (
        <EquipmentInfoPanel type={selected.type} instance={selected.instance}
          onPick={(inst) => setSelected({ type: selected.type, instance: inst })}
          onClose={() => setSelected(null)} />
      )}
    </div>
  )
}

function TypeCard({ type, active, onClick }) {
  const label = ENTRY[type.key]?.label || type.key
  return (
    <button className={`equip-card${active ? ' active' : ''}`} onClick={onClick} title={label}>
      <div className="equip-card-thumb-wrap">
        <LazyThumb propKey={type.key} />
        <span className="equip-card-dot" style={{ background: DOT[type.worst] || DOT.ok }} />
        {type.instances.length > 1 && <span className="equip-card-count">×{type.instances.length}</span>}
      </div>
      <div className="equip-card-name">{label}</div>
    </button>
  )
}

function EquipmentInfoPanel({ type, instance, onPick, onClose }) {
  const entry = ENTRY[type.key]
  const m = instance.metric
  const bad = instance.status === 'crit'
  return (
    <div className="equip-panel">
      <div className="equip-panel-head">
        <div>
          <div className="equip-panel-title">{entry?.label || type.key}</div>
          <div className="equip-panel-sub">{instance.label} · {instance.room}</div>
        </div>
        <button className="btn btn-ghost" onClick={onClose}><Icon n="ti-x" /></button>
      </div>

      <div className="equip-panel-3d">
        <AssetPreview assetKey={type.key} interactive showHuman showGrid background="#0d1017" />
      </div>

      {entry?.desc && <p className="equip-panel-desc">{entry.desc}</p>}

      <div className="equip-panel-grid">
        <Field label="Status" value={
          <span className={`pill ${bad ? 'pill-red' : instance.status === 'warn' ? 'pill-amber' : 'pill-green'}`}>
            {bad ? 'critical' : instance.status === 'warn' ? 'degraded' : 'nominal'}
          </span>} />
        {m && <Field label={m.label}
          value={<b style={{ color: bad ? 'var(--accent-red)' : 'var(--text)' }}>
            {m.value}{m.unit ? ` ${m.unit}` : ''}</b>}
          hint={`limit ${m.direction === 'above' ? '≤' : '≥'} ${m.limit}${m.unit ? ` ${m.unit}` : ''}`} />}
        <Field label="Sector" value={instance.sector} />
        <Field label="Criticality" value={instance.criticality} />
        <Field label="Condition" value={`${Math.round(instance.conditionIndex * 100)}%`} />
        <Field label="Manufacturer" value={instance.manufacturer} />
        <Field label="Model" value={instance.modelNumber} mono />
        <Field label="Serial" value={instance.serialNumber} mono />
        <Field label="Installed" value={instance.installDate} mono />
        <Field label="Warranty to" value={instance.warrantyExpiry} mono />
        <Field label="Runtime" value={`${instance.runtimeHours.toLocaleString()} h`} mono />
      </div>

      {type.instances.length > 1 && (
        <>
          <div className="equip-panel-label">All {type.instances.length} units</div>
          <div className="equip-panel-units">
            {type.instances.map((i) => (
              <button key={i.id} onClick={() => onPick(i)}
                className={`equip-unit${i.id === instance.id ? ' active' : ''}`}>
                <span className="equip-unit-dot" style={{ background: DOT[i.status] || DOT.ok }} />
                <span>{i.label}</span>
                <span className="equip-unit-room">{i.room}</span>
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

function Field({ label, value, hint, mono }) {
  return (
    <div className="equip-field">
      <div className="equip-field-label">{label}</div>
      <div className={`equip-field-value${mono ? ' mono' : ''}`}>{value}</div>
      {hint && <div className="equip-field-hint">{hint}</div>}
    </div>
  )
}
