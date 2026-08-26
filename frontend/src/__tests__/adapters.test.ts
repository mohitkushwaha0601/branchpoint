/**
 * The adapter layer: does the UI's model say only what the backend said?
 *
 * The load-bearing assertion in this file is that nothing from `heroRun` can
 * reach a live run. The fixture is deliberately rich, so any leak would show up
 * as a suspiciously complete live world.
 */

import { describe, expect, it } from "vitest";

import { adaptRun, adaptRunSummaries, stagesFor } from "../adapters/runAdapter";
import { adaptEvents } from "../adapters/eventAdapter";
import { heroRun } from "../data/heroRun";
import type { RunStatusDto } from "../api/types";
import {
  comparisonDto,
  demoStateDto,
  eventsDto,
  runDto,
  worldsDto,
  youngRunDto,
} from "./apiFixtures";

describe("worlds", () => {
  it("adapts every world the backend reported", () => {
    const run = adaptRun({ run: runDto(), worlds: worldsDto(), comparison: comparisonDto() });

    expect(run.worlds.map((world) => world.worldId)).toEqual([
      "world_alpha",
      "world_beta",
      "world_gamma",
    ]);
    expect(run.worlds.map((world) => world.label)).toEqual([
      "WORLD α",
      "WORLD β",
      "WORLD γ",
    ]);
    expect(run.worlds.map((world) => world.verdict)).toEqual([
      "VETOED",
      "SURVIVED",
      "SURVIVED",
    ]);
  });

  it("does not assume three worlds", () => {
    const two = worldsDto();
    two.worlds = two.worlds.slice(0, 2);
    const dto = runDto();
    dto.worlds = dto.worlds.slice(0, 2);

    const run = adaptRun({ run: dto, worlds: two });

    expect(run.worlds).toHaveLength(2);
  });

  it("marks a world with no verdict as pending, not inconclusive", () => {
    const dto = runDto({ status: "EXECUTING_WORLDS", comparison: null, approval: null });
    dto.worlds = dto.worlds.map((world) => ({
      ...world,
      status: "EXECUTING" as const,
      verdict: null,
      verdict_reason: "",
    }));

    const run = adaptRun({ run: dto });

    expect(run.worlds.map((world) => world.verdict)).toEqual([
      "PENDING",
      "PENDING",
      "PENDING",
    ]);
  });

  it("derives the replay row's failure from the reproduced counterexample", () => {
    const run = adaptRun({ run: runDto(), worlds: worldsDto(), comparison: comparisonDto() });

    const alpha = run.worlds[0]!;
    const replay = alpha.pipeline.find((stage) => stage.label === "BRANCHPOINT replay");
    expect(replay?.status).toBe("failed");
    expect(alpha.reproducedCounterexamples).toBe(1);

    const beta = run.worlds[1]!;
    expect(
      beta.pipeline.find((stage) => stage.label === "BRANCHPOINT replay")?.status,
    ).toBe("passed");
  });

  it("takes the recommendation from the backend's comparison, not from a guess", () => {
    const run = adaptRun({ run: runDto(), worlds: worldsDto(), comparison: comparisonDto() });

    expect(run.comparison.recommendedWorldId).toBe("world_beta");
    expect(run.worlds.filter((world) => world.recommended).map((w) => w.worldId)).toEqual(
      ["world_beta"],
    );
  });
});

describe("no fixture data leaks into a live run", () => {
  const live = adaptRun({
    run: runDto(),
    worlds: worldsDto(),
    comparison: comparisonDto(),
    events: eventsDto().events,
    demo: demoStateDto(),
  });

  it("marks the run as live", () => {
    expect(live.source).toBe("live");
    expect(heroRun.source).toBe("fixture");
  });

  it("carries no evidence rows the API did not send", () => {
    // The list endpoint carries counts, not rows. Rows come from the world
    // detail endpoint, which the Inspector fetches for the selected world.
    for (const world of live.worlds) {
      expect(world.evidence).toEqual([]);
    }
    // ...while the counts that *are* real stay real.
    expect(live.worlds.map((world) => world.evidenceCount)).toEqual([3, 6, 4]);
  });

  it("carries no hypothesis text the API did not send", () => {
    for (const world of live.worlds) {
      expect(world.counterexample.hypothesis).toBe("");
    }
    // The fixture's text must not appear anywhere in the live run.
    const serialised = JSON.stringify(live);
    expect(serialised).not.toContain("may not deserialize under v2.40");
    expect(serialised).not.toContain("sbx_");
  });

  it("carries no invented action parameters or durations", () => {
    for (const world of live.worlds) {
      expect(world.action.parameter).toBe("");
      expect(world.action.from).toBe("");
      expect(world.action.to).toBe("");
      expect(world.action.reversible).toBeNull();
      for (const stage of world.pipeline) expect(stage.duration).toBe("");
    }
  });

  it("fills the fingerprint only for the world the approval is bound to", () => {
    const bound = live.worlds.find((world) => world.worldId === "world_beta");
    expect(bound?.action.fingerprint).toBe("3d7a1e05c94b2f6d");
    expect(live.worlds.find((w) => w.worldId === "world_alpha")?.action.fingerprint).toBe(
      "",
    );
  });

  it("renders nothing at all when the backend has produced nothing", () => {
    const empty = adaptRun({ run: youngRunDto("CREATED") });

    expect(empty.worlds).toEqual([]);
    expect(empty.events).toEqual([]);
    expect(empty.reality.facts).toEqual([]);
    expect(empty.incident.metrics).toEqual([]);
    expect(empty.comparison.recommendedWorldId).toBeNull();
    expect(empty.approval.worldId).toBe("");
  });
});

