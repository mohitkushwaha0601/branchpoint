/**
 * Component status.
 *
 * Only BRANCHPOINT's own `/health` is reachable from a browser. TrueForge, the
 * sandbox provider, and the model provider sit behind the backend and are never
 * contacted from here — they read `NOT EXPOSED`, which is both more honest than
 * a green tick this page cannot justify and more accurate than `UNKNOWN`: their
 * health is not in doubt, it is deliberately not observable from here.
 */

import { Check, CircleDashed, EyeOff, X } from "lucide-react";
import { useEffect, useState } from "react";

import { ApiError, isAbortError } from "../api/errors";
import { getHealth } from "../api/system";
import { AppHeader } from "../components/shell/AppHeader";

type Health = "checking" | "healthy" | "unreachable";

const DERIVED = [
  {
    name: "TrueForge harness",
    detail: "sessions · subagents · approval gate — private to the backend",
  },
  {
    name: "MCP server",
    detail: "registered with TrueForge by the backend, not exposed publicly",
  },
  {
    name: "Sandbox provider",
    detail: "DOPPELGÄNGER only · exploratory execution",
  },
  { name: "Model provider", detail: "configured in TrueForge, never in the browser" },
] as const;

export function SystemPage() {
  const [health, setHealth] = useState<Health>("checking");
  const [version, setVersion] = useState<string>("");
  const [detail, setDetail] = useState<string>("");

  useEffect(() => {
    const controller = new AbortController();
    void (async () => {
      try {
        const payload = await getHealth(controller.signal);
        if (controller.signal.aborted) return;
        setHealth("healthy");
        setVersion(`${payload.service} ${payload.version}`);
      } catch (caught) {
        if (isAbortError(caught) || controller.signal.aborted) return;
        setHealth("unreachable");
        setDetail(caught instanceof ApiError ? caught.detail : "unreachable");
      }
    })();
    return () => controller.abort();
  }, []);

  return (
    <div className="flex h-full flex-col bg-canvas">
      <AppHeader />
      <main className="flex-1 overflow-y-auto px-6 py-6">
        <h1 className="text-[18px] font-semibold text-fg">System</h1>
        <p className="mt-1 text-[12px] text-fg-dim">
          Live for BRANCHPOINT itself. Everything behind it is deliberately not
          reachable from the browser.
        </p>

        <ul className="mt-5 max-w-2xl border-t border-edge">
          <li className="flex items-center gap-3 border-b border-edge-muted px-3 py-2.5">
            {health === "healthy" ? (
              <Check className="h-3.5 w-3.5 text-ok" strokeWidth={2.75} aria-hidden="true" />
            ) : health === "unreachable" ? (
              <X className="h-3.5 w-3.5 text-fail" strokeWidth={2.75} aria-hidden="true" />
            ) : (
              <CircleDashed className="h-3.5 w-3.5 text-fg-faint" aria-hidden="true" />
            )}
            <span className="flex-1">
              <span className="block text-[13px] text-fg">BRANCHPOINT backend</span>
              <span className="block font-mono text-[11px] text-fg-faint">
                {health === "healthy" ? version : detail || "GET /health"}
              </span>
            </span>
            <span
              className={`font-mono text-[10px] tracking-[0.1em] ${
                health === "healthy"
                  ? "text-ok"
                  : health === "unreachable"
                    ? "text-fail"
                    : "text-fg-faint"
              }`}
            >
              {health === "healthy"
                ? "HEALTHY"
                : health === "unreachable"
                  ? "UNREACHABLE"
                  : "CHECKING"}
            </span>
          </li>

          {DERIVED.map((component) => (
            <li
              key={component.name}
              className="flex items-center gap-3 border-b border-edge-muted px-3 py-2.5"
            >
              {/* Not the CircleDashed the backend row uses while it is still
                  checking: these are never going to resolve from a browser, and
                  sharing the pending glyph made a settled, deliberate state look
                  like a request that never came back. */}
              <EyeOff className="h-3.5 w-3.5 text-fg-faint" aria-hidden="true" />
              <span className="flex-1">
                <span className="block text-[13px] text-fg">{component.name}</span>
                <span className="block font-mono text-[11px] text-fg-faint">
                  {component.detail}
                </span>
              </span>
              {/* "NOT EXPOSED" is the accurate word. These components are not
                  of unknown health — they are deliberately unreachable from the
                  browser, which is a property of the design, not a gap in it. */}
              <span className="font-mono text-[10px] tracking-[0.1em] text-fg-faint">
                NOT EXPOSED
              </span>
            </li>
          ))}
        </ul>
      </main>
    </div>
  );
}
