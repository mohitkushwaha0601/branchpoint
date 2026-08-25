/**
 * Backend response fixtures and a mock `fetch`.
 *
 * These are transport DTOs captured in the backend's own shape — snake_case,
 * ISO timestamps, the same field names FastAPI emits. Tests drive the real API
 * client and the real adapters against them, so nothing in the live path is
 * stubbed out except the socket itself.
 *
 * No test in this suite reaches a real service.
 */

import { vi } from "vitest";

import type {
  ComparisonDetailDto,
  DemoStateDto,
  EventListDto,
  RunDto,
  RunStatusDto,
  WorldsDto,
} from "../api/types";

export const RUN_ID = "run_dbfa98c87f06";

export function runDto(overrides: Partial<RunDto> = {}): RunDto {
  return {
    run_id: RUN_ID,
    status: "AWAITING_APPROVAL",
    incident: {
      incident_id: "incident_1",
      title: "Checkout Regression",
      goal: "Restore checkout error rate to the declared recovery SLO.",
      severity: "CRITICAL",
      detected_at: "2026-08-26T18:42:01Z",
      description: "",
      affected_services: ["checkout", "pricing-service"],
    },
    created_at: "2026-08-26T18:42:01Z",
    updated_at: "2026-08-26T18:44:15Z",
    candidate_action_ids: ["action_a1c4", "action_b8e2", "action_c5f9"],
    worlds: [
      {
        world_id: "world_alpha",
        status: "VETOED",
        action_id: "action_a1c4",
        action_name: "Rollback Pricing Deployment",
        verdict: "VETOED",
        verdict_reason: "reproduced counterexample: schema compatibility",
        evidence_count: 3,
        counterexample_count: 1,
      },
      {
        world_id: "world_beta",
        status: "SURVIVED",
        action_id: "action_b8e2",
        action_name: "Disable Pricing V2",
        verdict: "SURVIVED",
        verdict_reason: "no reproduced counterexample",
        evidence_count: 6,
        counterexample_count: 1,
      },
      {
        world_id: "world_gamma",
        status: "SURVIVED",
        action_id: "action_c5f9",
        action_name: "Scale Pricing Service",
        verdict: "SURVIVED",
        verdict_reason: "no reproduced counterexample",
        evidence_count: 4,
        counterexample_count: 1,
      },
    ],
    comparison: {
      recommended_world_id: "world_beta",
      eligible_world_ids: ["world_beta", "world_gamma"],
      tied_world_ids: [],
      rejected_worlds: [
        {
          world_id: "world_alpha",
          reasons: ["VETOED"],
          detail: "a counterexample was reproduced",
        },
      ],
      summary: "world_beta ranked first",
    },
    approval: {
      approval_id: "approval_1",
      status: "PENDING",
      selected_world_id: "world_beta",
      action_id: "action_b8e2",
      action_fingerprint: "3d7a1e05c94b2f6d",
      requested_at: "2026-08-26T18:44:15Z",
      decided_at: null,
      actor: null,
      reason: "",
    },
    selected_world_id: "world_beta",
    commit_id: null,
    commit_status: null,
    verification_status: null,
    failure_reason: "",
    ...overrides,
  };
}

/** A run that has only just been accepted: no worlds, no comparison. */
export function youngRunDto(status: RunStatusDto = "OBSERVING"): RunDto {
  return runDto({
    status,
    candidate_action_ids: [],
    worlds: [],
    comparison: null,
    approval: null,
    selected_world_id: null,
  });
}

