// Chart.jsx — lightweight multi-series SVG line chart (light theme).
export default function Chart({ data, series, height = 190, redline }) {
  if (!data || data.length === 0) {
    return <div className="empty">No trajectory yet.</div>
  }
  const W = 640, H = height, padL = 44, padR = 12, padT = 12, padB = 22
  const xs = data.map(d => d.t_min)
  const xMin = Math.min(...xs), xMax = Math.max(...xs) || 1
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
    (d[key] == null ? '' : `${i === 0 ? 'M' : 'L'}${sx(d.t_min).toFixed(1)},${sy(d[key]).toFixed(1)}`)).join(' ')
  const yticks = [yMin, (yMin + yMax) / 2, yMax]
  const xLabel = (m) => m >= 1440 ? `${(m/1440).toFixed(0)}d` : m >= 60 ? `${(m/60).toFixed(0)}h` : `${m.toFixed(0)}m`
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: 'block' }}>
        {yticks.map((v, i) => (
          <g key={i}>
            <line x1={padL} x2={W - padR} y1={sy(v)} y2={sy(v)} stroke="#ebe9f2" strokeWidth="1" />
            <text x={padL - 6} y={sy(v) + 3} fill="#9aa1ad" fontSize="9" textAnchor="end" fontFamily="JetBrains Mono">{v.toFixed(0)}</text>
          </g>
        ))}
        {redline != null && (
          <line x1={padL} x2={W - padR} y1={sy(redline)} y2={sy(redline)} stroke="#e11d48" strokeWidth="1" strokeDasharray="4 3" opacity="0.7" />
        )}
        {series.map(s => (
          <path key={s.key} d={path(s.key)} fill="none" stroke={s.color} strokeWidth="2" strokeLinejoin="round" />
        ))}
        <text x={padL} y={H - 6} fill="#9aa1ad" fontSize="9" fontFamily="JetBrains Mono">0</text>
        <text x={W - padR} y={H - 6} fill="#9aa1ad" fontSize="9" textAnchor="end" fontFamily="JetBrains Mono">{xLabel(xMax)}</text>
      </svg>
      <div className="legend">
        {series.map(s => <span key={s.key}><i style={{ background: s.color }} />{s.label}</span>)}
        {redline != null && <span><i style={{ background: '#e11d48' }} />Redline</span>}
      </div>
    </div>
  )
}
