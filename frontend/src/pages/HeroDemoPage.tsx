/**
 * The Phase 4.1 fixture, rendered offline.
 *
 * Kept so the UI can be shown and tested without a backend. It is reachable
 * only at `/demo/hero`, it never polls, and its run is marked `source:
 * "fixture"` — no live run can inherit a value from it.
 */

import { useState } from "react";

import { RunViewProvider } from "../app/runView";
import { ApprovalGate } from "../components/approval/ApprovalGate";
import { EventDrawer } from "../components/events/EventDrawer";
import { BranchGraph } from "../components/graph/BranchGraph";
import { InspectorPanel } from "../components/inspector/InspectorPanel";
import { RunHeader } from "../components/run/RunHeader";
import { StageRail } from "../components/run/StageRail";
import { WorkspaceLayout } from "../components/shell/WorkspaceLayout";
import { heroRun } from "../data/heroRun";

export function HeroDemoPage() {
  const [inspectorOpen, setInspectorOpen] = useState(false);

  return (
    <RunViewProvider run={heroRun}>
      <WorkspaceLayout
        canvas={
          <>
            <p
              role="note"
              className="border-b border-warn-dim bg-warn/10 px-5 py-1.5 font-mono text-[10px] tracking-[0.1em] text-warn"
            >
              DEMO FIXTURE · Not a live TrueForge execution — the live path is
              /runs
            </p>
            <RunHeader run={heroRun} />
            <StageRail stages={heroRun.stages} />
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
