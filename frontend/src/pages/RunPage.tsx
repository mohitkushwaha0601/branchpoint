/**
 * Mission Control for one run: the full shell wired to a single run's data.
 */

import { PanelRight } from "lucide-react";
import { useState } from "react";
import { Navigate, useParams } from "react-router-dom";

import { RunViewProvider } from "../app/runView";
import { ApprovalGate } from "../components/approval/ApprovalGate";
import { EventDrawer } from "../components/events/EventDrawer";
import { BranchGraph } from "../components/graph/BranchGraph";
import { InspectorPanel } from "../components/inspector/InspectorPanel";
import { RunHeader } from "../components/run/RunHeader";
import { StageRail } from "../components/run/StageRail";
import { RunSidebar } from "../components/shell/RunSidebar";
import { WorkspaceLayout } from "../components/shell/WorkspaceLayout";
import { getRunById, runHistory } from "../data/heroRun";

export function RunPage() {
  const { runId } = useParams();
  const run = getRunById(runId);
  const [inspectorOpen, setInspectorOpen] = useState(false);

  if (run === undefined) return <Navigate to="/runs" replace />;

  return (
    <RunViewProvider run={run}>
      <WorkspaceLayout
        sidebar={<RunSidebar runs={runHistory} currentRunId={run.runId} />}
        canvas={
          <>
            <RunHeader run={run} />
            <StageRail stages={run.stages} />
            <div className="flex justify-end px-5 pt-3 inspector:hidden">
              <button
                type="button"
                onClick={() => setInspectorOpen(true)}
                className="flex items-center gap-1.5 rounded-md border border-edge bg-surface px-2.5 py-1 text-[12px] text-fg-dim hover:text-fg"
              >
                <PanelRight className="h-3.5 w-3.5" aria-hidden="true" />
                Inspector
              </button>
            </div>
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
        drawer={<EventDrawer />}
      />
    </RunViewProvider>
  );
}
