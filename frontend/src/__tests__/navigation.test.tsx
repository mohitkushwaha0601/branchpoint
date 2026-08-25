/**
 * Routing and shell chrome.
 */

import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { heroRun } from "../data/heroRun";
import { renderRun } from "./renderRun";

describe("routing", () => {
  it("opens the hero run from the index route", () => {
    renderRun("/");

    expect(
      screen.getByRole("heading", { level: 1, name: "Checkout Regression" }),
    ).toBeInTheDocument();
  });

  it("falls back to the hero run for an unknown path", () => {
    renderRun("/nope");

    expect(screen.getByText(heroRun.runId)).toBeInTheDocument();
  });

  it("renders the run history table at /runs", () => {
    renderRun("/runs");

    expect(
      screen.getByRole("heading", { level: 1, name: "Runs" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Pricing timeout" }),
    ).toBeInTheDocument();
    expect(screen.getByText("REJECTED")).toBeInTheDocument();
  });

  it("renders the system status page at /system", () => {
    renderRun("/system");

    expect(
      screen.getByRole("heading", { level: 1, name: "System" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Daytona sandbox")).toBeInTheDocument();
    expect(screen.getAllByText("HEALTHY")).toHaveLength(4);
  });
});

describe("shell", () => {
  it("marks the current run in the sidebar", () => {
    renderRun();

    const sidebar = screen.getByRole("complementary", { name: "Runs" });
    const current = within(sidebar).getByRole("link", {
      name: /Checkout regression/,
    });
    expect(current).toHaveAttribute("aria-current", "page");
  });

  it("keeps Evidence inert until a later phase", () => {
    renderRun();

    const nav = screen.getByRole("navigation", { name: "Primary" });
    const evidence = within(nav).getByText("Evidence");
    expect(evidence).toHaveAttribute("aria-disabled", "true");
    expect(evidence.tagName).not.toBe("A");
  });

  it("reports system health in the header", () => {
    renderRun();

    expect(screen.getByText("System healthy")).toBeInTheDocument();
  });
});
