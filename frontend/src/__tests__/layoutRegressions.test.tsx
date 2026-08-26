/**
 * Layout regressions caught by rendering the app in a real browser at the
 * resolutions it is presented on.
 *
 * Every case here is a defect that was live and visible on screen — none is a
 * speculative guard. Geometry itself cannot be asserted under jsdom, so each
 * test pins the *mechanism* that was wrong, at the level the fix was made.
 */

import { screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  RUN_ID,
  comparisonDto,
  demoStateDto,
  eventsDto,
  mockServer,
  runDto,
  worldsDto,
} from "./apiFixtures";
import { renderApp } from "./renderRun";

afterEach(() => vi.unstubAllGlobals());

function serve(run = runDto()) {
  return mockServer({
    run,
    worlds: worldsDto(),
    comparison: comparisonDto(),
    events: eventsDto(),
    demo: demoStateDto(),
  });
}

async function gateSection() {
  const heading = await screen.findByRole("heading", {
    name: /HUMAN CHECKPOINT|HUMAN DECISION/,
  });
  return heading.closest("section")!;
}

describe("the human checkpoint stays reachable", () => {
  /**
   * At 1440x900 the gate opened 249px below the fold, with Approve 507px below
   * it — the climax of the demo was behind ~840px of scrolling past the very
   * branches it asks you to judge. It is now pinned to the bottom of the canvas
   * while a decision is outstanding.
   */
  it("pins the gate to the canvas while a decision is outstanding", async () => {
    serve();
    renderApp(`/runs/${RUN_ID}`);

    const gate = await gateSection();
    expect(gate.className).toContain("sticky");
    expect(gate.className).toContain("bottom-0");
  });

  it("releases the pin once the run is no longer awaiting a decision", async () => {
    serve(
      runDto({
        status: "SUCCEEDED",
        commit_status: "SUCCEEDED",
        verification_status: "PASSED",
      }),
    );
    renderApp(`/runs/${RUN_ID}`);

    const gate = await gateSection();
    expect(gate.className).not.toContain("sticky");
  });

  /**
   * The gate is a child of the scrolling canvas, not a floating overlay. That
   * is what keeps the bottom drawer — a flex sibling of the canvas — unable to
   * cover the Approve and Reject controls no matter how far it expands.
   */
  it("keeps the gate inside the canvas so the drawer cannot cover it", async () => {
    serve();
    renderApp(`/runs/${RUN_ID}`);

    const gate = await gateSection();
    expect(gate.closest("main")).not.toBeNull();
  });
});

describe("the bound fingerprint is shown in full", () => {
  /**
   * A real action fingerprint is a 64-character SHA-256. Rendered as a
   * right-aligned cell it ran past the column and was clipped mid-hash, with no
   * ellipsis to say so — on the one value whose exact characters are the point.
   */
  it("renders every character of a full SHA-256 fingerprint", async () => {
    const fingerprint =
      "9f2c1b7ae04d3856b1cc7d29e5a40f6318bd92c47e0a5f816b3d7c92a4e850fb";
    const run = runDto();
    serve({ ...run, approval: { ...run.approval!, action_fingerprint: fingerprint } });
    renderApp(`/runs/${RUN_ID}`);

    const gate = await gateSection();
    const shown = within(gate).getByText(fingerprint);
    expect(shown.textContent).toBe(fingerprint);
    // Allowed to wrap rather than being cut off at the column edge.
    expect(shown.className).toContain("break-all");
  });
});

describe("the rejection panel behaves like the dialog it stands in for", () => {
  it("closes on Escape and restores the decision controls", async () => {
    serve();
    const { user } = renderApp(`/runs/${RUN_ID}`);

    const gate = await gateSection();
    await user.click(within(gate).getByRole("button", { name: "Reject" }));
    await screen.findByLabelText(/WHY ARE YOU DECLINING/);

    await user.keyboard("{Escape}");

    await waitFor(() =>
      expect(screen.queryByLabelText(/WHY ARE YOU DECLINING/)).toBeNull(),
    );
    expect(
      within(gate).getByRole("button", { name: "Approve & Commit" }),
    ).toBeInTheDocument();
  });

  /**
   * "Approve & Commit" and "Submitting…" are very different widths. A control
   * that shrinks under the cursor at the moment it is pressed reads as a
   * glitch, so both submit buttons carry a fixed minimum footprint.
   */
  it("gives the submit controls a footprint that survives the label change", async () => {
    serve();
    const { user } = renderApp(`/runs/${RUN_ID}`);

    const gate = await gateSection();
    expect(
      within(gate).getByRole("button", { name: "Approve & Commit" }).className,
    ).toContain("min-w-[148px]");

    await user.click(within(gate).getByRole("button", { name: "Reject" }));
    expect(
      within(gate).getByRole("button", { name: "Confirm rejection" }).className,
    ).toContain("min-w-[148px]");
  });
});

describe("the UI does not report gaps that are not there", () => {
  /**
   * Every live lane read "Hypothesis text unavailable from current API." The
   * hypothesis is not unavailable — it is served by
   * `GET /runs/{id}/worlds/{world_id}`, which the Inspector fetches on
   * selection. The lane renders from the run summary, which carries counts.
   * Claiming a backend deficiency that does not exist reads as a broken API.
   */
  it("points at where the hypothesis loads instead of claiming the API lacks it", async () => {
    serve();
    renderApp(`/runs/${RUN_ID}`);

    await screen.findByRole("heading", { level: 1, name: "Checkout Regression" });
    await waitFor(() =>
      expect(
        screen.getAllByText(/Open this world to read/).length,
      ).toBeGreaterThan(0),
    );
    expect(screen.queryByText(/unavailable from current API/)).toBeNull();
  });
});
