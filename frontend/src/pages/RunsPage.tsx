/** Run history as a dense table — the list view behind the sidebar. */

import { Link } from "react-router-dom";

import { AppHeader } from "../components/shell/AppHeader";
import { StatusBadge, runStatusDescriptor } from "../components/run/StatusBadge";
import { runHistory } from "../data/heroRun";

export function RunsPage() {
  return (
    <div className="flex h-full flex-col bg-canvas">
      <AppHeader />
      <main className="flex-1 overflow-y-auto px-6 py-6">
        <h1 className="text-[18px] font-semibold text-fg">Runs</h1>
        <p className="mt-1 text-[12px] text-fg-dim">
          Every counterfactual run BRANCHPOINT has driven to a decision.
        </p>

        <table className="mt-5 w-full max-w-4xl border-t border-edge">
          <thead>
            <tr className="text-left">
              <th className="px-3 py-2 font-mono text-[10px] font-semibold tracking-[0.14em] text-fg-faint">
                RUN
              </th>
              <th className="px-3 py-2 font-mono text-[10px] font-semibold tracking-[0.14em] text-fg-faint">
                ID
              </th>
              <th className="px-3 py-2 font-mono text-[10px] font-semibold tracking-[0.14em] text-fg-faint">
                STATUS
              </th>
              <th className="px-3 py-2 text-right font-mono text-[10px] font-semibold tracking-[0.14em] text-fg-faint">
                WHEN
              </th>
            </tr>
          </thead>
          <tbody>
            {runHistory.map((run) => (
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
      </main>
    </div>
  );
}
