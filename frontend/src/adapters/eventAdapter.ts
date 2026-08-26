/**
 * Backend `RunEvent` DTOs → the compact timeline rows the drawer renders.
 *
 * Every row comes from a real emitted event. Nothing is synthesised, reordered,
 * or padded: if the backend has emitted three events, the drawer shows three.
 */

import type { RunEventDto } from "../api/types";
import type { EventChannel, RunEvent } from "../types/run";

/**
 * Which column an event type belongs in.
 *
 * Deliberately explicit rather than derived from the string, so a new backend
 * event type shows up under a visible default instead of being silently
 * mis-filed into a channel that implies something it does not mean — in
 * particular, nothing lands in `REPLAY` unless BRANCHPOINT's own replay engine
 * emitted it.
 */
const CHANNEL_BY_TYPE: Record<string, EventChannel> = {
  RUN_CREATED: "OBSERVE",
  OBSERVATION_COMPLETED: "OBSERVE",
  TRUEFORGE_SESSION_CREATED: "PLAN",
  PLANNER_STARTED: "PLAN",
  PLANNER_COMPLETED: "PLAN",
  CANDIDATES_PLANNED: "PLAN",
  WORLD_CREATED: "FORK",
  WORLD_EXECUTION_STARTED: "FORK",
  WORLD_EXECUTION_COMPLETED: "FORK",
  WORLD_AGENT_STARTED: "DOPPEL",
  DOPPELGANGER_STARTED: "DOPPEL",
  DOPPELGANGER_SPAWNED: "DOPPEL",
  DOPPELGANGER_RUNNING: "DOPPEL",
  SANDBOX_TEST_STARTED: "DOPPEL",
  SANDBOX_TEST_COMPLETED: "DOPPEL",
  COUNTEREXAMPLE_PROPOSED: "DOPPEL",
  COUNTEREXAMPLE_REPRODUCED: "REPLAY",
  COUNTEREXAMPLE_REJECTED: "REPLAY",
  WORLD_VETOED: "VERDICT",
  WORLD_SURVIVED: "VERDICT",
  COMPARISON_COMPLETED: "COMPARE",
  APPROVAL_REQUESTED: "APPROVE",
  APPROVAL_GRANTED: "APPROVE",
  APPROVAL_REJECTED: "APPROVE",
  COMMIT_STARTED: "APPROVE",
  COMMIT_COMPLETED: "APPROVE",
  VERIFICATION_STARTED: "APPROVE",
  VERIFICATION_COMPLETED: "APPROVE",
  RUN_SUCCEEDED: "VERDICT",
  RUN_REJECTED: "VERDICT",
  RUN_FAILED: "VERDICT",
};

/** `18:42:01` from an ISO timestamp, in the viewer's own zone. */
export function formatEventTime(iso: string): string {
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return "--:--:--";
  return at.toLocaleTimeString("en-GB", { hour12: false });
}

export function adaptEvent(dto: RunEventDto): RunEvent {
  const event: RunEvent = {
    eventId: dto.event_id,
    timestamp: formatEventTime(dto.occurred_at),
    channel: CHANNEL_BY_TYPE[dto.event_type] ?? "OBSERVE",
    message: dto.summary,
  };
  if (dto.world_id !== null) event.worldId = dto.world_id;
  return event;
}

export function adaptEvents(dtos: RunEventDto[]): RunEvent[] {
  return dtos.map(adaptEvent);
}
