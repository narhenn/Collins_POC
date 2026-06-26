import type {
  AssetType, ControlType, TechniqueType, ScenarioSummary, Topology,
  RunConfig, RunSummary, SimEvent, ReportContent, Dashboard,
} from "./types";

async function get<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status} ${url}`);
  return r.json();
}
async function post<T>(url: string, body: unknown): Promise<T> {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${r.status} ${url}: ${await r.text()}`);
  return r.json();
}

export const api = {
  assets: () => get<AssetType[]>("/api/catalog/assets"),
  controls: () => get<ControlType[]>("/api/catalog/controls"),
  techniques: () => get<TechniqueType[]>("/api/catalog/techniques"),

  scenarios: () => get<ScenarioSummary[]>("/api/scenarios"),
  scenario: (id: string) => get<any>(`/api/scenarios/${id}`),
  topology: (id: string) => get<Topology>(`/api/scenarios/${id}/topology`),

  launch: (body: { scenario_id: string; environment_spec?: Topology; config?: RunConfig; operator?: string }) =>
    post<RunSummary>("/api/runs", body),
  runs: (limit = 20) => get<RunSummary[]>(`/api/runs?limit=${limit}`),
  run: (id: string) => get<RunSummary>(`/api/runs/${id}`),
  runEvents: (id: string) => get<SimEvent[]>(`/api/runs/${id}/events`),
  report: (id: string) => get<ReportContent>(`/api/runs/${id}/report`),

  dashboard: () => get<Dashboard>("/api/dashboard"),
  leaderboard: () => get<any[]>("/api/leaderboard"),
};
