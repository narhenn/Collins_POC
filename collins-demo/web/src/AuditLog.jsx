// AuditLog.jsx — filterable audit trail of all AI agent actions, scenario runs,
// maintenance sessions, and work order generations. Timeline view with
// expandable detail, filtering by type/domain, and CSV export.
import React, { useState } from 'react'
import { Icon } from './lib.jsx'

const TYPE_META = {
  diagnosis:    { icon: 'ti-stethoscope', color: '#2563eb', label: 'Diagnosis' },
  analysis:     { icon: 'ti-trending-up', color: '#0d9488', label: 'Analysis' },
  workorder:    { icon: 'ti-file-certificate', color: '#7c3aed', label: 'Work Order' },
  cascade:      { icon: 'ti-affiliate', color: '#7c3aed', label: 'Cascade' },
  narration:    { icon: 'ti-message-chatbot', color: '#16a34a', label: 'Narration' },
  scenario:     { icon: 'ti-cloud-storm', color: '#d97706', label: 'Scenario' },
  fault:        { icon: 'ti-alert-triangle', color: '#e11d48', label: 'Fault Inject' },
  maintenance:  { icon: 'ti-tool', color: '#7c3aed', label: 'Maintenance' },
  troubleshoot: { icon: 'ti-messages', color: '#2563eb', label: 'Troubleshoot' },
  procurement:  { icon: 'ti-package', color: '#0d9488', label: 'Procurement' },
  incident:     { icon: 'ti-report', color: '#e11d48', label: 'Incident Report' },
  build:        { icon: 'ti-wand', color: '#7c3aed', label: 'Build Twin' },
  alert:        { icon: 'ti-alert-octagon', color: '#e11d48', label: 'Alert' },
}

function formatTime(ts) {
  const d = new Date(ts)
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}
function formatDate(ts) {
  return new Date(ts).toLocaleDateString([], { month: 'short', day: 'numeric' })
}

export default function AuditLog({ entries = [] }) {
  const [filter, setFilter] = useState('all')
  const [search, setSearch] = useState('')
  const [expanded, setExpanded] = useState(null)

  const types = ['all', ...new Set(entries.map(e => e.type))]
  const filtered = entries.filter(e => {
    if (filter !== 'all' && e.type !== filter) return false
    if (search.trim()) {
      const q = search.toLowerCase()
      return `${e.summary} ${e.detail || ''} ${e.agent || ''} ${e.domain || ''} ${e.machine || ''}`.toLowerCase().includes(q)
    }
    return true
  }).sort((a, b) => b.timestamp - a.timestamp)

  function exportCSV() {
    const header = 'Timestamp,Type,Agent,Domain,Machine,Summary\n'
    const rows = filtered.map(e =>
      `"${new Date(e.timestamp).toISOString()}","${e.type}","${e.agent || ''}","${e.domain || ''}","${e.machine || ''}","${(e.summary || '').replace(/"/g, '""')}"`
    ).join('\n')
    const blob = new Blob([header + rows], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = `audit-log-${Date.now()}.csv`; a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="panel">
      <div className="panel-header">
        <div>
          <div className="panel-title">Audit Trail</div>
          <div className="panel-subtitle">Every AI agent action, scenario run, and maintenance session logged with full context.</div>
        </div>
        <div className="panel-actions">
          <span className="pill pill-surface">{filtered.length} entries</span>
          <button className="btn" onClick={exportCSV}><Icon n="ti-download" /> Export CSV</button>
        </div>
      </div>

      {/* filters */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap', alignItems: 'center' }}>
        {types.map(t => {
          const meta = TYPE_META[t] || {}
          return (
            <button key={t} className={`btn ${filter === t ? 'btn-primary' : ''}`}
              onClick={() => setFilter(t)} style={{ fontSize: 11 }}>
              {meta.icon && <Icon n={meta.icon} />}
              {t === 'all' ? 'All' : meta.label || t}
            </button>
          )
        })}
        <div style={{ flex: 1 }} />
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search…"
          className="input" style={{ width: 200, padding: '7px 12px', fontSize: 12 }} />
      </div>

      {/* timeline */}
      {filtered.length === 0 ? (
        <div className="empty">No audit entries{filter !== 'all' ? ` of type "${filter}"` : ''}. Actions will appear here as you use the platform.</div>
      ) : (
        <div style={{ position: 'relative', paddingLeft: 28 }}>
          {/* vertical line */}
          <div style={{ position: 'absolute', left: 10, top: 0, bottom: 0, width: 2,
            background: 'var(--border2)', borderRadius: 2 }} />

          {filtered.map((entry, i) => {
            const meta = TYPE_META[entry.type] || { icon: 'ti-circle', color: '#9aa1ad', label: entry.type }
            const isExpanded = expanded === entry.id
            return (
              <div key={entry.id || i} style={{ position: 'relative', marginBottom: 12 }}>
                {/* timeline dot */}
                <div style={{ position: 'absolute', left: -28, top: 8, width: 22, height: 22, borderRadius: '50%',
                  background: meta.color, display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 11, color: '#fff', zIndex: 2, boxShadow: `0 0 8px ${meta.color}44` }}>
                  <Icon n={meta.icon} />
                </div>

                {/* entry card */}
                <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12,
                  padding: '12px 14px', cursor: 'pointer', transition: 'border-color .12s',
                  borderColor: isExpanded ? meta.color : 'var(--border)',
                  animation: 'slideUp .25s ease both', animationDelay: `${Math.min(i, 10) * 40}ms` }}
                  onClick={() => setExpanded(isExpanded ? null : (entry.id || i))}>

                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span className="pill" style={{ fontSize: 9, background: `${meta.color}18`, color: meta.color }}>
                      {meta.label}
                    </span>
                    {entry.agent && <span className="pill pill-purple" style={{ fontSize: 9 }}>{entry.agent}</span>}
                    {entry.domain && <span className="pill pill-surface" style={{ fontSize: 9 }}>{entry.domain}</span>}
                    <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--hint)', fontFamily: 'var(--mono)' }}>
                      {formatTime(entry.timestamp)}
                    </span>
                  </div>

                  <div style={{ fontSize: 13, fontWeight: 600, marginTop: 6 }}>{entry.summary}</div>
                  {entry.machine && <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 2 }}>{entry.machine}</div>}

                  {/* expanded detail */}
                  {isExpanded && entry.detail && (
                    <div style={{ marginTop: 10, padding: '10px 12px', background: 'var(--surface2)',
                      borderRadius: 8, fontSize: 12, lineHeight: 1.7, whiteSpace: 'pre-wrap',
                      color: 'var(--muted)', borderLeft: `3px solid ${meta.color}` }}>
                      {entry.detail}
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
