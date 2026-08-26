/**
 * The hero run, as a typed fixture.
 *
 * **Not part of the live path.** Since Phase 4.2 the app renders runs adapted
 * from the real backend; this module exists so tests and the offline demo route
 * have a complete, stable scenario to render. It is reachable only through
 * `/demo/hero`, and `Run.source` marks anything built from it as `"fixture"` so
 * a live run can never quietly inherit a value from here.
 */

import type { Run, RunSummary, World } from "../types/run";

const worldAlpha: World = {
  worldId: "world_alpha",
  label: "WORLD α",
  name: "Rollback Pricing Deployment",
  action: {
    actionId: "action_a1c4",
    kind: "SET_DEPLOYMENT_VERSION",
    name: "Roll back pricing-service",
    target: "pricing-service",
    parameter: "pricing-service version",
    from: "v2.41",
    to: "v2.40",
    fingerprint: "e91c4d2a7b30f558",
    reversible: true,
  },
  pipeline: [
    {
      id: "alpha-execute",
      label: "Execute world",
      status: "passed",
      duration: "1.2s",
      detail: "Action applied to an isolated copy of production.",
    },
    {
      id: "alpha-doppelganger",
      label: "DOPPELGÄNGER",
      status: "passed",
      duration: "4.8s",
      detail:
        "Adversarial subagent investigated the world and proposed one counterexample.",
    },
    {
      id: "alpha-replay",
      label: "BRANCHPOINT replay",
      status: "failed",
      duration: "0.2s",
      detail:
        "BRANCHPOINT replayed the proposed counterexample and reproduced the failure itself.",
    },
  ],
  verdict: "VETOED",
  verdictReason: "Schema compatibility failure",
  outcome: {
    goalAchieved: true,
    goalAttainment: 0.94,
    regressions: 2,
    blastRadius: 3,
    costDelta: 0,
    results: [
      { label: "Checkout error", value: "2.1%", from: "41.3%", to: "2.1%" },
      { label: "p95", value: "610ms", from: "4.8s", to: "610ms" },
    ],
  },
  counterexample: {
    attackId: "attack_7f21",
    title: "Schema compatibility under rollback",
    hypothesis:
      "Orders created under schema 41 may not deserialize under v2.40.",
    status: "REPRODUCED",
    evidenceIds: ["ev_alpha_schema", "ev_alpha_payment"],
  },
  sandbox: {
    enabled: true,
    status: "Available",
    sandboxId: "sbx_4a19c72e",
    execCount: 3,
  },
  evidence: [
    {
      evidenceId: "ev_alpha_sandbox",
      source: "trueforge-doppelganger",
      authority: "EXPLORATORY",
      claim: "Sandbox probe over sampled order records",
      outcome: "INFO",
      observed: "3 exec calls, 1 hypothesis formed",
      expected: "exploratory only; not authoritative",
    },
    {
      evidenceId: "ev_alpha_schema",
      source: "branchpoint-replay",
      authority: "VERIFIED",
      claim: "schema_compatibility",
      outcome: "FAIL",
      observed: "3 of 3 sampled orders failed to deserialize",
      expected: "all orders deserialize under the deployed version",
    },
    {
      evidenceId: "ev_alpha_payment",
      source: "branchpoint-replay",
      authority: "VERIFIED",
      claim: "payment_retry",
      outcome: "FAIL",
      observed: "retry produced a duplicate payment revision",
      expected: "payment retry stays idempotent",
    },
  ],
  recommended: false,
  notes: [
    "Goal achieved, but the rollback breaks records written by the newer schema.",
  ],
  evidenceCount: 3,
  reproducedCounterexamples: 1,
};

