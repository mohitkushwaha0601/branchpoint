/**
 * `/how-it-works` — the protocol page.
 *
 * The two things this page can get wrong in ways that matter: the stage list
 * (nine, and REPLAY is not one of them) and the evidence chain (it accumulates
 * and is never cleared). Both are asserted here. The scroll choreography is
 * not: jsdom has no IntersectionObserver, and the page is deliberately built so
 * that every stage's content is in the DOM whether or not one ever fires.
 */

import { screen } from "@testing-library/react";
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

const STAGES = [
  "OBSERVE",
  "PLAN",
  "FORK",
  "EXECUTE",
  "ATTACK",
  "COMPARE",
  "APPROVE",
  "COMMIT",
  "VERIFY",
];

describe("the protocol", () => {
  it("has exactly nine stages, in order, and no REPLAY stage", () => {
    const { container } = renderApp("/how-it-works");

    const sections = [...container.querySelectorAll("[data-stage]")];
    expect(sections).toHaveLength(9);
    expect(
      sections.map((s) => s.querySelector(".bp-stg__name")?.textContent),
    ).toEqual(STAGES);

    // REPLAY is a step inside ATTACK, not a run state. It must never appear as
    // a peer in the rail.
    const rail = screen.getByRole("navigation", { name: "Protocol stages" });
    // Direct children only: ATTACK nests its two acts, and the legend below
    // the rail is a list too.
    expect(
      rail.querySelectorAll(".bp-pr__rail-list > li"),
    ).toHaveLength(9);
    expect(
      [...rail.querySelectorAll(".bp-pr__rail-name")].map((n) => n.textContent),
    ).toEqual(STAGES);
  });

  it("makes ATTACK the one stage with two acts", () => {
    const { container } = renderApp("/how-it-works");
    const acts = container.querySelectorAll(".bp-pr__rail-acts");

    expect(acts).toHaveLength(1);
    expect(acts[0]).toHaveTextContent("act 1 · hypothesis");
    expect(acts[0]).toHaveTextContent("act 2 · replay");
  });

  it("uses a real ordered list for the rail", () => {
    const { container } = renderApp("/how-it-works");
    const rail = container.querySelector(".bp-pr__rail-list");

    expect(rail?.tagName).toBe("OL");
    // Every entry is a real button, so the rail is keyboard-navigable.
    expect(rail?.querySelectorAll("button")).toHaveLength(9);
  });

  it("narrates one run that never changes", () => {
    const { container } = renderApp("/how-it-works");
    const text = container.textContent ?? "";

    expect(text).toContain("run_dbfa98c87f06");
    // The stale fixture's numbers may never appear here either.
    for (const stale of ["2.1%", "610ms", "16.2%", "1.9s", "12.4k"]) {
      expect(text).not.toContain(stale);
    }
  });
});

describe("the evidence chain", () => {
  it("starts empty and says so", () => {
    const { container } = renderApp("/how-it-works");
    const observe = container.querySelector('[data-stage="0"]');

    expect(observe).toHaveTextContent("No evidence yet");
    expect(
      observe?.querySelectorAll(".bp-pr__rows li"),
    ).toHaveLength(0);
  });

  it("is still empty at PLAN, because a plan is not evidence", () => {
    const { container } = renderApp("/how-it-works");
    const plan = container.querySelector('[data-stage="1"]');

    expect(plan?.querySelectorAll(".bp-pr__rows li")).toHaveLength(0);
    expect(plan).toHaveTextContent("A plan is not evidence.");
  });

  it("only ever grows — it is never cleared, filtered or re-ordered", () => {
    const { container } = renderApp("/how-it-works");

    const counts = [...container.querySelectorAll("[data-stage]")].map(
      (section) => section.querySelectorAll(".bp-pr__rows li").length,
    );

    // Monotonic, by construction: each stage renders a prefix of the chain.
    for (let i = 1; i < counts.length; i++) {
      expect(counts[i]!).toBeGreaterThanOrEqual(counts[i - 1]!);
    }
    expect(counts[0]).toBe(0);
    // Empty, empty, empty, then the execution suite lands.
    expect(counts.slice(0, 3)).toEqual([0, 0, 0]);
    expect(counts[8]).toBeGreaterThan(counts[3]!);

    // And the very first row recorded is still the first row at stage 09.
    const first = (index: number) =>
      container
        .querySelectorAll("[data-stage]")
        [index]?.querySelector(".bp-pr__rows li .bp-pr__row-claim")
        ?.textContent;
    expect(first(8)).toBe(first(3));
  });

  it("still holds the exploratory sandbox probe at the final stage", () => {
    const { container } = renderApp("/how-it-works");
    const verify = container.querySelector('[data-stage="8"]');

    expect(verify).toHaveTextContent("sandbox probe");
    expect(verify).toHaveTextContent("machine_verifiable = false");
    // Alongside the verification rows recorded eight stages later.
    expect(verify).toHaveTextContent("checkout_error_rate");
  });
});

