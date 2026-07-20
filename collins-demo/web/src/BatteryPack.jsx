// BatteryPack.jsx — a 3-D (CSS perspective) battery module: a grid of cylindrical
// cells that glow by temperature/health. Healthy cells read blue, warm cells amber,
// the failing hot-spot pulses red — and Gaadin's predictive-battery-health AI calls
// the failure ("Cell 17 · fails in 42 days"). Reacts live to the EV telemetry frame.
import React, { useMemo } from 'react'
import { Icon } from './lib.jsx'

const COLS = 14, ROWS = 6, N = COLS * ROWS
const HOTSPOT = 17            // the cell the AI singles out

// temp → colour (blue → teal → amber → red)
function tempColor(t) {
  // t in ~20..70 °C
  const k = Math.max(0, Math.min(1, (t - 24) / 40))
  if (k < 0.35) return { c: '#38bdf8', glow: '#0ea5e9' }           // cool
  if (k < 0.6) return { c: '#22d3ee', glow: '#06b6d4' }            // nominal
  if (k < 0.8) return { c: '#fbbf24', glow: '#f59e0b' }            // warm
  return { c: '#fb7185', glow: '#ef4444' }                          // hot
}

export default function BatteryPack({ live = {}, height = 320 }) {
  const cellTempMax = live['ev:cellTempMax'] ?? 33
  const imbalance = live['ev:cellImbalance'] ?? 14
  const soh = live['ev:stateOfHealth'] ?? 93
  const risk = live['ev:thermalRunawayRisk'] ?? 2

  const cells = useMemo(() => {
    const arr = []
    for (let i = 0; i < N; i++) {
      const r = Math.floor(i / COLS), c = i % COLS
      // deterministic per-cell base variation
      const noise = (Math.sin(i * 12.9898) * 43758.5453) % 1
      const jitter = Math.abs(noise) * 6 - 3
      // spatial: centre-ish runs a touch hotter, hotspot cell tracks runaway risk
      const centreBias = 6 * Math.exp(-(((c - COLS * 0.62) ** 2) / 30 + ((r - ROWS * 0.5) ** 2) / 8))
      let temp = 24 + (cellTempMax - 24) * 0.55 + centreBias + jitter
      let failing = false
      if (i === HOTSPOT) { temp = cellTempMax + risk * 0.35; failing = risk > 12 || temp > 46 }
      arr.push({ i, r, c, temp, failing })
    }
    return arr
  }, [cellTempMax, risk])

  // AI predicted failure horizon for the hot-spot cell
  const days = Math.max(2, Math.round(180 - risk * 2.6 - (100 - soh) * 6 - Math.max(0, cellTempMax - 34) * 3))
  const packTone = risk >= 40 ? 'crit' : cellTempMax >= 42 ? 'warn' : 'ok'

  return (
    <div className="card" style={{ overflow: 'hidden' }}>
      <div className="card-title"><Icon n="ti-battery-4" /> Battery Module · Cell-Level Twin
        <span className={`pill ${packTone === 'crit' ? 'pill-red' : packTone === 'warn' ? 'pill-amber' : 'pill-green'}`}>{N} cells</span>
      </div>

      <div className="batt-stage" style={{ height }}>
        <div className="batt-pack" style={{ gridTemplateColumns: `repeat(${COLS}, 1fr)` }}>
          {cells.map(cell => {
            const { c, glow } = tempColor(cell.temp)
            return (
              <div key={cell.i}
                className={`batt-cell ${cell.failing ? 'failing' : ''}`}
                title={`Cell ${cell.i} · ${cell.temp.toFixed(1)}°C`}
                style={{
                  '--cc': c, '--cg': glow,
                  transform: cell.failing ? 'translateZ(22px)' : cell.temp > 44 ? 'translateZ(10px)' : 'none',
                }} />
            )
          })}
        </div>

        {/* AI failure callout */}
        <div className="batt-callout">
          <div className="batt-callout-dot" />
          <div>
            <div className="batt-callout-t"><Icon n="ti-brain" /> Predictive Battery Health</div>
            <div className="batt-callout-m">Cell {HOTSPOT} — projected failure in <b>{days} days</b></div>
            <div className="batt-callout-s">Dendrite-growth precursor · schedule module swap</div>
          </div>
        </div>
      </div>

      {/* legend + stats */}
      <div className="batt-foot">
        <div className="batt-legend">
          <span><i style={{ background: '#38bdf8' }} /> Healthy</span>
          <span><i style={{ background: '#fbbf24' }} /> Warm</span>
          <span><i style={{ background: '#fb7185' }} /> Failing</span>
        </div>
        <div className="batt-stats">
          <div><span>Cell max</span><b style={{ color: cellTempMax >= 42 ? 'var(--accent-red)' : 'var(--text)' }}>{cellTempMax.toFixed(1)}°C</b></div>
          <div><span>Imbalance</span><b style={{ color: imbalance >= 35 ? 'var(--accent-amber)' : 'var(--text)' }}>{Math.round(imbalance)} mV</b></div>
          <div><span>Pack SoH</span><b>{soh.toFixed(1)}%</b></div>
          <div><span>Runaway risk</span><b style={{ color: risk >= 15 ? 'var(--accent-red)' : 'var(--text)' }}>{Math.round(risk)}%</b></div>
        </div>
      </div>
    </div>
  )
}
