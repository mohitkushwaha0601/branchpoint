/**
 * Guards on the canonical incident.
 *
 * Phase 2A found that the offline fixture (`heroRun.ts`) disagrees with the live
 * demo engine for worlds α and γ. These tests pin the engine's values so the
 * corrections cannot quietly regress — every expectation below was produced by
 * running `compute_metrics()` against `checkout_regression.json`, not by copying
 * a number from a document.
 *
 * @see docs/LANDING_INTERACTION_BLUEPRINT.md §2
 */

import { describe, expect, it } from "vitest";

import {
  DECLARED_BOUNDS,
  INITIAL_REALITY,
  WITNESS_ORDER,
  WORLDS,
  WORLD_ALPHA,
  WORLD_BETA,
  WORLD_GAMMA,
  disqualifyingChecks,
  nonDisqualifyingFailures,
  worldById,
} from "../data/canonicalIncident";

describe("initial reality", () => {
  it("is the regressed production the run actually observes", () => {
    expect(INITIAL_REALITY.version).toBe("v2.41");
    expect(INITIAL_REALITY.previousVersion).toBe("v2.40");
    expect(INITIAL_REALITY.flagEnabled).toBe(true);
    expect(INITIAL_REALITY.replicas).toBe(4);
    expect(INITIAL_REALITY.ordersSchemaVersion).toBe(41);
  });

  it("carries the engine's headline numbers", () => {
    expect(INITIAL_REALITY.metrics.errorRate.raw).toBe(0.413);
    expect(INITIAL_REALITY.metrics.p95.raw).toBe(4800);
    // round(19_370 × 0.413). The offline fixture says 12.4k; the engine does not.
    expect(INITIAL_REALITY.metrics.affectedUsers.raw).toBe(8000);
    // 4 replicas × $112.50
    expect(INITIAL_REALITY.metrics.dailyCost.raw).toBe(450);
  });

  it("is regressed because v2.41 is deployed and the flag is on", () => {
    expect(INITIAL_REALITY.regressionActive).toBe(true);
  });
});

describe("world α — the rollback", () => {
  it("recovers the headline metrics to the engine's values", () => {
    // BYPASSED_ERROR_RATE_BY_VERSION["v2.40"] = 0.018 — NOT the fixture's 2.1%
    expect(WORLD_ALPHA.metrics.errorRate.raw).toBe(0.018);
    expect(WORLD_ALPHA.metrics.errorRate.value).toBe("1.8%");
    // BYPASSED_P95_MS_BY_VERSION["v2.40"] = 190.0 — NOT the fixture's 610ms
    expect(WORLD_ALPHA.metrics.p95.raw).toBe(190);
    expect(WORLD_ALPHA.metrics.p95.value).toBe("190ms");
  });

  it("is the fastest world in the run — which is the whole point", () => {
    const others = WORLDS.filter((w) => w.id !== WORLD_ALPHA.id);
    for (const world of others) {
      expect(WORLD_ALPHA.metrics.p95.raw).toBeLessThan(world.metrics.p95.raw);
    }
  });

  it("meets every declared bound and is vetoed anyway", () => {
    expect(WORLD_ALPHA.metrics.errorRate.raw).toBeLessThanOrEqual(
      DECLARED_BOUNDS.recoveryErrorRate,
    );
    expect(WORLD_ALPHA.metrics.p95.raw).toBeLessThanOrEqual(
      DECLARED_BOUNDS.recoveryP95Ms,
    );
    expect(WORLD_ALPHA.verdict).toBe("VETOED");
  });

  it("is disqualified by exactly the two critical compatibility checks", () => {
    const critical = disqualifyingChecks(WORLD_ALPHA);
    expect(critical.map((c) => c.name)).toEqual([
      "order_deserialization_or_compatibility",
      "payment_retry",
    ]);
    for (const check of critical) {
      expect(check.passed).toBe(false);
      expect(check.severity).toBe("CRITICAL");
      // Only machine-verifiable evidence can disqualify.
      expect(check.authority).toBe("VERIFIED");
    }
  });

  it("degrades the payment key on the witness order", () => {
    const retry = WORLD_ALPHA.checks.find((c) => c.name === "payment_retry");
    expect(retry?.expected).toContain(WITNESS_ORDER.originalKey);
    expect(retry?.observed).toContain(WITNESS_ORDER.degradedKey);
    expect(retry?.artifact).toBe(`order:${WITNESS_ORDER.orderId}`);
  });
});