const worldBeta: World = {
  worldId: "world_beta",
  label: "WORLD β",
  name: "Disable Pricing V2",
  action: {
    actionId: "action_b8e2",
    kind: "SET_FEATURE_FLAG",
    name: "Disable PRICING_V2",
    target: "pricing-service",
    parameter: "PRICING_V2",
    from: "true",
    to: "false",
    fingerprint: "3d7a1e05c94b2f6d",
    reversible: true,
  },
  pipeline: [
    {
      id: "beta-execute",
      label: "Execute world",
      status: "passed",
      duration: "1.1s",
      detail: "Action applied to an isolated copy of production.",
    },
    {
      id: "beta-doppelganger",
      label: "DOPPELGÄNGER",
      status: "passed",
      duration: "5.2s",
      detail:
        "Adversarial subagent investigated the world and found nothing replayable.",
    },
    {
      id: "beta-replay",
      label: "BRANCHPOINT replay",
      status: "passed",
      duration: "0.2s",
      detail: "Every declared invariant was replayed and held.",
    },
  ],
  verdict: "SURVIVED",
  verdictReason: "No reproduced counterexample and no failing verifiable evidence",
  outcome: {
    goalAchieved: true,
    goalAttainment: 0.97,
    regressions: 0,
    blastRadius: 1,
    costDelta: 0,
    results: [
      { label: "Checkout error", value: "1.4%", from: "41.3%", to: "1.4%" },
      { label: "p95", value: "320ms", from: "4.8s", to: "320ms" },
    ],
  },
  counterexample: {
    attackId: "attack_9c04",
    title: "No replayable counterexample found",
    hypothesis:
      "Probed compatibility, integrity, and recovery; found nothing replayable.",
    status: "NONE_PROPOSED",
    evidenceIds: [],
  },
  sandbox: {
    enabled: true,
    status: "Available",
    sandboxId: "sbx_10bd63f4",
    execCount: 2,
  },
  evidence: [
    {
      evidenceId: "ev_beta_sandbox",
      source: "trueforge-doppelganger",
      authority: "EXPLORATORY",
      claim: "Sandbox probe over sampled order records",
      outcome: "INFO",
      observed: "2 exec calls, no hypothesis submitted",
      expected: "exploratory only; not authoritative",
    },
    {
      evidenceId: "ev_beta_healthy",
      source: "branchpoint-replay",
      authority: "VERIFIED",
      claim: "healthy_checkout",
      outcome: "PASS",
      observed: "1.4%",
      expected: "checkout error rate at most 2%",
    },
    {
      evidenceId: "ev_beta_recovery",
      source: "branchpoint-replay",
      authority: "VERIFIED",
      claim: "recovery_slo",
      outcome: "PASS",
      observed: "320ms",
      expected: "p95 latency at most 800ms",
    },
    {
      evidenceId: "ev_beta_integrity",
      source: "branchpoint-replay",
      authority: "VERIFIED",
      claim: "data_integrity",
      outcome: "PASS",
      observed: "0 corrupted records",
      expected: "no order loses a field it was written with",
    },
    {
      evidenceId: "ev_beta_payment",
      source: "branchpoint-replay",
      authority: "VERIFIED",
      claim: "payment_retry",
      outcome: "PASS",
      observed: "retry produced no duplicate revision",
      expected: "payment retry stays idempotent",
    },
    {
      evidenceId: "ev_beta_schema",
      source: "branchpoint-replay",
      authority: "VERIFIED",
      claim: "schema_compatibility",
      outcome: "PASS",
      observed: "all sampled orders deserialize",
      expected: "all orders deserialize under the deployed version",
    },
  ],
  recommended: true,
  notes: ["All declared invariants pass."],
  evidenceCount: 6,
  reproducedCounterexamples: 0,
};

