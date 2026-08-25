/**
 * Selection and approval state for one run's Mission Control view.
 *
 * The branch graph, the inspector, the approval gate, and the event drawer all
 * point at the same selection, so it lives in one place rather than being
 * threaded through five levels of props.
 *
 * Approval lives here too because it is the one interaction that changes the
 * *run* rather than the view. It never marks a run successful on its own: the
 * request records a human decision, and the outcome is whatever the backend
 * reports on the next read.
 */

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { approveRun } from "../api/runs";
import { ApiError, isAbortError } from "../api/errors";
import type { Run, World } from "../types/run";

/** Who the demo records a decision against. */
export const APPROVAL_ACTOR = "release-engineer";

interface RunViewValue {
  run: Run;
  selectedWorld: World | null;
  selectedWorldId: string;
  /** Pipeline row currently focused inside the selected world, if any. */
  selectedStageId: string | null;
  hoveredWorldId: string | null;
  selectWorld: (worldId: string) => void;
  selectStage: (worldId: string, stageId: string) => void;
  setHoveredWorldId: (worldId: string | null) => void;

  /** True from the moment Approve is pressed until the request settles. */
  approving: boolean;
  approvalError: ApiError | null;
  /** Whether this session has already submitted an approval for this run. */
  approvalSubmitted: boolean;
  approve: () => void;
  dismissApprovalError: () => void;
}

const RunViewContext = createContext<RunViewValue | null>(null);

export function RunViewProvider({
  run,
  onChanged,
  children,
}: {
  run: Run;
  /** Called after an approval settles, so the caller can re-read everything. */
  onChanged?: () => void;
  children: ReactNode;
}) {
  const [explicitWorldId, setExplicitWorldId] = useState<string | null>(null);
  const [selectedStageId, setSelectedStageId] = useState<string | null>(null);
  const [hoveredWorldId, setHoveredWorldId] = useState<string | null>(null);
  const [approving, setApproving] = useState(false);
  const [approvalSubmitted, setApprovalSubmitted] = useState(false);
  const [approvalError, setApprovalError] = useState<ApiError | null>(null);

  const selectWorld = useCallback((worldId: string) => {
    setExplicitWorldId(worldId);
    setSelectedStageId(null);
  }, []);

  const selectStage = useCallback((worldId: string, stageId: string) => {
    setExplicitWorldId(worldId);
    setSelectedStageId(stageId);
  }, []);

  const dismissApprovalError = useCallback(() => setApprovalError(null), []);

  const approve = useCallback(() => {
    // Guarded here rather than only in the button, so a second call cannot slip
    // through between a click and the re-render that disables it.
    if (approving || approvalSubmitted) return;
    const { approval } = run;
    setApproving(true);
    setApprovalError(null);

    void (async () => {
      try {
        await approveRun(run.runId, {
          actor: APPROVAL_ACTOR,
          // Read back from the run's own binding — never reconstructed here.
          expected_world_id: approval.worldId,
          expected_action_id: approval.actionId,
          expected_action_fingerprint: approval.actionFingerprint,
        });
        setApprovalSubmitted(true);
      } catch (caught) {
        if (isAbortError(caught)) return;
        setApprovalError(
          caught instanceof ApiError
            ? caught
            : new ApiError({
                status: 0,
                detail: "BRANCHPOINT backend unreachable",
                method: "POST",
                path: `/api/v1/runs/${run.runId}/approval`,
              }),
        );
      } finally {
        setApproving(false);
        // Re-read either way: a failed approval may still have moved the run.
        onChanged?.();
      }
    })();
  }, [approving, approvalSubmitted, run, onChanged]);

  const value = useMemo<RunViewValue>(() => {
    // Default to the comparator's pick: the thing a human is being asked about
    // should be what they are already looking at. Falls back to the first world
    // while a young run has no recommendation yet.
    const preferred =
      explicitWorldId ?? run.comparison.recommendedWorldId ?? run.worlds[0]?.worldId ?? "";
    const selectedWorld = run.worlds.find((world) => world.worldId === preferred) ?? null;

    return {
      run,
      selectedWorld,
      selectedWorldId: selectedWorld?.worldId ?? "",
      selectedStageId,
      hoveredWorldId,
      selectWorld,
      selectStage,
      setHoveredWorldId,
      approving,
      approvalError,
      approvalSubmitted,
      approve,
      dismissApprovalError,
    };
  }, [
    run,
    explicitWorldId,
    selectedStageId,
    hoveredWorldId,
    selectWorld,
    selectStage,
    approving,
    approvalError,
    approvalSubmitted,
    approve,
    dismissApprovalError,
  ]);

  return (
    <RunViewContext.Provider value={value}>{children}</RunViewContext.Provider>
  );
}

export function useRunView(): RunViewValue {
  const value = useContext(RunViewContext);
  if (value === null) {
    throw new Error("useRunView must be used inside a RunViewProvider");
  }
  return value;
}
