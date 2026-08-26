/**
 * The TRUEFORGE HARNESS view.
 *
 * What these tests defend is the claim the view makes: every row is something
 * TrueForge actually did. So they check both directions — that real trace
 * entries render as the capability they exercised, and that nothing appears
 * when the backend reported nothing.
 */

import { screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  RUN_ID,
  comparisonDto,
  demoStateDto,
  emptyHarnessTrace,
  eventsDto,
  harnessTraceDto,
  mockServer,
  runDto,
  unreachableHarnessTrace,
  worldsDto,
} from "./apiFixtures";
import { inspector, renderApp } from "./renderRun";

afterEach(() => vi.unstubAllGlobals());

function serveRun(harness = harnessTraceDto()) {
  return mockServer({
    run: runDto(),
    worlds: worldsDto(),
    comparison: comparisonDto(),
    events: eventsDto(),
    demo: demoStateDto(),
    harness,
  });
}

/** Open the drawer on the Harness tab and return it. */
async function openHarness() {
  const view = renderApp(`/runs/${RUN_ID}`);
  await screen.findByRole("heading", { level: 1, name: "Checkout Regression" });
  await view.user.click(await screen.findByRole("button", { name: /SHOW/ }));
  const panel = await screen.findByRole("tabpanel", { name: "Harness" });
  return { ...view, panel };
}

describe("harness trace", () => {
  it("is the drawer's leading tab", async () => {
    serveRun();
    const { panel } = await openHarness();

    expect(panel).toBeInTheDocument();
    expect(within(panel).getByText("TRUEFORGE HARNESS")).toBeInTheDocument();
  });

  it("shows the MCP tools TrueForge actually called", async () => {
    serveRun();
    const { panel } = await openHarness();

    await waitFor(() =>
      expect(
        within(panel).getByText("MCP · branchpoint_get_metrics"),
      ).toBeInTheDocument(),
    );
    expect(within(panel).getAllByText("MCP").length).toBeGreaterThan(0);
    expect(within(panel).getByText("branchpoint")).toBeInTheDocument();
  });

  it("shows the Daytona sandbox with its real id", async () => {
    serveRun();
    const { panel } = await openHarness();

    await waitFor(() =>
      expect(within(panel).getByText("Daytona sandbox created")).toBeInTheDocument(),
    );
    expect(within(panel).getByText("v1:daytona:4a19c72e")).toBeInTheDocument();
    expect(within(panel).getByText("SANDBOX")).toBeInTheDocument();
  });

  it("shows a successful sandbox exec with its exit code", async () => {
    serveRun();
    const { panel } = await openHarness();

    await waitFor(() =>
      expect(within(panel).getByText("Sandbox exec completed")).toBeInTheDocument(),
    );
    expect(within(panel).getByText("exitCode 0")).toBeInTheDocument();
    expect(within(panel).getByText("EXEC")).toBeInTheDocument();
  });

  it("shows the real subagent delegation", async () => {
    serveRun();
    const { panel } = await openHarness();

    await waitFor(() =>
      expect(
        within(panel).getByText("Subagent · Compatibility Skeptic"),
      ).toBeInTheDocument(),
    );
    expect(within(panel).getByText("SUBAGENT")).toBeInTheDocument();
  });

  it("shows the human approval checkpoint and the tool it paused", async () => {
    serveRun();
    const { panel } = await openHarness();

    await waitFor(() =>
      expect(within(panel).getByText("Human approval required")).toBeInTheDocument(),
    );
    expect(within(panel).getByText("APPROVAL")).toBeInTheDocument();
  });

  it("lists the TrueForge session ids the run is bound to", async () => {
    serveRun();
    const { panel } = await openHarness();

    await waitFor(() =>
      expect(within(panel).getByText("sess_planner")).toBeInTheDocument(),
    );
    expect(within(panel).getByText("sess_alpha")).toBeInTheDocument();
    expect(within(panel).getByText("PLANNER")).toBeInTheDocument();
    expect(within(panel).getByText("ADVERSARY")).toBeInTheDocument();
  });

  it("selects a world when a world-scoped trace row is activated", async () => {
    serveRun();
    const { user, panel } = await openHarness();
    await waitFor(() =>
      expect(within(panel).getByText("Daytona sandbox created")).toBeInTheDocument(),
    );

    await user.click(
      within(panel).getByRole("button", { name: /Daytona sandbox created/ }),
    );

    expect(
      within(inspector()).getAllByText("Rollback Pricing Deployment").length,
    ).toBeGreaterThan(0);
  });
});

