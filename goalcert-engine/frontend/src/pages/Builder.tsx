import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { AssetType, ControlType, TechniqueType } from "../api/types";

const BADGE: Record<string, [string, string]> = {
  red: ["badge-red", "Red Team"], blue: ["badge-blue", "Blue Team"], purple: ["badge-purple", "Purple Team"],
  soc: ["badge-green", "SOC"], ics: ["badge-orange", "ICS/OT"], cloud: ["badge-teal", "Cloud"],
};

interface Step { technique: string; phase: string; at_min: number; by: string; value: string; }

export default function Builder() {
  const nav = useNavigate();
  const assets = useQuery<AssetType[]>({ queryKey: ["assets"], queryFn: api.assets });
  const controls = useQuery<ControlType[]>({ queryKey: ["controls"], queryFn: api.controls });
  const techniques = useQuery<TechniqueType[]>({ queryKey: ["techniques"], queryFn: api.techniques });

  const [name, setName] = useState("");
  const [type, setType] = useState("purple");
  const [industry, setIndustry] = useState("generic");
  const [duration, setDuration] = useState(90);
  const [description, setDescription] = useState("");
  const [pickedAssets, setPickedAssets] = useState<Set<string>>(new Set());
  const [pickedControls, setPickedControls] = useState<Set<string>>(new Set(["edr", "siem", "firewall_ids"]));
  const [steps, setSteps] = useState<Step[]>([]);
  const [redObj, setRedObj] = useState("");
  const [blueObj, setBlueObj] = useState("");
  const [saving, setSaving] = useState(false);

  const toggle = (set: Set<string>, k: string, fn: (s: Set<string>) => void) => {
    const n = new Set(set); n.has(k) ? n.delete(k) : n.add(k); fn(n);
  };

  const addStep = () => setSteps((s) => [...s, { technique: "", phase: "Phase 1", at_min: (s.length + 1) * 5, by: "type", value: "" }]);
  const updateStep = (i: number, patch: Partial<Step>) => setSteps((s) => s.map((st, j) => (j === i ? { ...st, ...patch } : st)));

  const save = async () => {
    const id = name.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "") || `custom_${Date.now()}`;
    const phases = [...new Set(steps.map((s) => s.phase).filter(Boolean))];
    if (phases.length === 0) { alert("Add at least one step with a phase."); return; }
    const assetSpecs = [...pickedAssets].map((t, i) => {
      const at = assets.data!.find((a) => a.key === t)!;
      return { id: `${t}-${i + 1}`, type: t, name: at.name, zone: at.default_zone, criticality: at.default_criticality };
    });
    const controlSpecs = [...pickedControls].map((t) => ({ id: `c-${t}`, type: t, enabled: true }));
    const scenario = {
      schema_version: 1, id, name: name || "Custom Scenario", type, industry,
      badge: (BADGE[type] ?? BADGE.purple)[0], label: (BADGE[type] ?? BADGE.purple)[1],
      description: description || name, difficulties: ["Easy", "Medium", "Hard", "Expert"],
      nominal_duration_min: duration, mitre_tactics: phases,
      phases, recommended_topology: { assets: assetSpecs, controls: controlSpecs },
      playbook: steps.filter((s) => s.technique).map((s, i) => ({
        id: `s${i + 1}`, technique: s.technique, phase: s.phase, at_min: s.at_min,
        target: s.value ? { by: s.by, value: s.value, pick: "first" } : null,
        is_inject: false, label: null,
      })),
      objectives: {
        red: redObj.split("\n").map((x) => x.trim()).filter(Boolean),
        blue: blueObj.split("\n").map((x) => x.trim()).filter(Boolean),
      },
    };
    setSaving(true);
    try {
      const res = await fetch("/api/scenarios", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(scenario),
      });
      if (!res.ok) throw new Error(await res.text());
      nav(`/launch/${id}`);
    } catch (e) {
      alert("Save failed: " + e);
      setSaving(false);
    }
  };

  return (
    <>
      <div className="section-header"><h1>Scenario Builder</h1><p>Author a playbook against the catalog — it runs on the same engine immediately</p></div>
      <div className="grid-2">
        <div className="card">
          <div className="card-title" style={{ marginBottom: 12 }}><i className="fa fa-info-circle" /> Details</div>
          <div className="builder-label">Name</div>
          <input className="form-input" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Finance Ransomware Drill" style={{ marginBottom: 12 }} />
          <div style={{ display: "flex", gap: 12, marginBottom: 12 }}>
            <div style={{ flex: 1 }}>
              <div className="builder-label">Type</div>
              <select className="form-select" value={type} onChange={(e) => setType(e.target.value)}>
                {Object.keys(BADGE).map((t) => <option key={t} value={t}>{BADGE[t][1]}</option>)}
              </select>
            </div>
            <div style={{ flex: 1 }}>
              <div className="builder-label">Industry</div>
              <input className="form-input" value={industry} onChange={(e) => setIndustry(e.target.value)} />
            </div>
            <div style={{ width: 110 }}>
              <div className="builder-label">Duration</div>
              <input className="form-input" type="number" value={duration} onChange={(e) => setDuration(+e.target.value)} />
            </div>
          </div>
          <div className="builder-label">Description</div>
          <textarea className="form-textarea" value={description} onChange={(e) => setDescription(e.target.value)} style={{ marginBottom: 12 }} />

          <div className="builder-label">Environment assets</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, marginBottom: 12 }}>
            {(assets.data ?? []).map((a) => (
              <div key={a.key} className={"asset-tile" + (pickedAssets.has(a.key) ? " on" : "")} onClick={() => toggle(pickedAssets, a.key, setPickedAssets)}>
                <div className="icon"><i className={`fa ${a.icon}`} /></div>
                <div style={{ fontSize: 12 }}>{a.name}</div>
              </div>
            ))}
          </div>
          <div className="builder-label">Controls enabled</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {(controls.data ?? []).map((c) => (
              <button key={c.key} className={"filter-chip" + (pickedControls.has(c.key) ? " active" : "")} onClick={() => toggle(pickedControls, c.key, setPickedControls)}>{c.name}</button>
            ))}
          </div>
        </div>

        <div className="card">
          <div className="card-header"><div className="card-title"><i className="fa fa-bolt" /> Attacker Playbook</div>
            <button className="btn btn-primary" style={{ fontSize: 11, padding: "5px 10px" }} onClick={addStep}><i className="fa fa-plus" /> Step</button>
          </div>
          {steps.length === 0 && <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>Add technique steps; each runs against the environment in time order.</div>}
          {steps.map((s, i) => (
            <div key={i} style={{ display: "flex", gap: 6, marginBottom: 8, flexWrap: "wrap", alignItems: "center" }}>
              <select className="form-select" value={s.technique} onChange={(e) => updateStep(i, { technique: e.target.value })} style={{ flex: 2, minWidth: 150 }}>
                <option value="">technique…</option>
                {(techniques.data ?? []).map((t) => <option key={t.key} value={t.key}>{t.name}</option>)}
              </select>
              <input className="form-input" value={s.phase} onChange={(e) => updateStep(i, { phase: e.target.value })} placeholder="phase" style={{ width: 110 }} />
              <input className="form-input" type="number" value={s.at_min} onChange={(e) => updateStep(i, { at_min: +e.target.value })} title="T+min" style={{ width: 64 }} />
              <select className="form-select" value={s.by} onChange={(e) => updateStep(i, { by: e.target.value })} style={{ width: 74 }}>
                <option value="type">type</option><option value="role">role</option>
              </select>
              <input className="form-input" value={s.value} onChange={(e) => updateStep(i, { value: e.target.value })} placeholder="target" style={{ flex: 1, minWidth: 90 }} />
              <button className="btn btn-ghost" style={{ padding: "6px 8px" }} onClick={() => setSteps((st) => st.filter((_, j) => j !== i))}><i className="fa fa-times" /></button>
            </div>
          ))}
          <div className="builder-label" style={{ marginTop: 12 }}>Red objectives (one per line)</div>
          <textarea className="form-textarea" value={redObj} onChange={(e) => setRedObj(e.target.value)} style={{ minHeight: 60 }} />
          <div className="builder-label" style={{ marginTop: 8 }}>Blue objectives (one per line)</div>
          <textarea className="form-textarea" value={blueObj} onChange={(e) => setBlueObj(e.target.value)} style={{ minHeight: 60 }} />
        </div>
      </div>
      <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 16 }}>
        <button className="btn btn-primary" onClick={save} disabled={saving || !name}>
          {saving ? <><span className="spinner" /> Saving…</> : <><i className="fa fa-rocket" /> Save & Configure</>}
        </button>
      </div>
    </>
  );
}
