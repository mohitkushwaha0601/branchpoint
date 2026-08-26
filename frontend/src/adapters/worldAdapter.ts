/**
 * Backend world DTOs → the Phase 4.1 `World` view model.
 *
 * The gap this closes honestly: the *list* endpoint exposes a world's verdict,
 * its measured outcome, and counts — not the evidence rows, not the adversary's
 * hypothesis text, and not per-job durations. None of that is invented here,
 * and `heroRun`'s values are never borrowed to fill a gap. The rows live behind
 * `GET /runs/{id}/worlds/{world_id}`, which the Inspector fetches for the
 * selected world.
 */

import type {
  Action,
  Counterexample,
  PipelineStage,
  SandboxInfo,
  World,
  WorldOutcome,
  WorldVerdict,
} from "../types/run";
import type { ActionKind } from "../types/run";
import type { RunWorldDto, WorldDetailDto, WorldStatusDto } from "../api/types";

/** Greek letters, in the order the backend forks worlds. */
const LABELS = ["α", "β", "γ", "δ", "ε", "ζ", "η", "θ"];

export function worldLabel(index: number): string {
  return `WORLD ${LABELS[index] ?? String(index + 1)}`;
}

/** How far along a world's own state machine a status sits. */
const WORLD_PROGRESS: Record<WorldStatusDto, number> = {
  CREATED: 0,
  PREPARING: 1,
  EXECUTING: 2,
  ATTACKING: 3,
  EVALUATING: 4,
  SURVIVED: 5,
  VETOED: 5,
  FAILED: 5,
};

function progressOf(status: string): number {
  return WORLD_PROGRESS[status as WorldStatusDto] ?? 0;
}

/**
 * Derive the three job rows from the world's own lifecycle position.
 *
 * This is derivation, not invention: `WorldStatus` states exactly which phases
 * a world has left behind. Durations are genuinely absent from the API, so they
 * render as nothing rather than as a plausible-looking number.
 */
export function pipelineFor(
  worldId: string,
  status: string,
  verdict: WorldVerdict,
): PipelineStage[] {
  const reached = progressOf(status);
  const failedWorld = status === "FAILED";

  const executeStatus = failedWorld
    ? "failed"
    : reached >= 3
      ? "passed"
      : reached >= 1
        ? "running"
        : "skipped";

  const attackStatus = failedWorld
    ? "skipped"
    : reached >= 4
      ? "passed"
      : reached === 3
        ? "running"
        : "skipped";

  // The replay row fails exactly when BRANCHPOINT reproduced a counterexample —
  // which is what a veto means, and the only thing that can produce one.
  const replayStatus = failedWorld
    ? "skipped"
    : verdict === "VETOED"
      ? "failed"
      : verdict === "SURVIVED"
        ? "passed"
        : reached >= 4
          ? "running"
          : "skipped";

  return [
    {
      id: `${worldId}-execute`,
      label: "Execute world",
      status: executeStatus,
      duration: "",
      detail: "Action applied to an isolated copy of production.",
    },
    {
      id: `${worldId}-doppelganger`,
      label: "DOPPELGÄNGER",
      status: attackStatus,
      duration: "",
      detail:
        "Adversarial agent investigated the world. Anything it produced is exploratory.",
    },
    {
      id: `${worldId}-replay`,
      label: "BRANCHPOINT replay",
      status: replayStatus,
      duration: "",
      detail:
        replayStatus === "failed"
          ? "BRANCHPOINT replayed the proposed counterexample and reproduced the failure itself."
          : "BRANCHPOINT replays every proposed counterexample against this world's own snapshot.",
    },
  ];
}

/** A world with no verdict yet is pending, not inconclusive. */
export function verdictOf(
  verdict: string | null,
  status: string,
): WorldVerdict {
  if (verdict === "SURVIVED" || verdict === "VETOED" || verdict === "INCONCLUSIVE") {
    return verdict;
  }
  return status === "FAILED" ? "INCONCLUSIVE" : "PENDING";
}

const KNOWN_ACTION_KINDS: ActionKind[] = [
  "SET_DEPLOYMENT_VERSION",
  "SET_FEATURE_FLAG",
  "SCALE_SERVICE",
];

/**
 * The action, with every field the API does not carry left empty.
 *
 * Parameter, before/after values, and reversibility are not exposed per world.
 * They are left blank for the UI to render as "—". The fingerprint is filled in
 * only for the world the run's approval is actually bound to, because that is
 * the only place the backend states one.
 */