const worldGamma: World = {
  worldId: "world_gamma",
  label: "WORLD γ",
  name: "Scale Pricing Service",
  action: {
    actionId: "action_c5f9",
    kind: "SCALE_SERVICE",
    name: "Scale pricing-service",
    target: "pricing-service",
    parameter: "replicas",
    from: "4",
    to: "12",
    fingerprint: "b204ff8a61d3e770",
    reversible: true,
  },
  pipeline: [
    {
      id: "gamma-execute",
      label: "Execute world",
      status: "passed",
      duration: "1.4s",
      detail: "Action applied to an isolated copy of production.",
    },
    {
      id: "gamma-doppelganger",
      label: "DOPPELGÄNGER",
      status: "passed",
      duration: "4.1s",
      detail:
        "Adversarial subagent investigated the world and found nothing replayable.",
    },
    {
      id: "gamma-replay",
      label: "BRANCHPOINT replay",
      status: "passed",
      duration: "0.2s",
      detail: "Every declared invariant was replayed and held.",
    },
  ],
  verdict: "SURVIVED",
  verdictReason: "No reproduced counterexample and no failing verifiable evidence",
  outcome: {
    goalAchieved: false,
    goalAttainment: 0.58,
    regressions: 0,
    blastRadius: 2,
    costDelta: 1840,
    results: [
      { label: "Checkout error", value: "16.2%", from: "41.3%", to: "16.2%" },
      { label: "p95", value: "1.9s", from: "4.8s", to: "1.9s" },
    ],
  },
  counterexample: {
    attackId: "attack_2ab7",
    title: "No replayable counterexample found",
    hypothesis:
      "Probed saturation and cost assumptions; found nothing replayable.",
    status: "NONE_PROPOSED",
    evidenceIds: [],
  },
  sandbox: {
    enabled: true,
    status: "Available",
    sandboxId: "sbx_7e2c98a1",
    execCount: 1,
  },
  evidence: [
    {
      evidenceId: "ev_gamma_sandbox",
      source: "trueforge-doppelganger",
      authority: "EXPLORATORY",
      claim: "Sandbox probe over throughput samples",
      outcome: "INFO",
      observed: "1 exec call, no hypothesis submitted",
      expected: "exploratory only; not authoritative",
    },
    {
      evidenceId: "ev_gamma_healthy",
      source: "branchpoint-replay",
      authority: "VERIFIED",
      claim: "healthy_checkout",
      outcome: "PASS",
      observed: "16.2%",
      expected: "no declared bound breached",
    },
    {
      evidenceId: "ev_gamma_integrity",
      source: "branchpoint-replay",
      authority: "VERIFIED",
      claim: "data_integrity",
      outcome: "PASS",
      observed: "0 corrupted records",
      expected: "no order loses a field it was written with",
    },
    {
      evidenceId: "ev_gamma_payment",
      source: "branchpoint-replay",
      authority: "VERIFIED",
      claim: "payment_retry",
      outcome: "PASS",
      observed: "retry produced no duplicate revision",
      expected: "payment retry stays idempotent",
    },
  ],
  recommended: false,
  notes: ["Goal not fully achieved.", "Extra cost."],
  evidenceCount: 4,
  reproducedCounterexamples: 0,
};