export function worldsDto(): WorldsDto {
  return {
    run_id: RUN_ID,
    worlds: [
      {
        world_id: "world_alpha",
        status: "VETOED",
        verdict: "VETOED",
        verdict_reason: "reproduced counterexample: schema compatibility",
        action_id: "action_a1c4",
        action_name: "Rollback Pricing Deployment",
        action_type: "SET_DEPLOYMENT_VERSION",
        goal_achieved: true,
        goal_attainment: 0.94,
        regressions_detected: 2,
        blast_radius: 3,
        cost_delta: 0,
        evidence_count: 3,
        counterexample_count: 1,
        reproduced_counterexamples: 1,
      },
      {
        world_id: "world_beta",
        status: "SURVIVED",
        verdict: "SURVIVED",
        verdict_reason: "no reproduced counterexample",
        action_id: "action_b8e2",
        action_name: "Disable Pricing V2",
        action_type: "SET_FEATURE_FLAG",
        goal_achieved: true,
        goal_attainment: 0.97,
        regressions_detected: 0,
        blast_radius: 1,
        cost_delta: 0,
        evidence_count: 6,
        counterexample_count: 1,
        reproduced_counterexamples: 0,
      },
      {
        world_id: "world_gamma",
        status: "SURVIVED",
        verdict: "SURVIVED",
        verdict_reason: "no reproduced counterexample",
        action_id: "action_c5f9",
        action_name: "Scale Pricing Service",
        action_type: "SCALE_SERVICE",
        goal_achieved: false,
        goal_attainment: 0.58,
        regressions_detected: 0,
        blast_radius: 2,
        cost_delta: 1840,
        evidence_count: 4,
        counterexample_count: 1,
        reproduced_counterexamples: 0,
      },
    ],
  };
}

export function comparisonDto(): ComparisonDetailDto {
  return {
    run_id: RUN_ID,
    recommended_world_id: "world_beta",
    eligible_world_ids: ["world_beta", "world_gamma"],
    tied_world_ids: [],
    rankings: [
      {
        world_id: "world_beta",
        rank: 1,
        goal_achieved: true,
        goal_attainment: 0.97,
        regressions_detected: 0,
        blast_radius: 1,
        cost_delta: 0,
      },
      {
        world_id: "world_gamma",
        rank: 2,
        goal_achieved: false,
        goal_attainment: 0.58,
        regressions_detected: 0,
        blast_radius: 2,
        cost_delta: 1840,
      },
    ],
    rejected_worlds: [
      {
        world_id: "world_alpha",
        reasons: ["VETOED"],
        detail: "a counterexample was reproduced",
      },
    ],
    summary: "world_beta ranked first",
  };
}

export function eventsDto(): EventListDto {
  return {
    events: [
      {
        event_id: "evt_01",
        run_id: RUN_ID,
        world_id: null,
        event_type: "RUN_CREATED",
        summary: "run opened for incident incident_1",
        occurred_at: "2026-08-26T18:42:01Z",
      },
      {
        event_id: "evt_02",
        run_id: RUN_ID,
        world_id: null,
        event_type: "CANDIDATES_PLANNED",
        summary: "3 candidate action(s) proposed",
        occurred_at: "2026-08-26T18:42:03Z",
      },
      {
        event_id: "evt_03",
        run_id: RUN_ID,
        world_id: "world_alpha",
        event_type: "COUNTEREXAMPLE_REPRODUCED",
        summary: "counterexample reproduced against world_alpha",
        occurred_at: "2026-08-26T18:42:12Z",
      },
      {
        event_id: "evt_04",
        run_id: RUN_ID,
        world_id: "world_alpha",
        event_type: "WORLD_VETOED",
        summary: "world_alpha VETOED",
        occurred_at: "2026-08-26T18:42:12Z",
      },
      {
        event_id: "evt_05",
        run_id: RUN_ID,
        world_id: null,
        event_type: "APPROVAL_REQUESTED",
        summary: "approval requested for world world_beta",
        occurred_at: "2026-08-26T18:44:15Z",
      },
    ],
  };
}

export function demoStateDto(flagEnabled = true): DemoStateDto {
  return {
    deployment: {
      service: "pricing-service",
      version: "v2.41",
      previous_version: "v2.40",
      deployed_at: "2026-08-26T18:00:00Z",
    },
    feature_flag: {
      key: "PRICING_V2",
      enabled: flagEnabled,
      service: "pricing-service",
    },
    capacity: {
      service: "pricing-service",
      replicas: 4,
      daily_infra_cost_usd: 480,
    },
    metrics: {
      regression_active: flagEnabled,
      checkout_error_rate: flagEnabled ? 0.413 : 0.014,
      checkout_p95_ms: flagEnabled ? 4800 : 320,
      pricing_timeout_rate: 0.21,
      affected_users: flagEnabled ? 12400 : 200,
      database_latency_ms: 40,
      checkout_cpu_utilization: 0.7,
      pricing_cpu_utilization: 0.9,
      daily_infra_cost_usd: 480,
    },
    orders: {
      total_orders: 120,
      orders_schema_version: 41,
      orders_with_payment_revision: 40,
    },
    snapshot_at: "2026-08-26T18:44:20Z",
  };
}

