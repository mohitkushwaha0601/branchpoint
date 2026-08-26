/**
 * Evidence detail for the one world a reviewer is looking at.
 *
 * Fetched lazily and per selection, never for every world in the graph: a run
 * with five worlds should issue one detail request, not five, and none at all
 * until someone asks a question about a specific world.
 *
 * The stale-response guard matters more than it looks. Selections change faster
 * than requests return, so every response is checked against the selection that
 * is current *when it lands*. Without that, clicking α then β could leave β's
 * header above α's evidence — the single most misleading thing this panel could
 * do.
 */

import { useEffect, useRef, useState } from "react";

import { ApiError, isAbortError } from "../api/errors";
import { getWorldInspection } from "../api/runs";
import type { WorldInspectionDto } from "../api/types";

export interface WorldInspectionState {
  data: WorldInspectionDto | null;
  loading: boolean;
  error: ApiError | null;
}

export function useWorldInspection(
  runId: string | undefined,
  worldId: string | undefined,
): WorldInspectionState {
  const [state, setState] = useState<WorldInspectionState>({
    data: null,
    loading: false,
    error: null,
  });

  // The selection a response must still match to be allowed on screen.
  const activeKey = useRef<string>("");

  useEffect(() => {
    if (runId === undefined || worldId === undefined || worldId === "") {
      activeKey.current = "";
      setState({ data: null, loading: false, error: null });
      return;
    }

    const key = `${runId}::${worldId}`;
    activeKey.current = key;
    const controller = new AbortController();
    // Cleared rather than kept: showing the previous world's evidence under the
    // new world's name would be worse than showing nothing.
    setState({ data: null, loading: true, error: null });

    void (async () => {
      try {
        const payload = await getWorldInspection(runId, worldId, controller.signal);
        if (activeKey.current !== key || controller.signal.aborted) return;
        setState({ data: payload, loading: false, error: null });
      } catch (caught) {
        if (isAbortError(caught) || activeKey.current !== key) return;
        // Detail is supporting information. Failing to load it leaves the
        // world's summary and verdict intact rather than breaking the page.
        setState({
          data: null,
          loading: false,
          error:
            caught instanceof ApiError
              ? caught
              : new ApiError({
                  status: 0,
                  detail: "BRANCHPOINT backend unreachable",
                  method: "GET",
                  path: `/api/v1/runs/${runId}/worlds/${worldId}`,
                }),
        });
      }
    })();

    return () => controller.abort();
  }, [runId, worldId]);

  return state;
}
