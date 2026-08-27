/**
 * The canonical incident, as the live backend actually computes it.
 *
 * **This is the single frontend source of truth for the marketing site.** The
 * landing page and (later) How It Works both quote this incident; if the numbers
 * lived inline in components they would drift within a week.
 *
 * ## Where these values come from
 *
 * Every number below was produced by *running* the demo engine against
 * `scenarios/checkout_regression.json` and reading the result — not by copying a
 * fixture and not by arithmetic done in a design document. The engine is pure:
 * `compute_metrics(state)` is a deterministic function of state, so these values
 * are reproducible at any time with the snippet in
 * `docs/LANDING_INTERACTION_BLUEPRINT.md` §1.
 *
 * ## What must NOT be used
 *
 * `src/data/heroRun.ts` is the offline `/demo/hero` fixture. It marks itself
 * "not part of the live path", and its α and γ numbers are hand-written and
 * **disagree with the engine** (α 2.1%/610ms, γ 16.2%/1.9s, 12.4k users). Phase
 * 2A corrected these. Nothing in the marketing tree may import it.
 *
 * ## Shape
 *
 * Presentation-neutral: no copy, no class names, no JSX. Components decide how
 * to say things; this module decides what is true. Later phases extend it by
 * adding fields, never by editing the verified values below.
 *
 * @see docs/LANDING_INTERACTION_BLUEPRINT.md — §1 source paths, §2 discrepancies
 */

/* ------------------------------------------------------------------ sources */

/**
 * Backend origins, kept as data so a reader can audit a value without hunting.
 * Keys are referenced from the `source` field on the structures below.
 */
export const SOURCES = {
  metrics: "backend/app/infrastructure/demo/metrics.py",
  workload: "backend/app/infrastructure/demo/workload.py",
  scenario:
    "backend/app/infrastructure/demo/scenarios/checkout_regression.json",
  verdicts: "backend/app/domain/worlds/verdicts.py",
  evidence: "backend/app/domain/evidence/models.py",
  comparison: "backend/app/domain/comparison/models.py",
} as const;

export type SourceKey = keyof typeof SOURCES;

/* ------------------------------------------------------------------- types */

/** How much authority a piece of evidence carries. The only bit that matters. */
export type Authority = "EXPLORATORY" | "VERIFIED";

/** `CheckSeverity` in the demo engine; only CRITICAL disqualifies on its own. */
export type Severity = "INFO" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

/** `WorldVerdict` in the domain. */
export type Verdict = "SURVIVED" | "VETOED" | "INCONCLUSIVE";

/** Where a surviving world landed in the deterministic comparison. */
export type Selection = "RECOMMENDED" | "NOT_SELECTED" | "DISQUALIFIED";

export interface Metric {
  readonly label: string;
  /** Formatted for display — the engine's own rounding, already applied. */
  readonly value: string;
  /** Raw value, for tests and any future computation. */
  readonly raw: number;
}

export interface Check {
  /** The engine's own check name, e.g. `payment_retry`. */
  readonly name: string;
  readonly passed: boolean;
  readonly severity: Severity;
  readonly authority: Authority;
  /** Verbatim from the engine. */
  readonly expected: string;
  /** Verbatim from the engine. */
  readonly observed: string;
  /** The record the check bound itself to, when it selected one. */
  readonly artifact?: string;
}

export interface WorldAction {
  readonly kind: string;
  readonly target: string;
  readonly parameter: string;
  readonly from: string;
  readonly to: string;
}

export interface CanonicalWorld {
  readonly id: string;
  /** "α" — the glyph the product itself uses. */
  readonly glyph: string;
  readonly label: string;
  readonly shortName: string;
  readonly action: WorldAction;
  /** Whether v2.41's buggy code path still runs in this world. */
  readonly regressionActive: boolean;
  readonly metrics: {
    readonly errorRate: Metric;
    readonly p95: Metric;
    readonly affectedUsers: Metric;
    readonly costDelta: Metric;
  };
  readonly checks: readonly Check[];
  readonly verdict: Verdict;
  readonly selection: Selection;
  /** Why the verdict is what it is, in the domain's own terms. */
  readonly verdictReason: string;
}

/* ----------------------------------------------------------------- reality */

/**
 * Production as the run finds it.
 *
 * @source scenario — versions, flag, replicas, schema, order records
 * @source metrics — every derived number
 */
export const INITIAL_REALITY = {
  service: "pricing-service",
  version: "v2.41",
  previousVersion: "v2.40",
  flagKey: "PRICING_V2",
  flagEnabled: true,
  replicas: 4,
  /** metrics.py — state.pricing_capacity.cost_per_replica_per_day */
  costPerReplicaPerDay: 112.5,
  ordersSchemaVersion: 41,
  /**
   * The regression is v2.41's own code. It runs only when v2.41 is deployed
   * *and* the flag routes traffic through it.
   * @source metrics — is_regression_active()
   */
  regressionActive: true,
  metrics: {
    /** metrics.py — REGRESSION_BASE_ERROR_RATE = 0.413 */
    errorRate: { label: "Checkout error", value: "41.3%", raw: 0.413 },
    /** metrics.py — REGRESSION_BASE_P95_MS = 4800.0 */
    p95: { label: "p95 latency", value: "4.8s", raw: 4800 },
    /** metrics.py — round(DAILY_CHECKOUT_ATTEMPTS 19_370 × 0.413) */
    affectedUsers: { label: "Affected users", value: "8,000", raw: 8000 },
    /** metrics.py — replicas × cost_per_replica_per_day = 4 × 112.5 */
    dailyCost: { label: "Infra cost", value: "$450/day", raw: 450 },
  },
} as const;

/**
 * The order every compatibility failure binds itself to.
 *
 * `_select_payment_revision_order()` deterministically picks the lowest-id order
 * created under v2.41 that carries a `payment_revision` — always `order_1003`.
 * The entire α veto rests on this one nameable record, which is why it is worth
 * naming on the page.
 *
 * @source workload
 */
export const WITNESS_ORDER = {
  orderId: "order_1003",
  paymentRevision: "pr_7f3a91",
  schemaVersion: 41,
  /** The schema v2.40's order reader understands. */
  supportedSchemaUnderRollback: 40,
  originalKey: "order_1003:pr_7f3a91",
  degradedKey: "order_1003:legacy",
} as const;

/* --------------------------------------------------------- declared bounds */

/**
 * BRANCHPOINT's own thresholds. An adversary chooses which invariant to test; it
 * never chooses what the invariant says.
 *
 * @source metrics
 */
