/** Component status. Static in Phase 4.1 — no backend is polled. */

import { Check } from "lucide-react";

import { AppHeader } from "../components/shell/AppHeader";

const COMPONENTS = [
  { name: "BRANCHPOINT backend", detail: "replay engine · comparator · capability gate" },
  { name: "MCP server", detail: "17 tools · 13 read-only · 4 destructive" },
  { name: "TrueForge harness", detail: "sessions · subagents · approval gate" },
  { name: "Daytona sandbox", detail: "DOPPELGÄNGER only · exploratory execution" },
] as const;

export function SystemPage() {
  return (
    <div className="flex h-full flex-col bg-canvas">
      <AppHeader />
      <main className="flex-1 overflow-y-auto px-6 py-6">
        <h1 className="text-[18px] font-semibold text-fg">System</h1>
        <p className="mt-1 text-[12px] text-fg-dim">
          Static status view. Live health checks arrive with backend
          integration.
        </p>

        <ul className="mt-5 max-w-2xl border-t border-edge">
          {COMPONENTS.map((component) => (
            <li
              key={component.name}
              className="flex items-center gap-3 border-b border-edge-muted px-3 py-2.5"
            >
              <Check className="h-3.5 w-3.5 text-ok" strokeWidth={2.75} aria-hidden="true" />
              <span className="flex-1">
                <span className="block text-[13px] text-fg">{component.name}</span>
                <span className="block font-mono text-[11px] text-fg-faint">
                  {component.detail}
                </span>
              </span>
              <span className="font-mono text-[10px] tracking-[0.1em] text-ok">
                HEALTHY
              </span>
            </li>
          ))}
        </ul>
      </main>
    </div>
  );
}
