// Chart.jsx — interactive multi-series SVG line chart with crosshair tooltip,
// drag-to-zoom, gradient area fill, and animated line draw.
import { useRef, useState } from 'react'

export default function Chart({ data, series, height = 190, redline }) {
  const [hover, setHover] = useState(null)   // { x, idx }
  const [zoom, setZoom] = useState(null)     // { startIdx, endIdx } or null
  const [dragging, setDragging] = useState(null) // startX during drag
  const svgRef = useRef(null)

  if (!data || data.length === 0) return <div className="empty">No trajectory yet.</div>

  // apply zoom range
  const viewData = zoom ? data.slice(zoom.startIdx, zoom.endIdx + 1) : data

  const W = 640, H = height, padL = 48, padR = 16, padT = 14, padB = 24
  const xs = viewData.map(d => d.t_min)
  const xMin = Math.min(...xs), xMax = Math.max(...xs) || 1
  let yMin = Infinity, yMax = -Infinity
  for (const s of series) for (const d of viewData) {
    const v = d[s.key]; if (v == null) continue
    yMin = Math.min(yMin, v); yMax = Math.max(yMax, v)
  }
  if (redline != null) yMax = Math.max(yMax, redline)
  if (!isFinite(yMin)) { yMin = 0; yMax = 1 }
  const pad = (yMax - yMin) * 0.08 || 1
  yMin -= pad; yMax += pad
  const sx = t => padL + (W - padL - padR) * ((t - xMin) / (xMax - xMin || 1))
  const sy = v => padT + (H - padT - padB) * (1 - (v - yMin) / (yMax - yMin || 1))
  const path = (key) => viewData.map((d, i) =>
    (d[key] == null ? '' : `${i === 0 ? 'M' : 'L'}${sx(d.t_min).toFixed(1)},${sy(d[key]).toFixed(1)}`)).join(' ')
  const areaPath = (key) => {
    const pts = viewData.filter(d => d[key] != null)
    if (pts.length < 2) return ''
    const top = pts.map(d => `${sx(d.t_min).toFixed(1)},${sy(d[key]).toFixed(1)}`).join(' ')
    const bottom = `${sx(pts[pts.length - 1].t_min).toFixed(1)},${sy(yMin).toFixed(1)} ${sx(pts[0].t_min).toFixed(1)},${sy(yMin).toFixed(1)}`
    return `M${top} L${bottom} Z`
  }

  const yRange = yMax - yMin
  const useDecimals = yRange < 10
  const yticks = [yMin, yMin + yRange * 0.25, yMin + yRange * 0.5, yMin + yRange * 0.75, yMax]
  const fmtY = v => useDecimals ? v.toFixed(1) : v.toFixed(0)
  const xLabel = (m) => m >= 1440 ? `${(m / 1440).toFixed(0)}d` : m >= 60 ? `${(m / 60).toFixed(0)}h` : `${m.toFixed(0)}m`

  // mouse handlers for crosshair + zoom
  function getIdx(clientX) {
    const rect = svgRef.current?.getBoundingClientRect()
    if (!rect) return null
    const px = (clientX - rect.left) / rect.width * W
    const t = xMin + (px - padL) / (W - padL - padR) * (xMax - xMin)
    let best = 0, bestDist = Infinity
    viewData.forEach((d, i) => { const dist = Math.abs(d.t_min - t); if (dist < bestDist) { bestDist = dist; best = i } })
    return best
  }
  function onMouseMove(e) {
    const idx = getIdx(e.clientX)
    if (idx != null) setHover({ x: sx(viewData[idx].t_min), idx })
  }
  function onMouseDown(e) {
    if (zoom) return // already zoomed, don't allow nested zoom
    const idx = getIdx(e.clientX)
    if (idx != null) setDragging(idx)
  }
  function onMouseUp(e) {
    if (dragging != null) {
      const endIdx = getIdx(e.clientX)
      if (endIdx != null && Math.abs(endIdx - dragging) > 2) {
        const s = Math.min(dragging, endIdx), en = Math.max(dragging, endIdx)
        // map back to original data indices
        const origStart = data.indexOf(viewData[s])
        const origEnd = data.indexOf(viewData[en])
        if (origStart >= 0 && origEnd >= 0) setZoom({ startIdx: origStart, endIdx: origEnd })
      }
      setDragging(null)
    }
  }

  const hoverData = hover ? viewData[hover.idx] : null

  return (
    <div style={{ position: 'relative' }}>
      <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: 'block', cursor: 'crosshair' }}
        onMouseMove={onMouseMove} onMouseLeave={() => setHover(null)}
        onMouseDown={onMouseDown} onMouseUp={onMouseUp}>
        {/* y-axis grid + labels */}
        {yticks.map((v, i) => (
          <g key={i}>
            <line x1={padL} x2={W - padR} y1={sy(v)} y2={sy(v)} stroke="#ebe9f2" strokeWidth="1" opacity="0.5" />
            <text x={padL - 6} y={sy(v) + 3} fill="#9aa1ad" fontSize="9" textAnchor="end" fontFamily="JetBrains Mono">{fmtY(v)}</text>
          </g>
        ))}
        {/* redline */}
        {redline != null && <>
          <line x1={padL} x2={W - padR} y1={sy(redline)} y2={sy(redline)} stroke="#e11d48" strokeWidth="1" strokeDasharray="4 3" opacity="0.7" />
          <text x={W - padR - 4} y={sy(redline) - 4} fill="#e11d48" fontSize="9" textAnchor="end" fontFamily="JetBrains Mono" opacity="0.8">{redline}</text>
        </>}
        {/* gradient area fills */}
        <defs>
          {series.map((s, i) => (
            <linearGradient key={s.key} id={`area-${i}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={s.color} stopOpacity="0.15" />
              <stop offset="100%" stopColor={s.color} stopOpacity="0.02" />
            </linearGradient>
          ))}
        </defs>
        {series.map((s, i) => (
          <path key={`area-${s.key}`} d={areaPath(s.key)} fill={`url(#area-${i})`} />
        ))}
        {/* data lines */}
        {series.map((s, i) => (
          <path key={s.key} d={path(s.key)} fill="none" stroke={s.color} strokeWidth="2"
            strokeLinejoin="round" className="chart-line-anim" style={{ animationDelay: `${i * 0.15}s` }} />
        ))}
        {/* crosshair */}
        {hover && (
          <line x1={hover.x} x2={hover.x} y1={padT} y2={H - padB} stroke="#7c3aed" strokeWidth="1" strokeDasharray="3 2" opacity="0.6" />
        )}
        {/* hover dots on each series */}
        {hover && hoverData && series.map(s => {
          const v = hoverData[s.key]
          return v != null ? <circle key={s.key} cx={hover.x} cy={sy(v)} r="4" fill={s.color} stroke="#fff" strokeWidth="1.5" /> : null
        })}
        {/* x-axis labels */}
        <text x={padL} y={H - 6} fill="#9aa1ad" fontSize="9" fontFamily="JetBrains Mono">0</text>
        <text x={W - padR} y={H - 6} fill="#9aa1ad" fontSize="9" textAnchor="end" fontFamily="JetBrains Mono">{xLabel(xMax)}</text>
        {hover && hoverData && (
          <text x={hover.x} y={H - 6} fill="#7c3aed" fontSize="9" textAnchor="middle" fontFamily="JetBrains Mono">{xLabel(hoverData.t_min)}</text>
        )}
      </svg>

      {/* Tooltip */}
      {hover && hoverData && (
        <div style={{ position: 'absolute', left: Math.min(hover.x / W * 100, 75) + '%', top: 4,
          background: 'rgba(22,19,31,.92)', border: '1px solid rgba(124,58,237,.4)', borderRadius: 10,
          padding: '8px 11px', fontSize: 11, color: '#e9edff', fontFamily: 'var(--mono)',
          pointerEvents: 'none', zIndex: 5, backdropFilter: 'blur(8px)', minWidth: 100 }}>
          <div style={{ color: '#9aa1ad', marginBottom: 4 }}>t = {xLabel(hoverData.t_min)}</div>
          {series.map(s => {
            const v = hoverData[s.key]
            return v != null ? (
              <div key={s.key} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '1px 0' }}>
                <span style={{ width: 8, height: 3, borderRadius: 2, background: s.color }} />
                <span>{s.label}:</span>
                <span style={{ marginLeft: 'auto', fontWeight: 600 }}>{useDecimals ? v.toFixed(2) : Math.round(v)}</span>
              </div>
            ) : null
          })}
          {redline != null && (
            <div style={{ color: '#e11d48', borderTop: '1px solid rgba(225,29,72,.3)', paddingTop: 3, marginTop: 3 }}>
              Redline: {redline}
            </div>
          )}
        </div>
      )}

      {/* Zoom reset */}
      {zoom && (
        <button onClick={() => setZoom(null)} style={{
          position: 'absolute', top: 4, right: 4, fontSize: 10, padding: '3px 8px',
          borderRadius: 6, background: 'var(--brand-soft)', color: 'var(--brand)', border: '1px solid var(--brand-ring)',
          cursor: 'pointer', fontWeight: 600 }}>
          Reset zoom
        </button>
      )}

      {/* Legend */}
      <div className="legend">
        {series.map(s => <span key={s.key}><i style={{ background: s.color }} />{s.label}</span>)}
        {redline != null && <span><i style={{ background: '#e11d48' }} />Redline</span>}
      </div>
    </div>
  )
}