export const DECLARED_BOUNDS = {
  recoveryErrorRate: 0.02,
  recoveryP95Ms: 500,
  healthyCheckoutErrorRate: 0.02,
} as const;

/* ------------------------------------------------------------------ worlds */

const alpha: CanonicalWorld = {
  id: "world_alpha",
  glyph: "α",
  label: "WORLD α",
  shortName: "Rollback",
  action: {
    kind: "SET_DEPLOYMENT_VERSION",
    target: "pricing-service",
    parameter: "version",
    from: "v2.41",
    to: "v2.40",
  },
  // Rolling back removes v2.41, so the regression's code path is simply gone.
  regressionActive: false,
  metrics: {
    /** metrics.py — BYPASSED_ERROR_RATE_BY_VERSION["v2.40"] = 0.018 */
    errorRate: { label: "Checkout error", value: "1.8%", raw: 0.018 },
    /** metrics.py — BYPASSED_P95_MS_BY_VERSION["v2.40"] = 190.0 */
    p95: { label: "p95 latency", value: "190ms", raw: 190 },
    /** round(19_370 × 0.018) */
    affectedUsers: { label: "Affected users", value: "349", raw: 349 },
    costDelta: { label: "Cost delta", value: "$0", raw: 0 },
  },
  checks: [
    {
      name: "healthy_checkout",
      passed: true,
      severity: "INFO",
      authority: "VERIFIED",
      expected: "checkout_error_rate <= 0.020",
      observed: "checkout_error_rate = 0.0180",
    },
    {
      name: "recovery_slo",
      passed: true,
      severity: "INFO",
      authority: "VERIFIED",
      expected: "checkout_error_rate <= 0.020 and checkout_p95_ms <= 500",
      observed: "checkout_error_rate = 0.0180, checkout_p95_ms = 190.0",
    },
    {
      name: "data_integrity",
      passed: true,
      severity: "INFO",
      authority: "VERIFIED",
      expected: "orders store has unique order ids and non-negative amounts",
      observed: "5 order(s), duplicates=False",
    },
    {
      name: "order_deserialization_or_compatibility",
      passed: false,
      severity: "CRITICAL",
      authority: "VERIFIED",
      expected:
        "pricing-service v2.40 deserializes order order_1003 (schema 41)",
      observed:
        "pricing-service v2.40 supports orders schema up to 40; order requires schema 41",
      artifact: "order:order_1003",
    },
    {
      name: "payment_retry",
      passed: false,
      severity: "CRITICAL",
      authority: "VERIFIED",
      expected: "retry idempotency key == 'order_1003:pr_7f3a91'",
      observed: "retry idempotency key == 'order_1003:legacy'",
      artifact: "order:order_1003",
    },
  ],
  verdict: "VETOED",
  selection: "DISQUALIFIED",
  // verdicts.py — disqualifying_evidence(): CRITICAL severity disqualifies.
  verdictReason:
    "machine-verifiable failure: order_deserialization_or_compatibility, payment_retry",
};

const beta: CanonicalWorld = {
  id: "world_beta",
  glyph: "β",
  label: "WORLD β",
  shortName: "Flag off",
  action: {
    kind: "SET_FEATURE_FLAG",
    target: "pricing-service",
    parameter: "PRICING_V2",
    from: "true",
    to: "false",
  },
  // v2.41 is still deployed, but the flag no longer routes traffic through the
  // regression — so the buggy path does not run, and schema 41 stays readable.
  regressionActive: false,
  metrics: {
    /** metrics.py — BYPASSED_ERROR_RATE_LEGACY_FLAG_OFF = 0.014 */
    errorRate: { label: "Checkout error", value: "1.4%", raw: 0.014 },
    /** metrics.py — BYPASSED_P95_MS_LEGACY_FLAG_OFF = 320.0 */
    p95: { label: "p95 latency", value: "320ms", raw: 320 },
    /** round(19_370 × 0.014) */
    affectedUsers: { label: "Affected users", value: "271", raw: 271 },
    costDelta: { label: "Cost delta", value: "$0", raw: 0 },
  },
  checks: [
    {
      name: "healthy_checkout",
      passed: true,
      severity: "INFO",
      authority: "VERIFIED",
      expected: "checkout_error_rate <= 0.020",
      observed: "checkout_error_rate = 0.0140",
    },
    {
      name: "recovery_slo",
      passed: true,
      severity: "INFO",
      authority: "VERIFIED",
      expected: "checkout_error_rate <= 0.020 and checkout_p95_ms <= 500",
      observed: "checkout_error_rate = 0.0140, checkout_p95_ms = 320.0",
    },
    {
      name: "data_integrity",
      passed: true,
      severity: "INFO",
      authority: "VERIFIED",
      expected: "orders store has unique order ids and non-negative amounts",
      observed: "5 order(s), duplicates=False",
    },
    {
      name: "order_deserialization_or_compatibility",
      passed: true,
      severity: "INFO",
      authority: "VERIFIED",
      expected:
        "pricing-service v2.41 deserializes order order_1003 (schema 41)",
      observed:
        "pricing-service v2.41 supports orders schema up to 41; order requires schema 41",
      artifact: "order:order_1003",
    },
    {
      name: "payment_retry",
      passed: true,
      severity: "INFO",
      authority: "VERIFIED",
      expected: "retry idempotency key == 'order_1003:pr_7f3a91'",
      observed: "retry idempotency key == 'order_1003:pr_7f3a91'",
      artifact: "order:order_1003",
    },
  ],
  verdict: "SURVIVED",
  selection: "RECOMMENDED",
  // verdicts.py — derive_verdict() fallthrough.
  verdictReason:
    "no reproduced counterexample and no failing verifiable evidence",
};

