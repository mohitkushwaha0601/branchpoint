/**
 * Compact product header. Nav plus one health signal, nothing else — the
 * screen's vertical budget belongs to the graph.
 */

import { GitBranch } from "lucide-react";
import { NavLink } from "react-router-dom";

const NAV = [
  { to: "/runs", label: "Runs" },
  { to: "/evidence", label: "Evidence", disabled: true },
  { to: "/system", label: "System" },
] as const;

export function AppHeader() {
  return (
    <header className="flex h-[var(--header-height)] shrink-0 items-center gap-6 border-b border-edge bg-surface px-4">
      <div className="flex items-center gap-2">
        <GitBranch className="h-4 w-4 text-run" aria-hidden="true" />
        <span className="font-mono text-[13px] font-semibold tracking-[0.14em] text-fg">
          BRANCHPOINT
        </span>
      </div>

      <nav aria-label="Primary" className="flex items-center gap-1">
        {NAV.map((item) =>
          "disabled" in item && item.disabled ? (
            <span
              key={item.label}
              aria-disabled="true"
              title="Available in a later phase"
              className="cursor-not-allowed rounded-md px-2.5 py-1 text-[13px] text-fg-faint"
            >
              {item.label}
            </span>
          ) : (
            <NavLink
              key={item.label}
              to={item.to}
              className={({ isActive }) =>
                `rounded-md px-2.5 py-1 text-[13px] transition-colors ${
                  isActive
                    ? "bg-raised text-fg"
                    : "text-fg-dim hover:bg-raised hover:text-fg"
                }`
              }
            >
              {item.label}
            </NavLink>
          ),
        )}
      </nav>

      <div className="ml-auto flex items-center gap-2">
        <span
          className="h-1.5 w-1.5 rounded-full bg-ok"
          aria-hidden="true"
        />
        <span className="text-[12px] text-fg-dim">System healthy</span>
      </div>
    </header>
  );
}
