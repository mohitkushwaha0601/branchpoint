/**
 * Selection state for one run's Mission Control view.
 *
 * The branch graph, the inspector, the approval gate, and the event drawer all
 * point at the same selection, so it lives in one place rather than being
 * threaded through five levels of props. Nothing here talks to a backend: the
 * approval decision is local view state for Phase 4.1.
 */

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import type { Run, World } from "../types/run";

export type ApprovalDecision = "APPROVED" | "REJECTED" | null;

interface RunViewValue {
  run: Run;
  selectedWorld: World;
  selectedWorldId: string;
  /** Pipeline row currently focused inside the selected world, if any. */
  selectedStageId: string | null;
  hoveredWorldId: string | null;
  approvalDecision: ApprovalDecision;
  selectWorld: (worldId: string) => void;
  selectStage: (worldId: string, stageId: string) => void;
  setHoveredWorldId: (worldId: string | null) => void;
  decideApproval: (decision: Exclude<ApprovalDecision, null>) => void;
  resetApproval: () => void;
}

const RunViewContext = createContext<RunViewValue | null>(null);

export function RunViewProvider({
  run,
  children,
}: {
  run: Run;
  children: ReactNode;
}) {
  // The comparator's recommendation is the default focus: the thing a human is
  // being asked about should be what they are already looking at.
  const initialWorldId =
    run.comparison.recommendedWorldId ?? run.worlds[0]?.worldId ?? "";

  const [selectedWorldId, setSelectedWorldId] = useState(initialWorldId);
  const [selectedStageId, setSelectedStageId] = useState<string | null>(null);
  const [hoveredWorldId, setHoveredWorldId] = useState<string | null>(null);
  const [approvalDecision, setApprovalDecision] =
    useState<ApprovalDecision>(null);

  const selectWorld = useCallback((worldId: string) => {
    setSelectedWorldId(worldId);
    setSelectedStageId(null);
  }, []);

  const selectStage = useCallback((worldId: string, stageId: string) => {
    setSelectedWorldId(worldId);
    setSelectedStageId(stageId);
  }, []);

  const decideApproval = useCallback(
    (decision: Exclude<ApprovalDecision, null>) => setApprovalDecision(decision),
    [],
  );
  const resetApproval = useCallback(() => setApprovalDecision(null), []);

  const value = useMemo<RunViewValue>(() => {
    const selectedWorld =
      run.worlds.find((world) => world.worldId === selectedWorldId) ??
      run.worlds[0]!;
    return {
      run,
      selectedWorld,
      selectedWorldId: selectedWorld.worldId,
      selectedStageId,
      hoveredWorldId,
      approvalDecision,
      selectWorld,
      selectStage,
      setHoveredWorldId,
      decideApproval,
      resetApproval,
    };
  }, [
    run,
    selectedWorldId,
    selectedStageId,
    hoveredWorldId,
    approvalDecision,
    selectWorld,
    selectStage,
    decideApproval,
    resetApproval,
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