const gamma: CanonicalWorld = {
  id: "world_gamma",
  glyph: "γ",
  label: "WORLD γ",
  shortName: "Scale",
  action: {
    kind: "SCALE_SERVICE",
    target: "pricing-service",
    parameter: "replicas",
    from: "4",
    to: "12",
  },
  // The whole point of γ: v2.41 is still deployed AND the flag is still on, so
  // the regression keeps running no matter how much capacity is added.
  regressionActive: true,
  metrics: {
    /**
     * metrics.py — max(ERROR_RATE_FLOOR 0.07, 0.413 − 0.043 × 8).
     * The floor binds: extra replicas ease queueing pressure but cannot remove
     * a bug that is still deployed and still enabled.
     */
    errorRate: { label: "Checkout error", value: "7.0%", raw: 0.07 },
    /** metrics.py — max(LATENCY_FLOOR_MS 960, 4800 − 480 × 8). Floor binds. */
    p95: { label: "p95 latency", value: "960ms", raw: 960 },
    /** round(19_370 × 0.07) */
    affectedUsers: { label: "Affected users", value: "1,356", raw: 1356 },
    /** metrics.py — daily_cost_delta_usd(): (12 − 4) × $112.50 */
    costDelta: { label: "Cost delta", value: "+$900/day", raw: 900 },
  },
  checks: [
    {
      name: "healthy_checkout",
      passed: false,
      severity: "MEDIUM",
      authority: "VERIFIED",
      expected: "checkout_error_rate <= 0.020",
      observed: "checkout_error_rate = 0.0700",
    },
    {
      name: "recovery_slo",
      passed: false,
      severity: "MEDIUM",
      authority: "VERIFIED",
      expected: "checkout_error_rate <= 0.020 and checkout_p95_ms <= 500",
      observed: "checkout_error_rate = 0.0700, checkout_p95_ms = 960.0",
    },
    {
      name: "data_integrity",
      passed: true,
      severity: "INFO",
      authority: "VERIFIED",
      expected: "orders store has unique order ids and non-negative amounts",
      observed: "5 order(s), duplicates=False",
    },
    {
      name: "order_deserialization_or_compatibility",
      passed: true,
      severity: "INFO",
      authority: "VERIFIED",
      expected:
        "pricing-service v2.41 deserializes order order_1003 (schema 41)",
      observed:
        "pricing-service v2.41 supports orders schema up to 41; order requires schema 41",
      artifact: "order:order_1003",
    },
    {
      name: "payment_retry",
      passed: true,
      severity: "INFO",
      authority: "VERIFIED",
      expected: "retry idempotency key == 'order_1003:pr_7f3a91'",
      observed: "retry idempotency key == 'order_1003:pr_7f3a91'",
      artifact: "order:order_1003",
    },
  ],
  // MEDIUM severity is not disqualifying: kind TEST_RESULT is not in
  // DISQUALIFYING_EVIDENCE_KINDS and severity is not CRITICAL. γ misses the
  // goal but is still SAFE. Losing is a comparator concern, not a veto.
  verdict: "SURVIVED",
  selection: "NOT_SELECTED",
  verdictReason:
    "no reproduced counterexample and no failing verifiable evidence",
};

export const WORLDS: readonly CanonicalWorld[] = [alpha, beta, gamma];

export const WORLD_ALPHA = alpha;
export const WORLD_BETA = beta;
export const WORLD_GAMMA = gamma;

/* ---------------------------------------------------------------- helpers */

/** The checks that disqualified a world, in the engine's own order. */
export function disqualifyingChecks(world: CanonicalWorld): readonly Check[] {
  return world.checks.filter(
    (check) => !check.passed && check.severity === "CRITICAL",
  );
}

/** Failing checks that are real misses but do *not* disqualify. */
export function nonDisqualifyingFailures(
  world: CanonicalWorld,
): readonly Check[] {
  return world.checks.filter(
    (check) => !check.passed && check.severity !== "CRITICAL",
  );
}

export function worldById(id: string): CanonicalWorld | undefined {
  return WORLDS.find((world) => world.id === id);
}

/* ==========================================================================
 * PHASE 2D–3D EXTENSION
 *
 * Everything above is the Phase 2B core and is unchanged. Everything below it
 * is additive: the evidence chain, the comparator's real axes, the approval
 * binding, the commit gates, the verification re-read, the authority topology
 * and the nine protocol stages — all sourced the same way, all quoted by both
 * `/` and `/how-it-works`.
 * ========================================================================== */

/** The one run both pages narrate. It never resets and never changes. */
export const RUN_ID = "run_dbfa98c87f06";

/* ------------------------------------------------------- the authority spine */

/**
 * The three bands from the blueprint's authority model.
 *
 * This is deliberately a *different* type from `Authority` above. `Authority`
 * describes one piece of evidence — whether a machine checked it. `AuthorityBand`
 * describes an actor's standing in the system. Collapsing them is exactly the
 * mistake the site exists to prevent.
 */
export type AuthorityBand = "EXPLORATORY" | "DETERMINISTIC" | "PERMISSION";

export interface AuthorityBandSpec {
  readonly band: AuthorityBand;
  /** ░ ■ ▲ — so the band survives greyscale and colour blindness. */
  readonly mark: string;
  readonly who: string;
  readonly may: readonly string[];
  readonly mayNot: readonly string[];
}

/** @source blueprint §4, derived from `evidence/models.py` + `worlds/verdicts.py` */
export const AUTHORITY_BANDS: readonly AuthorityBandSpec[] = [
  {
    band: "EXPLORATORY",
    mark: "░",
    who: "DOPPELGÄNGER · its subagents · the sandbox · all model prose",
    may: [
      "Investigate a world snapshot",
      "Write and run throwaway code in an isolated sandbox",
      "Form a hypothesis and submit a typed CounterexampleSpec",
    ],
    mayNot: [
      "Veto a world",
      "Set or restate a threshold",
      "Mark anything REPRODUCED",
      "Contribute authority of any kind",
    ],
  },
  {
    band: "DETERMINISTIC",
    mark: "■",
    who: "BRANCHPOINT replay · world executor · comparator",
    may: [
      "Produce machine_verifiable evidence",
      "Veto a world on reproduced, disqualifying evidence",
      "Rank surviving worlds and recommend one",
    ],
    mayNot: ["Grant permission", "Change reality"],
  },
  {
    band: "PERMISSION",
    mark: "▲",
    who: "The human operator",
    may: ["Approve exactly one bound action", "Reject"],
    mayNot: [
      "Invent an action",
      "Override a veto",
      "Approve an action that changed after review",
    ],
  },
];

export function authorityBand(band: AuthorityBand): AuthorityBandSpec {
  const found = AUTHORITY_BANDS.find((entry) => entry.band === band);
  // The union is closed, so this cannot happen; the throw keeps the return
  // type honest without a non-null assertion.
  if (found === undefined) throw new Error(`unknown authority band ${band}`);
  return found;
}

/* -------------------------------------------------------------- the stages */

/** The nine canonical stages. There is no REPLAY stage — it is act two of ATTACK. */
export type StageId =
  | "observe"
  | "plan"
  | "fork"
  | "execute"
  | "attack"
  | "compare"
  | "approve"
  | "commit"
  | "verify";

