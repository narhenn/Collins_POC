export interface AssetType {
  key: string; name: string; category: string; icon: string; description: string;
  default_zone: string; default_criticality: number; default_data_sensitivity: number;
  supported_controls: string[];
}
export interface ControlType {
  key: string; name: string; icon: string; description: string;
  default_scope: string; default_enabled: boolean; attaches_to: string[];
}
export interface TechniqueType {
  key: string; name: string; mitre: string; tactic: string; description: string;
  severity: string; detects: string[]; prevents: string[];
}
export interface ScenarioSummary {
  id: string; name: string; type: string; industry: string; badge: string; label: string;
  description: string; is_seed: boolean; phases: string[]; nominal_duration_min: number;
  difficulties: string[]; objectives: { red: string[]; blue: string[] };
  step_count: number; mitre_tactics: string[];
}
export interface AssetSpec {
  id: string; type: string; name?: string; role?: string; zone?: string;
  criticality?: number; data_sensitivity?: number; props?: Record<string, unknown>;
}
export interface ControlSpec {
  id: string; type: string; name?: string; enabled: boolean;
  scope?: string; targets?: string[];
}
export interface Topology { assets: AssetSpec[]; controls: ControlSpec[]; }

export interface RunConfig {
  difficulty: "Easy" | "Medium" | "Hard" | "Expert";
  readiness: number; duration_min: number; industry?: string; seed?: number;
}
export interface RunSummary {
  id: string; scenario_id: string; scenario_name: string; operator?: string | null;
  status: string; duration_s: number; scores: { red: number; blue: number };
  kpis: Record<string, number>; summary: Record<string, any>; created_at: string;
  environment?: AssetNode[]; objectives?: { red: ObjStatus[]; blue: ObjStatus[] };
}
export interface ObjStatus { text: string; met: boolean; }
export interface AssetNode {
  id: string; type: string; name: string; role?: string | null; zone: string;
  criticality: number; security_state: string; health: string;
}
export interface SimEvent {
  seq: number; t: number; type: string; side: string; actor: string;
  phase?: string | null; severity: string; title: string; message: string;
  technique?: string | null; asset_id?: string | null; asset_label?: string | null;
  channel?: string | null; data: Record<string, any>;
}
export interface ReportContent {
  scenario_name: string; duration_min: number; exec_summary: string;
  timeline: any[]; mitre_map: any[]; scorecard: Record<string, any>;
  regulatory_impact: string[]; financial_impact: { estimate_low_usd: number; estimate_high_usd: number; drivers: string[] };
  recommendations: string[]; maturity_score: { score: number; band: string };
  corrective_actions: { priority: string; action: string }[];
}
export interface Dashboard {
  total_runs: number; total_scenarios: number; avg_blue_score: number; critical_findings: number;
  recent_runs: any[]; threat_coverage: { label: string; pct: number }[];
  readiness: Record<string, number>;
}
