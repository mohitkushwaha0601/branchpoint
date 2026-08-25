/**
 * Polling loop for one live run.
 *
 * Three things it must get right, all of which are silent failures if it does
 * not:
 *
 * *Staleness.* Every request carries the run id it was issued for. A response
 * that arrives after the user navigated to another run is dropped, so an old
 * run can never paint over a new one.
 *
 * *Cleanup.* Unmounting or changing run aborts the in-flight requests and
 * cancels the next tick. No timer outlives the view that started it.
 *
 * *Cadence.* Polling exists to watch a run move. Once it stops moving — waiting
 * on a human, or terminal — the loop stops with it rather than asking a settled
 * backend the same question forever.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { getDemoState } from "../api/demo";
import { ApiError, isAbortError } from "../api/errors";
import {
  getRun,
  getRunComparison,
  getRunEvents,
  getRunWorlds,
} from "../api/runs";
import type {
  ComparisonDetailDto,
  DemoStateDto,
  RunDto,
  RunEventDto,
  WorldsDto,
} from "../api/types";
import { adaptRun } from "../adapters/runAdapter";
import type { Run } from "../types/run";
import { isRunActive } from "../types/run";

/** How often to re-read a run that is still advancing. */
const ACTIVE_INTERVAL_MS = 1200;

export interface LiveRunState {
  run: Run | null;
  /** True only until the first response for this run id arrives. */
  loading: boolean;
  error: ApiError | null;
  /** Whether the loop is still polling. */
  polling: boolean;
  /** Re-read everything now — after an approval, or from a retry button. */
  refresh: () => void;
}

interface Snapshot {
  run: RunDto;
  events: RunEventDto[];
  worlds: WorldsDto | null;
  comparison: ComparisonDetailDto | null;
  demo: DemoStateDto | null;
}

/**
 * Fetch one complete picture of a run.
 *
 * `GET /runs/{id}` is the authoritative source and the only required call; it
 * already carries status, worlds, comparison, approval binding, and commit and
 * verification outcome. The rest is detail fetched only once the run has
 * something to say — asking for worlds before forking, or a comparison before
 * comparing, would be a guaranteed 404/409 every tick.
 */
async function fetchSnapshot(runId: string, signal: AbortSignal): Promise<Snapshot> {
  const run = await getRun(runId, signal);

  const wantWorlds = run.worlds.length > 0;
  const wantComparison = run.comparison !== null;

  const [events, worlds, comparison, demo] = await Promise.all([
    getRunEvents(runId, signal).then(
      (payload) => payload.events,
      () => [] as RunEventDto[],
    ),
    wantWorlds
      ? getRunWorlds(runId, signal).then(
          (payload) => payload,
          () => null,
        )
      : Promise.resolve(null),
    wantComparison
      ? getRunComparison(runId, signal).then(
          (payload) => payload,
          () => null,
        )
      : Promise.resolve(null),
    getDemoState(signal).then(
      (payload) => payload,
      () => null,
    ),
  ]);

  return { run, events, worlds, comparison, demo };
}

export function useLiveRun(runId: string | undefined): LiveRunState {
  const [run, setRun] = useState<Run | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);
  const [polling, setPolling] = useState(false);
  const [refreshToken, setRefreshToken] = useState(0);

  const refresh = useCallback(() => setRefreshToken((token) => token + 1), []);

  // Cleared on every run change so the previous run's data cannot linger on
  // screen under the new run's id.
  useEffect(() => {
    setRun(null);
    setLoading(true);
    setError(null);
  }, [runId]);

  const activeRunId = useRef<string | undefined>(runId);
  activeRunId.current = runId;

  useEffect(() => {
    if (runId === undefined) return;

    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let stopped = false;

    const tick = async (): Promise<void> => {
      try {
        const snapshot = await fetchSnapshot(runId, controller.signal);
        // The user may have navigated while this was in flight.
        if (stopped || activeRunId.current !== runId) return;

        setRun(adaptRun(snapshot));
        setError(null);
        setLoading(false);

        if (isRunActive(snapshot.run.status)) {
          setPolling(true);
          timer = setTimeout(() => void tick(), ACTIVE_INTERVAL_MS);
        } else {
          // Waiting on a human, or finished. Nothing further arrives on its own.
          setPolling(false);
        }
      } catch (caught) {
        if (stopped || isAbortError(caught) || activeRunId.current !== runId) return;
        setError(
          caught instanceof ApiError
            ? caught
            : new ApiError({
                status: 0,
                detail: "BRANCHPOINT backend unreachable",
                method: "GET",
                path: `/api/v1/runs/${runId}`,
              }),
        );
        setLoading(false);
        setPolling(false);
      }
    };

    void tick();

    return () => {
      stopped = true;
      setPolling(false);
      if (timer !== undefined) clearTimeout(timer);
      controller.abort();
    };
  }, [runId, refreshToken]);

  return { run, loading, error, polling, refresh };
}
