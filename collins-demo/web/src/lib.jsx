// lib.jsx — shared brand, helpers, and signal metadata.
import React from 'react'

// Goalcert logo mark (from the demo): ring + bars in a purple→blue gradient.
export function Logo({ size = 32 }) {
  return (
    <span className="brand-mark" style={{ width: size, height: size }}
      dangerouslySetInnerHTML={{ __html:
        `<svg viewBox="0 0 120 120" width="${size}" height="${size}" xmlns="http://www.w3.org/2000/svg">
          <defs><linearGradient id="gcg" x1="14" y1="14" x2="106" y2="106" gradientUnits="userSpaceOnUse">
            <stop stop-color="#7c3aed"/><stop offset="1" stop-color="#2563eb"/></linearGradient></defs>
          <circle cx="60" cy="62" r="33" stroke="url(#gcg)" stroke-width="13" fill="none"/>
          <rect x="53" y="11" width="14" height="100" rx="3" fill="url(#gcg)"/>
          <rect x="44" y="11" width="32" height="9" rx="3" fill="url(#gcg)"/>
          <rect x="44" y="102" width="32" height="9" rx="3" fill="url(#gcg)"/>
        </svg>` }} />
  )
}

export const Icon = ({ n }) => <i className={`ti ${n}`} />

// Signal display metadata + thresholds (mirror turbine/physics.py redlines).
export const SIG = {
  'aero:exhaustGasTemp': { label: 'EGT', unit: '°C', warn: 700, crit: 780, icon: 'ti-flame' },
  'aero:shaftSpeedN1': { label: 'N1', unit: 'RPM', warn: 5450, crit: 5500, icon: 'ti-rotate-clockwise' },
  'aero:shaftSpeedN2': { label: 'N2', unit: 'RPM', warn: 10700, crit: 10800, icon: 'ti-rotate-clockwise-2' },
  'aero:fuelFlow': { label: 'Fuel Flow', unit: 'kg/h', icon: 'ti-gas-station' },
  'aero:vibrationG': { label: 'Vibration', unit: 'g', warn: 1.5, crit: 2.0, icon: 'ti-activity' },
  'aero:oilTemperature': { label: 'Oil Temp', unit: '°C', warn: 80, crit: 85, icon: 'ti-temperature' },
  'aero:oilPressure': { label: 'Oil Press', unit: 'PSI', warnLow: 45, critLow: 40, icon: 'ti-gauge' },
  'aero:enginePressureRatio': { label: 'EPR', unit: '', icon: 'ti-chart-dots' },
}
export const TILE_ORDER = ['aero:exhaustGasTemp', 'aero:shaftSpeedN1', 'aero:vibrationG',
  'aero:oilTemperature', 'aero:oilPressure', 'aero:fuelFlow', 'aero:shaftSpeedN2',
  'aero:enginePressureRatio']

export function sevClass(sig, v) {
  const m = SIG[sig]; if (!m || v == null) return ''
  if (m.crit != null && v >= m.crit) return 'crit'
  if (m.critLow != null && v <= m.critLow) return 'crit'
  if (m.warn != null && v >= m.warn) return 'warn'
  if (m.warnLow != null && v <= m.warnLow) return 'warn'
  return ''
}
export const fmt = (v) => (v == null ? '—'
  : Math.abs(v) >= 100 ? Math.round(v).toLocaleString()
  : v.toFixed(Math.abs(v) < 10 ? 2 : 1))
export const pct = (h) => (h == null ? '—' : `${Math.round(h * 100)}%`)
export const hColor = (h) => (h == null ? 'var(--hint)' : h >= 0.8 ? 'var(--accent-green)'
  : h >= 0.6 ? 'var(--accent-teal)' : h >= 0.4 ? 'var(--accent-amber)' : 'var(--accent-red)')
export const statusColor = (s) => ({ ok: 'var(--accent-green)', good: 'var(--accent-green)',
  fair: 'var(--accent-teal)', warning: 'var(--accent-amber)', degraded: 'var(--accent-amber)',
  critical: 'var(--accent-red)' }[s] || 'var(--hint)')
