/**
 * The two sections below the frozen hero.
 *
 * These assert *meaning*, not motion: that the argument survives with no
 * IntersectionObserver (which jsdom has none of), that the semantic text is
 * present regardless of which visual state the interaction is in, and that the
 * corrected canonical values — not the offline fixture's — are what reach the
 * DOM.
 */

import { screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { renderApp } from "./renderRun";

afterEach(() => vi.unstubAllGlobals());

function stubMedia(matching: readonly string[]) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    media: query,
    matches: matching.some((m) => query.includes(m)),
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  }));
}

describe("section 01 — the trap", () => {
  it("names the rollback and its recovered metrics", () => {
    const { container } = renderApp("/");
    const section = container.querySelector(".bp-sec--problem");

    expect(section).not.toBeNull();
    expect(section).toHaveTextContent("An agent can be confident");
    // The engine's values, not the fixture's 2.1% / 610ms.
    expect(section).toHaveTextContent("1.8%");
    expect(section).toHaveTextContent("190ms");
  });

  it("offers both readings as a real radio group", () => {
    const { container } = renderApp("/");

    const group = container.querySelector('[role="radiogroup"]');
    expect(group).not.toBeNull();
    const radios = within(group as HTMLElement).getAllByRole("radio");
    expect(radios.map((r) => r.textContent)).toEqual([
      "HEADLINE VIEW",
      "EVIDENCE VIEW",
    ]);
    // Exactly one is checked, and it is the only tab stop.
    const checked = radios.filter(
      (r) => r.getAttribute("aria-checked") === "true",
    );
    expect(checked).toHaveLength(1);
    expect(checked[0]).toHaveAttribute("tabindex", "0");
  });

  it("flips the surface to the failing evidence when asked", async () => {
    const { container, user } = renderApp("/");

    await user.click(screen.getByRole("radio", { name: "EVIDENCE VIEW" }));

    const section = container.querySelector(".bp-sec--problem");
    expect(section).toHaveTextContent("payment_retry");
    expect(section).toHaveTextContent("order_deserialization_or_compatibility");
    expect(section).toHaveTextContent("CRITICAL");
    // The verdict replaces "ship to production" on the same path.
    expect(section).toHaveTextContent("VETOED");
  });

  it("keeps the argument in text with no animation at all", () => {
    const { container } = renderApp("/");
    const section = container.querySelector(".bp-sec--problem");

    // jsdom runs no IntersectionObserver, so nothing above has auto-advanced.
    // The static block must still carry the whole claim.
    expect(section).toHaveTextContent(
      /Headline metrics recover|critical evidence still fails/i,
    );
    expect(section).toHaveTextContent("order_1003");
    expect(section).toHaveTextContent("was VETOED");
  });

  it("starts on the conclusion under reduced motion", () => {
    stubMedia(["prefers-reduced-motion"]);
    const { container } = renderApp("/");

    // Nothing will flip for this reader, so the evidence reading is the one
    // they are given.
    const checked = container.querySelector('[role="radio"][aria-checked="true"]');
    expect(checked).toHaveTextContent("EVIDENCE VIEW");
    expect(container.querySelector(".bp-sec--problem")).toHaveTextContent(
      "VETOED",
    );
  });
});