export interface ProtocolStage {
  readonly id: StageId;
  /** "01".."09" */
  readonly number: string;
  readonly name: string;
  readonly band: AuthorityBand;
  /** For ATTACK only: the stage runs in two acts. */
  readonly acts?: readonly string[];
  /** One durable sentence. No numbers — those live in the evidence surfaces. */
  readonly thesis: string;
  /** What the viewport is showing. */
  readonly viewport: string;
  /** What leaving this stage establishes. */
  readonly transition: string;
  /** Why this stage holds the authority it holds. */
  readonly authorityNote: string;
}

/** @source blueprint §13, `domain/runs/lifecycle.py`, `domain/events.py` */
export const PROTOCOL_STAGES: readonly ProtocolStage[] = [
  {
    id: "observe",
    number: "01",
    name: "OBSERVE",
    band: "DETERMINISTIC",
    thesis: "Reality is read before anything is proposed.",
    viewport:
      "A snapshot of production: the deployed version, the flag, the replica count and the orders schema, with checkout burning.",
    transition:
      "An objective appears — get checkout error below the declared bound without losing order data.",
    authorityNote:
      "A snapshot is deterministic. Nothing has been decided and nothing has been proposed.",
  },
  {
    id: "plan",
    number: "02",
    name: "PLAN",
    band: "EXPLORATORY",
    thesis: "A plan is not evidence.",
    viewport:
      "Three candidate actions fan out from the objective. The planner runs read-only: no sandbox, no subagents, no mutations.",
    transition: "Three candidates. No permission granted.",
    authorityNote:
      "A model proposed these. Nothing here can be checked yet, so nothing here counts.",
  },
  {
    id: "fork",
    number: "03",
    name: "FORK",
    band: "DETERMINISTIC",
    thesis: "Fork reality. Not production.",
    viewport:
      "The production twin splits into three isolated snapshots, each sealed behind its own boundary.",
    transition: "All three worlds enter PREPARING.",
    authorityNote:
      "Isolation is structural, not promised. Nothing inside a world can reach reality.",
  },
  {
    id: "execute",
    number: "04",
    name: "EXECUTE",
    band: "DETERMINISTIC",
    thesis: "Measured, not predicted.",
    viewport:
      "Each world applies its own action and is measured. The execution suite runs against every world.",
    transition:
      "γ already missed the goal — and is not vetoed. Missing a goal is a quality result, not a safety one.",
    authorityNote:
      "These outcomes are machine-verifiable: the same snapshot and the same action produce the same numbers every time.",
  },
  {
    id: "attack",
    number: "05",
    name: "ATTACK",
    band: "DETERMINISTIC",
    acts: ["act 1 · hypothesis", "act 2 · replay"],
    thesis: "A guess is not a finding.",
    viewport:
      "Act one: DOPPELGÄNGER explores a world in a sandbox and submits one typed counterexample. Act two: BRANCHPOINT replays that spec against the world's own snapshot.",
    transition:
      "Reproduced, with disqualifying evidence behind it — so world α is VETOED.",
    authorityNote:
      "Authority transfers here, and only here. The adversary chose what to test; BRANCHPOINT decided what it means.",
  },
  {
    id: "compare",
    number: "06",
    name: "COMPARE",
    band: "DETERMINISTIC",
    thesis: "No score. Arithmetic.",
    viewport:
      "α is struck out with ADVERSARIAL_VETO before ranking begins. β and γ are ordered on the comparator's own axes.",
    transition: "β is rank 1. A deterministic recommendation — not permission.",
    authorityNote:
      "The comparator may rank and recommend. It cannot authorise anything.",
  },
  {
    id: "approve",
    number: "07",
    name: "APPROVE",
    band: "PERMISSION",
    thesis: "A recommendation is not permission.",
    viewport:
      "A binding card: the run, the world, the action id and the action's content fingerprint, with the five checks the approval binds.",
    transition: "Approved — a one-time capability is issued for that exact action.",
    authorityNote:
      "Only a human can grant permission, and only for the action they were shown.",
  },
  {
    id: "commit",
    number: "08",
    name: "COMMIT",
    band: "DETERMINISTIC",
    thesis: "The mutation was issued. That is all a commit proves.",
    viewport:
      "Four independent gates pass in order, the capability is spent, and PRICING_V2 goes true → false in production.",
    transition: "Reality changed once. Nothing has been proved yet.",
    authorityNote:
      "Permission was granted upstream; the commit itself is mechanical and re-checks every binding.",
  },
  {
    id: "verify",
    number: "09",
    name: "VERIFY",
    band: "DETERMINISTIC",
    thesis: "Approval changed permission. Verification proved reality.",
    viewport:
      "An independent re-read of production, expected against actual, with no reference to what the commit claimed.",
    transition: "Only now is the run SUCCEEDED.",
    authorityNote:
      "The verifier does not trust the commit's own report. It reads reality again.",
  },
];

export function stageById(id: StageId): ProtocolStage {
  const found = PROTOCOL_STAGES.find((stage) => stage.id === id);
  if (found === undefined) throw new Error(`unknown stage ${id}`);
  return found;
}

/* ------------------------------------------------------------- evidence rows */

/** `EvidenceKind` in `domain/evidence/models.py`. */
export type EvidenceKindName =
  | "METRIC"
  | "TEST_RESULT"
  | "INVARIANT"
  | "COST"
  | "DATA_INTEGRITY"
  | "EXECUTION_RESULT"
  | "COUNTEREXAMPLE"
  | "POLICY"
  | "VERIFICATION";

export interface EvidenceRow {
  readonly id: string;
  /** Which of the nine stages recorded it. Evidence never leaves the chain. */
  readonly stage: StageId;
  readonly kind: EvidenceKindName;
  /** `Evidence.source` — a string, and never the authority bit. */
  readonly source: string;
  readonly claim: string;
  /**
   * `Evidence.machine_verifiable` — the ONLY bit that carries authority. Never
   * inferred from `source`.
   */
  readonly machineVerifiable: boolean;
  readonly authority: Authority;
  /** `passed`: true → PASS, false → FAIL, null → INFO (proves nothing). */
  readonly outcome: "PASS" | "FAIL" | "INFO";
  readonly severity: Severity;
  readonly expected: string;
  readonly observed: string;
  readonly artifact?: string;
  /** True when `machine_verifiable && is_failing` — `Evidence.disqualifies`. */
  readonly disqualifies: boolean;
}

function row(input: Omit<EvidenceRow, "disqualifies" | "authority">): EvidenceRow {
  return {
    ...input,
    // Mirrors the domain property exactly rather than restating it by hand.
    disqualifies: input.machineVerifiable && input.outcome === "FAIL",
    authority: input.machineVerifiable ? "VERIFIED" : "EXPLORATORY",
  };
}