describe("nothing is invented", () => {
  it("shows no harness rows when the backend reported none", async () => {
    serveRun(emptyHarnessTrace());
    const { panel } = await openHarness();

    await waitFor(() =>
      expect(
        within(panel).getByText("No TrueForge harness activity recorded yet."),
      ).toBeInTheDocument(),
    );
    // Not one capability row appears without a real event behind it.
    for (const label of ["SANDBOX", "EXEC", "SUBAGENT", "APPROVAL"]) {
      expect(within(panel).queryByText(label)).not.toBeInTheDocument();
    }
  });

  it("leaks no fixture harness data into a live run", async () => {
    serveRun(emptyHarnessTrace());
    const { panel } = await openHarness();

    await waitFor(() =>
      expect(
        within(panel).getByText("No TrueForge harness activity recorded yet."),
      ).toBeInTheDocument(),
    );
    expect(panel.textContent).not.toContain("Compatibility Skeptic");
    expect(panel.textContent).not.toContain("v1:daytona");
    expect(panel.textContent).not.toContain("sbx_");
  });

  it("says TrueForge is unreachable rather than showing an empty timeline", async () => {
    serveRun(unreachableHarnessTrace());
    const { panel } = await openHarness();

    await waitFor(() =>
      expect(within(panel).getByText("TRUEFORGE UNREACHABLE")).toBeInTheDocument(),
    );
    expect(
      within(panel).getByText(/Session bindings above are BRANCHPOINT's own record/),
    ).toBeInTheDocument();
    // BRANCHPOINT's own record of the sessions survives the harness being down.
    expect(within(panel).getByText("sess_planner")).toBeInTheDocument();
    expect(within(panel).queryByText("SESSION CONTINUITY · RESTORED")).not.toBeInTheDocument();
  });

  it("keeps the run page working when the harness cannot be read", async () => {
    serveRun(unreachableHarnessTrace());
    renderApp(`/runs/${RUN_ID}`);

    // The graph, the header, and the gate are all unaffected.
    expect(
      await screen.findByRole("heading", { level: 1, name: "Checkout Regression" }),
    ).toBeInTheDocument();
    expect(
      await screen.findByRole("heading", { name: "HUMAN CHECKPOINT" }),
    ).toBeInTheDocument();
  });
});

describe("session continuity", () => {
  it("reports continuity from the backend's bindings, not from the browser", async () => {
    serveRun();
    const { panel } = await openHarness();

    await waitFor(() =>
      expect(
        within(panel).getByText("SESSION CONTINUITY · RESTORED"),
      ).toBeInTheDocument(),
    );
    // Nothing client-side is holding these ids.
    expect(window.localStorage.getItem("branchpoint.sessions")).toBeNull();
  });

  it("shows the same session ids after a reload of the same run", async () => {
    const server = serveRun();
    const first = await openHarness();
    await waitFor(() =>
      expect(within(first.panel).getByText("sess_alpha")).toBeInTheDocument(),
    );
    const before = within(first.panel)
      .getAllByText(/^sess_/)
      .map((node) => node.textContent);

    // A browser refresh is exactly this: tear the app down, mount it again at
    // the same route, and ask the same backend.
    first.unmount();
    const second = await openHarness();

    await waitFor(() =>
      expect(within(second.panel).getByText("sess_alpha")).toBeInTheDocument(),
    );
    const after = within(second.panel)
      .getAllByText(/^sess_/)
      .map((node) => node.textContent);

    expect(after).toEqual(before);
    expect(after).toEqual(["sess_planner", "sess_alpha"]);
    // No second drive: the reload only ever issued reads.
    expect(server.posts).toEqual([]);
  });

  it("does not re-read the trace on every poll tick", async () => {
    const server = serveRun();
    await openHarness();
    await waitFor(() =>
      expect(
        server.calls.filter((call) => call.includes("harness-trace")).length,
      ).toBeGreaterThan(0),
    );
    const afterFirst = server.calls.filter((c) => c.includes("harness-trace")).length;

    await new Promise((resolve) => setTimeout(resolve, 500));

    // The run is AWAITING_APPROVAL, so nothing is moving and nothing re-reads.
    expect(server.calls.filter((c) => c.includes("harness-trace")).length).toBe(
      afterFirst,
    );
  });
});