describe("the authority spine", () => {
  it("labels every stage with one of the three bands", () => {
    const { container } = renderApp("/how-it-works");

    const bands = [...container.querySelectorAll("[data-stage]")].map((s) =>
      s.querySelector(".bp-auth")?.getAttribute("data-band"),
    );
    expect(bands).toEqual([
      "DETERMINISTIC",
      "EXPLORATORY",
      "DETERMINISTIC",
      "DETERMINISTIC",
      "DETERMINISTIC",
      "DETERMINISTIC",
      "PERMISSION",
      "DETERMINISTIC",
      "DETERMINISTIC",
    ]);
  });

  it("says what each band may never do, not only what it may", () => {
    const { container } = renderApp("/how-it-works");
    const plan = container.querySelector('[data-stage="1"]');

    expect(plan?.querySelector(".bp-pr__auth-cannot")).toHaveTextContent(
      "Veto a world",
    );
    expect(plan?.querySelector(".bp-pr__auth-cannot")).toHaveTextContent(
      "Mark anything REPRODUCED",
    );
  });

  it("puts the transfer at ATTACK and nowhere else", () => {
    const { container } = renderApp("/how-it-works");
    const attack = container.querySelector('[data-stage="4"]');

    expect(attack).toHaveTextContent("act 1");
    expect(attack).toHaveTextContent("act 2");
    expect(attack).toHaveTextContent("EXPLORATORY");
    expect(attack).toHaveTextContent("DETERMINISTIC");
    expect(attack).toHaveTextContent(
      "Authority transfers here, and only here.",
    );
  });

  it("records no evidence at APPROVE, because permission is not evidence", () => {
    const { container } = renderApp("/how-it-works");
    const sections = [...container.querySelectorAll("[data-stage]")];
    const rows = (i: number) =>
      sections[i]!.querySelectorAll(".bp-pr__rows li").length;

    expect(rows(6)).toBe(rows(5));
    expect(sections[6]).toHaveTextContent("Approval adds no evidence");
  });
});

describe("stage content", () => {
  it("shows γ failing checks at EXECUTE without vetoing it", () => {
    const { container } = renderApp("/how-it-works");
    const execute = container.querySelector('[data-stage="3"]');

    expect(execute).toHaveTextContent("7.0% error");
    expect(execute).toHaveTextContent("MEDIUM severity, kind TEST_RESULT");
    expect(execute).toHaveTextContent("Not disqualifying");
    expect(execute).not.toHaveTextContent("VETOED");
  });

  it("strikes α out at COMPARE with the real rejection reason", () => {
    const { container } = renderApp("/how-it-works");
    const compare = container.querySelector('[data-stage="5"]');

    expect(compare).toHaveTextContent("ADVERSARIAL_VETO");
    expect(compare?.querySelectorAll("td[data-rejected]").length)
      .toBeGreaterThan(0);
  });

  it("shows four commit gates and then the mutation", () => {
    const { container } = renderApp("/how-it-works");
    const commit = container.querySelector('[data-stage="7"]');

    expect(commit?.querySelectorAll(".bp-stg__gates li")).toHaveLength(4);
    expect(commit).toHaveTextContent("PRICING_V2");
    expect(commit).toHaveTextContent("true → false");
  });

  it("keeps VERIFY independent of what the commit claimed", () => {
    const { container } = renderApp("/how-it-works");
    const verify = container.querySelector('[data-stage="8"]');

    expect(verify).toHaveTextContent(
      "never saw the commit report",
    );
    expect(verify).toHaveTextContent("RUN SUCCEEDED");
  });
});

describe("shell and navigation", () => {
  it("owns exactly one h1 and gives every stage a labelled h2", () => {
    const { container } = renderApp("/how-it-works");

    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    for (const section of container.querySelectorAll("[data-stage]")) {
      const id = section.getAttribute("aria-labelledby");
      expect(container.querySelector(`#${id}`)?.tagName).toBe("H2");
    }
  });

  it("offers a route back to the overview and into the live demo", () => {
    renderApp("/how-it-works");

    for (const cta of screen.getAllByRole("link", { name: /SEE LIVE DEMO/ })) {
      expect(cta).toHaveAttribute("href", "/runs");
    }
    for (const cta of screen.getAllByRole("link", {
      name: /BACK TO OVERVIEW/,
    })) {
      expect(cta).toHaveAttribute("href", "/");
    }
  });

  it("carries the compact stage header for the phone", () => {
    stubMedia(["max-width"]);
    const { container } = renderApp("/how-it-works");
    const compact = container.querySelector(".bp-pr__compact");

    // Stage number, stage name and authority band — the three things a reader
    // one screen into a nine-stage protocol must never lose.
    expect(compact).toHaveTextContent("01 / 09");
    expect(compact).toHaveTextContent("OBSERVE");
    expect(compact).toHaveTextContent("DETERMINISTIC");
  });

  it("never announces stage changes to a screen reader", () => {
    const { container } = renderApp("/how-it-works");
    expect(container.querySelector("[aria-live]")).toBeNull();
  });

  it("does not duplicate a landing section", () => {
    const { container } = renderApp("/how-it-works");

    // The operable approval demo lives on the landing page only; here the same
    // action appears as a static binding record.
    expect(container.querySelector(".bp-appr__card")).toBeNull();
    expect(container.querySelector(".bp-sec--mw")).toBeNull();
    expect(container.querySelector(".bp-hero")).toBeNull();
  });
});
