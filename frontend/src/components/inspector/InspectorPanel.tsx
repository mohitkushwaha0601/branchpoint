/**
 * The right pane. A fixed column on wide screens; below 900px the same content
 * becomes a slide-over so the graph keeps the full width.
 */

import { PanelRightClose, X } from "lucide-react";

import { useRunView } from "../../app/runView";
import { WorldInspector } from "./WorldInspector";

function InspectorBody() {
  const { run, selectedWorld, selectedStageId } = useRunView();

  // A run is readable the moment it is created, long before it has forked.
  if (selectedWorld === null) {
    return (
      <div className="px-4 py-4">
        <p className="text-[12px] text-fg-dim">Waiting for worlds…</p>
        <p className="mt-1 text-[11px] leading-relaxed text-fg-faint">
          Counterfactual worlds appear here as BRANCHPOINT forks them.
        </p>
      </div>
    );
  }

  const selectedStage =
    selectedWorld.pipeline.find((stage) => stage.id === selectedStageId) ?? null;
  const ranking = run.comparison.rankings.find(
    (item) => item.worldId === selectedWorld.worldId,
  );

  const comparatorNote = selectedWorld.recommended
    ? run.comparison.summary || "Ranked first by the deterministic comparator."
    : ranking
      ? `Ranked ${ranking.rank} by deterministic comparator. ${ranking.reason}`
      : run.comparison.rejectedWorldIds.includes(selectedWorld.worldId)
        ? "Disqualified by the comparator: a counterexample was reproduced against this world."
        : "Not yet compared.";

  return (
    <WorldInspector
      world={selectedWorld}
      selectedStage={selectedStage}
      recommended={selectedWorld.recommended}
      comparatorNote={comparatorNote}
    />
  );
}

export function InspectorPanel({
  open,
  onClose,
}: {
  /** Controls the small-screen slide-over only. */
  open: boolean;
  onClose: () => void;
}) {
  return (
    <>
      <aside
        aria-label="Inspector"
        className="hidden w-[var(--inspector-width)] shrink-0 flex-col overflow-hidden border-l border-edge bg-surface inspector:flex"
      >
        <div className="flex items-center gap-2 border-b border-edge px-4 py-2">
          <PanelRightClose className="h-3.5 w-3.5 text-fg-faint" aria-hidden="true" />
          <h2 className="font-mono text-[10px] font-semibold tracking-[0.14em] text-fg-faint">
            INSPECTOR
          </h2>
        </div>
        <InspectorBody />
      </aside>

      {open ? (
        <div className="fixed inset-0 z-40 inspector:hidden">
          <button
            type="button"
            aria-label="Close inspector"
            onClick={onClose}
            className="absolute inset-0 bg-canvas/70"
          />
          <aside
            aria-label="Inspector"
            className="absolute inset-y-0 right-0 flex w-[min(320px,90vw)] flex-col border-l border-edge bg-surface"
          >
            <div className="flex items-center gap-2 border-b border-edge px-4 py-2">
              <h2 className="flex-1 font-mono text-[10px] font-semibold tracking-[0.14em] text-fg-faint">
                INSPECTOR
              </h2>
              <button
                type="button"
                onClick={onClose}
                className="rounded-md p-1 text-fg-dim hover:bg-raised hover:text-fg"
              >
                <X className="h-4 w-4" aria-hidden="true" />
                <span className="sr-only">Close inspector</span>
              </button>
            </div>
            <InspectorBody />
          </aside>
        </div>
      ) : null}
    </>
  );
}
