// SitePredict.jsx — GoalCert location-intelligence & ROI forecasting, as a living
// miniature city (no real maps). Every parcel is an ROI heat-field cell (green =
// high yield, red = poor). Press scan and the AI sweeps the city — analysing
// demographics, traffic, EV density, grid proximity — then one parcel pulses as the
// recommended charging site with its projected ROI, utilisation and grid-readiness.
import React, { useMemo, useRef, useState } from 'react'
import { Icon } from './lib.jsx'

const COLS = 8, ROWS = 5, GAP = 12, PAD = 16
const VW = 760, VH = 430
const CW = (VW - PAD * 2 - GAP * (COLS - 1)) / COLS
const CH = (VH - PAD * 2 - GAP * (ROWS - 1)) / ROWS

const SCAN_STEPS = [
  'Analysing localized traffic patterns…', 'Modelling demographics & income bands…',
  'Reading EV registration density…', 'Mapping malls, offices & highway POIs…',
  'Gauging grid capacity & substation proximity…', 'Simulating CapEx / tariff / ROI scenarios…',
]

// heat colour: 0 (poor, red) → 0.5 (amber) → 1 (high, green)
function heat(s) {
  const h = 8 + s * 138            // 8° red → 146° green
  return `hsl(${h}, 72%, ${44 + s * 6}%)`
}

export default function SitePredict() {
  const [phase, setPhase] = useState('idle')   // idle | scanning | done
  const [step, setStep] = useState(0)
  const timers = useRef([])

  const parcels = useMemo(() => {
    const arr = []
    for (let r = 0; r < ROWS; r++) for (let c = 0; c < COLS; c++) {
      // smooth demand field + deterministic noise
      const field = Math.exp(-(((c - 5.3) ** 2) / 9 + ((r - 1.7) ** 2) / 6))
      const noise = Math.abs((Math.sin((r * COLS + c) * 12.9898) * 43758.5453) % 1)
      let score = Math.max(0.05, Math.min(1, field * 0.8 + noise * 0.35))
      arr.push({ r, c, score })
    }
    // pick the winner (highest score) and lift it clear
    let best = arr[0]; arr.forEach(p => { if (p.score > best.score) best = p })
    best.score = 0.98; best.best = true
    return arr
  }, [])
  const winner = parcels.find(p => p.best)

  function run() {
    timers.current.forEach(clearTimeout); timers.current = []
    setPhase('scanning'); setStep(0)
    SCAN_STEPS.forEach((_, i) => timers.current.push(setTimeout(() => setStep(i), i * 620)))
    timers.current.push(setTimeout(() => setPhase('done'), SCAN_STEPS.length * 620 + 300))
  }
  function reset() { timers.current.forEach(clearTimeout); setPhase('idle'); setStep(0) }
  React.useEffect(() => () => timers.current.forEach(clearTimeout), [])

  const armed = phase !== 'idle'
  const wx = PAD + winner.c * (CW + GAP), wy = PAD + winner.r * (CH + GAP)

  return (
    <div className="card" style={{ overflow: 'hidden' }}>
      <div className="card-title"><Icon n="ti-map-search" /> SitePredict — Location Intelligence & ROI
        <span className="pill pill-purple" style={{ fontSize: 9 }}>predictive ML</span>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          {phase === 'idle' && <button className="btn btn-primary" onClick={run}><Icon n="ti-radar" /> Run SitePredict scan</button>}
          {phase !== 'idle' && <button className="btn" onClick={reset}><Icon n="ti-refresh" /> Reset</button>}
        </div>
      </div>

      <div className="sp-stage">
        <svg viewBox={`0 0 ${VW} ${VH}`} className={`sp-svg ${armed ? 'armed' : ''} ${phase}`} preserveAspectRatio="xMidYMid meet">
          <defs>
            <linearGradient id="spScan" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0" stopColor="#22d3ee" stopOpacity="0" />
              <stop offset=".5" stopColor="#22d3ee" stopOpacity=".55" />
              <stop offset="1" stopColor="#22d3ee" stopOpacity="0" />
            </linearGradient>
          </defs>
          {/* parcels (ROI heat field) */}
          {parcels.map((p, i) => {
            const x = PAD + p.c * (CW + GAP), y = PAD + p.r * (CH + GAP)
            return (
              <rect key={i} x={x} y={y} width={CW} height={CH} rx="7"
                className="sp-parcel" style={{ '--hc': heat(p.score), transitionDelay: `${p.c * 90}ms` }} />
            )
          })}
          {/* road seams */}
          {Array.from({ length: COLS - 1 }).map((_, c) => (
            <line key={'v' + c} className="sp-road" x1={PAD + (c + 1) * CW + c * GAP + GAP / 2} y1={PAD}
              x2={PAD + (c + 1) * CW + c * GAP + GAP / 2} y2={VH - PAD} />
          ))}
          {Array.from({ length: ROWS - 1 }).map((_, r) => (
            <line key={'h' + r} className="sp-road" x1={PAD} y1={PAD + (r + 1) * CH + r * GAP + GAP / 2}
              x2={VW - PAD} y2={PAD + (r + 1) * CH + r * GAP + GAP / 2} />
          ))}
          {/* scanning sweep */}
          {phase === 'scanning' && <rect className="sp-sweep" x="-120" y="0" width="120" height={VH} fill="url(#spScan)" />}
          {/* recommended-site marker */}
          {phase === 'done' && (
            <g className="sp-winner">
              <circle cx={wx + CW / 2} cy={wy + CH / 2} r={Math.max(CW, CH) * 0.62} className="sp-ring" />
              <circle cx={wx + CW / 2} cy={wy + CH / 2} r="6" fill="#fff" />
              <rect x={wx - 2} y={wy - 2} width={CW + 4} height={CH + 4} rx="8" className="sp-winbox" />
            </g>
          )}
        </svg>

        {/* status ticker */}
        {phase === 'scanning' && (
          <div className="sp-ticker">
            <span className="spinner" /> <span>{SCAN_STEPS[step]}</span>
          </div>
        )}
        {phase === 'idle' && (
          <div className="sp-ticker idle"><Icon n="ti-info-circle" /> 46 candidate parcels · press scan to rank by predicted ROI</div>
        )}

        {/* result card */}
        {phase === 'done' && (
          <div className="sp-result">
            <div className="sp-result-h"><Icon n="ti-map-pin-check" /> Recommended Site</div>
            <div className="sp-result-grid">
              <div><span>Break-even</span><b>14 months</b></div>
              <div><span>Proj. utilisation</span><b>87%</b></div>
              <div><span>Grid ready</span><b className="up">YES</b></div>
              <div><span>ROI confidence</span><b>93%</b></div>
            </div>
            <div className="sp-result-s">6× DC-fast viable · substation 240 m · no transformer upgrade required</div>
          </div>
        )}
      </div>

      <div className="sp-scale">
        <span>Predicted ROI:</span>
        <i style={{ background: 'linear-gradient(90deg,hsl(8,72%,44%),hsl(77,72%,47%),hsl(146,72%,50%))' }} />
        <span>poor</span><span style={{ marginLeft: 'auto' }}>high yield</span>
      </div>
    </div>
  )
}
