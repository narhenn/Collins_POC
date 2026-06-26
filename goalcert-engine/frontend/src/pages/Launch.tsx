import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { AssetSpec, AssetType, ControlSpec, ControlType, Topology } from "../api/types";

const DIFFS = ["Easy", "Medium", "Hard", "Expert"] as const;

export default function Launch() {
  const { scenarioId } = useParams();
  const nav = useNavigate();

  const { data: scenario } = useQuery({ queryKey: ["scenario", scenarioId], queryFn: () => api.scenario(scenarioId!) });
  const { data: topology } = useQuery<Topology>({ queryKey: ["topology", scenarioId], queryFn: () => api.topology(scenarioId!) });
  const { data: assetCatalog } = useQuery<AssetType[]>({ queryKey: ["assets"], queryFn: api.assets });
  const { data: controlCatalog } = useQuery<ControlType[]>({ queryKey: ["controls"], queryFn: api.controls });

  const [assets, setAssets] = useState<AssetSpec[]>([]);
  const [enabledAssets, setEnabledAssets] = useState<Set<string>>(new Set());
  const [enabledControls, setEnabledControls] = useState<Set<string>>(new Set());
  const [difficulty, setDifficulty] = useState<(typeof DIFFS)[number]>("Hard");
  const [readiness, setReadiness] = useState(60);
  const [duration, setDuration] = useState(120);
  const [operator, setOperator] = useState("");
  const [addType, setAddType] = useState("");
  const [launching, setLaunching] = useState(false);

  useEffect(() => {
    if (topology) {
      setAssets(topology.assets);
      setEnabledAssets(new Set(topology.assets.map((a) => a.id)));
      setEnabledControls(new Set(topology.controls.filter((c) => c.enabled).map((c) => c.type)));
    }
    if (scenario?.nominal_duration_min) setDuration(scenario.nominal_duration_min);
  }, [topology, scenario]);

  const iconFor = useMemo(() => {
    const m: Record<string, string> = {};
    for (const a of assetCatalog ?? []) m[a.key] = a.icon;
    return m;
  }, [assetCatalog]);

  if (!scenario || !topology) return <div className="center-empty"><span className="spinner" /> Loading scenario…</div>;

  const toggleAsset = (id: string) => setEnabledAssets((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const toggleControl = (type: string) => setEnabledControls((s) => { const n = new Set(s); n.has(type) ? n.delete(type) : n.add(type); return n; });

  const addAsset = () => {
    if (!addType) return;
    const at = (assetCatalog ?? []).find((a) => a.key === addType)!;
    const count = assets.filter((a) => a.type === addType).length + 1;
    const id = `${addType}-${count}`;
    const spec: AssetSpec = { id, type: addType, name: `${at.name} ${count}`, zone: at.default_zone, criticality: at.default_criticality };
    setAssets((a) => [...a, spec]);
    setEnabledAssets((s) => new Set(s).add(id));
    setAddType("");
  };

  const launch = async () => {
    setLaunching(true);
    const env: Topology = {
      assets: assets.filter((a) => enabledAssets.has(a.id)),
      controls: (controlCatalog ?? []).map((c): ControlSpec => {
        const existing = topology.controls.find((tc) => tc.type === c.key);
        return existing
          ? { ...existing, enabled: enabledControls.has(c.key) }
          : { id: `c-${c.key}`, type: c.key, enabled: enabledControls.has(c.key) };
      }),
    };
    try {
      const run = await api.launch({
        scenario_id: scenarioId!, environment_spec: env,
        config: { difficulty, readiness, duration_min: duration },
        operator: operator || undefined,
      });
      nav(`/sim/${run.id}`);
    } catch (e) {
      alert("Launch failed: " + e);
      setLaunching(false);
    }
  };

  const zones = [...new Set(assets.filter((a) => enabledAssets.has(a.id)).map((a) => a.zone || "corp"))];

  return (
    <>
      <div className="section-header">
        <h1>Configure & Launch — {scenario.name}</h1>
        <p>{scenario.description}</p>
      </div>

      <div className="grid-2">
        {/* ENVIRONMENT / ASSET SELECTION */}
        <div className="card">
          <div className="card-header">
            <div className="card-title"><i className="fa fa-network-wired" /> Environment — select assets</div>
            <span className="muted" style={{ fontSize: 11 }}>{enabledAssets.size}/{assets.length} included · {zones.length} zones</span>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, maxHeight: 340, overflowY: "auto" }}>
            {assets.map((a) => {
              const on = enabledAssets.has(a.id);
              return (
                <div key={a.id} className={"asset-tile" + (on ? " on" : "")} onClick={() => toggleAsset(a.id)}>
                  <div className="icon"><i className={`fa ${iconFor[a.type] || "fa-server"}`} /></div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 12, fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{a.name || a.type}</div>
                    <div style={{ fontSize: 10, color: "var(--gc-muted)" }}>{a.zone} · crit {a.criticality}</div>
                  </div>
                  <i className={`fa ${on ? "fa-check-circle" : "fa-circle"}`} style={{ color: on ? "var(--gc-accent)" : "var(--gc-muted)", fontSize: 13 }} />
                </div>
              );
            })}
          </div>
          <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
            <select className="form-select" value={addType} onChange={(e) => setAddType(e.target.value)} style={{ flex: 1 }}>
              <option value="">+ add asset type…</option>
              {(assetCatalog ?? []).map((a) => <option key={a.key} value={a.key}>{a.name}</option>)}
            </select>
            <button className="btn btn-ghost" onClick={addAsset} disabled={!addType}>Add</button>
          </div>
        </div>

        {/* CONTROLS + CONFIG */}
        <div>
          <div className="card" style={{ marginBottom: 20 }}>
            <div className="card-header"><div className="card-title"><i className="fa fa-shield-alt" /> Security controls</div></div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              {(controlCatalog ?? []).map((c) => {
                const on = enabledControls.has(c.key);
                return (
                  <div key={c.key} className="toggle" onClick={() => toggleControl(c.key)}
                    title={c.description} style={{ justifyContent: "space-between", padding: "6px 4px" }}>
                    <span style={{ display: "flex", alignItems: "center", gap: 6 }}><i className={`fa ${c.icon}`} style={{ color: on ? "var(--gc-green)" : "var(--gc-muted)" }} /> {c.name}</span>
                    <span className={"toggle" + (on ? " on" : "")}><span className="track"><span className="knob" /></span></span>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="card">
            <div className="card-header"><div className="card-title"><i className="fa fa-sliders-h" /> Run configuration</div></div>
            <div className="builder-label">Difficulty (adversary sophistication)</div>
            <div style={{ display: "flex", gap: 8, marginBottom: 14 }}>
              {DIFFS.map((d) => (
                <button key={d} className={"filter-chip" + (difficulty === d ? " active" : "")} onClick={() => setDifficulty(d)}>{d}</button>
              ))}
            </div>
            <div className="builder-label">Team readiness — {readiness}</div>
            <input type="range" min={0} max={100} value={readiness} onChange={(e) => setReadiness(+e.target.value)} style={{ width: "100%", marginBottom: 14 }} />
            <div className="builder-label">Duration (minutes)</div>
            <select className="form-select" value={duration} onChange={(e) => setDuration(+e.target.value)} style={{ marginBottom: 14 }}>
              {[30, 60, 90, 120, 240].map((d) => <option key={d} value={d}>{d} minutes</option>)}
            </select>
            <div className="builder-label">Operator (optional)</div>
            <input className="form-input" value={operator} placeholder="Your name" onChange={(e) => setOperator(e.target.value)} />
          </div>
        </div>
      </div>

      <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 16 }}>
        <button className="btn btn-ghost" onClick={() => nav("/library")}>Cancel</button>
        <button className="btn btn-primary" onClick={launch} disabled={launching || enabledAssets.size === 0}>
          {launching ? <><span className="spinner" /> Launching…</> : <><i className="fa fa-play" /> Launch Simulation</>}
        </button>
      </div>
    </>
  );
}
