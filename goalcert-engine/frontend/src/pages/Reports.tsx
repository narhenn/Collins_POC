import { useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { ReportContent, RunSummary } from "../api/types";

export default function Reports() {
  const { runId } = useParams();
  const nav = useNavigate();
  const { data: runs } = useQuery<RunSummary[]>({ queryKey: ["runs"], queryFn: () => api.runs(30), enabled: !runId });
  const { data: report } = useQuery<ReportContent>({ queryKey: ["report", runId], queryFn: () => api.report(runId!), enabled: !!runId });

  if (!runId) {
    return (
      <>
        <div className="section-header"><h1>After-Action Reports</h1><p>Select a completed run to view its debrief</p></div>
        {(runs ?? []).length === 0 && <div className="center-empty">No runs yet.</div>}
        {(runs ?? []).map((r) => (
          <div key={r.id} className="card" style={{ marginBottom: 12, cursor: "pointer" }} onClick={() => nav(`/reports/${r.id}`)}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <div style={{ fontWeight: 600 }}>{r.scenario_name}</div>
                <div className="muted" style={{ fontSize: 12 }}>{new Date(r.created_at).toLocaleString()} · {r.operator || "Operator"}</div>
              </div>
              <div style={{ fontFamily: "var(--mono)" }}>
                <span style={{ color: "var(--gc-red)" }}>R {r.scores.red}</span> · <span style={{ color: "var(--gc-green)" }}>B {r.scores.blue}</span>
              </div>
            </div>
          </div>
        ))}
      </>
    );
  }

  if (!report) return <div className="center-empty"><span className="spinner" /> Loading report…</div>;
  const sc = report.scorecard;
  const fin = report.financial_impact;

  return (
    <>
      <div className="section-header" style={{ display: "flex", justifyContent: "space-between" }}>
        <div><h1>{report.scenario_name} — After-Action Report</h1><p>{report.duration_min}-minute exercise · executive debrief</p></div>
        <button className="btn btn-ghost" onClick={() => nav("/reports")}><i className="fa fa-arrow-left" /> All reports</button>
      </div>

      <div className="card" style={{ marginBottom: 20 }}>
        <div className="card-title" style={{ marginBottom: 10 }}><i className="fa fa-file-lines" /> Executive Summary</div>
        <p style={{ fontSize: 14, lineHeight: 1.7 }}>{report.exec_summary}</p>
      </div>

      <div className="stats-row">
        <Stat cls={sc.winner === "Blue" ? "green" : "red"} label="Outcome" value={`${sc.winner} advantage`} sub={`Red ${sc.red_score} / Blue ${sc.blue_score}`} />
        <Stat cls="accent" label="Detection rate" value={`${Math.round(sc.detection_rate * 100)}%`} sub={`MTTD ${sc.mttd_min}m · MTTR ${sc.mttr_min}m`} />
        <Stat cls="purple" label="Security maturity" value={`${report.maturity_score.score}`} sub={report.maturity_score.band} />
        <Stat cls="red" label="Est. financial impact" value={`$${(fin.estimate_low_usd / 1e6).toFixed(1)}–${(fin.estimate_high_usd / 1e6).toFixed(1)}M`} sub={`${sc.contained} contained · ${sc.blocked} blocked`} />
      </div>

      <div className="grid-2">
        <div className="card">
          <div className="card-title" style={{ marginBottom: 12 }}><i className="fa fa-stream" /> Attack Timeline</div>
          <div style={{ maxHeight: 360, overflowY: "auto" }}>
            {report.timeline.map((e, i) => (
              <div key={i} style={{ display: "flex", gap: 10, fontSize: 12, padding: "6px 0", borderBottom: "1px solid var(--gc-border)" }}>
                <span style={{ fontFamily: "var(--mono)", color: "var(--gc-muted)", minWidth: 48 }}>{e.clock}</span>
                <span className={`tag`} style={{ background: tagColor(e.type), minWidth: 70, textAlign: "center" }}>{e.type}</span>
                <span style={{ flex: 1 }}>{e.title}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="card">
          <div className="card-title" style={{ marginBottom: 12 }}><i className="fa fa-sitemap" /> MITRE ATT&CK Mapping</div>
          <table className="score-table">
            <thead><tr><th>Technique</th><th>Tactic</th><th>Detected</th></tr></thead>
            <tbody>
              {report.mitre_map.map((m, i) => (
                <tr key={i}>
                  <td><span style={{ fontFamily: "var(--mono)", color: "var(--gc-accent)", fontSize: 11 }}>{m.technique}</span> {m.name}</td>
                  <td className="muted" style={{ fontSize: 12 }}>{m.tactic}</td>
                  <td>{m.detected ? <i className="fa fa-check" style={{ color: "var(--gc-green)" }} /> : <i className="fa fa-times" style={{ color: "var(--gc-red)" }} />}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="grid-2" style={{ marginTop: 20 }}>
        <div className="card">
          <div className="card-title" style={{ marginBottom: 12 }}><i className="fa fa-gavel" /> Regulatory Impact</div>
          {report.regulatory_impact.map((r, i) => (
            <div key={i} className="alert-item warning" style={{ fontSize: 12 }}><i className="fa fa-balance-scale" style={{ color: "var(--gc-yellow)", marginRight: 8 }} />{r}</div>
          ))}
          <div className="card-title" style={{ margin: "16px 0 8px" }}><i className="fa fa-coins" /> Financial Impact Drivers</div>
          {fin.drivers.map((d, i) => <div key={i} className="muted" style={{ fontSize: 12, padding: "3px 0" }}>• {d}</div>)}
        </div>
        <div className="card">
          <div className="card-title" style={{ marginBottom: 12 }}><i className="fa fa-list-check" /> Corrective Action Plan</div>
          {report.corrective_actions.map((a, i) => (
            <div key={i} className="alert-item info" style={{ fontSize: 12 }}>
              <span className="tag" style={{ background: a.priority === "P1" ? "rgba(255,71,87,.2)" : a.priority === "P2" ? "rgba(255,214,0,.2)" : "rgba(77,208,225,.2)", color: a.priority === "P1" ? "var(--gc-red)" : a.priority === "P2" ? "var(--gc-yellow)" : "var(--gc-teal)", marginRight: 8 }}>{a.priority}</span>
              {a.action}
            </div>
          ))}
        </div>
      </div>
    </>
  );
}

function tagColor(type: string): string {
  return type === "attack" ? "rgba(255,112,67,.18)" : type === "detection" ? "rgba(0,230,118,.18)"
    : type === "block" ? "rgba(0,212,255,.15)" : type === "response" ? "rgba(77,208,225,.18)"
    : type === "inject" ? "rgba(123,97,255,.18)" : type === "fail" ? "rgba(107,122,149,.18)" : "rgba(255,255,255,.06)";
}

function Stat({ cls, label, value, sub }: { cls: string; label: string; value: string | number; sub: string }) {
  return <div className={`stat-card ${cls}`}><div className="stat-label">{label}</div><div className="stat-value" style={{ fontSize: 20 }}>{value}</div><div className="stat-sub">{sub}</div></div>;
}