/**
 * The evidence each world's verdict actually rests on, in the order the run
 * recorded it.
 *
 * ## Why the three lists are different lengths
 *
 * They are not a grid and must never be rendered as one. `derive_verdict()`
 * short-circuits: a reproduced counterexample with disqualifying evidence
 * returns `VETOED` *before* any other branch is consulted. So α's list is its
 * veto chain and nothing else — its execution suite passed and stopped mattering
 * the moment replay landed. β was attacked and the attack failed to reproduce,
 * which is a result worth recording, so β carries the most rows. γ was never
 * attacked: it lost on the comparator's axes, and losing is not a safety
 * question.
 *
 * 3 · 6 · 4. The asymmetry is the most honest thing on the page.
 */
export const WORLD_EVIDENCE: Readonly<Record<string, readonly EvidenceRow[]>> = {
  world_alpha: [
    row({
      id: "evidence_a1",
      stage: "attack",
      kind: "COUNTEREXAMPLE",
      source: "doppelganger-sandbox",
      claim:
        "sandbox probe: orders written under schema 41 may not deserialize under v2.40",
      machineVerifiable: false,
      outcome: "INFO",
      severity: "INFO",
      expected: "—",
      observed: "3 exec calls in sandbox sbx_4a19c72e; 1 hypothesis submitted",
    }),
    row({
      id: "evidence_a2",
      stage: "attack",
      kind: "DATA_INTEGRITY",
      source: "branchpoint-counterexample-replay",
      claim: "order_deserialization_or_compatibility",
      machineVerifiable: true,
      outcome: "FAIL",
      severity: "CRITICAL",
      expected:
        "pricing-service v2.40 deserializes order order_1003 (schema 41)",
      observed:
        "pricing-service v2.40 supports orders schema up to 40; order requires schema 41",
      artifact: "order:order_1003",
    }),
    row({
      id: "evidence_a3",
      stage: "attack",
      kind: "DATA_INTEGRITY",
      source: "branchpoint-counterexample-replay",
      claim: "payment_retry",
      machineVerifiable: true,
      outcome: "FAIL",
      severity: "CRITICAL",
      expected: "retry idempotency key == 'order_1003:pr_7f3a91'",
      observed: "retry idempotency key == 'order_1003:legacy'",
      artifact: "order:order_1003",
    }),
  ],
  world_beta: [
    row({
      id: "evidence_b1",
      stage: "execute",
      kind: "TEST_RESULT",
      source: "branchpoint-world-executor",
      claim: "healthy_checkout",
      machineVerifiable: true,
      outcome: "PASS",
      severity: "INFO",
      expected: "checkout_error_rate <= 0.020",
      observed: "checkout_error_rate = 0.0140",
    }),
    row({
      id: "evidence_b2",
      stage: "execute",
      kind: "TEST_RESULT",
      source: "branchpoint-world-executor",
      claim: "recovery_slo",
      machineVerifiable: true,
      outcome: "PASS",
      severity: "INFO",
      expected: "checkout_error_rate <= 0.020 and checkout_p95_ms <= 500",
      observed: "checkout_error_rate = 0.0140, checkout_p95_ms = 320.0",
    }),
    row({
      id: "evidence_b3",
      stage: "execute",
      kind: "DATA_INTEGRITY",
      source: "branchpoint-world-executor",
      claim: "data_integrity",
      machineVerifiable: true,
      outcome: "PASS",
      severity: "INFO",
      expected: "orders store has unique order ids and non-negative amounts",
      observed: "5 order(s), duplicates=False",
    }),
    row({
      id: "evidence_b4",
      stage: "execute",
      kind: "COST",
      source: "branchpoint-world-executor",
      claim: "daily_infra_cost_delta",
      machineVerifiable: true,
      outcome: "PASS",
      severity: "INFO",
      expected: "no additional daily infrastructure spend",
      observed: "daily_infra_cost_usd = 450.0 (unchanged)",
    }),
    row({
      id: "evidence_b5",
      stage: "attack",
      kind: "COUNTEREXAMPLE",
      source: "doppelganger-sandbox",
      claim:
        "sandbox probe: disabling the flag may leave schema-41 orders unreadable",
      machineVerifiable: false,
      outcome: "INFO",
      severity: "INFO",
      expected: "—",
      observed: "2 exec calls in sandbox sbx_4a19c72e; 1 hypothesis submitted",
    }),
    row({
      id: "evidence_b6",
      stage: "attack",
      kind: "DATA_INTEGRITY",
      source: "branchpoint-counterexample-replay",
      claim: "order_deserialization_or_compatibility",
      machineVerifiable: true,
      outcome: "PASS",
      severity: "INFO",
      expected:
        "pricing-service v2.41 deserializes order order_1003 (schema 41)",
      observed:
        "pricing-service v2.41 supports orders schema up to 41; order requires schema 41",
      artifact: "order:order_1003",
    }),
  ],
  world_gamma: [
    row({
      id: "evidence_g1",
      stage: "execute",
      kind: "TEST_RESULT",
      source: "branchpoint-world-executor",
      claim: "healthy_checkout",
      machineVerifiable: true,
      outcome: "FAIL",
      severity: "MEDIUM",
      expected: "checkout_error_rate <= 0.020",
      observed: "checkout_error_rate = 0.0700",
    }),
    row({
      id: "evidence_g2",
      stage: "execute",
      kind: "TEST_RESULT",
      source: "branchpoint-world-executor",
      claim: "recovery_slo",
      machineVerifiable: true,
      outcome: "FAIL",
      severity: "MEDIUM",
      expected: "checkout_error_rate <= 0.020 and checkout_p95_ms <= 500",
      observed: "checkout_error_rate = 0.0700, checkout_p95_ms = 960.0",
    }),
    row({
      id: "evidence_g3",
      stage: "execute",
      kind: "DATA_INTEGRITY",
      source: "branchpoint-world-executor",
      claim: "data_integrity",
      machineVerifiable: true,
      outcome: "PASS",
      severity: "INFO",
      expected: "orders store has unique order ids and non-negative amounts",
      observed: "5 order(s), duplicates=False",
    }),
    row({
      id: "evidence_g4",
      stage: "execute",
      kind: "COST",
      source: "branchpoint-world-executor",
      claim: "daily_infra_cost_delta",
      machineVerifiable: true,
      outcome: "PASS",
      severity: "INFO",
      expected: "cost delta is reported, not bounded",
      observed: "daily_infra_cost_usd = 1350.0 (+900.0/day)",
    }),
  ],
};

/**
 * Why a world's evidence list is the length it is. Shown next to the count so
 * the asymmetry reads as a fact about the run rather than a layout accident.
 */
