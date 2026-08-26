/**
 * "Run BRANCHPOINT" — one button, not a form.
 *
 * The demo has one incident, so the request body is a constant. The button
 * disables itself the moment the POST is accepted and navigates to the returned
 * run id, which is how one press stays one run.
 */

import { Play } from "lucide-react";
import { useCallback, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { ApiError, isAbortError } from "../../api/errors";
import { startRun } from "../../api/runs";
import type { StartRunRequest } from "../../api/types";

/** The hero incident, as the backend's start contract expects it. */
export const DEFAULT_RUN: StartRunRequest = {
  title: "Checkout Regression",
  objective:
    "Restore checkout error rate and latency to the declared recovery SLO without violating data integrity, payment retry, or schema compatibility invariants.",
  severity: "CRITICAL",
  affected_services: ["checkout", "pricing-service"],
};

export function StartRunButton({ compact = false }: { compact?: boolean }) {
  const navigate = useNavigate();
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  // Latched separately from `starting` so the button cannot be pressed again in
  // the frame between a successful response and the route change.
  const claimed = useRef(false);

  const start = useCallback(() => {
    if (claimed.current) return;
    claimed.current = true;
    setStarting(true);
    setError(null);

    void (async () => {
      try {
        const accepted = await startRun(DEFAULT_RUN);
        navigate(`/runs/${accepted.run_id}`);
      } catch (caught) {
        if (isAbortError(caught)) return;
        claimed.current = false;
        setStarting(false);
        setError(
          caught instanceof ApiError
            ? caught
            : new ApiError({
                status: 0,
                detail: "BRANCHPOINT backend unreachable",
                method: "POST",
                path: "/api/v1/agent-runs",
              }),
        );
      }
    })();
  }, [navigate]);

  return (
    <div className={compact ? "" : "flex flex-col items-start gap-1.5"}>
      <button
        type="button"
        onClick={start}
        disabled={starting}
        className="inline-flex items-center gap-2 rounded-md border border-run-dim bg-run/15 px-3 py-1.5 text-[12px] font-medium text-run transition-colors hover:bg-run/25 disabled:cursor-not-allowed disabled:opacity-60"
      >
        <Play className="h-3.5 w-3.5" strokeWidth={2.5} aria-hidden="true" />
        {starting ? "Starting…" : "Run BRANCHPOINT"}
      </button>
      {error !== null ? (
        <p role="alert" className="text-[11px] text-fail">
          {error.detail}
        </p>
      ) : null}
    </div>
  );
}
