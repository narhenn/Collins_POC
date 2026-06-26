import { useCallback, useEffect, useRef, useState } from "react";
import type { AssetNode, SimEvent } from "../api/types";

export interface SimInit {
  run_id: string;
  scenario: { name: string; phases: string[]; objectives: { red: string[]; blue: string[] }; type: string; label: string };
  duration_s: number;
  environment: AssetNode[];
  speed: number;
  total_events: number;
}
export interface SimComplete {
  scores: { red: number; blue: number };
  kpis: Record<string, number>;
  summary: Record<string, any>;
  objectives: { red: { text: string; met: boolean }[]; blue: { text: string; met: boolean }[] };
  final_assets: AssetNode[];
}

export interface SimState {
  connected: boolean;
  init?: SimInit;
  events: SimEvent[];
  simT: number;
  paused: boolean;
  speed: number;
  scores: { red: number; blue: number };
  assets: Record<string, AssetNode>;
  complete?: SimComplete;
}

function wsUrl(runId: string): string {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}/ws/runs/${runId}`;
}

export function useSimSocket(runId: string | null) {
  const wsRef = useRef<WebSocket | null>(null);
  const [state, setState] = useState<SimState>({
    connected: false, events: [], simT: 0, paused: false, speed: 30,
    scores: { red: 0, blue: 0 }, assets: {},
  });

  useEffect(() => {
    if (!runId) return;
    const ws = new WebSocket(wsUrl(runId));
    wsRef.current = ws;
    ws.onopen = () => setState((s) => ({ ...s, connected: true }));
    ws.onclose = () => setState((s) => ({ ...s, connected: false }));
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.type === "init") {
        const assets: Record<string, AssetNode> = {};
        for (const a of msg.environment as AssetNode[]) assets[a.id] = { ...a };
        setState((s) => ({ ...s, init: msg, speed: msg.speed, assets, events: [], complete: undefined, simT: 0 }));
      } else if (msg.type === "event") {
        const e = msg.event as SimEvent;
        setState((s) => {
          const next = { ...s, events: [...s.events, e] };
          if (e.type === "score" && e.data) next.scores = { red: e.data.red ?? s.scores.red, blue: e.data.blue ?? s.scores.blue };
          if (e.type === "state" && e.asset_id && e.data) {
            const a = s.assets[e.asset_id];
            if (a) next.assets = { ...s.assets, [e.asset_id]: { ...a, security_state: e.data.security_state ?? a.security_state, health: e.data.health ?? a.health } };
          }
          return next;
        });
      } else if (msg.type === "tick") {
        setState((s) => ({ ...s, simT: msg.sim_t, paused: msg.paused, speed: msg.speed }));
      } else if (msg.type === "complete") {
        setState((s) => ({ ...s, complete: msg as SimComplete }));
      }
    };
    return () => ws.close();
  }, [runId]);

  const send = useCallback((m: object) => {
    wsRef.current?.readyState === WebSocket.OPEN && wsRef.current.send(JSON.stringify(m));
  }, []);

  return {
    state,
    pause: () => send({ action: "pause" }),
    resume: () => send({ action: "resume" }),
    setSpeed: (value: number) => send({ action: "speed", value }),
    seek: (t: number) => send({ action: "seek", t }),
    stop: () => send({ action: "stop" }),
    inject: (technique: string, target_by?: string, target_value?: string, label?: string) =>
      send({ action: "inject", technique, target_by, target_value, label }),
  };
}
