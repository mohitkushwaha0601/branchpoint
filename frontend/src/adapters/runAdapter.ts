/**
 * Backend DTOs → the Phase 4.1 `Run` view model.
 *
 * One function assembles everything the UI renders, from whatever the backend
 * has produced so far. Two rules govern it:
 *
 * 1. **Nothing is invented.** A value the API does not carry is empty, and the
 *    UI renders "—" or says it is unavailable. `heroRun` is never consulted.
 * 2. **Progressive by construction.** Every input except the run itself is
 *    optional, because a run is readable the instant it is created and grows
 *    worlds, then verdicts, then a comparison, then an approval.
 */

import type {
  ComparisonDetailDto,
  DemoStateDto,
  RunDto,
  RunEventDto,
  RunStatusDto,
  WorldsDto,
} from "../api/types";
import type {
  Approval,
  Comparison,
  Incident,
  RealitySnapshot,
  Run,
  RunStatus,
  RunSummary,
  Stage,
  StageId,
  StageStatus,
  World,
} from "../types/run";
import { adaptEvents } from "./eventAdapter";
import { adaptRunWorld, adaptWorldDetail } from "./worldAdapter";

const STAGE_ORDER: { id: StageId; label: string }[] = [
  { id: "OBSERVE", label: "Observe" },
  { id: "PLAN", label: "Plan" },
  { id: "FORK", label: "Fork" },
  { id: "EXECUTE", label: "Execute" },
  { id: "ATTACK", label: "Attack" },
  { id: "COMPARE", label: "Compare" },
  { id: "APPROVE", label: "Approve" },
  { id: "COMMIT", label: "Commit" },
  { id: "VERIFY", label: "Verify" },
];

/** The stage a given lifecycle status *is*. Terminal statuses name none. */
const STAGE_FOR_STATUS: Partial<Record<RunStatusDto, StageId>> = {
  OBSERVING: "OBSERVE",
  PLANNING: "PLAN",
  FORKING: "FORK",
  EXECUTING_WORLDS: "EXECUTE",
  ADVERSARIAL_TESTING: "ATTACK",
  COMPARING: "COMPARE",
  AWAITING_APPROVAL: "APPROVE",
  APPROVED: "APPROVE",
  COMMITTING: "COMMIT",
  VERIFYING: "VERIFY",
};

function stageIndex(id: StageId): number {
  return STAGE_ORDER.findIndex((stage) => stage.id === id);
}

/**
 * How far a run demonstrably got, read from what it actually holds.
 *
 * A terminal status says a run stopped but not where, so the evidence it left
 * behind is what places it: an approval means it reached the gate, a comparison
 * means it compared, verdicts mean it was attacked, and so on. This is
 * derivation from real fields, never a guess.
 */
function progressIndex(run: RunDto): number {
  if (run.verification_status !== null) return stageIndex("VERIFY");
  if (run.commit_status !== null) return stageIndex("COMMIT");
  if (run.approval !== null) return stageIndex("APPROVE");
  if (run.comparison !== null) return stageIndex("COMPARE");
  if (run.worlds.some((world) => world.verdict !== null)) return stageIndex("ATTACK");
  if (run.worlds.length > 0) return stageIndex("FORK");
  if (run.candidate_action_ids.length > 0) return stageIndex("PLAN");
  return stageIndex("OBSERVE");
}

/**
 * Stage statuses for the rail.
 *
 * Never animates ahead of the backend: a stage is complete only once the run
 * has moved past it, and the current stage is whatever the live status names.
 * A terminal failure or rejection keeps its completed stages and marks the one
 * where execution stopped.
 */
