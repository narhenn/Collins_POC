// Chart.jsx — lightweight multi-series SVG line chart (no chart lib).
export default function Chart({ data, series, height = 200, redline }) {
  if (!data || data.length === 0) {
    return <div className="empty">No trajectory yet — run a scenario.</div>
  }
  const W = 640, H = height, padL = 42, padR = 12, padT = 12, padB = 22
  const xs = data.map(d => d.t_min)
  const xMin = Math.min(...xs), xMax = Math.max(...xs) || 1

  // shared Y range across the listed series (+ redline if given)
  let yMin = Infinity, yMax = -Infinity
  for (const s of series) for (const d of data) {
    const v = d[s.key]; if (v == null) continue
    yMin = Math.min(yMin, v); yMax = Math.max(yMax, v)
  }
  if (redline != null) yMax = Math.max(yMax, redline)
  if (!isFinite(yMin)) { yMin = 0; yMax = 1 }
  const pad = (yMax - yMin) * 0.08 || 1
  yMin -= pad; yMax += pad

  const sx = t => padL + (W - padL - padR) * ((t - xMin) / (xMax - xMin || 1))
  const sy = v => padT + (H - padT - padB) * (1 - (v - yMin) / (yMax - yMin || 1))

  const path = (key) => data.map((d, i) =>
    (d[key] == null ? '' : `${i === 0 ? 'M' : 'L'}${sx(d.t_min).toFixed(1)},${sy(d[key]).toFixed(1)}`)
  ).join(' ')

  const yticks = [yMin, (yMin + yMax) / 2, yMax]

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: 'block' }}>
        {yticks.map((v, i) => (
          <g key={i}>
            <line x1={padL} x2={W - padR} y1={sy(v)} y2={sy(v)} stroke="#232c3d" strokeWidth="1" />
            <text x={padL - 6} y={sy(v) + 3} fill="#5f6b80" fontSize="9" textAnchor="end" fontFamily="JetBrains Mono">
              {v.toFixed(0)}
            </text>
          </g>
        ))}
        {redline != null && (
          <line x1={padL} x2={W - padR} y1={sy(redline)} y2={sy(redline)}
                stroke="#e2564e" strokeWidth="1" strokeDasharray="4 3" opacity="0.8" />
        )}
        {series.map(s => (
          <path key={s.key} d={path(s.key)} fill="none" stroke={s.color}
                strokeWidth="1.8" strokeLinejoin="round" />
        ))}
        <text x={padL} y={H - 6} fill="#5f6b80" fontSize="9" fontFamily="JetBrains Mono">0 min</text>
        <text x={W - padR} y={H - 6} fill="#5f6b80" fontSize="9" textAnchor="end" fontFamily="JetBrains Mono">
          {xMax.toFixed(0)} min
        </text>
      </svg>
      <div className="legend">
        {series.map(s => <span key={s.key}><i style={{ background: s.color }} />{s.label}</span>)}
        {redline != null && <span><i style={{ background: '#e2564e' }} />Redline</span>}
      </div>
    </div>
  )
}
