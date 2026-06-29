// api.js — the only surface the web app talks to. Vite proxies /api -> orchestrator (:8090).
const BASE = '/api'

async function req(path, opts = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' }, ...opts,
  })
  if (!res.ok) {
    let detail
    try { detail = (await res.json()).detail } catch { detail = res.statusText }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  return res.status === 204 ? null : res.json()
}

export const api = {
  health: () => req('/health'),
  build: (body) => req('/build', { method: 'POST', body: JSON.stringify(body) }),

  // real-time turbine twin
  twinState: (tenant) => req(`/twin/${tenant}/state`),
  step: (body) => req('/twin/step', { method: 'POST', body: JSON.stringify(body) }),

  // scenario builder
  scenarioLibrary: () => req('/scenarios/library'),
  authorScenario: (body) => req('/scenarios/author', { method: 'POST', body: JSON.stringify(body) }),
  runScenario: (body) => req('/scenarios/run', { method: 'POST', body: JSON.stringify(body) }),

  // twin intelligence: analysis + diagnosis agents + prediction engine
  horizons: () => req('/agents/horizons'),
  diagnostics: (tenant) => req(`/twin/${tenant}/diagnostics`),
  runDiagnosis: (body) => req('/agents/diagnosis', { method: 'POST', body: JSON.stringify(body) }),
  runAnalysis: (body) => req('/agents/analysis', { method: 'POST', body: JSON.stringify(body) }),

  // AI co-pilot: narration, work orders, predictive alerts, cascade analysis
  narrate: (tenant, machine) => req(`/agents/narrate/${tenant}?machine=${encodeURIComponent(machine || 'Turbine Engine')}`),
  workOrder: (body) => req('/agents/work-order', { method: 'POST', body: JSON.stringify(body) }),
  predictAlert: (body) => req('/agents/predict-alert', { method: 'POST', body: JSON.stringify(body) }),
  cascade: (body) => req('/agents/cascade', { method: 'POST', body: JSON.stringify(body) }),

  // build a twin: conversational agent + Tripo image->3D
  buildTwinMessage: (body) => req('/build-twin/message', { method: 'POST', body: JSON.stringify(body) }),
  buildTwinGenerate: (body) => req('/build-twin/generate', { method: 'POST', body: JSON.stringify(body) }),
  buildTwinStatus: (taskId) => req(`/build-twin/status/${taskId}`),
  modelUrl: (tenant) => `/api/model/${tenant}.glb`,
}

export default api
