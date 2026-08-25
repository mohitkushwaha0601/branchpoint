/**
 * The inspector follows the selection, and it never blurs the line between the
 * adversary's opinion and BRANCHPOINT's own replay.
 */

import { within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { inspector, lane, renderRun } from "./renderRun";

describe("inspector", () => {
  it("defaults to the recommended world", () => {
    renderRun();

    const panel = inspector();
    expect(within(panel).getByText("Disable Pricing V2")).toBeInTheDocument();
    expect(within(panel).getByText("SURVIVED")).toBeInTheDocument();
    expect(within(panel).getByText("RECOMMENDED")).toBeInTheDocument();
    expect(within(panel).getByText("PRICING_V2")).toBeInTheDocument();
    expect(within(panel).getByText("true")).toBeInTheDocument();
    expect(within(panel).getByText("false")).toBeInTheDocument();
  });

  it("shows the recommended world's replayed invariants, all passing", () => {
    const panel = (renderRun(), inspector());

    for (const claim of [
      "healthy_checkout",
      "recovery_slo",
      "data_integrity",
      "payment_retry",
      "schema_compatibility",
    ]) {
      expect(within(panel).getByText(claim)).toBeInTheDocument();
    }
    expect(within(panel).getAllByText("PASS")).toHaveLength(5);
    expect(within(panel).queryByText("FAIL")).not.toBeInTheDocument();
  });

  it("attributes the comparator, not a model, for the recommendation", () => {
    const panel = (renderRun(), inspector());

    expect(
      within(panel).getByText("Ranked first by deterministic comparator."),
    ).toBeInTheDocument();
  });

  it("switches to Alpha when its lane is selected", async () => {
    const { user } = renderRun();

    await user.click(
      within(lane("WORLD α")).getByRole("button", {
        name: /Rollback Pricing Deployment/,
      }),
    );

    const panel = inspector();
    expect(
      within(panel).getByText("Rollback Pricing Deployment"),
    ).toBeInTheDocument();
    expect(within(panel).getByText("VETOED")).toBeInTheDocument();
    expect(within(panel).getByText("v2.41")).toBeInTheDocument();
    expect(within(panel).getByText("v2.40")).toBeInTheDocument();
    expect(within(panel).getAllByText("FAIL")).toHaveLength(2);
  });

  it("switches back to Beta when its lane is selected", async () => {
    const { user } = renderRun();

    await user.click(
      within(lane("WORLD α")).getByRole("button", {
        name: /Rollback Pricing Deployment/,
      }),
    );
    await user.click(
      within(lane("WORLD β")).getByRole("button", { name: /Disable Pricing V2/ }),
    );

    const panel = inspector();
    expect(within(panel).getByText("Disable Pricing V2")).toBeInTheDocument();
    expect(within(panel).getByText("SURVIVED")).toBeInTheDocument();
  });

  it("shows the selected pipeline step when a row is activated", async () => {
    const { user } = renderRun();

    await user.click(
      within(lane("WORLD α")).getByRole("button", {
        name: /BRANCHPOINT replay/,
      }),
    );

    const panel = inspector();
    expect(within(panel).getByText("SELECTED STEP")).toBeInTheDocument();
    expect(
      within(panel).getByText(/replayed the proposed counterexample/),
    ).toBeInTheDocument();
  });

  it("is reachable by keyboard", async () => {
    const { user } = renderRun();

    const alphaTitle = within(lane("WORLD α")).getByRole("button", {
      name: /Rollback Pricing Deployment/,
    });
    alphaTitle.focus();
    await user.keyboard("{Enter}");

    expect(alphaTitle).toHaveAttribute("aria-pressed", "true");
    expect(within(inspector()).getByText("VETOED")).toBeInTheDocument();
  });
});

describe("evidence authority", () => {
  it("labels sandbox evidence EXPLORATORY and replay evidence VERIFIED", () => {
    renderRun();

    const panel = inspector();
    expect(within(panel).getByText("EXPLORATORY")).toBeInTheDocument();
    expect(within(panel).getByText("VERIFIED")).toBeInTheDocument();
    expect(
      within(panel).getByText(/it can never justify a verdict/),
    ).toBeInTheDocument();
  });

  it("labels both voices inside every world lane", () => {
    renderRun();

    for (const label of ["WORLD α", "WORLD β", "WORLD γ"]) {
      const section = lane(label);
      expect(within(section).getByText("EXPLORATORY")).toBeInTheDocument();
      expect(within(section).getByText("VERIFIED")).toBeInTheDocument();
    }
  });

  it("never marks sandbox output as verified", () => {
    renderRun();

    const alpha = within(lane("WORLD α"));
    const sandbox = within(
      alpha.getByRole("region", { name: "DOPPELGÄNGER evidence" }),
    );
    expect(sandbox.getByText("EXPLORATORY")).toBeInTheDocument();
    expect(sandbox.queryByText("VERIFIED")).not.toBeInTheDocument();
    // ...and the quoted hypothesis lives on that side of the line, never the
    // replay side.
    expect(sandbox.getByText(/may not deserialize under v2.40/)).toBeInTheDocument();

    const replay = within(
      alpha.getByRole("region", { name: "BRANCHPOINT replay evidence" }),
    );
    expect(replay.getByText("VERIFIED")).toBeInTheDocument();
    expect(replay.queryByText("EXPLORATORY")).not.toBeInTheDocument();
    expect(replay.getAllByText("FAIL")).toHaveLength(2);
  });
});
