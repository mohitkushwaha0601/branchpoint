/**
 * The human rejection flow.
 *
 * Two things these tests defend. First, that a refusal is a *real* backend
 * decision — the request goes out, it carries no action content, and the
 * outcome is read back rather than assumed. Second, that a rejection never
 * reads as a veto: they are different layers, and a judge must be able to see
 * which one happened at a glance.
 */

import { screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  RUN_ID,
  comparisonDto,
  demoStateDto,
  eventsDto,
  mockServer,
  rejectedRunDto,
  runDto,
  worldsDto,
} from "./apiFixtures";
import { APPROVAL_ACTOR } from "../app/runView";
import { lane, renderApp } from "./renderRun";

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

async function openGate() {
  const view = renderApp(`/runs/${RUN_ID}`);
  const gate = await screen.findByRole("heading", {
    name: /MANUAL APPROVAL REQUIRED|HUMAN APPROVAL/,
  });
  return { ...view, gate: gate.closest("section")! };
}

/** Press Reject, type a reason, confirm. */
async function rejectWith(
  user: ReturnType<typeof renderApp>["user"],
  gate: HTMLElement,
  reason: string,
) {
  await user.click(within(gate).getByRole("button", { name: "Reject" }));
  if (reason) {
    await user.type(within(gate).getByLabelText(/WHY ARE YOU DECLINING/), reason);
  }
  await user.click(within(gate).getByRole("button", { name: "Confirm rejection" }));
}

// ----- 1-3. the interaction and the request ----------------------------------

describe("the decision", () => {
  it("offers approve and reject while a decision is pending", async () => {
    serve();
    const { gate } = await openGate();

    expect(within(gate).getByText("AWAITING HUMAN DECISION")).toBeInTheDocument();
    expect(within(gate).getByRole("button", { name: "Reject" })).toBeEnabled();
    expect(
      within(gate).getByRole("button", { name: "Approve & Commit" }),
    ).toBeEnabled();
  });

  it("collects a reason before submitting", async () => {
    const server = serve();
    const { user, gate } = await openGate();

    await user.click(within(gate).getByRole("button", { name: "Reject" }));

    // Nothing is sent on the first press: the operator gets to say why first.
    expect(server.posts.filter((p) => p.path.endsWith("/rejection"))).toHaveLength(0);
    expect(within(gate).getByLabelText(/WHY ARE YOU DECLINING/)).toBeInTheDocument();
    expect(
      within(gate).getByRole("button", { name: "Confirm rejection" }),
    ).toBeInTheDocument();
  });

  it("can be backed out of without deciding anything", async () => {
    const server = serve();
    const { user, gate } = await openGate();

    await user.click(within(gate).getByRole("button", { name: "Reject" }));
    await user.click(within(gate).getByRole("button", { name: "Cancel" }));

    expect(server.posts).toEqual([]);
    expect(within(gate).getByRole("button", { name: "Approve & Commit" })).toBeEnabled();
  });

  it("sends the actor and reason, and no action content", async () => {
    const server = serve();
    const { user, gate } = await openGate();

    await rejectWith(user, gate, "Rollback risk is unacceptable.");

    await waitFor(() =>
      expect(server.posts.some((p) => p.path.endsWith("/rejection"))).toBe(true),
    );
    const post = server.posts.find((p) => p.path.endsWith("/rejection"))!;
    expect(post.path).toBe(`/api/v1/runs/${RUN_ID}/rejection`);

    const body = post.body as Record<string, unknown>;
    expect(body["actor"]).toBe("release-engineer");
    expect(body["reason"]).toBe("Rollback risk is unacceptable.");
    // Nothing that could name a different action, and no capability request.
    expect(Object.keys(body).sort()).toEqual(["actor", "reason"]);
    expect(server.calls.some((call) => call.includes("commit-capability"))).toBe(false);
    // A rejection is not an approval.
    expect(server.posts.some((p) => p.path.endsWith("/approval"))).toBe(false);
  });
});

// ----- 4-6. the outcome --------------------------------------------------------

