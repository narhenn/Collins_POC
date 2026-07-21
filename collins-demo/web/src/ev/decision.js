// decision.js — client-side port of the scenario engine's EV decision intelligence
// (backend/app/api/ev.py). A real optimiser over the response action-space + multi-fault
// composition, so the Optimizer/Combine-faults tiles run with no backend.
// The optimiser brute-forces lever combinations to minimise TOTAL cost (residual damage +
// cost of responding) — so it finds the optimum rather than picking a preset.

const HOURS = 6
const COST = { rev_inr_per_kwh: 18, penalty_inr_per_hour_down: 1200 }

// per (asset:fault): kW knocked offline, stations down, share a response can contain
const SPEC = {
  'TX-1:overload': { prev: 0.55, kw: 480, stations: 2 },
  'TX-1:overheat': { prev: 0.50, kw: 260, stations: 1 },
  'F-1:overcurrent_trip': { prev: 0.35, kw: 420, stations: 2 },
  'F-2:overcurrent_trip': { prev: 0.40, kw: 150, stations: 1 },
  'DCFC:charger_offline': { prev: 0.60, kw: 240, stations: 1 },
  'DCFC:connector_fault': { prev: 0.70, kw: 120, stations: 0 },
  'BESS-A:thermal_runaway': { prev: 0.50, kw: 180, stations: 1 },
  'BESS-A:offline': { prev: 0.60, kw: 120, stations: 0 },
  'GRID:brownout': { prev: 0.40, kw: 360, stations: 2 },
  'GRID:supply_loss': { prev: 0.30, kw: 600, stations: 3 },
}
const DEFAULT = { prev: 0.5, kw: 300, stations: 1 }

// fault-specific response levers: containment weight (w) + cost (fraction of full exposure)
const LEVER_SETS = {
  'TX-1:overload': [
    { id: 'bess', label: 'Dispatch BESS', w: 0.55, cost: 0.05 },
    { id: 'shed', label: 'Shed non-critical DC', w: 0.40, cost: 0.06 },
    { id: 'curtail', label: 'Curtail charging', w: 0.35, cost: 0.08 },
  ],
  'TX-1:overheat': [
    { id: 'cool', label: 'Force-cool transformer', w: 0.50, cost: 0.03 },
    { id: 'throttle', label: 'Throttle DC power', w: 0.40, cost: 0.06 },
    { id: 'shift', label: 'Shift load to Feeder F-2', w: 0.30, cost: 0.04 },
  ],
  'F-1:overcurrent_trip': [
    { id: 'reclose', label: 'Re-close after load-shed', w: 0.55, cost: 0.04 },
    { id: 'rebal', label: 'Rebalance to Feeder F-2', w: 0.45, cost: 0.06 },
  ],
  'F-2:overcurrent_trip': [
    { id: 'shift', label: 'Shift AC bays to F-1', w: 0.50, cost: 0.05 },
    { id: 'stagger', label: 'Stagger AC charging', w: 0.35, cost: 0.03 },
  ],
  'DCFC:charger_offline': [
    { id: 'reboot', label: 'Remote-reboot OCPP', w: 0.60, cost: 0.01 },
    { id: 'reroute', label: 'Reroute drivers', w: 0.30, cost: 0.03 },
    { id: 'truck', label: 'Dispatch truck-roll', w: 0.45, cost: 0.09 },
  ],
  'DCFC:connector_fault': [
    { id: 'lock', label: 'Lock + reroute', w: 0.65, cost: 0.02 },
    { id: 'reset', label: 'Remote diagnostic reset', w: 0.40, cost: 0.03 },
  ],
  'BESS-A:thermal_runaway': [
    { id: 'isolate', label: 'Isolate + cool pack', w: 0.70, cost: 0.03 },
    { id: 'gridcov', label: 'Cover load from grid', w: 0.30, cost: 0.09 },
  ],
  'BESS-A:offline': [
    { id: 'hold', label: 'Hold peak on grid', w: 0.45, cost: 0.07 },
    { id: 'backup', label: 'Bring backup online', w: 0.55, cost: 0.05 },
  ],
  'GRID:brownout': [
    { id: 'ride', label: 'Ride through on BESS + solar', w: 0.60, cost: 0.05 },
    { id: 'curtail', label: 'Curtail DC-fast', w: 0.35, cost: 0.06 },
  ],
  'GRID:supply_loss': [
    { id: 'island', label: 'Island on BESS + solar', w: 0.55, cost: 0.05 },
    { id: 'priority', label: 'Prioritise AC bays', w: 0.30, cost: 0.02 },
    { id: 'restart', label: 'Sequence restart', w: 0.20, cost: 0.03 },
  ],
}
const DEFAULT_LEVERS = [
  { id: 'bess', label: 'Dispatch BESS', w: 0.50, cost: 0.05 },
  { id: 'shed', label: 'Shed non-critical load', w: 0.35, cost: 0.05 },
  { id: 'curtail', label: 'Curtail charging', w: 0.40, cost: 0.06 },
]
const COND_PEN = { peak: 0.15, heatwave: 0.18, rain: 0.08 }

