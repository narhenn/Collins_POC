import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { TechniqueType } from "../api/types";
import { useSimSocket } from "../hooks/useSimSocket";
import NetworkMap from "../components/NetworkMap";

const fmt = (s: number) => `${String(Math.floor(s / 3600)).padStart(2, "0")}:${String(Math.floor((s % 3600) / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
const TABS = ["console", "network", "alerts"] as const;
const CONSOLE_TYPES = new Set(["telemetry", "attack", "block", "fail", "detection", "response", "inject", "phase", "system"]);

export default function ActiveSim() {
  const { runId } = useParams();
  const nav = useNavigate();
  const { state, pause, resume, setSpeed, stop, inject } = useSimSocket(runId ?? null);
  const { data: techniques } = useQuery<TechniqueType[]>({ queryKey: ["techniques"], queryFn: api.techniques });

  const [tab, setTab] = useState<(typeof TABS)[number]>("console");
  const [injTech, setInjTech] = useState("");
  const [injBy, setInjBy] = useState("type");
  const [injVal, setInjVal] = useState("");
  const consoleRef = useRef<HTMLDivElement>(null);

  useEffect(() => { if (consoleRef.current) consoleRef.current.scrollTop = consoleRef.current.scrollHeight; }, [state.events.length, tab]);

  const phases = state.init?.scenario.phases ?? [];
  const phaseEvents = state.events.filter((e) => e.type === "phase");
  const activePhase = phaseEvents.length ? phaseEvents[phaseEvents.length - 1].phase : null;
  const activeIdx = activePhase ? phases.indexOf(activePhase) : -1;

  const duration = state.init?.duration_s ?? 1;
  const pct = Math.min(100, Math.round((state.simT / duration) * 100));
  const scores = state.complete?.scores ?? state.scores;

  const objectives = useMemo(() => {
    const red = state.complete?.objectives.red ?? (state.init?.scenario.objectives.red ?? []).map((text) => ({ text, met: false }));
    const blue = state.complete?.objectives.blue ?? (state.init?.scenario.objectives.blue ?? []).map((text) => ({ text, met: false }));
    return { red, blue };
  }, [state.complete, state.init]);

  const alerts = state.events.filter((e) => ["detection", "block", "inject"].includes(e.type)).slice().reverse();

  if (!state.init) return <div className="center-empty"><span className="spinner" /> Connecting to simulation…</div>;

  return (
    <>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 700 }}>{state.init.scenario.name}</h1>
          <p className="muted" style={{ fontSize: 13 }}>{state.init.scenario.label} · engine-driven · {state.connected ? "live" : "disconnected"}</p>
        </div>
        <div style={{ display: "flex", gap: 10 }}>
          {!state.complete && (state.paused
            ? <button className="btn btn-success" onClick={resume}><i className="fa fa-play" /> Resume</button>
            : <button className="btn btn-ghost" onClick={pause}><i className="fa fa-pause" /> Pause</button>)}
          {!state.complete && <button className="btn btn-danger" onClick={stop}><i className="fa fa-stop" /> End</button>}
          {state.complete && <button className="btn btn-primary" onClick={() => nav(`/reports/${runId}`)}><i className="fa fa-file-alt" /> View AAR</button>}
        </div>
      </div>

      {/* phase tracker */}
      <div className="phase-track">
        {phases.map((p, i) => (
          <div key={p} className={"phase-step" + (i < activeIdx ? " done" : i === activeIdx ? " active" : "")}>
            {i < activeIdx ? "✓ " : ""}{p}
          </div>
        ))}
      </div>

      <div className="grid-2" style={{ marginBottom: 20 }}>
        <div className="card">
          <div className="card-header">
            <div className="card-title"><i className="fa fa-clock" /> Simulation Timer</div>
            <div style={{ fontFamily: "var(--mono)", fontSize: 16, fontWeight: 700 }}>
              <span style={{ color: "var(--gc-red)" }}>Red {scores.red}</span> · <span style={{ color: "var(--gc-green)" }}>Blue {scores.blue}</span>
            </div>
          </div>
          <div className={"sim-timer" + (duration - state.simT < 300 ? " danger" : "")}>{fmt(state.simT)}</div>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--gc-muted)", marginBottom: 6 }}>
            <span>Progress · {state.paused ? "paused" : `${state.speed}× speed`}</span><span>{pct}%</span>
          </div>
          <div className="progress-bar"><div className="progress-fill progress-accent" style={{ width: `${pct}%` }} /></div>

          <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 14, flexWrap: "wrap" }}>
            <span className="muted" style={{ fontSize: 11 }}>Speed</span>
            {[10, 30, 60, 120].map((sp) => (
              <button key={sp} className={"filter-chip" + (state.speed === sp ? " active" : "")} style={{ padding: "3px 8px" }} onClick={() => setSpeed(sp)}>{sp}×</button>
            ))}
          </div>

          {/* manual inject */}
          {!state.complete && (
            <div style={{ marginTop: 14, padding: 12, background: "var(--gc-surface)", borderRadius: 8 }}>
              <div className="builder-label" style={{ marginBottom: 8 }}>Manual inject (recomputes the run)</div>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                <select className="form-select" value={injTech} onChange={(e) => setInjTech(e.target.value)} style={{ flex: 2, minWidth: 140 }}>
                  <option value="">technique…</option>
                  {(techniques ?? []).map((t) => <option key={t.key} value={t.key}>{t.name}</option>)}
                </select>
                <select className="form-select" value={injBy} onChange={(e) => setInjBy(e.target.value)} style={{ width: 80 }}>
                  <option value="type">type</option><option value="role">role</option>
                </select>
                <input className="form-input" placeholder="target (optional)" value={injVal} onChange={(e) => setInjVal(e.target.value)} style={{ flex: 1, minWidth: 100 }} />
                <button className="btn btn-ghost" disabled={!injTech} onClick={() => { inject(injTech, injVal ? injBy : undefined, injVal || undefined); setInjTech(""); setInjVal(""); }}>
                  <i className="fa fa-bolt" /> Inject
                </button>
              </div>
            </div>
          )}
        </div>

        <div className="card">
          <div className="card-header"><div className="card-title"><i className="fa fa-tasks" /> Objectives</div></div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            {(["red", "blue"] as const).map((side) => (
              <div key={side}>
                <div className="builder-label" style={{ color: side === "red" ? "var(--gc-red)" : "#5B8CFF" }}>{side} team</div>
                {objectives[side].map((o, i) => (
                  <div key={i} style={{ display: "flex", gap: 8, fontSize: 12, marginBottom: 6, alignItems: "flex-start" }}>
                    <i className={`fa ${o.met ? "fa-check-circle" : "fa-circle"}`} style={{ color: o.met ? "var(--gc-green)" : "var(--gc-muted)", marginTop: 2 }} />
                    <span style={{ color: o.met ? "var(--gc-text)" : "var(--gc-muted)" }}>{o.text}</span>
                  </div>
                ))}
              </div>
            ))}
          </div>
          {state.complete && (
            <div className="alert-item success" style={{ marginTop: 12 }}>
              <div className="alert-icon"><i className="fa fa-flag-checkered" style={{ color: "var(--gc-green)" }} /></div>
              <div className="alert-content"><strong>Simulation complete</strong>
                <div>Detection rate {Math.round((state.complete.kpis.detection_rate || 0) * 100)}% · MTTD {((state.complete.kpis.mttd_s || 0) / 60).toFixed(1)}m · {state.complete.summary.assets_compromised} compromised</div>
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="tabs">
        {TABS.map((t) => <button key={t} className={"tab-btn" + (tab === t ? " active" : "")} onClick={() => setTab(t)}>{t[0].toUpperCase() + t.slice(1)}</button>)}
      </div>

      {tab === "console" && (
        <div className="card">
          <div className="card-header"><div className="card-title"><i className="fa fa-terminal" /> Simulation Console</div></div>
          <div id="sim-console" ref={consoleRef}>
            {state.events.filter((e) => CONSOLE_TYPES.has(e.type)).map((e) => (
              <div key={e.seq} className={`console-line c-${e.type === "telemetry" ? e.severity : e.type === "attack" ? "attack" : e.type === "phase" || e.type === "system" ? "system" : e.type === "detection" || e.type === "block" ? "success" : e.severity}`}>
                <span className="ts">{fmt(e.t)}</span>
                <span className="msg">[{e.actor}] {e.message}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {tab === "network" && (
        <div className="card">
          <div className="card-header">
            <div className="card-title"><i className="fa fa-network-wired" /> Network Topology</div>
            <div style={{ display: "flex", gap: 12, fontSize: 12 }}>
              <span style={{ color: "var(--gc-green)" }}>● Safe</span>
              <span style={{ color: "var(--gc-yellow)" }}>● Suspicious</span>
              <span style={{ color: "var(--gc-red)" }}>● Compromised</span>
              <span style={{ color: "var(--gc-teal)" }}>● Contained</span>
            </div>
          </div>
          <NetworkMap assets={state.assets} />
        </div>
      )}

      {tab === "alerts" && (
        <div className="card">
          <div className="card-header"><div className="card-title"><i className="fa fa-bell" /> Alert Feed ({alerts.length})</div></div>
          <div style={{ maxHeight: 420, overflowY: "auto" }}>
            {alerts.length === 0 && <div className="muted" style={{ fontSize: 13 }}>No alerts yet.</div>}
            {alerts.map((e) => (
              <div key={e.seq} className={`alert-item ${e.severity}`}>
                <div className="alert-icon"><i className={`fa ${e.type === "block" ? "fa-ban" : e.type === "inject" ? "fa-bolt" : "fa-exclamation-circle"}`} /></div>
                <div className="alert-content"><strong>{e.title}</strong><div>{e.message}</div><span>{fmt(e.t)} · {e.phase}</span></div>
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  );
}
