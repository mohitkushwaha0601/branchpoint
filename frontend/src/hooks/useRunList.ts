/** The sidebar's run list, read from the backend. */

import { useCallback, useEffect, useState } from "react";

import { ApiError, isAbortError } from "../api/errors";
import { listRuns } from "../api/runs";
import { adaptRunSummaries } from "../adapters/runAdapter";
import type { RunSummary } from "../types/run";

export function useRunList(refreshKey: unknown): {
  runs: RunSummary[];
  error: ApiError | null;
} {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [error, setError] = useState<ApiError | null>(null);

  const load = useCallback(async (signal: AbortSignal) => {
    try {
      const payload = await listRuns(signal);
      if (signal.aborted) return;
      // Newest first: the backend returns them in that order already.
      setRuns(adaptRunSummaries(payload.runs));
      setError(null);
    } catch (caught) {
      if (isAbortError(caught) || signal.aborted) return;
      setError(caught instanceof ApiError ? caught : null);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load, refreshKey]);

  return { runs, error };
}
