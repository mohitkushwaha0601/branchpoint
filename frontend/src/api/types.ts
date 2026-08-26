/**
 * Transport DTOs, mirroring the backend's response models exactly.
 *
 * These are the wire shape and nothing else. Nothing in `components/` imports
 * from this file: an adapter turns these into the Phase 4.1 view model, so a
 * backend schema change lands in one place instead of across the UI.
 *
 * Field names are snake_case on purpose — they are the server's names, and
 * renaming them here would hide which side of the boundary a value came from.
 */

export type RunStatusDto =
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

export type WorldStatusDto =
  | "CREATED"
  | "PREPARING"
  | "EXECUTING"
  | "ATTACKING"
  | "EVALUATING"
  | "SURVIVED"
  | "VETOED"
  | "FAILED";

export type WorldVerdictDto = "SURVIVED" | "VETOED" | "INCONCLUSIVE";

export interface AcceptedRunDto {
  run_id: string;
  status: RunStatusDto;
  detail: string;
}

export interface IncidentDto {
  incident_id: string;
  title: string;
  goal: string;
  severity: string;
  detected_at: string;
  description: string;
  affected_services: string[];
}

/** The summary world shape carried inside `GET /runs/{id}`. */
export interface RunWorldDto {
  world_id: string;
  status: WorldStatusDto;
  action_id: string;
  action_name: string;
  verdict: WorldVerdictDto | null;
  verdict_reason: string;
  evidence_count: number;
  counterexample_count: number;
}

export interface RejectedWorldDto {
  world_id: string;
  reasons: string[];
  detail: string;
}

export interface ComparisonDto {
  recommended_world_id: string | null;
  eligible_world_ids: string[];
  tied_world_ids: string[];
  rejected_worlds: RejectedWorldDto[];
  summary: string;
}

export interface ApprovalDto {
  approval_id: string;
  status: string;
  selected_world_id: string;
  action_id: string;
  action_fingerprint: string;
  requested_at: string;
  decided_at: string | null;
  actor: string | null;
  reason: string;
}

export interface RunDto {
  run_id: string;
  status: RunStatusDto;
  incident: IncidentDto;
  created_at: string;
  updated_at: string;
  candidate_action_ids: string[];
  worlds: RunWorldDto[];
  comparison: ComparisonDto | null;
  approval: ApprovalDto | null;
  selected_world_id: string | null;
  commit_id: string | null;
  commit_status: string | null;
  verification_status: string | null;
  failure_reason: string;
}

export interface RunListDto {
  runs: RunDto[];
}

/** The richer world shape from `GET /runs/{id}/worlds`. */
export interface WorldDetailDto {
  world_id: string;
  status: string;
  verdict: WorldVerdictDto | null;
  verdict_reason: string;
  action_id: string;
  action_name: string;
  action_type: string;
  goal_achieved: boolean | null;
  goal_attainment: number | null;
  regressions_detected: number | null;
  blast_radius: number | null;
  cost_delta: number | null;
  evidence_count: number;
  counterexample_count: number;
  reproduced_counterexamples: number;
}

export interface WorldsDto {
  run_id: string;
  worlds: WorldDetailDto[];
}

export interface RankingDto {
  world_id: string;
  rank: number;
  goal_achieved: boolean;
  goal_attainment: number;
  regressions_detected: number;
  blast_radius: number;
  cost_delta: number;
}

export interface ComparisonDetailDto {
  run_id: string;
  recommended_world_id: string | null;
  eligible_world_ids: string[];
  tied_world_ids: string[];
  rankings: RankingDto[];
  rejected_worlds: RejectedWorldDto[];
  summary: string;
}

export interface RunEventDto {
  event_id: string;
  run_id: string;
  world_id: string | null;
  event_type: string;
  summary: string;
  occurred_at: string;
}

export interface EventListDto {
  events: RunEventDto[];
}

export interface DemoStateDto {
  deployment: {
    service: string;
    version: string;
    previous_version: string | null;
    deployed_at: string;
  };
  feature_flag: { key: string; enabled: boolean; service: string };
  capacity: { service: string; replicas: number; daily_infra_cost_usd: number };
  metrics: {
    regression_active: boolean;
    checkout_error_rate: number;
    checkout_p95_ms: number;
    pricing_timeout_rate: number;
    affected_users: number;
    database_latency_ms: number;
    checkout_cpu_utilization: number;
    pricing_cpu_utilization: number;
    daily_infra_cost_usd: number;
  };
  orders: {
    total_orders: number;
    orders_schema_version: number;
    orders_with_payment_revision: number;
  };
  snapshot_at: string;
}

export interface ApprovalDecisionDto {
  run_id: string;
  world_id: string;
  action_id: string;
  action_name: string;
  approval_status: string;
  run_status: RunStatusDto;
  commit_status: string | null;
  verification_status: string | null;
  detail: string;
}

export interface HealthDto {
  status: string;
  service: string;
  version: string;
}

export interface StartRunRequest {
  objective: string;
  title: string;
  severity: string;
  affected_services: string[];
}

/**
 * The approval body. Deliberately has no place to put an action, a parameter,
 * or a target: a human confirms the binding BRANCHPOINT already made, and the
 * browser cannot name something else to commit.
 */
export interface ApprovalRequest {
  actor: string;
  expected_world_id?: string;
  expected_action_id?: string;
  expected_action_fingerprint?: string;
}

// ----- TrueForge harness trace -----------------------------------------------
//
// A redacted, backend-normalized view of what the TrueForge harness actually
// did. It is provenance about the agent runtime, never evidence: nothing here
// can reproduce a counterexample or veto a world.

export type HarnessCategoryDto =
  | "SESSION"
  | "MCP_TOOL"
  | "SANDBOX_CREATED"
  | "SANDBOX_EXEC"
  | "SUBAGENT_CREATED"
  | "SUBAGENT_COMPLETED"
  | "APPROVAL_REQUIRED"
  | "APPROVAL_RESUMED"
  | "MODEL_TURN";

export type HarnessStatusDto = "OK" | "FAILED" | "PENDING" | "INFO";

export interface HarnessSessionDto {
  purpose: string;
  trueforge_session_id: string;
  world_id: string | null;
  status: string;
  last_turn_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface HarnessTraceEntryDto {
  trace_id: string;
  timestamp: string;
  session_id: string;
  purpose: string;
  world_id: string | null;
  category: HarnessCategoryDto;
  status: HarnessStatusDto;
  summary: string;
  tool_name: string;
  mcp_server: string;
  thread_id: string;
  sandbox_id: string;
  exit_code: number | null;
}

export interface HarnessTraceDto {
  run_id: string;
  /** `"available"` or `"unavailable"` — the backend never guesses. */
  trueforge_status: string;
  detail: string;
  sessions: HarnessSessionDto[];
  entries: HarnessTraceEntryDto[];
}
