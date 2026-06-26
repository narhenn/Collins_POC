import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { ScenarioSummary } from "../api/types";

const FILTERS = [
  { key: "all", label: "All" }, { key: "red", label: "Red Team" }, { key: "blue", label: "Blue Team" },
  { key: "purple", label: "Purple" }, { key: "soc", label: "SOC" }, { key: "ics", label: "ICS/OT" },
  { key: "cloud", label: "Cloud" },
];

export default function Library() {
  const nav = useNavigate();
  const [filter, setFilter] = useState("all");
  const { data, isLoading } = useQuery<ScenarioSummary[]>({ queryKey: ["scenarios"], queryFn: api.scenarios });

  const scenarios = (data ?? []).filter((s) => filter === "all" || s.type === filter || s.industry === filter);

  return (
    <>
      <div className="section-header">
        <h1>Scenario Library</h1>
        <p>Pre-built and custom scenarios — each runs on the model-driven engine</p>
      </div>

      <div className="scenario-filters">
        {FILTERS.map((f) => (
          <button key={f.key} className={"filter-chip" + (filter === f.key ? " active" : "")} onClick={() => setFilter(f.key)}>
            {f.label}
          </button>
        ))}
      </div>

      {isLoading && <div className="center-empty"><span className="spinner" /> Loading…</div>}
      <div className="scenario-grid">
        {scenarios.map((s) => (
          <div key={s.id} className="scenario-card" onClick={() => nav(`/launch/${s.id}`)}>
            <div className={`scenario-badge ${s.badge}`}>{s.label}</div>
            <div className="scenario-name">{s.name}</div>
            <div className="scenario-desc">{s.description}</div>
            <div className="scenario-meta">
              <div className="meta-item"><i className="fa fa-clock" /> {s.nominal_duration_min}m</div>
              <div className="meta-item"><i className="fa fa-layer-group" /> {s.phases.length} phases</div>
              <div className="meta-item"><i className="fa fa-bolt" /> {s.step_count} steps</div>
              <div className="meta-item"><i className="fa fa-industry" /> {s.industry}</div>
            </div>
          </div>
        ))}
      </div>
    </>
  );
}
