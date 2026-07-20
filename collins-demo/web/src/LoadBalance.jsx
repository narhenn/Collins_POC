// LoadBalance.jsx — GoalCert EMS dynamic load-balancing / peak-shaving demo.
// Plug a rush of EVs into a bank of chargers: with AI off, everyone pulls max and
// the site demand blows past the transformer limit (OVERLOAD). Flip AI on and the
// EMS fair-shares allocation and taps the BESS for peak-shaving so the grid draw
// stays safely under the limit — bars smoothly redistribute in real time.
import React, { useEffect, useRef, useState } from 'react'
import { Icon } from './lib.jsx'

const PORTS = 16, PORT_MAX = 60, LIMIT = 550, BESS_BOOST = 140

export default function LoadBalance() {
  const [vehicles, setVehicles] = useState(4)
  const [aiOn, setAiOn] = useState(true)
  const rampRef = useRef(null)

  // animate a rush of vehicles plugging in
  function rush() {
    if (rampRef.current) clearInterval(rampRef.current)
    setVehicles(2)
    rampRef.current = setInterval(() => {
      setVehicles(v => { if (v >= PORTS) { clearInterval(rampRef.current); return PORTS } return v + 1 })
    }, 130)
  }
  function reset() { if (rampRef.current) clearInterval(rampRef.current); setVehicles(4) }
  useEffect(() => () => rampRef.current && clearInterval(rampRef.current), [])

  // allocation model
  const active = vehicles
  let alloc, gridDraw, bessDraw, curtailed
  if (aiOn) {
    const avail = LIMIT + BESS_BOOST
    const per = Math.min(PORT_MAX, active ? avail / active : PORT_MAX)
    alloc = per
    const demand = per * active
    gridDraw = Math.min(demand, LIMIT)
    bessDraw = Math.max(0, demand - LIMIT)
    curtailed = per < PORT_MAX - 0.5
  } else {
    alloc = PORT_MAX
    gridDraw = PORT_MAX * active
    bessDraw = 0
    curtailed = false
  }
  const overload = gridDraw > LIMIT + 1
  const FULL = LIMIT * 1.2                      // meter shows up to 120% of limit
  const gridPct = Math.min(100, (gridDraw / FULL) * 100)
  const bessPct = Math.min(100 - gridPct, (bessDraw / FULL) * 100)
  const limitPct = (LIMIT / FULL) * 100
  const tone = overload ? 'crit' : gridDraw / LIMIT > 0.85 ? 'warn' : 'ok'

  return (
    <div className="card" style={{ overflow: 'hidden' }}>
      <div className="card-title"><Icon n="ti-adjustments-bolt" /> EMS Load Balancing & Peak Shaving
        <span className={`pill ${overload ? 'pill-red' : 'pill-green'}`}>{overload ? 'OVERLOAD' : 'WITHIN LIMIT'}</span>
        <div className="ai-toggle" style={{ marginLeft: 'auto' }} title="Toggle GoalCert EMS AI">
          <button className={!aiOn ? 'on' : ''} onClick={() => setAiOn(false)}><Icon n="ti-plug-off" /> AI off</button>
          <button className={aiOn ? 'on' : ''} onClick={() => setAiOn(true)}><Icon n="ti-sparkles" /> AI on</button>
        </div>
      </div>

      {/* actions */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 14, flexWrap: 'wrap' }}>
        <button className="btn btn-primary" onClick={rush}><Icon n="ti-bolt" /> Simulate rush — plug in all</button>
        <button className="btn" onClick={reset}><Icon n="ti-refresh" /> Reset</button>
        <span className="hint" style={{ alignSelf: 'center' }}>{active} of {PORTS} bays charging</span>
      </div>

      {/* site demand meter */}
      <div className="lb-meter">
        <div className="lb-meter-head">
          <span>Site demand</span>
          <b className={tone === 'crit' ? 'down' : ''}>{Math.round(gridDraw)} kW <span className="hint">/ {LIMIT} kW limit</span></b>
        </div>
        <div className="lb-track">
          <div className={`lb-fill ${tone}`} style={{ width: `${gridPct}%` }} />
          {bessPct > 0 && <div className="lb-bess" style={{ left: `${gridPct}%`, width: `${bessPct}%` }} title="BESS peak-shave" />}
          <div className="lb-limit" style={{ left: `${limitPct}%` }} />
        </div>
        <div className="lb-meter-foot">
          <span className={`pill ${overload ? 'pill-red' : 'pill-green'}`}>
            <Icon n="ti-transform" /> Transformer {overload ? 'OVERLOAD' : 'SAFE'}</span>
          {aiOn && bessDraw > 0 && <span className="pill pill-amber"><Icon n="ti-battery-charging" /> BESS peak-shave {Math.round(bessDraw)} kW</span>}
          {aiOn && curtailed && <span className="pill pill-blue"><Icon n="ti-arrows-minimize" /> Fair-share curtail → {Math.round(alloc)} kW/bay</span>}
        </div>
      </div>

      {/* charger bars */}
      <div className="lb-bank">
        {Array.from({ length: PORTS }).map((_, i) => {
          const on = i < active
          const kw = on ? alloc : 0
          const h = (kw / PORT_MAX) * 100
          const barTone = !on ? 'idle' : overload ? 'crit' : curtailed ? 'warn' : 'ok'
          return (
            <div key={i} className="lb-charger">
              <div className="lb-bar-wrap">
                <div className={`lb-bar ${barTone} ${overload && on ? 'fight' : ''}`} style={{ height: `${h}%` }} />
              </div>
              <div className="lb-kw">{on ? Math.round(kw) : '—'}</div>
              <div className="lb-id">{i + 1}</div>
            </div>
          )
        })}
      </div>

      <div className="analysis" style={{ marginTop: 14 }}>
        {overload
          ? `⚠ Without dynamic balancing, ${active} vehicles each pulling ${PORT_MAX} kW demand ${Math.round(gridDraw)} kW — ${Math.round(gridDraw - LIMIT)} kW over the ${LIMIT} kW transformer limit. Utility peak-demand penalties trigger and the transformer overheats.`
          : aiOn
            ? `GoalCert EMS holds grid draw at ${Math.round(gridDraw)} kW — under the ${LIMIT} kW limit — by fair-sharing ${Math.round(alloc)} kW to each of ${active} bays${bessDraw > 0 ? ` and peak-shaving ${Math.round(bessDraw)} kW from the on-site BESS` : ''}. No transformer upgrade required.`
            : `${active} bays at ${PORT_MAX} kW = ${Math.round(gridDraw)} kW, still within the ${LIMIT} kW limit. Plug in the full rush to see the difference.`}
      </div>
    </div>
  )
}
