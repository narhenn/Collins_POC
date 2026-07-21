/**
 * HospitalViews — the hospital-campus live surface: the equipment catalog plus
 * the five clinical views (infection map, medical-gas P&ID, bed board, OR
 * utilisation calendar, ED patient-flow funnel), all fed by the campus twin's
 * network payload (GET /api/twins/{tenant}/network).
 *
 * Rendered inside the St. Vera Hospital dashboard, below the 3-D building — the
 * building stays the twin's hero (and the model Repair-with-AI drives); these are
 * the operational surfaces layered on top of it.
 */
import { useEffect, useState } from 'react'
import api from './api.js'
import { Icon } from './lib.jsx'
import EquipmentGallery from './EquipmentGallery.jsx'
import HospitalBedBoard from './HospitalBedBoard.jsx'
import HospitalORCalendar from './HospitalORCalendar.jsx'
import HospitalPatientFlow from './HospitalPatientFlow.jsx'
import HospitalInfectionMap from './HospitalInfectionMap.jsx'
import HospitalMedicalGasSchematic from './HospitalMedicalGasSchematic.jsx'

function Card({ title, icon, action, children, className = '' }) {
  return (
    <div className={`card ${className}`}>
      <div className="card-title"><Icon n={icon} /> {title}{action}</div>
      {children}
    </div>
  )
}

export default function HospitalViews({ tenant, running = true }) {
  const [net, setNet] = useState(null)

  useEffect(() => {
    if (!tenant) return
    let alive = true
    const load = () => api.twinNetwork(tenant)
      .then((r) => { if (alive) setNet(r) })
      .catch(() => {})
    load()
    if (!running) return () => { alive = false }
    const id = setInterval(load, 3000)
    return () => { alive = false; clearInterval(id) }
  }, [tenant, running])

  if (!net) {
    return <div className="card section-gap"><div className="empty">Loading hospital campus…</div></div>
  }

  const gasCrit = (net.medical_gas?.zones || []).some((z) => z.status === 'critical')
  const closures = (net.zones || []).filter((z) => z.recommend_closure).length

  return (
    <>
      <Card className="section-gap" icon="ti-stethoscope" title="Equipment · 3-D Assets & Health"
        action={<span className="pill pill-surface">click an asset to inspect</span>}>
        <EquipmentGallery equipment={net.equipment} />
      </Card>

      <div className="grid-2 section-gap" style={{ alignItems: 'start' }}>
        <Card icon="ti-map-2" title="Infection Spread Map"
          action={closures
            ? <span className="pill pill-red">{closures} closure</span>
            : <span className="pill pill-green">● contained</span>}>
          <HospitalInfectionMap zones={net.zones} />
        </Card>
        <Card icon="ti-topology-star-3" title="Medical Gas Schematic"
          action={gasCrit
            ? <span className="pill pill-red">low pressure</span>
            : <span className="pill pill-green">● nominal</span>}>
          <HospitalMedicalGasSchematic gas={net.medical_gas} />
        </Card>
      </div>

      <Card className="section-gap" icon="ti-bed" title="Bed Board"
        action={<span className="pill pill-surface">live · RTLS</span>}>
        <HospitalBedBoard beds={net.beds} />
      </Card>

      <div className="grid-2 section-gap" style={{ alignItems: 'start' }}>
        <Card icon="ti-calendar-stats" title="OR Utilisation Calendar">
          <HospitalORCalendar schedule={net.or_schedule} />
        </Card>
        <Card icon="ti-filter" title="ED Patient-Flow Funnel">
          <HospitalPatientFlow flow={net.patient_flow} />
        </Card>
      </div>
    </>
  )
}
