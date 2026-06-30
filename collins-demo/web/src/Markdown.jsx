// Markdown.jsx — a compact, dependency-free markdown renderer for agent replies.
// Handles headings, bold/italic/code, bullet & numbered lists, tables, blockquotes,
// horizontal rules and paragraphs — enough to make Claude's output look polished.
import React from 'react'

// inline: **bold** *italic* `code`
function inline(text, key) {
  const parts = []
  let i = 0, last = 0, n = 0
  const push = (node) => parts.push(node)
  const re = /(\*\*([^*]+)\*\*|`([^`]+)`|\*([^*]+)\*)/g
  let m
  while ((m = re.exec(text))) {
    if (m.index > last) push(text.slice(last, m.index))
    if (m[2] != null) push(<b key={`${key}-${n++}`}>{m[2]}</b>)
    else if (m[3] != null) push(<code key={`${key}-${n++}`} className="md-code">{m[3]}</code>)
    else if (m[4] != null) push(<i key={`${key}-${n++}`}>{m[4]}</i>)
    last = m.index + m[0].length
  }
  if (last < text.length) push(text.slice(last))
  return parts
}

export default function Markdown({ text, className }) {
  if (!text) return null
  const lines = String(text).replace(/\r/g, '').split('\n')
  const blocks = []
  let i = 0
  const keyOf = () => `b${blocks.length}`

  while (i < lines.length) {
    let line = lines[i]

    // blank
    if (!line.trim()) { i++; continue }

    // horizontal rule
    if (/^\s*([-*_])\1{2,}\s*$/.test(line)) { blocks.push(<hr key={keyOf()} className="md-hr" />); i++; continue }

    // heading
    const h = line.match(/^(#{1,6})\s+(.*)$/)
    if (h) {
      const lvl = h[1].length
      const Tag = `h${Math.min(lvl + 1, 6)}`
      blocks.push(<Tag key={keyOf()} className={`md-h md-h${lvl}`}>{inline(h[2], keyOf())}</Tag>)
      i++; continue
    }

    // table: header row + separator row of |---|
    if (line.includes('|') && i + 1 < lines.length && /^\s*\|?[\s:|-]+\|?\s*$/.test(lines[i + 1]) && lines[i + 1].includes('-')) {
      const cells = (r) => r.replace(/^\s*\|/, '').replace(/\|\s*$/, '').split('|').map(c => c.trim())
      const header = cells(line)
      i += 2
      const rows = []
      while (i < lines.length && lines[i].includes('|') && lines[i].trim()) { rows.push(cells(lines[i])); i++ }
      blocks.push(
        <div key={keyOf()} className="md-table-wrap">
          <table className="md-table"><thead><tr>{header.map((c, j) => <th key={j}>{inline(c, `${keyOf()}h${j}`)}</th>)}</tr></thead>
            <tbody>{rows.map((r, ri) => <tr key={ri}>{r.map((c, cj) => <td key={cj}>{inline(c, `${keyOf()}r${ri}c${cj}`)}</td>)}</tr>)}</tbody>
          </table></div>
      )
      continue
    }

    // blockquote
    if (/^\s*>\s?/.test(line)) {
      const buf = []
      while (i < lines.length && /^\s*>\s?/.test(lines[i])) { buf.push(lines[i].replace(/^\s*>\s?/, '')); i++ }
      blocks.push(<blockquote key={keyOf()} className="md-quote">{inline(buf.join(' '), keyOf())}</blockquote>)
      continue
    }

    // unordered list
    if (/^\s*[-*+]\s+/.test(line)) {
      const items = []
      while (i < lines.length && /^\s*[-*+]\s+/.test(lines[i])) { items.push(lines[i].replace(/^\s*[-*+]\s+/, '')); i++ }
      blocks.push(<ul key={keyOf()} className="md-ul">{items.map((it, j) => <li key={j}>{inline(it, `${keyOf()}i${j}`)}</li>)}</ul>)
      continue
    }

    // ordered list
    if (/^\s*\d+[.)]\s+/.test(line)) {
      const items = []
      while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i])) { items.push(lines[i].replace(/^\s*\d+[.)]\s+/, '')); i++ }
      blocks.push(<ol key={keyOf()} className="md-ol">{items.map((it, j) => <li key={j}>{inline(it, `${keyOf()}i${j}`)}</li>)}</ol>)
      continue
    }

    // paragraph (merge consecutive non-blank, non-special lines)
    const buf = [line]; i++
    while (i < lines.length && lines[i].trim() && !/^(#{1,6}\s|\s*[-*+]\s|\s*\d+[.)]\s|\s*>|\s*([-*_])\2{2,}\s*$)/.test(lines[i]) && !lines[i].includes('|')) {
      buf.push(lines[i]); i++
    }
    blocks.push(<p key={keyOf()} className="md-p">{inline(buf.join(' '), keyOf())}</p>)
  }

  return <div className={`md ${className || ''}`}>{blocks}</div>
}
