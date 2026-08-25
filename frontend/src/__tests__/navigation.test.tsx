/**
 * Routing and shell chrome.
 *
 * The routes are backed by the real API client, so each test says what the
 * backend is serving.
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
import { renderApp, renderFixture } from "./renderRun";

afterEach(() => vi.unstubAllGlobals());

function serveFullRun() {
  return mockServer({
    run: runDto(),
    worlds: worldsDto(),
    comparison: comparisonDto(),
    events: eventsDto(),
    demo: demoStateDto(),
    health: { status: "ok", service: "branchpoint-backend", version: "0.1.0" },
  });
}

describe("routing", () => {
  it("sends the index route to the run list", async () => {
    serveFullRun();
    renderApp("/");

    expect(
      await screen.findByRole("heading", { level: 1, name: "Runs" }),
    ).toBeInTheDocument();
  });

  it("sends an unknown path to the run list", async () => {
    serveFullRun();
    renderApp("/nope");

    expect(
      await screen.findByRole("heading", { level: 1, name: "Runs" }),
    ).toBeInTheDocument();
  });

  it("lists the backend's runs at /runs", async () => {
    serveFullRun();
    renderApp("/runs");

    expect(
      await screen.findByRole("link", { name: "Checkout Regression" }),
    ).toBeInTheDocument();
    expect(screen.getByText(RUN_ID)).toBeInTheDocument();
    expect(screen.getByText("AWAITING APPROVAL")).toBeInTheDocument();
  });

  it("says so when the backend has no runs", async () => {
    mockServer({});
    renderApp("/runs");

    expect(await screen.findByText(/No runs yet/)).toBeInTheDocument();
  });

  it("reports live backend health at /system", async () => {
    serveFullRun();
    renderApp("/system");

    expect(
      screen.getByRole("heading", { level: 1, name: "System" }),
    ).toBeInTheDocument();
    expect(await screen.findByText("HEALTHY")).toBeInTheDocument();
    expect(screen.getByText("branchpoint-backend 0.1.0")).toBeInTheDocument();
  });

  it("reports the backend as unreachable rather than guessing", async () => {
    const server = mockServer({});
    server.goOffline();
    renderApp("/system");

    expect(await screen.findByText("UNREACHABLE")).toBeInTheDocument();
  });

  it("leaves everything behind the backend as UNKNOWN", async () => {
    serveFullRun();
    renderApp("/system");

    await screen.findByText("HEALTHY");
    // TrueForge, MCP, sandbox, model: never contacted from the browser.
    expect(screen.getAllByText("UNKNOWN")).toHaveLength(4);
    expect(screen.getByText("TrueForge harness")).toBeInTheDocument();
  });

  it("never puts a TrueForge address in the bundle", async () => {
    const server = serveFullRun();
    renderApp(`/runs/${RUN_ID}`);
    await waitFor(() => expect(server.calls.length).toBeGreaterThan(0));

    expect(server.calls.some((call) => call.includes("8790"))).toBe(false);
  });
});

describe("shell", () => {
  it("marks the current run in the sidebar", async () => {
    serveFullRun();
    renderApp(`/runs/${RUN_ID}`);

    // Queried after the run lands: the shell re-mounts on that first
    // transition, so a node captured beforehand would be detached.
    await screen.findByRole("heading", { level: 1, name: "Checkout Regression" });
    const current = await screen.findByRole("link", {
      name: /Checkout Regression/,
    });

    expect(current).toHaveAttribute("aria-current", "page");
    expect(current).toHaveAttribute("href", `/runs/${RUN_ID}`);
  });

  it("keeps Evidence inert until a later phase", () => {
    renderFixture();

    const nav = screen.getByRole("navigation", { name: "Primary" });
    const evidence = within(nav).getByText("Evidence");
    expect(evidence).toHaveAttribute("aria-disabled", "true");
    expect(evidence.tagName).not.toBe("A");
  });

  it("marks the offline fixture as a fixture", () => {
    renderFixture();

    expect(screen.getByText(/FIXTURE — not a live run/)).toBeInTheDocument();
  });
});
