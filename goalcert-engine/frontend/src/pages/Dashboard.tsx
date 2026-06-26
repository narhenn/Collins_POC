import { useQuery } from "@tanstack/react-query";
import { Radar } from "react-chartjs-2";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { Dashboard as DashboardData } from "../api/types";

const TYPE_COLOR: Record<string, string> = {
  red: "var(--gc-red)", soc: "var(--gc-green)", ics: "var(--gc-orange)",
  cloud: "var(--gc-teal)", blue: "#5B8CFF", purple: "var(--gc-accent2)",
};

export default function Dashboard() {
  const nav = useNavigate();
  const { data, isLoading } = useQuery<DashboardData>({ queryKey: ["dashboard"], queryFn: api.dashboard });

  if (isLoading || !data) return <div className="center-empty"><span className="spinner" /> Loading dashboard…</div>;

  const radarLabels = Object.keys(data.readiness);
  return (
    <>
      <div className="section-header">
        <h1>Simulation Dashboard</h1>
        <p>Overview of training activity, readiness and recent simulations</p>
      </div>

      <div className="stats-row">
        <Stat cls="accent" label="Total Simulations" value={data.total_runs} sub="runs executed" />
        <Stat cls="purple" label="Scenarios" value={data.total_scenarios} sub="in the library" />
        <Stat cls="green" label="Avg. Blue Score" value={data.avg_blue_score} sub="recent runs" />
        <Stat cls="red" label="Critical Findings" value={data.critical_findings} sub="ransomware / OT impact" />
      </div>

      <div className="grid-2">
        <div className="card">
          <div className="card-header">
            <div className="card-title"><i className="fa fa-history" /> Recent Simulations</div>
            <button className="btn btn-ghost" style={{ fontSize: 11, padding: "4px 8px" }} onClick={() => nav("/library")}>New</button>
          </div>
          {data.recent_runs.length === 0 && <div className="muted" style={{ fontSize: 13 }}>No runs yet — launch one from the library.</div>}
          {data.recent_runs.map((r) => (
            <div key={r.id} onClick={() => nav(`/reports/${r.id}`)}
              style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 0", borderBottom: "1px solid var(--gc-border)", cursor: "pointer" }}>
              <div style={{ width: 8, height: 8, borderRadius: "50%", background: TYPE_COLOR[r.type] || "#fff", flexShrink: 0 }} />
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 13, fontWeight: 500 }}>{r.name}</div>
                <div style={{ fontSize: 11, color: "var(--gc-muted)" }}>{new Date(r.created_at).toLocaleString()}</div>
              </div>
              <div style={{ fontFamily: "var(--mono)", fontSize: 12 }}>
                <span style={{ color: "var(--gc-red)" }}>R {r.red}</span> · <span style={{ color: "var(--gc-green)" }}>B {r.blue}</span>
              </div>
            </div>
          ))}
        </div>

        <div className="card">
          <div className="card-header"><div className="card-title"><i className="fa fa-bullseye" /> Team Readiness</div></div>
          <Radar
            data={{
              labels: radarLabels,
              datasets: [{
                label: "Recent runs", data: radarLabels.map((k) => data.readiness[k]),
                backgroundColor: "rgba(0,212,255,.1)", borderColor: "var(--gc-accent)",
                pointBackgroundColor: "var(--gc-accent)", pointRadius: 3,
              }],
            }}
            options={{
              plugins: { legend: { labels: { color: "#6B7A95", font: { size: 11 } } } },
              scales: { r: { suggestedMin: 0, suggestedMax: 100, grid: { color: "rgba(255,255,255,.07)" }, angleLines: { color: "rgba(255,255,255,.07)" }, ticks: { display: false }, pointLabels: { color: "#6B7A95", font: { size: 11 } } } },
            }}
            height={220}
          />
        </div>
      </div>

      <div className="grid-2" style={{ marginTop: 20 }}>
        <div className="card">
          <div className="card-header"><div className="card-title"><i className="fa fa-chart-bar" /> Threat Coverage (MITRE tactics)</div></div>
          {data.threat_coverage.map((c) => (
            <div key={c.label} style={{ marginBottom: 10 }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, marginBottom: 4 }}>
                <span>{c.label}</span><span style={{ color: "var(--gc-accent)", fontFamily: "var(--mono)" }}>{c.pct}%</span>
              </div>
              <div className="progress-bar"><div className="progress-fill" style={{ width: `${c.pct}%`, background: c.pct > 70 ? "var(--gc-green)" : c.pct > 40 ? "var(--gc-yellow)" : "var(--gc-red)" }} /></div>
            </div>
          ))}
        </div>
        <div className="card">
          <div className="card-header"><div className="card-title"><i className="fa fa-bolt" /> Quick Launch</div></div>
          <button className="btn btn-ghost" style={{ justifyContent: "flex-start", gap: 10, width: "100%" }} onClick={() => nav("/launch/operation_black_phoenix")}>
            <i className="fa fa-crosshairs" style={{ color: "var(--gc-purple)" }} /> Operation Black Phoenix — configure & launch
          </button>
          <button className="btn btn-ghost" style={{ justifyContent: "flex-start", gap: 10, width: "100%", marginTop: 8 }} onClick={() => nav("/library")}>
            <i className="fa fa-database" /> Browse all scenarios
          </button>
          <button className="btn btn-ghost" style={{ justifyContent: "flex-start", gap: 10, width: "100%", marginTop: 8 }} onClick={() => nav("/catalog")}>
            <i className="fa fa-cubes" /> Explore asset & technique catalog
          </button>
        </div>
      </div>
    </>
  );
}

function Stat({ cls, label, value, sub }: { cls: string; label: string; value: number | string; sub: string }) {
  return (
    <div className={`stat-card ${cls}`}>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      <div className="stat-sub">{sub}</div>
    </div>
  );
}
