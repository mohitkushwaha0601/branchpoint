/**
 * Mission Control for one live run.
 *
 * Everything on screen comes from the backend. While the run is still moving
 * the view polls; once it is waiting on a human or finished, polling stops.
 * A failed fetch shows a banner and keeps the shell usable — it is never
 * replaced with fixture data.
 */

import { PanelRight } from "lucide-react";
import { useState } from "react";
import { useParams } from "react-router-dom";

import { RunViewProvider } from "../app/runView";
import { ApprovalGate } from "../components/approval/ApprovalGate";
import { EventDrawer } from "../components/events/EventDrawer";
import { BranchGraph } from "../components/graph/BranchGraph";
import { InspectorPanel } from "../components/inspector/InspectorPanel";
import { RunHeader } from "../components/run/RunHeader";
import { StageRail } from "../components/run/StageRail";
import { RunSidebar } from "../components/shell/RunSidebar";
import { ActivityDot, ErrorBanner } from "../components/shell/StatusStrip";
import { WorkspaceLayout } from "../components/shell/WorkspaceLayout";
import { useHarnessTrace } from "../hooks/useHarnessTrace";
import { useLiveRun } from "../hooks/useLiveRun";
import { useRunList } from "../hooks/useRunList";
import type { Run } from "../types/run";

export function RunPage() {
  const { runId } = useParams();
  const { run, loading, error, polling, refresh } = useLiveRun(runId);
  // Re-read the list whenever the run's status changes, so the sidebar follows.
  const { runs } = useRunList(run?.status);
  // The harness trace changes only when the harness does something, so it is
  // keyed on the run's status rather than re-fetched on every poll tick.
  const harness = useHarnessTrace(runId, run?.status);
  const [inspectorOpen, setInspectorOpen] = useState(false);

  const sidebar = <RunSidebar runs={runs} currentRunId={runId} />;

  if (run === null) {
    return (
      <WorkspaceLayout
        sidebar={sidebar}
        canvas={
          <>
            {error !== null ? (
              <ErrorBanner
                title={
                  error.isUnreachable
                    ? "BRANCHPOINT backend unreachable"
                    : error.isNotFound
                      ? `Run ${runId} not found`
                      : "Could not load this run"
                }
                detail={error.isUnreachable ? undefined : error.detail}
                onRetry={refresh}
              />
            ) : null}
            <div className="px-5 py-5">
              {loading && error === null ? (
                <ActivityDot label="LOADING RUN" />
              ) : null}
            </div>
          </>
        }
      />
    );
  }

  return (
    <RunViewProvider run={run} onChanged={refresh}>
      <WorkspaceLayout
        sidebar={sidebar}
        canvas={
          <>
            {error !== null ? (
              <ErrorBanner
                title={
                  error.isUnreachable
                    ? "BRANCHPOINT backend unreachable — showing the last response"
                    : "Could not refresh this run"
                }
                detail={error.isUnreachable ? undefined : error.detail}
                onRetry={refresh}
              />
            ) : null}
            <RunHeader run={run} />
            <StageRail stages={run.stages} />
            <RunToolbar
              run={run}
              polling={polling}
              onOpenInspector={() => setInspectorOpen(true)}
            />
            <BranchGraph />
            <ApprovalGate />
          </>
        }
        inspector={
          <InspectorPanel
            open={inspectorOpen}
            onClose={() => setInspectorOpen(false)}
          />
        }
        drawer={<EventDrawer harness={harness} />}
      />
    </RunViewProvider>
  );
}

function RunToolbar({
  run,
  polling,
  onOpenInspector,
}: {
  run: Run;
  polling: boolean;
  onOpenInspector: () => void;
}) {
  return (
    <div className="flex items-center gap-3 px-5 pt-3">
      {polling ? <ActivityDot label={run.status} /> : null}
      {run.status === "FAILED" && run.failureReason ? (
        <p className="text-[12px] text-fail">{run.failureReason}</p>
      ) : null}
      <button
        type="button"
        onClick={onOpenInspector}
        className="ml-auto flex items-center gap-1.5 rounded-md border border-edge bg-surface px-2.5 py-1 text-[12px] text-fg-dim hover:text-fg inspector:hidden"
      >
        <PanelRight className="h-3.5 w-3.5" aria-hidden="true" />
        Inspector
      </button>
    </div>
  );
}