export const heroRun: Run = {
  source: "fixture",
  runId: "run_dbfa98c87f06",
  title: "Checkout Regression",
  status: "AWAITING_APPROVAL",
  startedAt: "18:42:01",
  elapsed: "2m 14s",
  objective: "Return checkout error rate below 2% without losing order data.",
  incident: {
    title: "Checkout Regression",
    summary:
      "Checkout error rate and latency regressed after pricing-service v2.41.",
    metrics: [
      { label: "Checkout error", value: "41.3%" },
      { label: "p95 latency", value: "4.8s" },
      { label: "Affected users", value: "12.4k" },
    ],
  },
  reality: {
    facts: [
      { label: "Pricing version", value: "v2.41" },
      { label: "PRICING_V2", value: "ON" },
      { label: "Replicas", value: "4" },
      { label: "Orders schema", value: "41" },
    ],
  },
  stages: [
    { id: "OBSERVE", label: "Observe", status: "complete" },
    { id: "PLAN", label: "Plan", status: "complete", detail: "3 candidates" },
    { id: "FORK", label: "Fork", status: "complete", detail: "3 worlds" },
    { id: "EXECUTE", label: "Execute", status: "complete" },
    { id: "ATTACK", label: "Attack", status: "complete", detail: "1 veto" },
    { id: "COMPARE", label: "Compare", status: "complete" },
    { id: "APPROVE", label: "Approve", status: "current", detail: "waiting" },
    { id: "COMMIT", label: "Commit", status: "pending" },
    { id: "VERIFY", label: "Verify", status: "pending" },
  ],
  worlds: [worldAlpha, worldBeta, worldGamma],
  comparison: {
    recommendedWorldId: "world_beta",
    rankings: [
      {
        worldId: "world_beta",
        rank: 1,
        reason: "Goal achieved, no regressions, smallest blast radius.",
      },
      {
        worldId: "world_gamma",
        rank: 2,
        reason: "Goal not achieved; higher cost.",
      },
    ],
    rejectedWorldIds: ["world_alpha"],
    summary: "Ranked first by deterministic comparator.",
  },
  approval: {
    required: true,
    status: "PENDING",
    worldId: "world_beta",
    actionId: "action_b8e2",
    actionFingerprint: "3d7a1e05c94b2f6d",
    checks: [
      { label: "Goal achieved", satisfied: true },
      { label: "All declared invariants passed", satisfied: true },
      { label: "No reproduced counterexamples", satisfied: true },
      { label: "Deterministic comparator recommendation", satisfied: true },
      { label: "Action fingerprint bound", satisfied: true },
    ],
  },
  realityCommitted: false,
  commitStatus: null,
  verificationStatus: null,
  failureReason: "",
  events: [
    {
      eventId: "evt_01",
      timestamp: "18:42:01",
      channel: "OBSERVE",
      message: "Incident snapshot captured",
    },
    {
      eventId: "evt_02",
      timestamp: "18:42:03",
      channel: "PLAN",
      message: "3 candidate actions generated",
    },
    {
      eventId: "evt_03",
      timestamp: "18:42:04",
      channel: "FORK",
      message: "world_alpha created",
      worldId: "world_alpha",
    },
    {
      eventId: "evt_04",
      timestamp: "18:42:04",
      channel: "FORK",
      message: "world_beta created",
      worldId: "world_beta",
    },
    {
      eventId: "evt_05",
      timestamp: "18:42:04",
      channel: "FORK",
      message: "world_gamma created",
      worldId: "world_gamma",
    },
    {
      eventId: "evt_06",
      timestamp: "18:42:07",
      channel: "DOPPEL",
      message: "Daytona sandbox created",
      worldId: "world_alpha",
    },
    {
      eventId: "evt_07",
      timestamp: "18:42:11",
      channel: "DOPPEL",
      message: "Counterexample proposed",
      worldId: "world_alpha",
    },
    {
      eventId: "evt_08",
      timestamp: "18:42:12",
      channel: "REPLAY",
      message: "Compatibility failure reproduced",
      worldId: "world_alpha",
    },
    {
      eventId: "evt_09",
      timestamp: "18:42:12",
      channel: "VERDICT",
      message: "world_alpha VETOED",
      worldId: "world_alpha",
    },
    {
      eventId: "evt_10",
      timestamp: "18:42:15",
      channel: "COMPARE",
      message: "world_beta ranked first",
      worldId: "world_beta",
    },
    {
      eventId: "evt_11",
      timestamp: "18:42:16",
      channel: "APPROVE",
      message: "Human approval required",
      worldId: "world_beta",
    },
  ],
};

/** Sidebar rows: the live run, then finished history. */
export const runHistory: RunSummary[] = [
  {
    runId: heroRun.runId,
    title: "Checkout regression",
    status: "AWAITING_APPROVAL",
    timeLabel: "2m 14s",
  },
  {
    runId: "run_4c17ab30e9d2",
    title: "Pricing timeout",
    status: "SUCCEEDED",
    timeLabel: "8m ago",
  },
  {
    runId: "run_9f02de5518a7",
    title: "Inventory incident",
    status: "REJECTED",
    timeLabel: "Yesterday",
  },
];

export function getRunById(runId: string | undefined): Run | undefined {
  return runId === undefined || runId === heroRun.runId ? heroRun : undefined;
}

export function getWorld(run: Run, worldId: string): World | undefined {
  return run.worlds.find((world) => world.worldId === worldId);
}