describe("world β — the flag", () => {
  it("carries the engine's values, which the fixture happens to agree with", () => {
    expect(WORLD_BETA.metrics.errorRate.raw).toBe(0.014);
    expect(WORLD_BETA.metrics.p95.raw).toBe(320);
    expect(WORLD_BETA.metrics.costDelta.raw).toBe(0);
  });

  it("survives with nothing failing and is the recommendation", () => {
    expect(WORLD_BETA.checks.every((c) => c.passed)).toBe(true);
    expect(WORLD_BETA.verdict).toBe("SURVIVED");
    expect(WORLD_BETA.selection).toBe("RECOMMENDED");
  });

  it("is the only recommended world", () => {
    const recommended = WORLDS.filter((w) => w.selection === "RECOMMENDED");
    expect(recommended).toHaveLength(1);
    expect(recommended[0]?.id).toBe("world_beta");
  });
});

describe("world γ — the scale", () => {
  it("hits the engine's floors, not the fixture's invented numbers", () => {
    // max(ERROR_RATE_FLOOR 0.07, 0.413 − 0.043×8) — NOT the fixture's 16.2%
    expect(WORLD_GAMMA.metrics.errorRate.raw).toBe(0.07);
    expect(WORLD_GAMMA.metrics.errorRate.value).toBe("7.0%");
    // max(LATENCY_FLOOR_MS 960, 4800 − 480×8) — NOT the fixture's 1.9s
    expect(WORLD_GAMMA.metrics.p95.raw).toBe(960);
    expect(WORLD_GAMMA.metrics.p95.value).toBe("960ms");
    // (12 − 4) × $112.50 — NOT the fixture's 1840
    expect(WORLD_GAMMA.metrics.costDelta.raw).toBe(900);
  });

  it("hits a floor because the root cause is still running", () => {
    // This is the reason the floor exists, and the reason the section works.
    expect(WORLD_GAMMA.regressionActive).toBe(true);
    expect(WORLD_ALPHA.regressionActive).toBe(false);
    expect(WORLD_BETA.regressionActive).toBe(false);
  });

  it("misses the goal but is still safe — losing is not a veto", () => {
    const failures = nonDisqualifyingFailures(WORLD_GAMMA);
    expect(failures.map((c) => c.name)).toEqual([
      "healthy_checkout",
      "recovery_slo",
    ]);
    // MEDIUM is not CRITICAL and TEST_RESULT is not in the disqualifying kinds,
    // so a world can fail its goal and still survive.
    for (const check of failures) expect(check.severity).toBe("MEDIUM");
    expect(disqualifyingChecks(WORLD_GAMMA)).toHaveLength(0);
    expect(WORLD_GAMMA.verdict).toBe("SURVIVED");
    expect(WORLD_GAMMA.selection).toBe("NOT_SELECTED");
  });
});

describe("stale fixture values never appear", () => {
  /**
   * The offline fixture's α/γ numbers, plus the prompt's original guesses. If
   * any of these turns up in the canonical module, a correction has regressed.
   */
  const STALE = [
    "2.1%",
    "610ms",
    "16.2%",
    "1.9s",
    "1840",
    "12.4k",
    "12400",
    "8a91",
  ];

  it("is free of every superseded value", () => {
    const serialised = JSON.stringify({
      INITIAL_REALITY,
      WORLDS,
      WITNESS_ORDER,
    });
    for (const value of STALE) {
      expect(serialised).not.toContain(value);
    }
  });

  it("exposes exactly three worlds, keyed by the domain's ids", () => {
    expect(WORLDS.map((w) => w.id)).toEqual([
      "world_alpha",
      "world_beta",
      "world_gamma",
    ]);
    expect(worldById("world_beta")).toBe(WORLD_BETA);
    expect(worldById("nope")).toBeUndefined();
  });
});
