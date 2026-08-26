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
import { StartRunButton } from "../components/run/StartRunButton";
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
  // keyed on the run's status rather than re-fetched on every poll tick. It is
  // also not asked for until the run itself has loaded: a trace describes a
  // run's sessions, and there is nothing to describe before the run resolves —
  // or ever, if it 404s.
  const runIsMissing = error?.isNotFound ?? false;
  const harness = useHarnessTrace(run === null ? undefined : runId, run?.status);
  const [inspectorOpen, setInspectorOpen] = useState(false);

  const sidebar = <RunSidebar runs={runs} currentRunId={runId} />;

  if (run === null) {
    return (
      <WorkspaceLayout
        sidebar={sidebar}
        canvas={
          runIsMissing ? (
            <LostRun runId={runId} />
          ) : (
            <>
              {error !== null ? (
                <ErrorBanner
                  title={
                    error.isUnreachable
                      ? "BRANCHPOINT backend unreachable"
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
          )
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

/**
 * A run the backend no longer knows about.
 *
 * Almost always a restart: this build keeps active runs in process memory, so
 * the honest thing is to say that rather than offer a Retry that cannot
 * succeed. Nothing is polled from here — the 404 is authoritative and final.
 */
function LostRun({ runId }: { runId: string | undefined }) {
  return (
    <div className="px-5 py-6">
      <h2 className="text-[15px] font-semibold text-fg">Run no longer exists</h2>
      <code className="mt-1 block font-mono text-[11px] text-fg-faint">
        {runId}
      </code>
      <p className="mt-3 max-w-xl text-[12px] leading-relaxed text-fg-dim">
        This hackathon build stores active BRANCHPOINT runs in process memory,
        so a backend restart ends them. Nothing was committed and reality is
        unchanged.
      </p>
      <div className="mt-4">
        <StartRunButton />
      </div>
    </div>
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