describe("the outcome", () => {
  it("renders the human decision and its reason", async () => {
    const reason = "Rollback risk is unacceptable.";
    const server = serve();
    const { user, gate } = await openGate();
    // What the run says after the decision is what the panel reports.
    server.set({ run: rejectedRunDto(reason) });

    await rejectWith(user, gate, reason);

    const status = await screen.findByText("HUMAN DECISION · REJECTED");
    expect(status).toBeInTheDocument();
    const panel = within(status.closest("footer")!);
    expect(panel.getByText("release-engineer")).toBeInTheDocument();
    expect(panel.getByText(`“${reason}”`)).toBeInTheDocument();
  });

  it("stops offering a decision once one is made", async () => {
    const server = serve();
    const { user, gate } = await openGate();
    server.set({ run: rejectedRunDto() });

    await rejectWith(user, gate, "no");

    await screen.findByText("HUMAN DECISION · REJECTED");
    expect(screen.queryByRole("button", { name: "Reject" })).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Approve & Commit" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Confirm rejection" }),
    ).not.toBeInTheDocument();
  });

  it("names the operator the backend recorded, not this browser", async () => {
    // A decision made in another session, by someone else. Displaying this
    // browser's own actor would misattribute the decision to whoever happens
    // to be looking at the run.
    serve(rejectedRunDto("Change freeze is in effect.", "sre-oncall-priya"));
    renderApp(`/runs/${RUN_ID}`);

    const status = await screen.findByText("HUMAN DECISION · REJECTED");
    const panel = within(status.closest("footer")!);

    expect(panel.getByText("sre-oncall-priya")).toBeInTheDocument();
    expect(panel.queryByText(APPROVAL_ACTOR)).not.toBeInTheDocument();
    expect(panel.getByText("“Change freeze is in effect.”")).toBeInTheDocument();
  });

  it("never suggests a commit is still possible", async () => {
    serve(rejectedRunDto());
    renderApp(`/runs/${RUN_ID}`);

    await screen.findByText("HUMAN DECISION · REJECTED");
    expect(
      screen.getByText(/Nothing was committed and reality is\s+unchanged/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Committing the approved action/)).not.toBeInTheDocument();
    expect(
      screen.queryByText("Committed and independently verified"),
    ).not.toBeInTheDocument();
  });

  it("reads the decision from the backend, not from having clicked", async () => {
    // The click succeeds but the run still reports PENDING. The panel must not
    // claim a rejection the backend has not recorded.
    serve();
    const { user, gate } = await openGate();

    await rejectWith(user, gate, "declined");

    await waitFor(() => expect(screen.queryByRole("button", { name: "Reject" })).toBeNull());
    expect(screen.queryByText("HUMAN DECISION · REJECTED")).not.toBeInTheDocument();
  });
});

// ----- 7. rejection is not a veto ---------------------------------------------

describe("governance is not safety", () => {
  it("keeps the human rejection visually distinct from a world veto", async () => {
    serve(rejectedRunDto());
    renderApp(`/runs/${RUN_ID}`);

    await screen.findByText("HUMAN DECISION · REJECTED");
    const status = screen.getByText("HUMAN DECISION · REJECTED").closest("footer")!;

    // The governance panel never borrows the veto's word...
    expect(within(status).queryByText("VETOED")).not.toBeInTheDocument();
    expect(
      within(status).getByText(/governance decision, not an adversarial veto/),
    ).toBeInTheDocument();

    // ...and the vetoed world keeps its own, unchanged by the human decision.
    await waitFor(() => expect(lane("WORLD α")).toBeInTheDocument());
    expect(within(lane("WORLD α")).getByText("VETOED")).toBeInTheDocument();
    expect(
      within(lane("WORLD α")).queryByText(/HUMAN DECISION/),
    ).not.toBeInTheDocument();
  });

  it("leaves the recommended world still marked as having survived", async () => {
    serve(rejectedRunDto());
    renderApp(`/runs/${RUN_ID}`);

    await screen.findByText("HUMAN DECISION · REJECTED");
    await waitFor(() => expect(lane("WORLD β")).toBeInTheDocument());

    // A refusal says nothing about whether the world was safe.
    expect(within(lane("WORLD β")).getByText("SURVIVED")).toBeInTheDocument();
  });
});

// ----- 8. errors ---------------------------------------------------------------

describe("errors", () => {
  it("keeps the gate usable when the backend refuses the rejection", async () => {
    const server = serve();
    server.fail("/rejection", 409, "run is APPROVED; only a run awaiting approval may be rejected");
    const { user, gate } = await openGate();

    await rejectWith(user, gate, "too risky");

    expect(
      await screen.findByText(/only a run awaiting approval may be rejected/),
    ).toBeInTheDocument();
    expect(screen.queryByText("HUMAN DECISION · REJECTED")).not.toBeInTheDocument();
    // The rest of the run page is unaffected.
    expect(
      screen.getByRole("heading", { level: 1, name: "Checkout Regression" }),
    ).toBeInTheDocument();
  });

  it("reports an unreachable backend without claiming a decision", async () => {
    const server = serve();
    const { user, gate } = await openGate();
    server.goOffline();

    await rejectWith(user, gate, "declined");

    expect(
      await screen.findByText("BRANCHPOINT backend unreachable"),
    ).toBeInTheDocument();
    expect(screen.queryByText("HUMAN DECISION · REJECTED")).not.toBeInTheDocument();
  });
});