export const EVIDENCE_NOTE: Readonly<Record<string, string>> = {
  world_alpha:
    "α's execution suite passed. It is not listed: derive_verdict() returns at the reproduced counterexample, so nothing after it was consulted.",
  world_beta:
    "β is the only world that was attacked and survived the attack. A counterexample that fails to reproduce is still a recorded result.",
  world_gamma:
    "γ was never attacked. It lost on the comparator's axes, and losing is not a safety question.",
};

export function evidenceFor(worldId: string): readonly EvidenceRow[] {
  return WORLD_EVIDENCE[worldId] ?? [];
}

/**
 * Evidence a world produced that its verdict did not end up resting on.
 *
 * α's execution suite ran and passed, exactly like β's. It is not in α's
 * verdict-bearing list above because `derive_verdict()` returns at the
 * reproduced-counterexample branch, before it looks at anything else — so these
 * three rows are real, recorded, and irrelevant to the outcome.
 *
 * They are kept because hiding them would be the dishonest version of the same
 * point: the argument is *not* "α looked bad", it is "α looked fine and was
 * disqualified anyway". The world explorer offers them behind a disclosure; the
 * protocol page's chain includes them at stage 04, where they actually landed.
 */
export const SUPERSEDED_EVIDENCE: Readonly<
  Record<string, readonly EvidenceRow[]>
> = {
  world_alpha: [
    row({
      id: "evidence_a0a",
      stage: "execute",
      kind: "TEST_RESULT",
      source: "branchpoint-world-executor",
      claim: "healthy_checkout",
      machineVerifiable: true,
      outcome: "PASS",
      severity: "INFO",
      expected: "checkout_error_rate <= 0.020",
      observed: "checkout_error_rate = 0.0180",
    }),
    row({
      id: "evidence_a0b",
      stage: "execute",
      kind: "TEST_RESULT",
      source: "branchpoint-world-executor",
      claim: "recovery_slo",
      machineVerifiable: true,
      outcome: "PASS",
      severity: "INFO",
      expected: "checkout_error_rate <= 0.020 and checkout_p95_ms <= 500",
      observed: "checkout_error_rate = 0.0180, checkout_p95_ms = 190.0",
    }),
    row({
      id: "evidence_a0c",
      stage: "execute",
      kind: "COST",
      source: "branchpoint-world-executor",
      claim: "daily_infra_cost_delta",
      machineVerifiable: true,
      outcome: "PASS",
      severity: "INFO",
      expected: "no additional daily infrastructure spend",
      observed: "daily_infra_cost_usd = 450.0 (unchanged)",
    }),
  ],
};

export function supersededFor(worldId: string): readonly EvidenceRow[] {
  return SUPERSEDED_EVIDENCE[worldId] ?? [];
}

/* ------------------------------------------------------------- the attack */

/**
 * The adversarial phase against world α, as the engine records it.
 *
 * @source `demo/counterexample.py` — the spec language and `reproduce()`
 * @source `domain/worlds/verdicts.py` — `counterexample_vetoes()`
 */
export const ATTACK = {
  sandboxId: "sbx_4a19c72e",
  targetWorldId: "world_alpha",
  execCalls: 3,
  hypotheses: 1,
  hypothesis:
    "Orders created under schema 41 may not deserialize under v2.40.",
  /** What the sandbox is and is not. */
  sandboxNote:
    "A Daytona sandbox, reachable only by DOPPELGÄNGER. It can read a world snapshot and run throwaway code. It cannot write evidence.",
  /** The typed structure — the only thing BRANCHPOINT accepts as veto input. */
  spec: {
    counterexample_type: "COMPATIBILITY",
    target_world_id: "world_alpha",
    operation: "DESERIALIZE_ORDER",
    assertion: { kind: "CHECK_PASSES" },
    setup: { created_under_version: "v2.41", min_schema_version: 41 },
    expected: "pricing-service v2.40 deserializes order order_1003 (schema 41)",
  },
  specNote:
    "No shell, no SQL, no model-supplied Python. Every operation maps to a deterministic demo primitive, and the threshold comes from BRANCHPOINT's own registry — never from the spec.",
  /** `CounterexampleStatus` after replay. */
  status: "REPRODUCED",
  replaySource: "branchpoint-counterexample-replay",
  replayNote:
    "Replayed against world α's own snapshot. Reality was never touched.",
  /** Both halves are required. Either alone vetoes nothing. */
  vetoRule:
    "counterexample.status is REPRODUCED  AND  any(evidence.disqualifies)",
  verdict: "VETOED",
} as const;

/* ------------------------------------------------------ the comparison axes */

export interface ComparisonAxis {
  readonly key: keyof typeof COMPARISON_VALUES.world_beta;
  /** The comparator's own field name — quoted, not paraphrased. */
  readonly field: string;
  readonly explain: string;
}

/**
 * The comparator's real fields. There is no score, no weight and no confidence
 * anywhere in `WorldRanking` — which is the whole point of the section.
 *
 * @source `domain/comparison/models.py` — `WorldRanking`
 */
export const COMPARISON_AXES: readonly ComparisonAxis[] = [
  {
    key: "goal_achieved",
    field: "goal_achieved",
    explain: "Did the world reach the objective it was forked to test?",
  },
  {
    key: "goal_attainment",
    field: "goal_attainment",
    explain:
      "How far toward the objective the world got. A measurement, not a rating.",
  },
  {
    key: "invariants_preserved",
    field: "invariants_preserved",
    explain:
      "Did every declared invariant still hold after the action was applied?",
  },
  {
    key: "regressions_detected",
    field: "regressions_detected",
    explain: "Machine-verifiable checks that failed in this world.",
  },
  {
    key: "blast_radius",
    field: "blast_radius",
    explain: "How many production surfaces the action would touch.",
  },
  {
    key: "reversible",
    field: "reversible",
    explain: "Can the action be undone by a single opposite action?",
  },
  {
    key: "cost_delta",
    field: "cost_delta",
    explain: "Change in daily infrastructure spend, in dollars.",
  },
];

/** Per-world values, formatted for display. @source blueprint §10 wireframe */
export const COMPARISON_VALUES = {
  world_alpha: {
    goal_achieved: "true",
    goal_attainment: "0.94",
    invariants_preserved: "false",
    regressions_detected: "2",
    blast_radius: "3",
    reversible: "true",
    cost_delta: "$0",
  },
  world_beta: {
    goal_achieved: "true",
    goal_attainment: "0.97",
    invariants_preserved: "true",
    regressions_detected: "0",
    blast_radius: "1",
    reversible: "true",
    cost_delta: "$0",
  },
  world_gamma: {
    goal_achieved: "false",
    goal_attainment: "0.58",
    invariants_preserved: "true",
    regressions_detected: "0",
    blast_radius: "2",
    reversible: "true",
    cost_delta: "+$900/day",
  },
} as const;