describe("reality", () => {
  it("reads the header from the reality endpoint", () => {
    const run = adaptRun({ run: runDto(), demo: demoStateDto(true) });

    expect(run.incident.metrics).toEqual([
      { label: "Checkout error", value: "41.3%" },
      { label: "p95 latency", value: "4.8s" },
      { label: "Affected users", value: "12.4k" },
    ]);
    expect(run.reality.facts).toEqual([
      { label: "Pricing version", value: "v2.41" },
      { label: "PRICING_V2", value: "ON" },
      { label: "Replicas", value: "4" },
      { label: "Orders schema", value: "41" },
    ]);
  });

  it("follows reality after a commit turns the flag off", () => {
    const run = adaptRun({
      run: runDto({
        status: "SUCCEEDED",
        commit_status: "SUCCEEDED",
        verification_status: "PASSED",
      }),
      demo: demoStateDto(false),
    });

    expect(run.reality.facts).toContainEqual({ label: "PRICING_V2", value: "OFF" });
    expect(run.incident.metrics[0]).toEqual({
      label: "Checkout error",
      value: "1.4%",
    });
    expect(run.realityCommitted).toBe(true);
  });

  it("does not call reality changed until verification confirms it", () => {
    // Committed but not yet verified: the mutation was issued, and BRANCHPOINT
    // has not yet re-read reality to confirm it reads that way.
    const run = adaptRun({
      run: runDto({ status: "VERIFYING", commit_status: "SUCCEEDED" }),
      demo: demoStateDto(false),
    });

    expect(run.realityCommitted).toBe(false);
  });
});

describe("stage rail", () => {
  const stageStatus = (dto: Parameters<typeof stagesFor>[0], id: string) =>
    stagesFor(dto).find((stage) => stage.id === id)?.status;

  it("marks nothing started for a freshly created run", () => {
    const stages = stagesFor(youngRunDto("CREATED"));
    expect(stages.every((stage) => stage.status === "pending")).toBe(true);
  });

  const cases: [RunStatusDto, string][] = [
    ["OBSERVING", "OBSERVE"],
    ["PLANNING", "PLAN"],
    ["FORKING", "FORK"],
    ["EXECUTING_WORLDS", "EXECUTE"],
    ["ADVERSARIAL_TESTING", "ATTACK"],
    ["COMPARING", "COMPARE"],
    ["AWAITING_APPROVAL", "APPROVE"],
    ["COMMITTING", "COMMIT"],
    ["VERIFYING", "VERIFY"],
  ];

  it.each(cases)("makes %s the current stage %s", (status, stageId) => {
    const stages = stagesFor(runDto({ status }));
    expect(stages.find((stage) => stage.id === stageId)?.status).toBe("current");
    expect(stages.filter((stage) => stage.status === "current")).toHaveLength(1);
  });

  it("completes every stage once a run succeeds", () => {
    const stages = stagesFor(runDto({ status: "SUCCEEDED" }));
    expect(stages.every((stage) => stage.status === "complete")).toBe(true);
  });

  it("keeps completed stages and marks where a failure stopped", () => {
    // Failed after comparing but before approval was requested.
    const dto = runDto({ status: "FAILED", approval: null, failure_reason: "boom" });
    expect(stageStatus(dto, "OBSERVE")).toBe("complete");
    expect(stageStatus(dto, "ATTACK")).toBe("complete");
    expect(stageStatus(dto, "COMPARE")).toBe("failed");
    expect(stageStatus(dto, "APPROVE")).toBe("pending");
  });

  it("marks an early failure at the stage it actually reached", () => {
    const dto = runDto({
      status: "FAILED",
      candidate_action_ids: [],
      worlds: [],
      comparison: null,
      approval: null,
    });
    expect(stageStatus(dto, "OBSERVE")).toBe("failed");
    expect(stageStatus(dto, "PLAN")).toBe("pending");
  });

  it("never runs ahead of the backend", () => {
    const stages = stagesFor(runDto({ status: "EXECUTING_WORLDS" }));
    for (const id of ["ATTACK", "COMPARE", "APPROVE", "COMMIT", "VERIFY"]) {
      expect(stages.find((stage) => stage.id === id)?.status).toBe("pending");
    }
  });
});

describe("events", () => {
  it("adapts real events without adding any", () => {
    const events = adaptEvents(eventsDto().events);

    expect(events).toHaveLength(5);
    expect(events.map((event) => event.message)).toEqual([
      "run opened for incident incident_1",
      "3 candidate action(s) proposed",
      "counterexample reproduced against world_alpha",
      "world_alpha VETOED",
      "approval requested for world world_beta",
    ]);
  });

  it("keeps the world link so an event can select its world", () => {
    const events = adaptEvents(eventsDto().events);

    expect(events[0]?.worldId).toBeUndefined();
    expect(events[3]?.worldId).toBe("world_alpha");
  });

  it("files replay events under REPLAY and adversary events under DOPPEL", () => {
    const events = adaptEvents(eventsDto().events);

    expect(events[2]?.channel).toBe("REPLAY");
    expect(
      adaptEvents([
        {
          ...eventsDto().events[0]!,
          event_type: "SANDBOX_TEST_COMPLETED",
        },
      ])[0]?.channel,
    ).toBe("DOPPEL");
  });
});

describe("run summaries", () => {
  it("adapts the sidebar rows from the backend list", () => {
    const summaries = adaptRunSummaries([runDto()]);

    expect(summaries).toEqual([
      {
        runId: "run_dbfa98c87f06",
        title: "Checkout Regression",
        status: "AWAITING_APPROVAL",
        timeLabel: "2m 14s",
      },
    ]);
  });
});
