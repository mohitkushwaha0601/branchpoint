/**
 * The API client: does it read the backend correctly, and does it fail legibly?
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../api/errors";
import { getDemoState } from "../api/demo";
import {
  approveRun,
  getRun,
  getRunComparison,
  getRunEvents,
  getRunWorlds,
  listRuns,
  startRun,
} from "../api/runs";
import { getHealth } from "../api/system";
import {
  RUN_ID,
  comparisonDto,
  demoStateDto,
  eventsDto,
  mockServer,
  runDto,
  worldsDto,
} from "./apiFixtures";

afterEach(() => vi.unstubAllGlobals());

describe("successful calls", () => {
  it("reads a run, its events, worlds, comparison, and reality", async () => {
    mockServer({
      run: runDto(),
      events: eventsDto(),
      worlds: worldsDto(),
      comparison: comparisonDto(),
      demo: demoStateDto(),
      health: { status: "ok", service: "branchpoint-backend", version: "0.1.0" },
    });

    expect((await getRun(RUN_ID)).run_id).toBe(RUN_ID);
    expect((await getRunEvents(RUN_ID)).events).toHaveLength(5);
    expect((await getRunWorlds(RUN_ID)).worlds).toHaveLength(3);
    expect((await getRunComparison(RUN_ID)).recommended_world_id).toBe("world_beta");
    expect((await getDemoState()).feature_flag.enabled).toBe(true);
    expect((await listRuns()).runs).toHaveLength(1);
    expect((await getHealth()).status).toBe("ok");
  });

  it("starts a run and returns the accepted id", async () => {
    const server = mockServer({});

    const accepted = await startRun({
      objective: "o",
      title: "t",
      severity: "CRITICAL",
      affected_services: ["checkout"],
    });

    expect(accepted.run_id).toBe(RUN_ID);
    expect(accepted.status).toBe("CREATED");
    expect(server.calls).toContain("POST /api/v1/agent-runs");
  });
});

describe("error parsing", () => {
  it("turns a FastAPI detail into a typed ApiError", async () => {
    const server = mockServer({ run: runDto() });
    server.fail("/runs/", 404, "run run_x not found");

    const error = await getRun("run_x").catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(ApiError);
    const api = error as ApiError;
    expect(api.status).toBe(404);
    expect(api.detail).toBe("run run_x not found");
    expect(api.method).toBe("GET");
    expect(api.path).toBe("/api/v1/runs/run_x");
    expect(api.isNotFound).toBe(true);
  });

  it("marks a conflict so the UI can explain it", async () => {
    const server = mockServer({ run: runDto() });
    server.fail("/approval", 409, "approval does not match the bound action");

    const error = (await approveRun(RUN_ID, { actor: "release-engineer" }).catch(
      (caught: unknown) => caught,
    )) as ApiError;

    expect(error.isConflict).toBe(true);
    expect(error.detail).toBe("approval does not match the bound action");
  });

  it("reports an unreachable backend as status 0, not as a crash", async () => {
    const server = mockServer({});
    server.goOffline();

    const error = (await getRun(RUN_ID).catch((caught: unknown) => caught)) as ApiError;

    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(0);
    expect(error.isUnreachable).toBe(true);
    expect(error.detail).toBe("BRANCHPOINT backend unreachable");
  });

  it("survives a body that is not JSON", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response("<html>502 Bad Gateway</html>", {
            status: 502,
            headers: { "content-type": "text/html" },
          }),
      ),
    );

    const error = (await getRun(RUN_ID).catch((caught: unknown) => caught)) as ApiError;

    expect(error.status).toBe(502);
    expect(error.detail).toContain("502 Bad Gateway");
  });

  it("flattens a validation error list into one message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({ detail: [{ msg: "objective is required" }] }),
            { status: 422, headers: { "content-type": "application/json" } },
          ),
      ),
    );

    const error = (await getRun(RUN_ID).catch((caught: unknown) => caught)) as ApiError;

    expect(error.detail).toBe("objective is required");
  });
});

describe("cancellation", () => {
  it("propagates an abort rather than turning it into an error banner", async () => {
    mockServer({ run: runDto() });
    const controller = new AbortController();
    controller.abort();

    const error = await getRun(RUN_ID, controller.signal).catch(
      (caught: unknown) => caught,
    );

    expect(error).toBeInstanceOf(DOMException);
    expect((error as DOMException).name).toBe("AbortError");
  });
});

describe("credentials", () => {
  it("sends no auth header and no credentials", async () => {
    const calls: RequestInit[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_input: unknown, init?: RequestInit) => {
        calls.push(init ?? {});
        return new Response(JSON.stringify(runDto()), {
          status: 200,
          headers: { "content-type": "application/json" },
        });
      }),
    );

    await getRun(RUN_ID);

    const init = calls[0]!;
    expect(init.credentials).toBeUndefined();
    expect(init.headers).toBeUndefined();
  });
});