const _levers = (a, f) => LEVER_SETS[`${a}:${f}`] || DEFAULT_LEVERS
const _spec = (a, f) => SPEC[`${a}:${f}`] || DEFAULT
const _full = (spec) => spec.kw * HOURS * COST.rev_inr_per_kwh + spec.stations * HOURS * COST.penalty_inr_per_hour_down

// cartesian product of `steps` taken `n` at a time
function* product(steps, n) {
  if (n === 0) { yield []; return }
  for (const head of steps) for (const tail of product(steps, n - 1)) yield [head, ...tail]
}

export function evOptimize(assetId, faultId, conditions = []) {
  const spec = _spec(assetId, faultId)
  const full = _full(spec)
  const prev = spec.prev
  const cond = Math.min(0.6, conditions.reduce((a, c) => a + (COND_PEN[c] || 0), 0))
  const levers = _levers(assetId, faultId)
  const steps = [0.0, 0.25, 0.5, 0.75, 1.0]

  const evaluate = (vals) => {
    const contain = Math.min(0.95, levers.reduce((a, l, i) => a + l.w * vals[i], 0)) * (1 - cond)
    const residual = full * (1 - prev * contain)
    const action = full * levers.reduce((a, l, i) => a + l.cost * vals[i], 0)
    return { residual, action, total: residual + action, contain }
  }

  let best = null, evals = 0
  for (const combo of product(steps, levers.length)) {
    const r = evaluate(combo); evals++
    if (!best || r.total < best.total) best = { vals: combo, contain: +r.contain.toFixed(3), residual: Math.round(r.residual), action_cost: Math.round(r.action), total: Math.round(r.total) }
  }

  // best achievable with a SINGLE lever (what a preset gives you)
  let bestSingle = null
  for (let i = 0; i < levers.length; i++) for (const v of steps.slice(1)) {
    const vals = levers.map(() => 0); vals[i] = v
    const t = evaluate(vals).total
    if (bestSingle == null || t < bestSingle) bestSingle = t
  }

  const doNothing = Math.round(full)
  return {
    full_exposure: doNothing, do_nothing: doNothing,
    optimal: { contain: best.contain, residual: best.residual, action_cost: best.action_cost, total: best.total },
    savings: doNothing - best.total,
    vs_single: bestSingle == null ? 0 : Math.round(bestSingle - best.total),
    evaluations: evals,
    levers: levers.map((l, i) => ({ id: l.id, label: l.label, value: best.vals[i] })),
  }
}

export function evMultifault(faults = [], _conditions = []) {
  const parts = faults.map(fr => ({ assetId: fr.assetId, faultId: fr.faultId, exposure: Math.round(_full(_spec(fr.assetId, fr.faultId))) }))
  const base = parts.reduce((a, p) => a + p.exposure, 0)
  const n = parts.length
  const interaction = n > 1 ? 0.15 * (n - 1) : 0   // concurrent faults on shared infra compound
  return { parts, base_exposure: base, count: n, interaction_pct: Math.round(interaction * 100), combined_exposure: Math.round(base * (1 + interaction)) }
}
