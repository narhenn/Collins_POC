// ExportPDF.jsx — print-optimized work order / incident report renderer.
// Renders the data into a hidden div with print-friendly layout, then calls
// window.print(). The @media print stylesheet in styles.css handles hiding
// the nav/sidebar and applying A4-friendly margins.
import React, { useRef } from 'react'
import { Icon } from './lib.jsx'

function formatDate() {
  return new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })
}

export function PrintWorkOrder({ wo, machineName }) {
  if (!wo) return null
  return (
    <div className="print-wo" style={{ fontFamily: 'Inter, system-ui, sans-serif', fontSize: 11, lineHeight: 1.7, color: '#1a1a2e' }}>
      {/* header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', borderBottom: '2px solid #7c3aed', paddingBottom: 12, marginBottom: 16 }}>
        <div>
          <div style={{ fontFamily: 'Poppins, sans-serif', fontSize: 18, fontWeight: 700, color: '#7c3aed' }}>Goalcert</div>
          <div style={{ fontSize: 9, color: '#9aa1ad', letterSpacing: '.1em', textTransform: 'uppercase' }}>Digital Twin Platform</div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: 16, fontWeight: 700 }}>Maintenance Work Order</div>
          <div style={{ fontSize: 12, color: '#6b7280' }}>{wo.wo_number}</div>
          <div style={{ fontSize: 10, color: '#9aa1ad' }}>{formatDate()}</div>
        </div>
      </div>

      {/* meta grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10, marginBottom: 16 }}>
        <div style={{ padding: '8px 10px', background: '#f4f3f9', borderRadius: 6 }}>
          <div style={{ fontSize: 9, color: '#9aa1ad', textTransform: 'uppercase', fontWeight: 700 }}>Machine</div>
          <div style={{ fontWeight: 600 }}>{machineName}</div>
        </div>
        <div style={{ padding: '8px 10px', background: '#f4f3f9', borderRadius: 6 }}>
          <div style={{ fontSize: 9, color: '#9aa1ad', textTransform: 'uppercase', fontWeight: 700 }}>ATA Chapter</div>
          <div style={{ fontWeight: 600 }}>{wo.ata_chapter}</div>
        </div>
        <div style={{ padding: '8px 10px', background: wo.priority === 'AOG' ? '#fef2f2' : '#f4f3f9', borderRadius: 6 }}>
          <div style={{ fontSize: 9, color: '#9aa1ad', textTransform: 'uppercase', fontWeight: 700 }}>Priority</div>
          <div style={{ fontWeight: 700, color: wo.priority === 'AOG' ? '#e11d48' : '#1a1a2e' }}>{wo.priority}</div>
        </div>
      </div>

      {/* fault + root cause */}
      <div style={{ marginBottom: 14 }}>
        <div style={{ fontWeight: 700, marginBottom: 4 }}>Fault Description</div>
        <div style={{ padding: '6px 10px', background: '#fef2f2', borderRadius: 6, borderLeft: '3px solid #e11d48' }}>{wo.fault_description}</div>
      </div>
      <div style={{ marginBottom: 14 }}>
        <div style={{ fontWeight: 700, marginBottom: 4 }}>Root Cause</div>
        <div style={{ padding: '6px 10px', background: '#fffbeb', borderRadius: 6, borderLeft: '3px solid #d97706' }}>{wo.root_cause}</div>
      </div>

      {/* compliance */}
      <div style={{ fontSize: 10, color: '#6b7280', marginBottom: 14 }}>
        Compliance: {wo.compliance_ref} | Est. Hours: {wo.estimated_hours}h
      </div>

      {/* steps */}
      <div style={{ fontWeight: 700, marginBottom: 8, fontSize: 13 }}>Repair Procedure</div>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10.5, marginBottom: 14 }}>
        <thead>
          <tr style={{ borderBottom: '2px solid #ddd' }}>
            <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 700 }}>#</th>
            <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 700 }}>Action</th>
            <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 700 }}>Pass / Fail Criteria</th>
            <th style={{ padding: '6px 8px', textAlign: 'left', fontWeight: 700 }}>Safety</th>
          </tr>
        </thead>
        <tbody>
          {(wo.steps || []).map((s, i) => (
            <tr key={i} style={{ borderBottom: '1px solid #eee' }}>
              <td style={{ padding: '6px 8px', fontWeight: 700 }}>{s.step}</td>
              <td style={{ padding: '6px 8px' }}>{s.action}</td>
              <td style={{ padding: '6px 8px', color: '#6b7280' }}>{s.criteria}</td>
              <td style={{ padding: '6px 8px', color: s.safety ? '#d97706' : '#9aa1ad' }}>{s.safety || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* parts */}
      {wo.parts_required?.length > 0 && (
        <div style={{ marginBottom: 14 }}>
          <div style={{ fontWeight: 700, marginBottom: 4 }}>Parts Required</div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {wo.parts_required.map((p, i) => (
              <span key={i} style={{ padding: '3px 8px', background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: 4, fontSize: 10 }}>{p}</span>
            ))}
          </div>
        </div>
      )}

      {/* sign-off block */}
      <div style={{ marginTop: 20, padding: '12px 14px', border: '1px solid #ddd', borderRadius: 6 }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 20 }}>
          <div>
            <div style={{ fontSize: 9, color: '#9aa1ad', textTransform: 'uppercase', fontWeight: 700, marginBottom: 6 }}>Performed By</div>
            <div style={{ borderBottom: '1px solid #000', height: 30 }} />
            <div style={{ fontSize: 9, color: '#9aa1ad', marginTop: 4 }}>Name / Signature / Date</div>
          </div>
          <div>
            <div style={{ fontSize: 9, color: '#9aa1ad', textTransform: 'uppercase', fontWeight: 700, marginBottom: 6 }}>Inspected By</div>
            <div style={{ borderBottom: '1px solid #000', height: 30 }} />
            <div style={{ fontSize: 9, color: '#9aa1ad', marginTop: 4 }}>{wo.sign_off || 'Level II Inspector'}</div>
          </div>
          <div>
            <div style={{ fontSize: 9, color: '#9aa1ad', textTransform: 'uppercase', fontWeight: 700, marginBottom: 6 }}>Approved By</div>
            <div style={{ borderBottom: '1px solid #000', height: 30 }} />
            <div style={{ fontSize: 9, color: '#9aa1ad', marginTop: 4 }}>Quality / Compliance</div>
          </div>
        </div>
      </div>

      {/* footer */}
      <div style={{ marginTop: 16, fontSize: 9, color: '#9aa1ad', textAlign: 'center', borderTop: '1px solid #eee', paddingTop: 8 }}>
        Generated by Goalcert Digital Twin Platform · {formatDate()} · {wo.wo_number} · CONFIDENTIAL
      </div>
    </div>
  )
}

