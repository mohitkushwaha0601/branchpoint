/** Run history, read from the backend. */

import { Link } from "react-router-dom";

import { StartRunButton } from "../components/run/StartRunButton";
import { StatusBadge, runStatusDescriptor } from "../components/run/StatusBadge";
import { AppHeader } from "../components/shell/AppHeader";
import { ErrorBanner } from "../components/shell/StatusStrip";
import { useRunList } from "../hooks/useRunList";

export function RunsPage() {
  const { runs, error } = useRunList(null);

  return (
    <div className="flex h-full flex-col bg-canvas">
      <AppHeader />
      {error !== null ? (
        <ErrorBanner
          title={
            error.isUnreachable
              ? "BRANCHPOINT backend unreachable"
              : "Could not load runs"
          }
          detail={error.isUnreachable ? undefined : error.detail}
        />
      ) : null}
      <main className="flex-1 overflow-y-auto px-6 py-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-[18px] font-semibold text-fg">Runs</h1>
            <p className="mt-1 text-[12px] text-fg-dim">
              Every counterfactual run BRANCHPOINT has driven to a decision.
            </p>
          </div>
          <StartRunButton />
        </div>

        {runs.length === 0 ? (
          <p className="mt-6 text-[12px] text-fg-faint">
            No runs yet. Start one to watch BRANCHPOINT fork reality.
          </p>
        ) : (
          <table className="mt-5 w-full max-w-4xl border-t border-edge">
            <thead>
              <tr className="text-left">
                {["RUN", "ID", "STATUS", "ELAPSED"].map((heading, index) => (
                  <th
                    key={heading}
                    className={`px-3 py-2 font-mono text-[10px] font-semibold tracking-[0.14em] text-fg-faint ${
                      index === 3 ? "text-right" : ""
                    }`}
                  >
                    {heading}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.runId} className="border-t border-edge-muted">
                  <td className="px-3 py-2">
                    <Link
                      to={`/runs/${run.runId}`}
                      className="text-[13px] text-run hover:underline"
                    >
                      {run.title}
                    </Link>
                  </td>
                  <td className="px-3 py-2 font-mono text-[11px] text-fg-faint">
                    {run.runId}
                  </td>
                  <td className="px-3 py-2">
                    <StatusBadge descriptor={runStatusDescriptor(run.status)} />
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-[11px] text-fg-dim">
                    {run.timeLabel}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </main>
    </div>
  );
}
