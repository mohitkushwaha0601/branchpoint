/**
 * The live Mission Control path, end to end against a mocked backend.
 *
 * These are the assertions that would let a real regression through if they
 * were missing: that the UI advances only when the backend does, that approval
 * carries a binding and never an action, and that a failure is shown rather
 * than papered over with fixture data.
 */

import { screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ApprovalRequest } from "../api/types";
import {
  RUN_ID,
  comparisonDto,
  demoStateDto,
  eventsDto,
  mockServer,
  runDto,
  worldsDto,
  youngRunDto,
} from "./apiFixtures";
import { inspector, lane, renderApp } from "./renderRun";

afterEach(() => vi.unstubAllGlobals());

function serveSettledRun(overrides = {}) {
  return mockServer({
    run: runDto(overrides),
    worlds: worldsDto(),
    comparison: comparisonDto(),
    events: eventsDto(),
    demo: demoStateDto(),
  });
}

describe("starting a run", () => {
  it("navigates to the run id the backend returned", async () => {
    const server = mockServer({
      run: runDto(),
      worlds: worldsDto(),
      comparison: comparisonDto(),
      events: eventsDto(),
      demo: demoStateDto(),
    });
    const { user } = renderApp("/runs");

    await user.click(
      await screen.findByRole("button", { name: "Run BRANCHPOINT" }),
    );

    // Landed on the run page for exactly the id the POST returned.
    expect(
      await screen.findByRole("heading", { level: 1, name: "Checkout Regression" }),
    ).toBeInTheDocument();
    expect(await screen.findByText(RUN_ID)).toBeInTheDocument();
    expect(server.posts[0]?.path).toBe("/api/v1/agent-runs");
  });

  it("sends the demo incident and disables the button once accepted", async () => {
    const server = mockServer({ run: youngRunDto("CREATED"), demo: demoStateDto() });
    const { user } = renderApp("/runs");

    const button = await screen.findByRole("button", { name: "Run BRANCHPOINT" });
    await user.click(button);

    const body = server.posts[0]?.body as Record<string, unknown>;
    expect(body["title"]).toBe("Checkout Regression");
    expect(body["severity"]).toBe("CRITICAL");
    expect(body["affected_services"]).toEqual(["checkout", "pricing-service"]);
    expect(
      server.posts.filter((post) => post.path === "/api/v1/agent-runs"),
    ).toHaveLength(1);
  });

  it("reports a refusal instead of navigating", async () => {
    const server = mockServer({});
    server.fail("/agent-runs", 503, "no model configured");
    const { user } = renderApp("/runs");

    await user.click(
      await screen.findByRole("button", { name: "Run BRANCHPOINT" }),
    );

    expect(await screen.findByText("no model configured")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Runs" })).toBeInTheDocument();
  });
});

describe("lifecycle progression", () => {
  it("shows a young run before it has any worlds", async () => {
    mockServer({ run: youngRunDto("OBSERVING"), demo: demoStateDto() });
    renderApp(`/runs/${RUN_ID}`);

    const waiting = await screen.findAllByText("Waiting for worlds…");
    expect(waiting.length).toBeGreaterThan(0);
    const rail = screen.getByRole("navigation", { name: "Run stages" });
    expect(rail.querySelector('[aria-current="step"]')).toHaveTextContent("OBSERVE");
  });

  it("advances the stage rail as the backend advances, and no sooner", async () => {
    const server = mockServer({
      run: youngRunDto("OBSERVING"),
      demo: demoStateDto(),
      events: { events: [] },
    });
    renderApp(`/runs/${RUN_ID}`);

    const rail = async () =>
      (await screen.findByRole("navigation", { name: "Run stages" })).querySelector(
        '[aria-current="step"]',
      );
    expect(await rail()).toHaveTextContent("OBSERVE");

    const nextPoll = { timeout: 4000 };

    server.set({ run: youngRunDto("PLANNING") });
    await waitFor(async () => expect(await rail()).toHaveTextContent("PLAN"), nextPoll);

    server.set({ run: youngRunDto("ADVERSARIAL_TESTING") });
    await waitFor(async () => expect(await rail()).toHaveTextContent("ATTACK"), nextPoll);

    server.set({
      run: runDto(),
      worlds: worldsDto(),
      comparison: comparisonDto(),
      events: eventsDto(),
    });
    await waitFor(async () => expect(await rail()).toHaveTextContent("APPROVE"), nextPoll);
  });

  it("renders the real worlds once the backend reports them", async () => {
    serveSettledRun();
    renderApp(`/runs/${RUN_ID}`);

    await screen.findByRole("heading", { level: 1, name: "Checkout Regression" });
    await waitFor(() => expect(lane("WORLD α")).toBeInTheDocument());

    expect(within(lane("WORLD α")).getByText("VETOED")).toBeInTheDocument();
    expect(within(lane("WORLD β")).getByText("SURVIVED")).toBeInTheDocument();
    expect(within(lane("WORLD γ")).getByText("SURVIVED")).toBeInTheDocument();
    expect(screen.getAllByText("RECOMMENDED").length).toBeGreaterThan(0);
  });

  it("stops polling once the run is waiting on a human", async () => {
    const server = serveSettledRun();
    renderApp(`/runs/${RUN_ID}`);

    await screen.findByRole("heading", { level: 1, name: "Checkout Regression" });
    await waitFor(() => expect(lane("WORLD β")).toBeInTheDocument());
    const settled = server.calls.filter((call) => call.includes(`/runs/${RUN_ID}`)).length;

    await new Promise((resolve) => setTimeout(resolve, 400));

    expect(
      server.calls.filter((call) => call.includes(`/runs/${RUN_ID}`)).length,
    ).toBe(settled);
  });

  it("cleans up its polling when the view unmounts", async () => {
    const server = mockServer({ run: youngRunDto("PLANNING"), demo: demoStateDto() });
    const { unmount } = renderApp(`/runs/${RUN_ID}`);

    await screen.findAllByText("Waiting for worlds…");
    unmount();
    const afterUnmount = server.calls.length;

    await new Promise((resolve) => setTimeout(resolve, 400));

    expect(server.calls.length).toBe(afterUnmount);
  });
});

describe("real events", () => {
  it("lists the backend's events and nothing else", async () => {
    serveSettledRun();
    const { user } = renderApp(`/runs/${RUN_ID}`);

    await screen.findByRole("heading", { level: 1, name: "Checkout Regression" });
    await user.click(await screen.findByRole("button", { name: /SHOW/ }));
    await user.click(screen.getByRole("tab", { name: "Events" }));

    const panel = screen.getByRole("tabpanel", { name: "Events" });
    expect(within(panel).getByText("run opened for incident incident_1")).toBeInTheDocument();
    expect(within(panel).getByText("world_alpha VETOED")).toBeInTheDocument();
    // Fixture-only events must not appear in a live run.
    expect(within(panel).queryByText("Daytona sandbox created")).not.toBeInTheDocument();
    expect(within(panel).queryAllByRole("listitem")).toHaveLength(5);
  });

  it("selects a world when its event is activated", async () => {
    serveSettledRun();
    const { user } = renderApp(`/runs/${RUN_ID}`);

    await screen.findByRole("heading", { level: 1, name: "Checkout Regression" });
    await user.click(await screen.findByRole("button", { name: /SHOW/ }));
    await user.click(screen.getByRole("tab", { name: "Events" }));
    await user.click(
      within(screen.getByRole("tabpanel", { name: "Events" })).getByRole("button", {
        name: /world_alpha VETOED/,
      }),
    );

    expect(
      within(inspector()).getAllByText("Rollback Pricing Deployment").length,
    ).toBeGreaterThan(0);
  });
});

describe("evidence authority under live data", () => {
  it("keeps EXPLORATORY and VERIFIED distinct and says what is missing", async () => {
    serveSettledRun();
    renderApp(`/runs/${RUN_ID}`);

    await screen.findByRole("heading", { level: 1, name: "Checkout Regression" });
    await waitFor(() => expect(lane("WORLD α")).toBeInTheDocument());

    const alpha = within(lane("WORLD α"));
    const sandbox = within(alpha.getByRole("region", { name: "DOPPELGÄNGER evidence" }));
    expect(sandbox.getByText("EXPLORATORY")).toBeInTheDocument();
    expect(sandbox.queryByText("VERIFIED")).not.toBeInTheDocument();

    const replay = within(
      alpha.getByRole("region", { name: "BRANCHPOINT replay evidence" }),
    );
    expect(replay.getByText("VERIFIED")).toBeInTheDocument();
    // The count is live; the rows behind it are on the world-detail resource.
    expect(replay.getByText("reproduced counterexamples")).toBeInTheDocument();
  });

  it("says where evidence rows load from rather than showing an empty list", async () => {
    serveSettledRun();
    renderApp(`/runs/${RUN_ID}`);

    await screen.findByRole("heading", { level: 1, name: "Checkout Regression" });
    await waitFor(() =>
      expect(
        within(inspector()).getByText("Evidence rows load with this world’s detail."),
      ).toBeInTheDocument(),
    );
  });
});

describe("approval", () => {
  async function reachTheGate() {
    const server = serveSettledRun();
    const view = renderApp(`/runs/${RUN_ID}`);
    await screen.findByRole("heading", { level: 1, name: "Checkout Regression" });
    await screen.findByRole("heading", { name: "HUMAN CHECKPOINT" });
    return { server, ...view };
  }

  it("sends the bound world, action, and fingerprint — and no action content", async () => {
    const { server, user } = await reachTheGate();

    await user.click(screen.getByRole("button", { name: "Approve & Commit" }));

    await waitFor(() =>
      expect(server.posts.some((post) => post.path.endsWith("/approval"))).toBe(true),
    );
    const body = server.posts.find((post) => post.path.endsWith("/approval"))!
      .body as ApprovalRequest & Record<string, unknown>;

    expect(body.actor).toBe("release-engineer");
    expect(body.expected_world_id).toBe("world_beta");
    expect(body.expected_action_id).toBe("action_b8e2");
    expect(body.expected_action_fingerprint).toBe("3d7a1e05c94b2f6d");

    // Nothing that could name a different action, and no capability request.
    expect(Object.keys(body).sort()).toEqual([
      "actor",
      "expected_action_fingerprint",
      "expected_action_id",
      "expected_world_id",
    ]);
    expect(
      server.calls.some((call) => call.includes("commit-capability")),
    ).toBe(false);
  });

  it("prevents a duplicate submission", async () => {
    const { server, user } = await reachTheGate();

    const button = screen.getByRole("button", { name: "Approve & Commit" });
    await user.click(button);
    await waitFor(() =>
      expect(server.posts.filter((p) => p.path.endsWith("/approval"))).toHaveLength(1),
    );
    // The button is gone once submitted, so a second press is impossible.
    expect(
      screen.queryByRole("button", { name: "Approve & Commit" }),
    ).not.toBeInTheDocument();
    expect(server.posts.filter((p) => p.path.endsWith("/approval"))).toHaveLength(1);
  });

  it("explains a 409 conflict instead of proceeding", async () => {
    const { server, user } = await reachTheGate();
    server.fail("/approval", 409, "approval does not match the bound action");

    await user.click(screen.getByRole("button", { name: "Approve & Commit" }));

    // The backend's own detail is shown, not a canned line — a 409 means
    // different things for approval and rejection, and only it knows which.
    expect(
      await screen.findByText("approval does not match the bound action"),
    ).toBeInTheDocument();
    expect(screen.getByText("Re-read the run before deciding again.")).toBeInTheDocument();
    expect(screen.queryByText(/committed and independently verified/i)).not.toBeInTheDocument();
  });

  it("shows COMMITTING only when the backend reports COMMITTING", async () => {
    serveSettledRun({ status: "COMMITTING", commit_status: "PENDING" });
    renderApp(`/runs/${RUN_ID}`);

    expect(
      await screen.findByText("Committing the approved action…"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("Committed and independently verified"),
    ).not.toBeInTheDocument();
  });

  it("shows VERIFYING only when the backend reports VERIFYING", async () => {
    serveSettledRun({ status: "VERIFYING", commit_status: "SUCCEEDED" });
    renderApp(`/runs/${RUN_ID}`);

    expect(
      await screen.findByText("Verifying reality independently…"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("Committed and independently verified"),
    ).not.toBeInTheDocument();
  });

  it("advances from committing to verified as the backend does", async () => {
    const server = serveSettledRun({ status: "COMMITTING", commit_status: "PENDING" });
    renderApp(`/runs/${RUN_ID}`);
    await screen.findByText("Committing the approved action…");

    server.set({
      run: runDto({
        status: "SUCCEEDED",
        commit_status: "SUCCEEDED",
        verification_status: "PASSED",
      }),
    });

    expect(
      await screen.findByText("Committed and independently verified", undefined, {
        timeout: 4000,
      }),
    ).toBeInTheDocument();
  });

  it("declares success only from the backend's own status", async () => {
    const server = serveSettledRun({
      status: "SUCCEEDED",
      commit_status: "SUCCEEDED",
      verification_status: "PASSED",
    });
    server.set({ demo: demoStateDto(false) });
    renderApp(`/runs/${RUN_ID}`);

    expect(
      await screen.findByText("Committed and independently verified"),
    ).toBeInTheDocument();
    expect(screen.getAllByText("SUCCEEDED").length).toBeGreaterThan(0);
  });

  it("shows reality changing after a successful commit", async () => {
    serveSettledRun({
      status: "SUCCEEDED",
      commit_status: "SUCCEEDED",
      verification_status: "PASSED",
    });
    mockServer({
      run: runDto({
        status: "SUCCEEDED",
        commit_status: "SUCCEEDED",
        verification_status: "PASSED",
      }),
      worlds: worldsDto(),
      comparison: comparisonDto(),
      events: eventsDto(),
      demo: demoStateDto(false),
    });
    renderApp(`/runs/${RUN_ID}`);

    const reality = within(
      await screen.findByRole("region", { name: "CURRENT REALITY" }),
    );
    expect(await reality.findByText("OFF")).toBeInTheDocument();
    expect(screen.getByText(/CURRENT REALITY/)).toHaveTextContent("VERIFIED CHANGE");
  });

  it("labels reality as unchanged while nothing has been committed", async () => {
    serveSettledRun();
    renderApp(`/runs/${RUN_ID}`);

    const heading = await screen.findByRole("region", { name: "CURRENT REALITY" });
    expect(within(heading).getByText("ON")).toBeInTheDocument();
    expect(heading).toHaveTextContent("UNCHANGED");
  });
});

describe("backend unreachable", () => {
  it("says so, keeps navigation, and shows no fixture data", async () => {
    const server = mockServer({});
    server.goOffline();
    renderApp(`/runs/${RUN_ID}`);

    expect(
      await screen.findByText("BRANCHPOINT backend unreachable"),
    ).toBeInTheDocument();

    // Navigation survives.
    expect(screen.getByRole("navigation", { name: "Primary" })).toBeInTheDocument();
    // No hero fallback anywhere.
    expect(screen.queryByText("Disable Pricing V2")).not.toBeInTheDocument();
    expect(screen.queryByText("world_beta")).not.toBeInTheDocument();
  });

  it("offers a retry that re-reads the run", async () => {
    const server = mockServer({ run: runDto() });
    server.fail("/runs/run_dbfa98c87f06", 500, "internal error");
    const { user } = renderApp(`/runs/${RUN_ID}`);

    await screen.findByText("Could not load this run");
    server.set({ worlds: worldsDto(), comparison: comparisonDto(), demo: demoStateDto() });
    await user.click(screen.getByRole("button", { name: /Retry/ }));

    expect(
      await screen.findByRole("heading", { level: 1, name: "Checkout Regression" }),
    ).toBeInTheDocument();
  });

  it("explains a missing run instead of offering a retry that cannot work", async () => {
    const server = mockServer({});
    renderApp("/runs/run_missing");

    expect(await screen.findByText("Run no longer exists")).toBeInTheDocument();
    expect(
      screen.getByText(/stores active BRANCHPOINT runs in process memory/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Nothing was committed and reality is\s+unchanged/),
    ).toBeInTheDocument();
    // A way forward, not a Retry against a run that is gone. Scoped to the
    // canvas: the sidebar always carries a start button of its own.
    const canvas = within(screen.getByRole("main"));
    expect(canvas.getByRole("button", { name: "Run BRANCHPOINT" })).toBeEnabled();
    expect(canvas.queryByRole("button", { name: /Retry/ })).not.toBeInTheDocument();

    // The 404 on the run is authoritative: its children are not asked about.
    await new Promise((resolve) => setTimeout(resolve, 300));
    expect(server.calls.some((call) => call.includes("harness-trace"))).toBe(false);
    expect(server.calls.some((call) => call.includes("/worlds/"))).toBe(false);
  });
});
