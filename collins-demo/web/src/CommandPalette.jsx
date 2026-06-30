// CommandPalette.jsx — Cmd+K spotlight-style command palette.
// Fuzzy search over all actions: navigate pages, open twins, run agents,
// inject faults, toggle dark mode. Keyboard arrow navigation + Enter to execute.
import React, { useEffect, useRef, useState } from 'react'
import { Icon } from './lib.jsx'

export default function CommandPalette({ commands, onClose }) {
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState(0)
  const inputRef = useRef(null)

  // focus input on mount
  useEffect(() => { inputRef.current?.focus() }, [])

  // filter commands by fuzzy substring match
  const filtered = query.trim()
    ? commands.filter(c => {
        const q = query.toLowerCase()
        const target = `${c.label} ${c.group || ''} ${c.hint || ''}`.toLowerCase()
        return target.includes(q)
      })
    : commands

  // keyboard navigation
  function onKeyDown(e) {
    if (e.key === 'Escape') { onClose(); return }
    if (e.key === 'ArrowDown') { e.preventDefault(); setSelected(s => Math.min(s + 1, filtered.length - 1)) }
    if (e.key === 'ArrowUp') { e.preventDefault(); setSelected(s => Math.max(s - 1, 0)) }
    if (e.key === 'Enter' && filtered[selected]) {
      filtered[selected].action()
      onClose()
    }
  }

  useEffect(() => { setSelected(0) }, [query])

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 9999, display: 'flex', alignItems: 'flex-start',
      justifyContent: 'center', paddingTop: '15vh' }}
      onClick={e => { if (e.target === e.currentTarget) onClose() }}>
      {/* backdrop */}
      <div style={{ position: 'absolute', inset: 0, background: 'rgba(11,13,24,.55)',
        backdropFilter: 'blur(6px)' }} onClick={onClose} />

      {/* palette */}
      <div style={{ position: 'relative', width: '100%', maxWidth: 520, background: 'var(--surface)',
        border: '1px solid var(--border)', borderRadius: 18, boxShadow: '0 24px 80px rgba(22,19,31,.35)',
        overflow: 'hidden', animation: 'fadeIn .15s ease' }}>

        {/* search input */}
        <div style={{ padding: '14px 16px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 10 }}>
          <Icon n="ti-search" />
          <input ref={inputRef} value={query} onChange={e => setQuery(e.target.value)}
            onKeyDown={onKeyDown} placeholder="Search commands…"
            style={{ flex: 1, border: 'none', outline: 'none', fontSize: 15, background: 'transparent',
              color: 'var(--text)', fontFamily: 'var(--font)' }} />
          <kbd style={{ fontSize: 10, padding: '2px 6px', borderRadius: 4, background: 'var(--surface2)',
            border: '1px solid var(--border)', color: 'var(--muted)', fontFamily: 'var(--mono)' }}>ESC</kbd>
        </div>

        {/* results */}
        <div style={{ maxHeight: 340, overflowY: 'auto', padding: '6px 0' }}>
          {filtered.length === 0 && (
            <div style={{ padding: '20px 16px', textAlign: 'center', color: 'var(--muted)', fontSize: 13 }}>
              No matching commands
            </div>
          )}
          {filtered.map((cmd, i) => (
            <div key={cmd.id || i}
              onClick={() => { cmd.action(); onClose() }}
              onMouseEnter={() => setSelected(i)}
              style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 16px', cursor: 'pointer',
                background: i === selected ? 'var(--brand-soft)' : 'transparent',
                borderLeft: i === selected ? '3px solid var(--brand)' : '3px solid transparent',
                transition: 'background .08s' }}>
              <div style={{ width: 30, height: 30, borderRadius: 8, display: 'flex', alignItems: 'center',
                justifyContent: 'center', fontSize: 15, flexShrink: 0,
                background: i === selected ? 'var(--brand)' : 'var(--surface2)',
                color: i === selected ? '#fff' : 'var(--muted)' }}>
                <Icon n={cmd.icon || 'ti-command'} />
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)' }}>{cmd.label}</div>
                {cmd.hint && <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 1 }}>{cmd.hint}</div>}
              </div>
              {cmd.group && (
                <span style={{ fontSize: 9, padding: '2px 7px', borderRadius: 99, background: 'var(--surface2)',
                  color: 'var(--muted)', fontWeight: 600, fontFamily: 'var(--mono)' }}>{cmd.group}</span>
              )}
              {cmd.shortcut && (
                <kbd style={{ fontSize: 9, padding: '2px 6px', borderRadius: 4, background: 'var(--surface2)',
                  border: '1px solid var(--border)', color: 'var(--hint)', fontFamily: 'var(--mono)' }}>{cmd.shortcut}</kbd>
              )}
            </div>
          ))}
        </div>

        {/* footer */}
        <div style={{ padding: '8px 16px', borderTop: '1px solid var(--border)', display: 'flex', gap: 14,
          fontSize: 10, color: 'var(--hint)', fontFamily: 'var(--mono)' }}>
          <span><kbd style={{ fontSize: 9, padding: '1px 4px', borderRadius: 3, background: 'var(--surface2)', border: '1px solid var(--border)' }}>↑↓</kbd> navigate</span>
          <span><kbd style={{ fontSize: 9, padding: '1px 4px', borderRadius: 3, background: 'var(--surface2)', border: '1px solid var(--border)' }}>↵</kbd> select</span>
          <span><kbd style={{ fontSize: 9, padding: '1px 4px', borderRadius: 3, background: 'var(--surface2)', border: '1px solid var(--border)' }}>esc</kbd> close</span>
        </div>
      </div>
    </div>
  )
}
