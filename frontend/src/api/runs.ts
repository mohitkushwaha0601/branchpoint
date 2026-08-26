/** Run endpoints. Every call takes an `AbortSignal` so a view can cancel it. */

import { request } from "./client";
import type {
  AcceptedRunDto,
  ApprovalDecisionDto,
  ApprovalRequest,
  ComparisonDetailDto,
  EventListDto,
  HumanDecisionDto,
  HarnessTraceDto,
  RejectionRequest,
  RunDto,
  RunListDto,
  StartRunRequest,
  WorldInspectionDto,
  WorldsDto,
} from "./types";

/** Accepted with `202` as soon as the run exists; the pipeline runs after. */
export function startRun(
  body: StartRunRequest,
  signal?: AbortSignal,
): Promise<AcceptedRunDto> {
  return request<AcceptedRunDto>("/api/v1/agent-runs", {
    method: "POST",
    body,
    signal,
  });
}

export function listRuns(signal?: AbortSignal): Promise<RunListDto> {
  return request<RunListDto>("/api/v1/runs", { signal });
}

/**
 * The authoritative view of a run: status, worlds, comparison, approval
 * binding, commit and verification outcome, all in one response. Everything
 * else below is detail layered on top of it, never a second source for the
 * same fact.
 */
export function getRun(runId: string, signal?: AbortSignal): Promise<RunDto> {
  return request<RunDto>(`/api/v1/runs/${encodeURIComponent(runId)}`, { signal });
}

export function getRunEvents(
  runId: string,
  signal?: AbortSignal,
): Promise<EventListDto> {
  return request<EventListDto>(
    `/api/v1/runs/${encodeURIComponent(runId)}/events`,
    { signal },
  );
}

/** Per-world measured outcome — richer than the summary inside `getRun`. */
export function getRunWorlds(
  runId: string,
  signal?: AbortSignal,
): Promise<WorldsDto> {
  return request<WorldsDto>(`/api/v1/runs/${encodeURIComponent(runId)}/worlds`, {
    signal,
  });
}

/** Deterministic rankings. `409` until the run has been compared. */
export function getRunComparison(
  runId: string,
  signal?: AbortSignal,
): Promise<ComparisonDetailDto> {
  return request<ComparisonDetailDto>(
    `/api/v1/runs/${encodeURIComponent(runId)}/comparison`,
    { signal },
  );
}

/**
 * Record a human decision.
 *
 * The body carries no action content — see {@link ApprovalRequest}. The
 * `expected_*` values are read back from the run's own approval binding and
 * sent as confirmation; a mismatch is a `409` the human must resolve, never an
 * instruction to commit something else. Capability issuance and the commit
 * itself belong to BRANCHPOINT and are never touched from here.
 */
export function approveRun(
  runId: string,
  body: ApprovalRequest,
  signal?: AbortSignal,
): Promise<ApprovalDecisionDto> {
  return request<ApprovalDecisionDto>(
    `/api/v1/runs/${encodeURIComponent(runId)}/approval`,
    { method: "POST", body, signal },
  );
}

/**
 * Record a human's refusal of the recommended world.
 *
 * A separate route from {@link approveRun} on purpose: approval is the only
 * path that reaches the destructive commit operator, and rejection has no
 * reachable commit code at all. Nothing here can mutate reality.
 */
export function rejectRun(
  runId: string,
  body: RejectionRequest,
  signal?: AbortSignal,
): Promise<HumanDecisionDto> {
  return request<HumanDecisionDto>(
    `/api/v1/runs/${encodeURIComponent(runId)}/rejection`,
    { method: "POST", body, signal },
  );
}

/**
 * One world with its evidence, counterexamples, and veto linkage.
 *
 * Everything needed to reconstruct exploratory finding → replay → reproduced
 * counterexample → veto without parsing any human-readable string.
 */
export function getWorldInspection(
  runId: string,
  worldId: string,
  signal?: AbortSignal,
): Promise<WorldInspectionDto> {
  return request<WorldInspectionDto>(
    `/api/v1/runs/${encodeURIComponent(runId)}/worlds/${encodeURIComponent(worldId)}`,
    { signal },
  );
}

/**
 * TrueForge harness activity for one run.
 *
 * Read through BRANCHPOINT, always: TrueForge is private to the backend and its
 * address never appears in this bundle. A run whose harness cannot be reached
 * still answers 200, with `trueforge_status: "unavailable"`.
 */
export function getHarnessTrace(
  runId: string,
  signal?: AbortSignal,
): Promise<HarnessTraceDto> {
  return request<HarnessTraceDto>(
    `/api/v1/runs/${encodeURIComponent(runId)}/harness-trace`,
    { signal },
  );
}
