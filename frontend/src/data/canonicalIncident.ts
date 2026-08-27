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
