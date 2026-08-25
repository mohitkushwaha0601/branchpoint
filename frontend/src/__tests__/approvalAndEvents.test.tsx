/**
 * The human checkpoint and the run log.
 */

import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { inspector, renderFixture } from "./renderRun";

describe("approval gate", () => {
  it("renders the checkpoint, its checks, and the exact bound action", () => {
    renderFixture();

    const gate = screen
      .getByRole("heading", { name: "MANUAL APPROVAL REQUIRED" })
      .closest("section");
    expect(gate).not.toBeNull();

    const panel = within(gate!);
    expect(panel.getByText(/World β — Disable Pricing V2/)).toBeInTheDocument();
    for (const check of [
      "Goal achieved",
      "All declared invariants passed",
      "No reproduced counterexamples",
      "Deterministic comparator recommendation",
      "Action fingerprint bound",
    ]) {
      expect(panel.getByText(check)).toBeInTheDocument();
    }
    expect(panel.getByText("3d7a1e05c94b2f6d")).toBeInTheDocument();
    expect(
      panel.getByRole("button", { name: "Approve & Commit" }),
    ).toBeInTheDocument();
  });

  it("names the exact binding a human is being asked to confirm", () => {
    renderFixture();

    const gate = within(
      screen.getByRole("heading", { name: "MANUAL APPROVAL REQUIRED" }).closest("section")!,
    );
    expect(gate.getByText("world_beta")).toBeInTheDocument();
    expect(gate.getByText("action_b8e2")).toBeInTheDocument();
    expect(gate.getByText("3d7a1e05c94b2f6d")).toBeInTheDocument();
    expect(
      gate.getByText(/commits the action they identify and nothing else/),
    ).toBeInTheDocument();
  });

  it("does not offer a reject the backend cannot honour", () => {
    renderFixture();

    expect(screen.getByRole("button", { name: "Reject" })).toBeDisabled();
    expect(
      screen.getByText(/Rejection is not exposed by the current API/),
    ).toBeInTheDocument();
  });
});

describe("event drawer", () => {
  it("starts collapsed and toggles open and shut", async () => {
    const { user } = renderFixture();

    const toggle = screen.getByRole("button", { name: /SHOW/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("Incident snapshot captured")).not.toBeInTheDocument();

    await user.click(toggle);
    expect(
      screen.getByRole("button", { name: /HIDE/ }),
    ).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Incident snapshot captured")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /HIDE/ }));
    expect(screen.queryByText("Incident snapshot captured")).not.toBeInTheDocument();
  });

  it("lists the run's events with monospace timestamps", async () => {
    const { user } = renderFixture();
    await user.click(screen.getByRole("button", { name: /SHOW/ }));

    const panel = screen.getByRole("tabpanel", { name: "Events" });
    expect(within(panel).getByText("18:42:01")).toBeInTheDocument();
    expect(within(panel).getByText("3 candidate actions generated")).toBeInTheDocument();
    expect(within(panel).getByText("Daytona sandbox created")).toBeInTheDocument();
    expect(within(panel).getByText("world_alpha VETOED")).toBeInTheDocument();
    expect(within(panel).getByText("Human approval required")).toBeInTheDocument();
  });

  it("selects the related world when an event is activated", async () => {
    const { user } = renderFixture();
    await user.click(screen.getByRole("button", { name: /SHOW/ }));

    const panel = screen.getByRole("tabpanel", { name: "Events" });
    await user.click(
      within(panel).getByRole("button", { name: /Compatibility failure reproduced/ }),
    );

    expect(
      within(inspector()).getByText("Rollback Pricing Deployment"),
    ).toBeInTheDocument();
  });

  it("switches streams and keeps the sandbox authority boundary explicit", async () => {
    const { user } = renderFixture();

    await user.click(screen.getByRole("tab", { name: "Sandbox" }));
    const panel = screen.getByRole("tabpanel", { name: "Sandbox" });
    expect(
      within(panel).getByText(/EXPLORATORY and can never veto a world/),
    ).toBeInTheDocument();
    expect(
      within(panel).getByText(/only BRANCHPOINT/i),
    ).toBeInTheDocument();
  });
});