export const COMPARISON = {
  /** `RejectionReason.ADVERSARIAL_VETO` — the enum's own spelling. */
  rejectionReason: "ADVERSARIAL_VETO",
  rejectedWorldId: "world_alpha",
  rejectedDetail: "disqualified before ranking began",
  ranks: {
    world_alpha: "removed",
    world_beta: "1",
    world_gamma: "2",
  },
  recommendedWorldId: "world_beta",
  /**
   * `ComparisonResult.recommended_world_id` is `None` when the best worlds tie.
   * Worth stating: it is the difference between arithmetic and a scoreboard.
   */
  tieNote:
    "When the leading worlds are deterministically tied, recommended_world_id is null. BRANCHPOINT never invents a winner and never breaks a tie at random.",
  scoreNote:
    "There is no score in WorldRanking. No weights, no confidence, no 0–100 gauge — anywhere in the system.",
} as const;

/* --------------------------------------------------------- the human gate */

/**
 * The approval card's contents.
 *
 * ## Both fingerprints are real
 *
 * They are `sha256(json.dumps(action.model_dump(), sort_keys=True,
 * separators=(",", ":")))` — the exact construction in
 * `domain/actions/models.py:84` — computed over the canonical JSON quoted in
 * `APPROVAL.canonicalJson`, once with `flag_key: "PRICING_V2"` and once with
 * `flag_key: "CHECKOUT_V2"`. A reader can reproduce either in one line.
 *
 * ## This is a local fixture
 *
 * Nothing in the checkpoint section may import the approval client, construct a
 * request, or reach the network. A test asserts no fetch is issued.
 */
export const APPROVAL = {
  runId: RUN_ID,
  worldId: "world_beta",
  worldLabel: "WORLD β",
  actionId: "action_b8e2",
  actionType: "FEATURE_FLAG_DISABLE",
  actionName: "SET_FEATURE_FLAG",
  target: "pricing-service",
  riskClass: "MEDIUM",
  reversible: true,
  reviewedFlagKey: "PRICING_V2",
  mutatedFlagKey: "CHECKOUT_V2",
  from: "true",
  to: "false",
  /** sha256 over the canonical action JSON, `flag_key = PRICING_V2`. */
  reviewedFingerprint:
    "555150ab72d353be7951caa4899e23e6645d4f446687c587a91e7b53ed966551",
  /** The same action with one parameter changed. Nothing else differs. */
  mutatedFingerprint:
    "6dca77350f38e65e63ebc5d3c39049b58226f1987ca120d712f06d394be2fce9",
  canonicalJson:
    '{"action_id":"action_b8e2","action_type":"FEATURE_FLAG_DISABLE",…,"parameters":{"enabled":false,"flag_key":"PRICING_V2"},…}',
  /**
   * The five bindings an approval carries.
   *
   * @source `domain/approvals/rules.py` — `build_approval_request()` and
   *   `assert_commit_allowed()`
   */
  bindings: [
    { key: "goal", label: "goal achieved in this world" },
    { key: "invariants", label: "all declared invariants passed" },
    { key: "counterexamples", label: "no reproduced counterexamples" },
    { key: "recommendation", label: "deterministic comparator recommendation" },
    { key: "fingerprint", label: "action fingerprint bound" },
  ],
  /** Only the last binding depends on the action's content. */
  fingerprintBindingKey: "fingerprint",
  invalidatedLabel: "APPROVAL INVALIDATED",
  invalidatedNote:
    "The action changed after it was reviewed, so the fingerprint no longer matches. assert_commit_allowed() would refuse this commit — an approval is not transferable.",
} as const;

/* ---------------------------------------------------------- commit + verify */

export interface CommitGate {
  readonly key: string;
  readonly label: string;
  readonly detail: string;
}

/**
 * The four independent gates a commit passes, in order.
 *
 * @source `domain/approvals/rules.py:assert_commit_allowed`
 * @source `infrastructure/demo/capability.py`
 */
export const COMMIT_GATES: readonly CommitGate[] = [
  {
    key: "approval_granted",
    label: "approval granted, run is APPROVED",
    detail: "commit requires approval",
  },
  {
    key: "world_bound",
    label: "approval binds the selected world",
    detail: "run.selected_world_id == approval.selected_world_id",
  },
  {
    key: "action_bound",
    label: "approval binds the exact action id",
    detail: "world.candidate_action.action_id == approval.action_id",
  },
  {
    key: "fingerprint_bound",
    label: "action content unchanged since approval",
    detail: "candidate_action.fingerprint() == approval.action_fingerprint",
  },
];

export const COMMIT = {
  capabilityNote:
    "A one-time capability is issued for exactly this run, world, action and fingerprint, and can be spent once. A caller who reaches the mutation path directly still cannot use it twice.",
  mutation: {
    key: "PRICING_V2",
    from: "true",
    to: "false",
    service: "pricing-service",
  },
  kicker:
    "The mutation was issued. That is all a commit proves — which is why it is not the last stage.",
} as const;

export interface VerificationPair {
  readonly key: string;
  readonly expected: string;
  readonly actual: string;
}

/**
 * The independent re-read. It does not consult the commit's own report.
 *
 * @source `demo/metrics.py` with `PRICING_V2` disabled — the β numbers
 */
export const VERIFICATION: readonly VerificationPair[] = [
  { key: "checkout_error_rate", expected: "1.4%", actual: "1.4%" },
  { key: "checkout_p95_ms", expected: "320ms", actual: "320ms" },
  { key: "orders_schema_version", expected: "41", actual: "41" },
];

export const VERIFY_NOTE =
  "Read from production a second time, by a component that never saw the commit's report. Only when expected and actual agree does the run become SUCCEEDED.";

/* --------------------------------------------------- the authority topology */

export interface ArchitectureNode {
  readonly id: string;
  readonly label: string;
  readonly band: AuthorityBand;
  /** What it does. */
  readonly does: string;
  /** What authority it holds. */
  readonly holds: string;
  /** What authority it does NOT hold. The point of the section. */
  readonly lacks: string;
  /** One quantified fact, where the repo has one. */
  readonly fact?: string;
}

