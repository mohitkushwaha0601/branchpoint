/**
 * The TrueForge harness trace for one run.
 *
 * Fetched alongside the run's own polling but on its own cadence: the trace
 * only changes when the harness does something, so it is re-read when the run's
 * status moves rather than on every tick. That keeps a long-running page from
 * asking TrueForge the same question 50 times a minute.
 */

import { useEffect, useState } from "react";

import { ApiError, isAbortError } from "../api/errors";
import { getHarnessTrace } from "../api/runs";
import type { HarnessTraceDto } from "../api/types";

export interface HarnessTraceState {
  trace: HarnessTraceDto | null;
  error: ApiError | null;
  loading: boolean;
}

export function useHarnessTrace(
  runId: string | undefined,
  /** Re-read when this changes — the run's status, in practice. */
  revision: unknown,
): HarnessTraceState {
  const [trace, setTrace] = useState<HarnessTraceDto | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (runId === undefined) return;
    const controller = new AbortController();
    setLoading(true);

    void (async () => {
      try {
        const payload = await getHarnessTrace(runId, controller.signal);
        if (controller.signal.aborted) return;
        setTrace(payload);
        setError(null);
      } catch (caught) {
        if (isAbortError(caught) || controller.signal.aborted) return;
        // A trace is supporting detail: failing to read it must never blank the
        // run page, so the error is recorded and the last good trace is kept.
        setError(caught instanceof ApiError ? caught : null);
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    })();

    return () => controller.abort();
  }, [runId, revision]);

  return { trace, error, loading };
}