export function PrintIncidentReport({ report, machineName }) {
  if (!report) return null
  return (
    <div style={{ fontFamily: 'Inter, system-ui, sans-serif', fontSize: 11, lineHeight: 1.7, color: '#1a1a2e' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '2px solid #e11d48', paddingBottom: 12, marginBottom: 16 }}>
        <div>
          <div style={{ fontFamily: 'Poppins, sans-serif', fontSize: 18, fontWeight: 700, color: '#e11d48' }}>Incident Report</div>
          <div style={{ fontSize: 12, color: '#6b7280' }}>{report.report_id}</div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: 12 }}>{machineName}</div>
          <div style={{ fontSize: 10, color: '#9aa1ad' }}>{report.timestamp || formatDate()}</div>
        </div>
      </div>

      <div style={{ padding: '8px 10px', background: '#f4f3f9', borderRadius: 6, marginBottom: 12 }}>
        <div style={{ fontSize: 9, color: '#9aa1ad', textTransform: 'uppercase', fontWeight: 700 }}>Classification</div>
        <div style={{ fontWeight: 700 }}>{report.classification}</div>
      </div>

      {report.symptoms?.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontWeight: 700, marginBottom: 4 }}>Observed Symptoms</div>
          <ul style={{ paddingLeft: 18 }}>
            {report.symptoms.map((s, i) => <li key={i} style={{ marginBottom: 3 }}>{s}</li>)}
          </ul>
        </div>
      )}

      <div style={{ marginBottom: 10 }}><b>Physics Evidence:</b> {report.physics_evidence}</div>
      <div style={{ marginBottom: 10, padding: '6px 10px', background: '#fef2f2', borderRadius: 6, borderLeft: '3px solid #e11d48' }}>
        <b>Probable Cause:</b> {report.probable_cause}
      </div>
      <div style={{ marginBottom: 10 }}><b>Corrective Action:</b> {report.corrective_action}</div>
      <div style={{ marginBottom: 10, padding: '6px 10px', background: '#eff6ff', borderRadius: 6, borderLeft: '3px solid #2563eb' }}>
        <b>Regulatory Closure:</b> {report.regulatory_closure}
      </div>
      <div style={{ padding: '6px 10px', background: '#f0fdf4', borderRadius: 6, borderLeft: '3px solid #16a34a' }}>
        <b>Return to Service:</b> {report.return_to_service}
      </div>

      <div style={{ marginTop: 16, fontSize: 9, color: '#9aa1ad', textAlign: 'center', borderTop: '1px solid #eee', paddingTop: 8 }}>
        Generated by Goalcert Digital Twin Platform · {formatDate()} · {report.report_id} · CONFIDENTIAL
      </div>
    </div>
  )
}
