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
  ActionDetailDto,
  ComparisonDetailDto,
  CounterexampleDto,
  EvidenceDto,
  HarnessTraceDto,
  WorldInspectionDto,
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
        authoritative_counterexamples: 1,
        veto: {
          basis: "REPRODUCED_COUNTEREXAMPLE",
          counterexample_id: "attack_7f21",
          evidence_ids: ["ev_alpha_schema", "ev_alpha_payment"],
          authoritative: true,
          summary: "Schema compatibility under rollback",
        },
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
        authoritative_counterexamples: 0,
        veto: null,
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
        authoritative_counterexamples: 0,
        veto: null,
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
  /** World inspection payloads, keyed by world id. */
  inspection?: Record<string, WorldInspectionDto>;
  harness?: HarnessTraceDto;
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
        if (path.endsWith("/rejection")) {
          const body = init?.body === undefined ? {} : JSON.parse(String(init.body));
          return json({
            run_id: RUN_ID,
            world_id: "world_beta",
            approval_status: "REJECTED",
            run_status: "REJECTED",
            actor: body.actor ?? null,
            reason: body.reason ?? "",
            decided_at: "2026-08-26T18:45:00Z",
            commit_possible: false,
            detail: "human rejection recorded; nothing was committed",
          });
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
      // Must precede the /runs/ catch-all, which would otherwise answer with
      // the run itself and hand the Inspector a payload of the wrong shape.
      const worldDetail =
        /\/api\/v1\/runs\/[^/]+\/worlds\/([^/]+?)(\/evidence|\/counterexamples)?$/.exec(
          path,
        );
      if (worldDetail !== null) {
        const inspection = routes.inspection?.[worldDetail[1]!];
        if (inspection === undefined) {
          return json({ detail: `world ${worldDetail[1]} not found` }, 404);
        }
        // Sub-resources serve the same records as the full detail, exactly as
        // the backend does — a narrower fetch must not disagree.
        if (worldDetail[2] === "/evidence") {
          return json({
            run_id: RUN_ID,
            world_id: worldDetail[1],
            evidence: inspection.evidence,
          });
        }
        if (worldDetail[2] === "/counterexamples") {
          return json({
            run_id: RUN_ID,
            world_id: worldDetail[1],
            counterexamples: inspection.counterexamples,
          });
        }
        return json(inspection);
      }
      if (path.endsWith("/harness-trace")) {
        return routes.harness === undefined
          ? json(emptyHarnessTrace())
          : json(routes.harness);
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

/** A run whose harness has done nothing yet. The default for most tests. */
export function emptyHarnessTrace(): HarnessTraceDto {
  return {
    run_id: RUN_ID,
    trueforge_status: "available",
    detail: "no TrueForge sessions bound to this run yet",
    sessions: [],
    entries: [],
  };
}

/**
 * A harness trace carrying one of every TrueForge capability, in the exact
 * shape `GET /runs/{id}/harness-trace` returns — MCP calls, a Daytona sandbox,
 * a successful exec, a real subagent thread, and the approval checkpoint.
 */
export function harnessTraceDto(): HarnessTraceDto {
  const base = {
    session_id: "sess_alpha",
    purpose: "ADVERSARY",
    world_id: "world_alpha",
    tool_name: "",
    mcp_server: "",
    thread_id: "main",
    sandbox_id: "",
    exit_code: null,
  };
  return {
    run_id: RUN_ID,
    trueforge_status: "available",
    detail: "read 2 TrueForge session(s)",
    sessions: [
      {
        purpose: "PLANNER",
        trueforge_session_id: "sess_planner",
        world_id: null,
        status: "COMPLETED",
        last_turn_id: "turn_1",
        created_at: "2026-08-26T18:42:01Z",
        updated_at: "2026-08-26T18:42:09Z",
      },
      {
        purpose: "ADVERSARY",
        trueforge_session_id: "sess_alpha",
        world_id: "world_alpha",
        status: "COMPLETED",
        last_turn_id: "turn_2",
        created_at: "2026-08-26T18:42:10Z",
        updated_at: "2026-08-26T18:42:19Z",
      },
    ],
    entries: [
      {
        ...base,
        trace_id: "t1",
        timestamp: "2026-08-26T18:42:03Z",
        category: "MCP_TOOL",
        status: "OK",
        summary: "MCP · branchpoint_get_metrics",
        tool_name: "branchpoint_get_metrics",
        mcp_server: "branchpoint",
      },
      {
        ...base,
        trace_id: "t2",
        timestamp: "2026-08-26T18:42:05Z",
        category: "SANDBOX_CREATED",
        status: "OK",
        summary: "Daytona sandbox created",
        sandbox_id: "v1:daytona:4a19c72e",
      },
      {
        ...base,
        trace_id: "t3",
        timestamp: "2026-08-26T18:42:08Z",
        category: "SUBAGENT_CREATED",
        status: "OK",
        summary: "Subagent · Compatibility Skeptic",
        thread_id: "thread_sub_1",
      },
      {
        ...base,
        trace_id: "t4",
        timestamp: "2026-08-26T18:42:11Z",
        category: "SANDBOX_EXEC",
        status: "OK",
        summary: "Sandbox exec completed",
        tool_name: "exec",
        thread_id: "thread_sub_1",
        exit_code: 0,
      },
      {
        ...base,
        trace_id: "t5",
        timestamp: "2026-08-26T18:44:15Z",
        session_id: "sess_operator",
        purpose: "COMMIT_OPERATOR",
        world_id: "world_beta",
        category: "APPROVAL_REQUIRED",
        status: "PENDING",
        summary: "Human approval required",
        tool_name: "branchpoint_commit_recommended_world",
      },
    ],
  };
}

/** TrueForge down: bindings survive, the timeline does not. */
export function unreachableHarnessTrace(): HarnessTraceDto {
  const trace = harnessTraceDto();
  return {
    ...trace,
    trueforge_status: "unavailable",
    detail: "could not read 2 of 2 session(s)",
    entries: [],
  };
}

/**
 * A world inspection payload in the exact shape
 * `GET /runs/{id}/worlds/{world_id}` returns.
 *
 * `world` is reused from `worldsDto()` so the fixture cannot drift from the
 * list shape the same backend serves.
 */
function inspectionFor(
  worldId: string,
  evidence: EvidenceDto[],
  counterexamples: CounterexampleDto[],
): WorldInspectionDto {
  const world = worldsDto().worlds.find((item) => item.world_id === worldId)!;
  return {
    run_id: RUN_ID,
    world,
    action: actionDetailDto(world.action_id, world.action_name, world.action_type),
    outcome: {
      succeeded: true,
      goal_achieved: world.goal_achieved ?? false,
      goal_attainment: world.goal_attainment ?? 0,
      invariants_preserved: true,
      reversible: true,
      regressions_detected: world.regressions_detected ?? 0,
      blast_radius: world.blast_radius ?? 0,
      cost_delta: world.cost_delta ?? 0,
      summary: "checkout_error_rate 0.413 -> 0.021",
    },
    evidence,
    counterexamples,
  };
}

/** The action shape the world detail route returns. */
function actionDetailDto(
  actionId: string,
  name: string,
  actionType: string,
): ActionDetailDto {
  const parameters: Record<string, string> =
    actionType === "SET_DEPLOYMENT_VERSION"
      ? { version: "v2.40" }
      : actionType === "SET_FEATURE_FLAG"
        ? { flag_key: "PRICING_V2" }
        : { target_replicas: "12" };
  return {
    action_id: actionId,
    name,
    description: `${name} in production`,
    action_type: actionType,
    target_service: "pricing-service",
    target_component: null,
    target_environment: "production",
    parameters,
    expected_outcome: "Checkout error rate returns below threshold",
    risk_class: "HIGH",
    reversible: true,
    action_fingerprint: "e91c4d2a7b30f558",
    source_kind: "PLANNER",
    source_name: "hero-demo-planner",
  };
}

function evidenceDto(
  overrides: Partial<EvidenceDto> & { evidence_id: string },
): EvidenceDto {
  return {
    kind: "TEST_RESULT",
    source: "branchpoint-counterexample-replay",
    claim: "check: property holds",
    world_id: "world_alpha",
    observed: null,
    expected: null,
    passed: true,
    severity: "INFO",
    machine_verifiable: true,
    disqualifying: false,
    artifact: null,
    recorded_at: "2026-08-26T18:42:12Z",
    ...overrides,
  };
}

function counterexampleDto(
  overrides: Partial<CounterexampleDto> & { counterexample_id: string },
): CounterexampleDto {
  return {
    world_id: "world_alpha",
    title: "Rollback order-compatibility regression",
    hypothesis: "Orders created under schema 41 may not deserialize under v2.40.",
    status: "REPRODUCED",
    reproduced: true,
    authoritative: true,
    created_at: "2026-08-26T18:42:12Z",
    reproduction_steps: [],
    evidence_ids: [],
    supporting_evidence_ids: [],
    ...overrides,
  };
}

/**
 * The complete TrueForge-backed chain: an exploratory sandbox record, failing
 * replay evidence, an authoritative reproduced counterexample, and a veto.
 */
export function fullChainInspection(): WorldInspectionDto {
  return inspectionFor(
    "world_alpha",
    [
      evidenceDto({
        evidence_id: "ev_sandbox",
        source: "trueforge-doppelganger",
        claim: "adversarial exploration performed in a TrueForge sandbox",
        machine_verifiable: false,
        passed: null,
        observed: "subagents=1 sandboxes=1",
      }),
      evidenceDto({
        evidence_id: "ev_schema",
        claim: "schema_compatibility: all orders deserialize",
        passed: false,
        disqualifying: true,
        severity: "CRITICAL",
      }),
      evidenceDto({
        evidence_id: "ev_payment",
        claim: "payment_retry: retry stays idempotent",
        passed: false,
        disqualifying: true,
        severity: "CRITICAL",
      }),
    ],
    [
      counterexampleDto({
        counterexample_id: "attack_alpha",
        evidence_ids: ["ev_sandbox", "ev_schema", "ev_payment"],
        supporting_evidence_ids: ["ev_schema", "ev_payment"],
      }),
    ],
  );
}

/**
 * The deterministic demo: a real veto with **no** exploratory stage, because
 * the demo's attacker is a deterministic compatibility suite, not DOPPELGÄNGER.
 */
export function deterministicInspection(): WorldInspectionDto {
  return inspectionFor(
    "world_alpha",
    [
      evidenceDto({
        evidence_id: "ev_demo_schema",
        source: "hero-adversarial-tester",
        claim: "order_deserialization_or_compatibility: orders deserialize",
        passed: false,
        disqualifying: true,
        severity: "CRITICAL",
      }),
    ],
    [
      counterexampleDto({
        counterexample_id: "attack_demo",
        hypothesis: "",
        evidence_ids: ["ev_demo_schema"],
        supporting_evidence_ids: ["ev_demo_schema"],
      }),
    ],
  );
}

/** An attack claiming reproduction with nothing qualifying behind it. */
export function unsupportedClaimInspection(): WorldInspectionDto {
  const inspection = inspectionFor(
    "world_beta",
    [
      evidenceDto({
        evidence_id: "ev_sandbox_only",
        source: "trueforge-doppelganger",
        claim: "sandbox script observed the invariant break",
        machine_verifiable: false,
        passed: null,
      }),
    ],
    [
      counterexampleDto({
        counterexample_id: "attack_unsupported",
        world_id: "world_beta",
        reproduced: true,
        authoritative: false,
        evidence_ids: ["ev_sandbox_only"],
        supporting_evidence_ids: [],
      }),
    ],
  );
  return { ...inspection, world: { ...inspection.world, veto: null } };
}

/** A world that survived: passing checks, no reproduced attack, no veto. */
export function survivingInspection(): WorldInspectionDto {
  return inspectionFor(
    "world_beta",
    [
      evidenceDto({
        evidence_id: "ev_healthy",
        world_id: "world_beta",
        claim: "healthy_checkout: error rate at most 2%",
        passed: true,
      }),
    ],
    [
      counterexampleDto({
        counterexample_id: "attack_beta",
        world_id: "world_beta",
        title: "No replayable counterexample found",
        status: "NOT_REPRODUCED",
        reproduced: false,
        authoritative: false,
      }),
    ],
  );
}

/**
 * Exploratory evidence that did **not** come from the DOPPELGÄNGER.
 *
 * Non-machine-verifiable, so it is genuinely exploratory — but nothing about it
 * says an adversarial agent ran, and the Inspector must not claim one did.
 */
export function nonDoppelgangerExploratoryInspection(): WorldInspectionDto {
  return inspectionFor(
    "world_alpha",
    [
      evidenceDto({
        evidence_id: "ev_note",
        source: "manual-note",
        claim: "operator flagged this rollback as risky",
        machine_verifiable: false,
        passed: null,
      }),
      evidenceDto({
        evidence_id: "ev_schema",
        claim: "schema_compatibility: all orders deserialize",
        passed: false,
        disqualifying: true,
        severity: "CRITICAL",
      }),
    ],
    [
      counterexampleDto({
        counterexample_id: "attack_note",
        hypothesis: "",
        evidence_ids: ["ev_note", "ev_schema"],
        supporting_evidence_ids: ["ev_schema"],
      }),
    ],
  );
}

/**
 * Two machine-verifiable records, only one of which the veto cites.
 *
 * The unlinked one passed and is unrelated to the conclusion; presenting it as
 * the replay proof would overstate what BRANCHPOINT actually verified.
 */
export function partiallyLinkedInspection(): WorldInspectionDto {
  const inspection = inspectionFor(
    "world_alpha",
    [
      evidenceDto({
        evidence_id: "ev_unrelated",
        claim: "cost_budget: daily spend within budget",
        passed: true,
      }),
      evidenceDto({
        evidence_id: "ev_linked",
        claim: "payment_retry: retry stays idempotent",
        passed: false,
        disqualifying: true,
        severity: "CRITICAL",
      }),
    ],
    [
      counterexampleDto({
        counterexample_id: "attack_linked",
        evidence_ids: ["ev_unrelated", "ev_linked"],
        supporting_evidence_ids: ["ev_linked"],
      }),
    ],
  );
  return {
    ...inspection,
    world: {
      ...inspection.world,
      veto: {
        basis: "REPRODUCED_COUNTEREXAMPLE",
        counterexample_id: "attack_linked",
        evidence_ids: ["ev_linked"],
        authoritative: true,
        summary: "Payment retry idempotency regression",
      },
    },
  };
}

/**
 * A run a human declined: terminal REJECTED, approval REJECTED, no commit.
 *
 * `actor` is a parameter so a test can name someone other than this browser's
 * `APPROVAL_ACTOR` — a run decided in another session, or by another operator.
 */
export function rejectedRunDto(
  reason = "Rollback risk is unacceptable.",
  actor = "release-engineer",
): RunDto {
  const run = runDto({ status: "REJECTED" });
  return {
    ...run,
    approval: {
      ...run.approval!,
      status: "REJECTED",
      actor,
      reason,
      decided_at: "2026-08-26T18:45:00Z",
    },
  };
}
