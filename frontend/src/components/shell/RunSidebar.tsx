/**
 * Run list. CI-style status glyphs, monospace ids, one selected row with a left
 * accent. Hidden below 1100px, where the canvas needs the width more.
 */

import { NavLink } from "react-router-dom";

import type { RunSummary } from "../../types/run";
import { StartRunButton } from "../run/StartRunButton";
import { StatusIcon, runStatusDescriptor } from "../run/StatusBadge";

function RunRow({ run, current }: { run: RunSummary; current: boolean }) {
  const descriptor = runStatusDescriptor(run.status);
  return (
    <NavLink
      to={`/runs/${run.runId}`}
      aria-current={current ? "page" : undefined}
      className={({ isActive }) =>
        `block border-l-2 px-3 py-2 transition-colors ${
          isActive
            ? "border-l-run bg-raised"
            : "border-l-transparent hover:bg-raised/60"
        }`
      }
    >
      <span className="flex items-center gap-2">
        <StatusIcon descriptor={descriptor} decorative />
        <span className="truncate text-[13px] text-fg">{run.title}</span>
      </span>
      <span className="mt-0.5 flex items-center gap-2 pl-[22px]">
        <span className="font-mono text-[10px] tracking-[0.05em] text-fg-faint">
          {descriptor.label}
        </span>
        <span className="font-mono text-[10px] text-fg-faint">
          {run.timeLabel}
        </span>
      </span>
    </NavLink>
  );
}

export function RunSidebar({
  runs,
  currentRunId,
}: {
  runs: RunSummary[];
  currentRunId?: string;
}) {
  return (
    <aside
      aria-label="Runs"
      className="hidden w-[var(--sidebar-width)] shrink-0 flex-col overflow-y-auto border-r border-edge bg-surface sidebar:flex"
    >
      <div className="flex items-center gap-2 px-3 pt-3 pb-2">
        <h2 className="font-mono text-[10px] font-semibold tracking-[0.14em] text-fg-faint">
          RUNS
        </h2>
      </div>
      <div className="px-3 pb-3">
        <StartRunButton compact />
      </div>

      {runs.length === 0 ? (
        <p className="border-t border-edge-muted px-3 py-3 text-[12px] text-fg-faint">
          No runs yet.
        </p>
      ) : (
        <div className="border-t border-edge-muted">
          {runs.map((run) => (
            <RunRow
              key={run.runId}
              run={run}
              current={run.runId === currentRunId}
            />
          ))}
        </div>
      )}
    </aside>
  );
}