export interface RouteTable {
  run?: RunDto | (() => RunDto);
  worlds?: WorldsDto | null;
  comparison?: ComparisonDetailDto | null;
  events?: EventListDto;
  demo?: DemoStateDto | (() => DemoStateDto);
  health?: { status: string; service: string; version: string };
}

export interface MockServer {
  /** Every request the app made, in order, as `"METHOD /path"`. */
  calls: string[];
  /** Bodies of every POST, parsed. */
  posts: { path: string; body: unknown }[];
  /** Swap what a route serves mid-test, to simulate the run advancing. */
  set: (routes: RouteTable) => void;
  /** Force the next matching request to fail with a status. */
  fail: (fragment: string, status: number, detail: string) => void;
  /** Make every request behave as if the backend were down. */
  goOffline: () => void;
}

function resolve<T>(value: T | (() => T)): T {
  return typeof value === "function" ? (value as () => T)() : value;
}

/**
 * Install a `fetch` that answers from fixtures.
 *
 * Anything the app requests that is not configured here answers 404, so a test
 * cannot accidentally pass because a call silently succeeded.
 */
export function mockServer(initial: RouteTable = {}): MockServer {
  let routes: RouteTable = { ...initial };
  const calls: string[] = [];
  const posts: { path: string; body: unknown }[] = [];
  const failures: { fragment: string; status: number; detail: string }[] = [];
  let offline = false;

  const json = (payload: unknown, status = 200) =>
    new Response(JSON.stringify(payload), {
      status,
      headers: { "content-type": "application/json" },
    });

  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      const path = url.replace(/^https?:\/\/[^/]+/, "");
      const method = init?.method ?? "GET";
      calls.push(`${method} ${path}`);

      if (init?.signal?.aborted) {
        throw new DOMException("Aborted", "AbortError");
      }
      if (offline) throw new TypeError("Failed to fetch");

      const failure = failures.find((item) => path.includes(item.fragment));
      if (failure !== undefined) {
        failures.splice(failures.indexOf(failure), 1);
        return json({ detail: failure.detail }, failure.status);
      }

      if (method === "POST") {
        posts.push({
          path,
          body: init?.body === undefined ? null : JSON.parse(String(init.body)),
        });
        if (path.endsWith("/agent-runs")) {
          return json({ run_id: RUN_ID, status: "CREATED", detail: "run accepted" }, 202);
        }
        if (path.endsWith("/approval")) {
          return json({
            run_id: RUN_ID,
            world_id: "world_beta",
            action_id: "action_b8e2",
            action_name: "Disable Pricing V2",
            approval_status: "APPROVED",
            run_status: "COMMITTING",
            commit_status: null,
            verification_status: null,
            detail: "approved",
          });
        }
      }

      if (path === "/health") {
        return routes.health === undefined
          ? json({ detail: "not found" }, 404)
          : json(routes.health);
      }
      if (path === "/api/v1/demo/state") {
        return routes.demo === undefined
          ? json({ detail: "not found" }, 404)
          : json(resolve(routes.demo));
      }
      if (path === "/api/v1/runs") {
        const run = routes.run === undefined ? null : resolve(routes.run);
        return json({ runs: run === null ? [] : [run] });
      }
      if (path.endsWith("/events")) {
        return routes.events === undefined
          ? json({ events: [] })
          : json(routes.events);
      }
      if (path.endsWith("/worlds")) {
        return routes.worlds === undefined || routes.worlds === null
          ? json({ detail: "no worlds" }, 404)
          : json(routes.worlds);
      }
      if (path.endsWith("/comparison")) {
        return routes.comparison === undefined || routes.comparison === null
          ? json({ detail: "run has not been compared yet" }, 409)
          : json(routes.comparison);
      }
      if (path.startsWith("/api/v1/runs/")) {
        return routes.run === undefined
          ? json({ detail: `run not found` }, 404)
          : json(resolve(routes.run));
      }

      return json({ detail: `unhandled ${path}` }, 404);
    }),
  );

  return {
    calls,
    posts,
    set: (next) => {
      routes = { ...routes, ...next };
    },
    fail: (fragment, status, detail) => failures.push({ fragment, status, detail }),
    goOffline: () => {
      offline = true;
    },
  };
}