/** @source blueprint §8/§13, `trueforge/README.md` tool inventory */
export const ARCHITECTURE_NODES: readonly ArchitectureNode[] = [
  {
    id: "trueforge",
    label: "TRUEFORGE",
    band: "EXPLORATORY",
    does: "Hosts the agents, their sessions, their planning and the MCP tool surface.",
    holds: "The right to call tools BRANCHPOINT exposes to it.",
    lacks: "It cannot decide anything. Running an agent is not evidence.",
    fact: "17 MCP tools · 13 read-only · 4 destructive, every one annotated.",
  },
  {
    id: "doppelganger",
    label: "DOPPELGÄNGER",
    band: "EXPLORATORY",
    does: "Attacks a surviving world: reads its snapshot, runs throwaway code in a Daytona sandbox, and submits one typed CounterexampleSpec.",
    holds:
      "The right to choose which declared invariant to test, and to be heard.",
    lacks:
      "It cannot veto, cannot set a threshold, and cannot mark anything REPRODUCED. An adversary asserting a reproduction with only sandbox output behind it is recorded and ignored — never obeyed, and never able to halt a run either.",
    fact: "Sandbox access: DOPPELGÄNGER only.",
  },
  {
    id: "branchpoint",
    label: "BRANCHPOINT",
    band: "DETERMINISTIC",
    does: "Plans, forks, executes, replays counterexamples and compares worlds.",
    holds:
      "Evidence authority. It is the only component that may write machine_verifiable evidence, veto a world, and rank the survivors.",
    lacks:
      "It cannot grant permission, and it cannot change reality. Its recommendation is a sentence, not an instruction.",
    fact: "A veto needs REPRODUCED status AND disqualifying evidence.",
  },
  {
    id: "human",
    label: "HUMAN",
    band: "PERMISSION",
    does: "Reviews the bound action and either approves it or rejects it.",
    holds: "Permission — for exactly one action, identified by content hash.",
    lacks:
      "Cannot invent an action, cannot override a veto, and cannot approve an action that changed after review.",
    fact: "One approval per run.",
  },
  {
    id: "commit",
    label: "COMMIT OPERATOR",
    band: "DETERMINISTIC",
    does: "Re-checks four independent gates, spends a one-time capability, and issues the mutation.",
    holds: "The ability to mutate reality — once, for one bound action.",
    lacks:
      "It cannot decide that a mutation was correct. Issuing a change is not evidence that the change worked.",
    fact: "4 independent gates · single-use capability token.",
  },
  {
    id: "verifier",
    label: "VERIFIER",
    band: "DETERMINISTIC",
    does: "Independently re-reads production and compares expected against actual.",
    holds: "The right to declare a run SUCCEEDED — or not.",
    lacks:
      "It cannot commit, cannot approve, and does not read the commit's own report.",
    fact: "3 expected/actual pairs, re-read from reality.",
  },
];

export function architectureNode(id: string): ArchitectureNode {
  const found = ARCHITECTURE_NODES.find((node) => node.id === id);
  if (found === undefined) throw new Error(`unknown architecture node ${id}`);
  return found;
}

/* ------------------------------------------------------- the evidence chain */

/**
 * One run's evidence, in the order the run produced it.
 *
 * This is the spine of `/how-it-works`. The page shows a single run advancing
 * through nine stages, and the chain **only ever grows**: at stage 09 the
 * inspector still holds the sandbox probe recorded at stage 05. Nothing is
 * cleared, replaced or re-ordered when the reader moves on, because the whole
 * point of the page is that a conclusion can be traced back to the observation
 * that produced it.
 *
 * The world rows are the same rows the landing page's explorer shows — the same
 * module, not a copy — with their world attached, plus the rows the later
 * stages add on their own behalf.
 */
export interface ChainRow extends EvidenceRow {
  /** Which world it belongs to, where it belongs to one. */
  readonly worldId?: string;
  readonly worldGlyph?: string;
}

function chainFor(worldId: string, stage: StageId): ChainRow[] {
  const world = worldById(worldId);
  return [...evidenceFor(worldId), ...supersededFor(worldId)]
    .filter((entry) => entry.stage === stage)
    .map((entry) => ({ ...entry, worldId, worldGlyph: world?.glyph }));
}

export const PROTOCOL_EVIDENCE: readonly ChainRow[] = [
  // 04 EXECUTE — every world's own suite, in world order.
  ...chainFor("world_alpha", "execute"),
  ...chainFor("world_beta", "execute"),
  ...chainFor("world_gamma", "execute"),

  // 05 ATTACK — act one is exploratory, act two is the replay.
  ...chainFor("world_alpha", "attack"),
  ...chainFor("world_beta", "attack"),

  // 06 COMPARE — the comparison attaches its own evidence ids.
  row({
    id: "evidence_c1",
    stage: "compare",
    kind: "POLICY",
    source: "branchpoint-comparator",
    claim: "world_alpha rejected: ADVERSARIAL_VETO",
    machineVerifiable: true,
    outcome: "PASS",
    severity: "INFO",
    expected: "vetoed worlds are removed before ranking",
    observed: "eligible = [world_beta, world_gamma]; recommended = world_beta",
  }),

  // 07 APPROVE adds nothing. Approval is permission, not evidence.

  // 08 COMMIT — the receipt is a record that a mutation was issued.
  row({
    id: "evidence_m1",
    stage: "commit",
    kind: "EXECUTION_RESULT",
    source: "branchpoint-commit-operator",
    claim: "commit receipt",
    machineVerifiable: true,
    outcome: "PASS",
    severity: "INFO",
    expected: "PRICING_V2 set to false under a single-use capability",
    observed: "4 gates passed; capability spent; mutation issued",
  }),

  // 09 VERIFY — the independent re-read.
  ...VERIFICATION.map((pair) =>
    row({
      id: `evidence_v_${pair.key}`,
      stage: "verify" as StageId,
      kind: "VERIFICATION" as EvidenceKindName,
      source: "branchpoint-verifier",
      claim: pair.key,
      machineVerifiable: true,
      outcome: "PASS" as const,
      severity: "INFO" as Severity,
      expected: pair.expected,
      observed: pair.actual,
    }),
  ),
];

/**
 * The chain as it stands at the end of a stage. Never a filter that *removes* —
 * always a prefix, which is what makes "evidence accumulates" true by
 * construction rather than by discipline.
 */
export function evidenceThrough(stage: StageId): readonly ChainRow[] {
  const limit = PROTOCOL_STAGES.findIndex((entry) => entry.id === stage);
  const order = (id: StageId) =>
    PROTOCOL_STAGES.findIndex((entry) => entry.id === id);
  return PROTOCOL_EVIDENCE.filter((entry) => order(entry.stage) <= limit);
}