export function stagesFor(run: RunDto): Stage[] {
  const status = run.status;

  if (status === "SUCCEEDED") {
    return STAGE_ORDER.map((stage) => ({ ...stage, status: "complete" as StageStatus }));
  }

  if (status === "FAILED" || status === "REJECTED") {
    const stopped = progressIndex(run);
    return STAGE_ORDER.map((stage, index) => ({
      ...stage,
      status:
        index < stopped ? "complete" : index === stopped ? "failed" : ("pending" as StageStatus),
    }));
  }

  const currentId = STAGE_FOR_STATUS[status];
  if (currentId === undefined) {
    // CREATED: nothing has started yet.
    return STAGE_ORDER.map((stage) => ({ ...stage, status: "pending" as StageStatus }));
  }
  const current = stageIndex(currentId);
  return STAGE_ORDER.map((stage, index) => ({
    ...stage,
    status:
      index < current ? "complete" : index === current ? "current" : ("pending" as StageStatus),
  }));
}

function percent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function millis(value: number): string {
  return value >= 1000 ? `${(value / 1000).toFixed(1)}s` : `${Math.round(value)}ms`;
}

function compact(value: number): string {
  return value >= 1000 ? `${(value / 1000).toFixed(1)}k` : String(value);
}

/**
 * The incident readings and current reality, both from `GET /demo/state`.
 *
 * That endpoint is the reality source: what it returns is what is true now. A
 * change in it after a commit is evidence the commit landed — which is exactly
 * why nothing here may come from a model's description of the world.
 */
export function realityFor(demo: DemoStateDto | null): {
  incidentMetrics: Incident["metrics"];
  reality: RealitySnapshot;
} {
  if (demo === null) {
    return { incidentMetrics: [], reality: { facts: [] } };
  }
  return {
    incidentMetrics: [
      { label: "Checkout error", value: percent(demo.metrics.checkout_error_rate) },
      { label: "p95 latency", value: millis(demo.metrics.checkout_p95_ms) },
      { label: "Affected users", value: compact(demo.metrics.affected_users) },
    ],
    reality: {
      facts: [
        { label: "Pricing version", value: demo.deployment.version },
        {
          label: demo.feature_flag.key,
          value: demo.feature_flag.enabled ? "ON" : "OFF",
        },
        { label: "Replicas", value: String(demo.capacity.replicas) },
        { label: "Orders schema", value: String(demo.orders.orders_schema_version) },
      ],
    },
  };
}

function comparisonFor(run: RunDto, detail: ComparisonDetailDto | null): Comparison {
  const source = detail ?? run.comparison;
  if (source === null) {
    return {
      recommendedWorldId: null,
      rankings: [],
      rejectedWorldIds: [],
      summary: "",
    };
  }
  const rankings =
    detail === null
      ? []
      : detail.rankings.map((ranking) => ({
          worldId: ranking.world_id,
          rank: ranking.rank,
          reason: ranking.goal_achieved
            ? `Goal achieved. ${ranking.regressions_detected} regression(s), blast radius ${ranking.blast_radius}.`
            : `Goal not achieved. Blast radius ${ranking.blast_radius}.`,
        }));
  return {
    recommendedWorldId: source.recommended_world_id,
    rankings,
    rejectedWorldIds: source.rejected_worlds.map((rejected) => rejected.world_id),
    summary: source.summary,
  };
}

/**
 * The approval binding, exactly as the backend states it.
 *
 * The checklist is derived from the run's own facts — not from anything a model
 * said — and each item is either demonstrably true or shown as not satisfied.
 */