describe("section 02 — manyworlds", () => {
  it("states the incident's starting reality", () => {
    const { container } = renderApp("/");
    const section = container.querySelector(".bp-sec--mw");

    expect(section).toHaveTextContent("Execute what could");
    expect(section).toHaveTextContent("pricing-service");
  });

  it("carries every world's action and outcome as a real table", () => {
    const { container } = renderApp("/");
    const table = container.querySelector(".bp-mw__table");

    expect(table).not.toBeNull();
    const rows = table!.querySelectorAll("tbody tr");
    expect(rows).toHaveLength(3);

    const text = table!.textContent ?? "";
    // actions
    expect(text).toContain("v2.41");
    expect(text).toContain("v2.40");
    expect(text).toContain("PRICING_V2");
    expect(text).toContain("replicas");
    // engine values, not fixture values
    expect(text).toContain("1.8%");
    expect(text).toContain("190ms");
    expect(text).toContain("1.4%");
    expect(text).toContain("320ms");
    expect(text).toContain("7.0%");
    expect(text).toContain("960ms");
    expect(text).toContain("+$900/day");
  });

  it("settles each world on its real verdict and selection", () => {
    const { container } = renderApp("/");
    const rows = container.querySelectorAll(".bp-mw__table tbody tr");

    const byVerdict = [...rows].map((row) => ({
      verdict: row.getAttribute("data-verdict"),
      text: row.textContent ?? "",
    }));

    expect(byVerdict[0]?.verdict).toBe("VETOED");
    expect(byVerdict[1]?.text).toContain("RECOMMENDED");
    expect(byVerdict[2]?.text).toContain("NOT SELECTED");
    // γ survived — losing the comparison is not a veto.
    expect(byVerdict[2]?.verdict).toBe("SURVIVED");
  });

  it("explains the floor rather than calling γ a partial improvement", () => {
    const { container } = renderApp("/");
    const section = container.querySelector(".bp-sec--mw");

    expect(section).toHaveTextContent(
      /cannot scale your way out of code that is still running/i,
    );
    expect(section).toHaveTextContent("7.0%");
  });

  it("renders the acts as a static list when motion is withheld", () => {
    stubMedia(["prefers-reduced-motion"]);
    const { container } = renderApp("/");

    // No sticky track at all — the acts become an ordered list of captions.
    expect(container.querySelector(".bp-mw__track")).toBeNull();
    const stack = container.querySelector(".bp-mw__stack");
    expect(stack).not.toBeNull();
    // Direct children only: each act also lists the worlds as nested items.
    expect(stack!.querySelectorAll(":scope > li")).toHaveLength(5);
    expect(stack).toHaveTextContent("One production system");
    expect(stack).toHaveTextContent("Evidence decides");

    // The fork is carried by type here, not the SVG — four acts list the three
    // worlds each, and the first (reality) lists none because nothing has
    // forked yet.
    expect(stack!.querySelectorAll(".bp-mw__lane")).toHaveLength(12);
    expect(stack).toHaveTextContent("SURVIVED · RECOMMENDED");
    expect(stack).toHaveTextContent("VETOED");
  });

  it("drops the sticky scene on a phone too", () => {
    stubMedia(["max-width"]);
    const { container } = renderApp("/");

    expect(container.querySelector(".bp-mw__track")).toBeNull();
    expect(container.querySelector(".bp-mw__stack")).not.toBeNull();
    // The outcomes are still fully stated.
    expect(container.querySelector(".bp-mw__table")).toHaveTextContent("7.0%");
  });

  it("keeps the decorative scene out of the accessibility tree", () => {
    const { container } = renderApp("/");

    for (const svg of container.querySelectorAll(".bp-fork")) {
      expect(svg).toHaveAttribute("aria-hidden", "true");
    }
    // Nothing on this page may announce itself while the reader scrolls.
    expect(container.querySelector("[aria-live]")).toBeNull();
  });
});

describe("the completed page", () => {
  it("runs the argument end to end, in order, with no placeholder left", () => {
    const { container } = renderApp("/");

    // The nine sections below the hero, in the blueprint's order.
    const sections = [...container.querySelectorAll(".bp-sec")].map((node) =>
      [...node.classList].find((name) => name.startsWith("bp-sec--")),
    );
    expect(sections).toEqual([
      "bp-sec--problem",
      "bp-sec--mw",
      "bp-sec--wx",
      "bp-sec--atk",
      "bp-sec--cmp",
      "bp-sec--appr",
      "bp-sec--cv",
      "bp-sec--arch",
      "bp-sec--close",
    ]);
    // The Phase 2B "next" marker is gone: nothing is unfinished any more.
    expect(container.querySelector(".bp-next")).toBeNull();
  });

  it("gives every section a labelled heading and keeps one h1", () => {
    const { container } = renderApp("/");

    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    for (const section of container.querySelectorAll(".bp-sec")) {
      const id = section.getAttribute("aria-labelledby");
      expect(id).not.toBeNull();
      expect(container.querySelector(`#${id}`)).not.toBeNull();
    }
  });

  it("leaves the frozen hero untouched above it", () => {
    const { container } = renderApp("/");

    // The hero still owns the only h1 and still points at its own media.
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(container.querySelector(".bp-hero__poster")).toHaveAttribute(
      "src",
      "/hero/branchpoint-desktop-monitor-poster.webp",
    );
  });

  it("never imports the offline fixture's superseded numbers", () => {
    const { container } = renderApp("/");
    const text = container.textContent ?? "";

    for (const stale of ["2.1%", "610ms", "16.2%", "1.9s", "12.4k"]) {
      expect(text).not.toContain(stale);
    }
  });
});
