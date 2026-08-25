/**
 * Domain types for a BRANCHPOINT run, as the UI consumes them.
 *
 * These mirror the backend's vocabulary deliberately. The one distinction the
 * whole product rests on is `EvidenceAuthority`: DOPPELGÄNGER sandbox output is
 * `EXPLORATORY` and can never justify a verdict, while BRANCHPOINT's own
 * deterministic replay is `VERIFIED` and is the only thing that can. Nothing in
 * the UI may present the first as the second.
 */

/**
 * The backend's own run lifecycle, adopted verbatim.
 *
 * Narrowing it here would mean the UI inventing a vocabulary the server does
 * not use, and then having to guess which server state maps to which invented
 * one. Displaying the real state is both simpler and more truthful.
 */
export type RunStatus =
  | "CREATED"
  | "OBSERVING"
  | "PLANNING"
  | "FORKING"
  | "EXECUTING_WORLDS"
  | "ADVERSARIAL_TESTING"
  | "COMPARING"
  | "AWAITING_APPROVAL"
  | "APPROVED"
  | "COMMITTING"
  | "VERIFYING"
  | "SUCCEEDED"
  | "REJECTED"
  | "FAILED";

/** Statuses after which nothing further happens on its own. */
export const TERMINAL_RUN_STATUSES: readonly RunStatus[] = [
  "SUCCEEDED",
  "REJECTED",
  "FAILED",
];

/** Whether a run is still advancing and therefore worth polling. */
export function isRunActive(status: RunStatus): boolean {
  return !TERMINAL_RUN_STATUSES.includes(status) && status !== "AWAITING_APPROVAL";
}

export type StageId =
  | "OBSERVE"
  | "PLAN"
  | "FORK"
  | "EXECUTE"
  | "ATTACK"
  | "COMPARE"
  | "APPROVE"
  | "COMMIT"
  | "VERIFY";

export type StageStatus = "complete" | "current" | "pending" | "failed";

export type WorldVerdict =
  | "SURVIVED"
  | "VETOED"
  | "INCONCLUSIVE"
  /** No verdict yet: the world exists but has not been evaluated. */
  | "PENDING";

export type PipelineStatus = "passed" | "failed" | "running" | "skipped";

/** Who produced a piece of evidence, and therefore what it is allowed to prove. */
export type EvidenceAuthority = "EXPLORATORY" | "VERIFIED";

export type EvidenceOutcome = "PASS" | "FAIL" | "INFO";

export interface Stage {
  id: StageId;
  label: string;
  status: StageStatus;
  detail?: string;
}

export interface MetricReading {
  label: string;
  value: string;
  /** Present when this reading moved between two observations. */
  from?: string;
  to?: string;
}

export interface RealityFact {
  label: string;
  value: string;
}

export interface Incident {
  title: string;
  summary: string;
  metrics: MetricReading[];
}

export interface RealitySnapshot {
  facts: RealityFact[];
}

export type ActionKind =
  | "SET_DEPLOYMENT_VERSION"
  | "SET_FEATURE_FLAG"
  | "SCALE_SERVICE";

export interface Action {
  actionId: string;
  kind: ActionKind;
  name: string;
  target: string;
  /** The single parameter this action family changes, e.g. `PRICING_V2`. */
  parameter: string;
  from: string;
  to: string;
  fingerprint: string;
  /** `null` when the API does not say. Rendered as "—", never guessed. */
  reversible: boolean | null;
}

export interface PipelineStage {
  id: string;
  label: string;
  status: PipelineStatus;
  duration: string;
  /** One line explaining the outcome, shown in the inspector. */
  detail: string;
}

export interface Evidence {
  evidenceId: string;
  /** `branchpoint-replay` or `trueforge-doppelganger`. */
  source: string;
  authority: EvidenceAuthority;
  claim: string;
  outcome: EvidenceOutcome;
  observed?: string;
  expected?: string;
}

export type CounterexampleStatus =
  | "REPRODUCED"
  | "NOT_REPRODUCED"
  | "ERROR"
  | "NONE_PROPOSED";

export interface Counterexample {
  attackId: string;
  title: string;
  /** The adversary's own words. Exploratory by construction. */
  hypothesis: string;
  status: CounterexampleStatus;
  /** Ids of the `VERIFIED` evidence that reproduced it, if any. */
  evidenceIds: string[];
}

export interface SandboxInfo {
  enabled: boolean;
  status: "Available" | "Unavailable" | "Not requested";
  sandboxId?: string;
  execCount: number;
}

export interface WorldOutcome {
  goalAchieved: boolean;
  goalAttainment: number;
  regressions: number;
  blastRadius: number;
  costDelta: number;
  /** Before/after readings the world produced. */
  results: MetricReading[];
}

export interface World {
  worldId: string;
  label: string;
  name: string;
  action: Action;
  pipeline: PipelineStage[];
  verdict: WorldVerdict;
  verdictReason: string;
  outcome: WorldOutcome;
  counterexample: Counterexample;
  sandbox: SandboxInfo;
  evidence: Evidence[];
  recommended: boolean;
  notes: string[];
  /**
   * Whether `evidence` and `counterexample.hypothesis` hold real rows.
   *
   * The current HTTP API exposes per-world evidence *counts*, not the rows
   * themselves. When this is false the UI says so in words rather than
   * rendering empty or invented evidence — `evidenceCount` and
   * `reproducedCounterexamples` stay live and authoritative either way.
   */
  evidenceDetailAvailable: boolean;
  evidenceCount: number;
  reproducedCounterexamples: number;
}

export interface ComparisonRanking {
  worldId: string;
  rank: number;
  reason: string;
}

export interface Comparison {
  recommendedWorldId: string | null;
  rankings: ComparisonRanking[];
  rejectedWorldIds: string[];
  summary: string;
}

export interface ApprovalCheck {
  label: string;
  satisfied: boolean;
}

export interface Approval {
  required: boolean;
  status: "PENDING" | "APPROVED" | "REJECTED";
  worldId: string;
  actionId: string;
  actionFingerprint: string;
  checks: ApprovalCheck[];
}

export type EventChannel =
  | "OBSERVE"
  | "PLAN"
  | "FORK"
  | "DOPPEL"
  | "REPLAY"
  | "VERDICT"
  | "COMPARE"
  | "APPROVE";

export interface RunEvent {
  eventId: string;
  timestamp: string;
  channel: EventChannel;
  message: string;
  /** Set when clicking the event should select a world. */
  worldId?: string;
}

export type RunSource = "live" | "fixture";

export interface Run {
  /** Where this run's values came from. Live runs never borrow fixture data. */
  source: RunSource;
  runId: string;
  title: string;
  status: RunStatus;
  startedAt: string;
  elapsed: string;
  objective: string;
  incident: Incident;
  reality: RealitySnapshot;
  stages: Stage[];
  worlds: World[];
  comparison: Comparison;
  approval: Approval;
  events: RunEvent[];
  /** Present once reality has been re-read after a commit. */
  realityCommitted: boolean;
  commitStatus: string | null;
  verificationStatus: string | null;
  failureReason: string;
}

/** A row in the run sidebar. The current run plus finished history. */
export interface RunSummary {
  runId: string;
  title: string;
  status: RunStatus;
  timeLabel: string;
}