function approvalFor(run: RunDto, worlds: World[]): Approval {
  const dto = run.approval;
  if (dto === null) {
    return {
      required: false,
      status: "PENDING",
      actor: null,
      worldId: "",
      actionId: "",
      actionFingerprint: "",
      checks: [],
    };
  }
  const selected = worlds.find((world) => world.worldId === dto.selected_world_id);
  const status =
    dto.status === "APPROVED" || dto.status === "REJECTED" ? dto.status : "PENDING";

  return {
    required: run.status === "AWAITING_APPROVAL",
    status,
    actor: dto.actor,
    worldId: dto.selected_world_id,
    actionId: dto.action_id,
    actionFingerprint: dto.action_fingerprint,
    checks: [
      { label: "Goal achieved", satisfied: selected?.outcome.goalAchieved ?? false },
      {
        label: "Survived adversarial testing",
        satisfied: selected?.verdict === "SURVIVED",
      },
      {
        label: "No reproduced counterexamples",
        satisfied: (selected?.reproducedCounterexamples ?? 0) === 0,
      },
      {
        label: "Deterministic comparator recommendation",
        satisfied: run.comparison?.recommended_world_id === dto.selected_world_id,
      },
      { label: "Action fingerprint bound", satisfied: dto.action_fingerprint !== "" },
    ],
  };
}

function elapsedBetween(from: string, to: string): string {
  const start = new Date(from).getTime();
  const end = new Date(to).getTime();
  if (Number.isNaN(start) || Number.isNaN(end) || end < start) return "—";
  const seconds = Math.floor((end - start) / 1000);
  const minutes = Math.floor(seconds / 60);
  return minutes > 0 ? `${minutes}m ${seconds % 60}s` : `${seconds}s`;
}

export interface RunSources {
  run: RunDto;
  events?: RunEventDto[] | null;
  worlds?: WorldsDto | null;
  comparison?: ComparisonDetailDto | null;
  demo?: DemoStateDto | null;
}

/** Assemble everything the UI renders from whatever the backend has so far. */
export function adaptRun({
  run,
  events = null,
  worlds = null,
  comparison = null,
  demo = null,
}: RunSources): Run {
  const recommendedWorldId =
    comparison?.recommended_world_id ?? run.comparison?.recommended_world_id ?? null;
  const context = {
    recommendedWorldId,
    boundFingerprint: run.approval?.action_fingerprint ?? "",
    boundWorldId: run.approval?.selected_world_id ?? "",
  };

  // `/worlds` is richer, but the run response carries worlds the moment they
  // are forked. Prefer the richer source once it has caught up.
  const adaptedWorlds: World[] =
    worlds !== null && worlds.worlds.length >= run.worlds.length
      ? worlds.worlds.map((dto, index) => adaptWorldDetail(dto, index, context))
      : run.worlds.map((dto, index) => adaptRunWorld(dto, index, context));

  const { incidentMetrics, reality } = realityFor(demo);

  return {
    source: "live",
    runId: run.run_id,
    title: run.incident.title,
    status: run.status as RunStatus,
    startedAt: new Date(run.created_at).toLocaleTimeString("en-GB", { hour12: false }),
    elapsed: elapsedBetween(run.created_at, run.updated_at),
    objective: run.incident.goal,
    incident: {
      title: run.incident.title,
      summary: run.incident.description || run.incident.goal,
      metrics: incidentMetrics,
    },
    reality,
    stages: stagesFor(run),
    worlds: adaptedWorlds,
    comparison: comparisonFor(run, comparison),
    approval: approvalFor(run, adaptedWorlds),
    events: events === null ? [] : adaptEvents(events),
    rejectionReason: run.approval?.status === "REJECTED" ? run.approval.reason : "",
    // Both halves required. A successful commit says the mutation was issued;
    // only independent verification says reality actually reads that way, and
    // the header claims a change on the strength of the second.
    realityCommitted:
      run.commit_status === "SUCCEEDED" && run.verification_status === "PASSED",
    commitStatus: run.commit_status,
    verificationStatus: run.verification_status,
    failureReason: run.failure_reason,
  };
}

/** Sidebar rows, newest first, straight from `GET /runs`. */
export function adaptRunSummaries(runs: RunDto[]): RunSummary[] {
  return runs.map((run) => ({
    runId: run.run_id,
    title: run.incident.title,
    status: run.status as RunStatus,
    timeLabel: elapsedBetween(run.created_at, run.updated_at),
  }));
}
