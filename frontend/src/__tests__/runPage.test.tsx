/**
 * Mission Control: the run renders, all three branches render, and each one
 * reports the verdict BRANCHPOINT actually reached.
 */

import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { heroRun } from "../data/heroRun";
import { lane, renderFixture } from "./renderRun";

describe("hero run", () => {
  it("renders the run identity and status", () => {
    renderFixture();

    expect(
      screen.getByRole("heading", { level: 1, name: "Checkout Regression" }),
    ).toBeInTheDocument();
    expect(screen.getByText(heroRun.runId)).toBeInTheDocument();
    expect(screen.getAllByText("AWAITING APPROVAL").length).toBeGreaterThan(0);
  });

  it("renders the incident readings and current reality", () => {
    renderFixture();

    const incident = within(
      screen.getByRole("region", { name: "OBSERVED METRICS" }),
    );
    expect(incident.getByText("41.3%")).toBeInTheDocument();
    expect(incident.getByText("4.8s")).toBeInTheDocument();
    expect(incident.getByText("12.4k")).toBeInTheDocument();

    const reality = within(
      screen.getByRole("region", { name: "CURRENT REALITY" }),
    );
    expect(reality.getByText("v2.41")).toBeInTheDocument();
    expect(reality.getByText("ON")).toBeInTheDocument();
    expect(reality.getByText("4")).toBeInTheDocument();
    expect(reality.getByText("41")).toBeInTheDocument();
  });

  it("renders every stage of the pipeline with approval current", () => {
    renderFixture();

    const rail = screen.getByRole("navigation", { name: "Run stages" });
    for (const label of [
      "OBSERVE",
      "PLAN",
      "FORK",
      "EXECUTE",
      "ATTACK",
      "COMPARE",
      "APPROVE",
      "COMMIT",
      "VERIFY",
    ]) {
      expect(within(rail).getByText(label)).toBeInTheDocument();
    }
    expect(within(rail).getByText("APPROVE").closest("span")).toBeTruthy();
    expect(rail.querySelector('[aria-current="step"]')).toHaveTextContent(
      "APPROVE",
    );
  });
});

describe("branch graph", () => {
  it("renders three world lanes", () => {
    renderFixture();

    expect(lane("WORLD α")).toBeInTheDocument();
    expect(lane("WORLD β")).toBeInTheDocument();
    expect(lane("WORLD γ")).toBeInTheDocument();
  });

  it("shows Alpha as VETOED with its reason", () => {
    renderFixture();

    const alpha = lane("WORLD α");
    expect(within(alpha).getByText("VETOED")).toBeInTheDocument();
    expect(
      within(alpha).getByText(/Schema compatibility failure/),
    ).toBeInTheDocument();
  });

  it("shows Beta as SURVIVED and RECOMMENDED", () => {
    renderFixture();

    const beta = lane("WORLD β");
    expect(within(beta).getByText("SURVIVED")).toBeInTheDocument();

    // RECOMMENDED is a property of the branch's terminal node, not the lane.
    expect(screen.getAllByText("RECOMMENDED").length).toBeGreaterThan(0);
  });

  it("shows Gamma as SURVIVED but not recommended", () => {
    renderFixture();

    const gamma = lane("WORLD γ");
    expect(within(gamma).getByText("SURVIVED")).toBeInTheDocument();
    expect(within(gamma).queryByText("RECOMMENDED")).not.toBeInTheDocument();
    expect(within(gamma).getByText("Goal not fully achieved.")).toBeInTheDocument();
  });

  it("renders each world's pipeline rows as activatable controls", () => {
    renderFixture();

    const alpha = lane("WORLD α");
    expect(
      within(alpha).getByRole("button", { name: /Execute world/ }),
    ).toBeInTheDocument();
    expect(
      within(alpha).getByRole("button", { name: /DOPPELGÄNGER/ }),
    ).toBeInTheDocument();
    expect(
      within(alpha).getByRole("button", { name: /BRANCHPOINT replay/ }),
    ).toBeInTheDocument();
  });
});