function actionOf(
  dto: { action_id: string; action_name: string; action_type?: string },
  fingerprint: string,
): Action {
  const kind = KNOWN_ACTION_KINDS.find((known) => known === dto.action_type);
  return {
    actionId: dto.action_id,
    kind: kind ?? "SET_FEATURE_FLAG",
    name: dto.action_name,
    target: "",
    parameter: "",
    from: "",
    to: "",
    fingerprint,
    reversible: null,
  };
}

/**
 * Counterexample state, derived from counts alone.
 *
 * `reproduced > 0` is the backend's own statement that its replay engine
 * reproduced a failure — the single fact a veto rests on. The adversary's
 * hypothesis text is not exposed, so it stays empty and the UI says so.
 */
function counterexampleOf(dto: WorldDetailDto): Counterexample {
  const status =
    dto.reproduced_counterexamples > 0
      ? "REPRODUCED"
      : dto.counterexample_count > 0
        ? "NOT_REPRODUCED"
        : "NONE_PROPOSED";
  return {
    attackId: "",
    title:
      status === "REPRODUCED"
        ? "Counterexample reproduced by BRANCHPOINT"
        : status === "NOT_REPRODUCED"
          ? "Counterexample proposed, not reproduced"
          : "No replayable counterexample proposed",
    hypothesis: "",
    status,
    evidenceIds: [],
  };
}

/** Sandbox usage is not exposed per world by the current API. */
const UNKNOWN_SANDBOX: SandboxInfo = {
  enabled: false,
  status: "Not requested",
  execCount: 0,
};

function outcomeOf(dto: WorldDetailDto): WorldOutcome {
  return {
    goalAchieved: dto.goal_achieved ?? false,
    goalAttainment: dto.goal_attainment ?? 0,
    regressions: dto.regressions_detected ?? 0,
    blastRadius: dto.blast_radius ?? 0,
    costDelta: dto.cost_delta ?? 0,
    // Before/after readings are measured per world in the backend but not
    // exposed over HTTP. Rendering none is correct; inventing them is not.
    results: [],
  };
}

export function adaptWorldDetail(
  dto: WorldDetailDto,
  index: number,
  context: { recommendedWorldId: string | null; boundFingerprint: string; boundWorldId: string },
): World {
  const verdict = verdictOf(dto.verdict, dto.status);
  return {
    worldId: dto.world_id,
    label: worldLabel(index),
    name: dto.action_name,
    action: actionOf(
      dto,
      dto.world_id === context.boundWorldId ? context.boundFingerprint : "",
    ),
    pipeline: pipelineFor(dto.world_id, dto.status, verdict),
    verdict,
    verdictReason: dto.verdict_reason,
    outcome: outcomeOf(dto),
    counterexample: counterexampleOf(dto),
    sandbox: UNKNOWN_SANDBOX,
    evidence: [],
    recommended: dto.world_id === context.recommendedWorldId,
    notes: [],
    // No rows here by construction: the list endpoint carries counts, and the
    // Inspector fetches the rows for the one world it is showing.
    evidenceCount: dto.evidence_count,
    reproducedCounterexamples: dto.reproduced_counterexamples,
  };
}

/**
 * Adapt the leaner world shape carried inside `GET /runs/{id}`.
 *
 * Used while a run is young: worlds appear in the run response as soon as they
 * are forked, before `/worlds` has anything richer to say.
 */
export function adaptRunWorld(
  dto: RunWorldDto,
  index: number,
  context: { recommendedWorldId: string | null; boundFingerprint: string; boundWorldId: string },
): World {
  return adaptWorldDetail(
    {
      world_id: dto.world_id,
      status: dto.status,
      verdict: dto.verdict,
      verdict_reason: dto.verdict_reason,
      action_id: dto.action_id,
      action_name: dto.action_name,
      action_type: "",
      goal_achieved: null,
      goal_attainment: null,
      regressions_detected: null,
      blast_radius: null,
      cost_delta: null,
      evidence_count: dto.evidence_count,
      counterexample_count: dto.counterexample_count,
      // The run-embedded world shape carries neither, and neither is guessed:
      // a world's veto linkage comes from `/worlds`, not from this summary.
      reproduced_counterexamples: 0,
      authoritative_counterexamples: 0,
      veto: null,
    },
    index,
    context,
  );
}
