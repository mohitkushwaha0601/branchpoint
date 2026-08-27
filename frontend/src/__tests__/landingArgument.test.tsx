/**
 * Sections 03 – 09: the argument below Manyworlds.
 *
 * These assert the *claims*, not the choreography. Milliseconds and beat
 * indices are deliberately untested: they change whenever the pacing is tuned,
 * and none of them is what the page is for. What is tested is everything that
 * would be a lie if it broke — the authority distinction, the asymmetric
 * evidence counts, the absence of a score, and the fact that the checkpoint
 * demo never touches the network.
 */

import { within } from "@testing-library/react";
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

function section(container: HTMLElement, name: string) {
  const node = container.querySelector<HTMLElement>(`.bp-sec--${name}`);
  if (node === null) throw new Error(`section ${name} not rendered`);
  return node;
}

describe("section 03 — world explorer", () => {
  it("is a real tablist with roving tabindex", () => {
    const { container } = renderApp("/");
    const tablist = within(section(container, "wx")).getByRole("tablist");
    const tabs = within(tablist).getAllByRole("tab");

    expect(tabs).toHaveLength(3);
    expect(tabs.filter((t) => t.getAttribute("aria-selected") === "true"))
      .toHaveLength(1);
    // Only the selected tab is a tab stop.
    expect(tabs.filter((t) => t.getAttribute("tabindex") === "0"))
      .toHaveLength(1);
    for (const tab of tabs) {
      expect(container.querySelector(`#${tab.getAttribute("aria-controls")}`))
        .not.toBeNull();
    }
  });

  it("gives each world its own real, asymmetric evidence count", async () => {
    const { container, user } = renderApp("/");
    const wx = section(container, "wx");

    // The counts are on the tabs, so all three are visible at once and the
    // asymmetry is legible before anything is clicked.
    const counts = within(wx)
      .getAllByRole("tab")
      .map((tab) => tab.querySelector(".bp-wx__tab-count")?.textContent);
    expect(counts).toEqual(["3 evidence", "6 evidence", "4 evidence"]);

    // And the open panel really renders that many rows.
    expect(wx.querySelectorAll(".bp-evlist__rows > .bp-ev")).toHaveLength(3);

    await user.click(within(wx).getAllByRole("tab")[1]!);
    expect(wx.querySelectorAll(".bp-evlist__rows > .bp-ev")).toHaveLength(6);

    await user.click(within(wx).getAllByRole("tab")[2]!);
    expect(wx.querySelectorAll(".bp-evlist__rows > .bp-ev")).toHaveLength(4);
  });

  it("cycles worlds with the arrow keys", async () => {
    const { container, user } = renderApp("/");
    const wx = section(container, "wx");
    const tabs = within(wx).getAllByRole("tab");

    tabs[0]!.focus();
    await user.keyboard("{ArrowRight}");
    expect(within(wx).getAllByRole("tab")[1]).toHaveAttribute(
      "aria-selected",
      "true",
    );
    // And it wraps rather than dead-ending.
    await user.keyboard("{ArrowLeft}{ArrowLeft}");
    expect(within(wx).getAllByRole("tab")[2]).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  it("states the authority bit in words on every row", () => {
    const { container } = renderApp("/");
    const wx = section(container, "wx");

    // α's chain: one exploratory probe, two verified failures.
    const auth = [...wx.querySelectorAll(".bp-ev__auth")].map(
      (n) => n.textContent,
    );
    expect(auth).toEqual([
      "machine_verifiable = false",
      "machine_verifiable = true",
      "machine_verifiable = true",
    ]);
    // Only the machine-verifiable failures disqualify.
    expect(wx.querySelectorAll(".bp-ev__dq")).toHaveLength(2);
  });

  it("keeps α's superseded execution suite reachable rather than deleting it", async () => {
    const { container, user } = renderApp("/");
    const wx = section(container, "wx");

    const more = within(wx).getByRole("button", { name: /superseded/i });
    expect(more).toHaveAttribute("aria-expanded", "false");
    await user.click(more);
    // 3 verdict-bearing + 3 superseded.
    expect(wx.querySelectorAll(".bp-ev")).toHaveLength(6);
    expect(wx).toHaveTextContent("healthy_checkout");
    expect(wx).toHaveTextContent("recovery_slo");
  });

  it("never implies that surviving means winning", () => {
    const { container } = renderApp("/");
    const wx = section(container, "wx");
    expect(wx).toHaveTextContent(/γ survived\. γ also lost\./);
  });
});

describe("section 04 — the attack", () => {
  it("marks the adversary exploratory and gives it no authority", () => {
    const { container } = renderApp("/");
    const atk = section(container, "atk");

    expect(atk).toHaveTextContent("EXPLORATORY");
    expect(atk).toHaveTextContent("NO AUTHORITY");
    expect(atk).toHaveTextContent("machine_verifiable = false");
  });

  it("never says the adversary vetoed anything", () => {
    const { container } = renderApp("/");
    const text = section(container, "atk").textContent ?? "";

    expect(/DOPPELG[ÄA]NGER\s+vetoed/i.test(text)).toBe(false);
    // The veto is attributed to the replay, in so many words.
    expect(text).toContain(
      "by BRANCHPOINT’s replay, not by the adversary that suggested where to look",
    );
  });

  it("states the two-part veto rule verbatim", () => {
    const { container } = renderApp("/");
    expect(section(container, "atk")).toHaveTextContent(
      "counterexample.status is REPRODUCED AND any(evidence.disqualifies)",
    );
  });

  it("carries the authority boundary as text, not only as colour", () => {
    const { container } = renderApp("/");
    const atk = section(container, "atk");

    // The rule prints its own label and its own meaning.
    expect(atk.querySelector(".bp-atk__rule-label")).toHaveTextContent(
      "CounterexampleSpec · typed · validated",
    );
    expect(atk).toHaveTextContent("Nothing above this line may conclude anything.");
    // Both halves are separately headed, so the crossing survives greyscale.
    expect(atk).toHaveTextContent("Above the line · exploratory");
    expect(atk).toHaveTextContent("Below the line · deterministic");
  });

  it("lands on the conclusion when motion is withheld", () => {
    stubMedia(["prefers-reduced-motion"]);
    const { container } = renderApp("/");
    const atk = section(container, "atk");

    // No pinned track at all, and the replay result is present rather than
    // waiting for a scroll that will never be animated.
    expect(atk.querySelector(".bp-atk__track")).toBeNull();
    expect(atk).toHaveTextContent("REPRODUCED");
    expect(atk).toHaveTextContent("WORLD α · VETOED");
  });
});

describe("section 05 — comparison", () => {
  it("is a real table on the comparator's own axes", () => {
    const { container } = renderApp("/");
    const table = section(container, "cmp").querySelector("table");

    expect(table?.querySelector("caption")).not.toBeNull();
    const axes = [...(table?.querySelectorAll("tbody th[scope=row]") ?? [])].map(
      (n) => n.textContent?.replace(/[?−]$/, "").trim(),
    );
    expect(axes).toEqual([
      "goal_achieved",
      "goal_attainment",
      "invariants_preserved",
      "regressions_detected",
      "blast_radius",
      "reversible",
      "cost_delta",
      "rank",
    ]);
  });

  it("removes α before ranking and recommends β", () => {
    const { container } = renderApp("/");
    const cmp = section(container, "cmp");

    expect(cmp).toHaveTextContent("ADVERSARIAL_VETO");
    expect(cmp).toHaveTextContent("removed");
    expect(cmp).toHaveTextContent("RECOMMENDED");
  });

  it("has no score, no confidence and no percentage gauge anywhere", () => {
    const { container } = renderApp("/");
    const text = section(container, "cmp").textContent ?? "";

    // None of the shapes a score would arrive in.
    expect(container.querySelector("progress")).toBeNull();
    expect(container.querySelector("meter")).toBeNull();
    expect(container.querySelector('[role="progressbar"]')).toBeNull();

    // And no 0–100 number or percentage inside the matrix itself.
    const matrix = section(container, "cmp").querySelector("table");
    expect(matrix?.textContent ?? "").not.toMatch(/%/);

    // "score" and "confidence" appear only in the sentences denying them.
    expect(text).toContain("does not have a confidence number to give you");
    expect(text).toContain("There is no score in WorldRanking");
    expect(text).toContain("No weights, no confidence, no 0–100 gauge");
  });

  it("transposes rather than shrinking on a phone, and stays a table", () => {
    stubMedia(["max-width"]);
    const { container } = renderApp("/");
    const cmp = section(container, "cmp");

    expect(cmp.querySelector(".bp-cmp__table--transposed")).not.toBeNull();
    expect(cmp.querySelector("caption")).not.toBeNull();
    // One world at a time, chosen with a real radio group.
    const group = within(cmp).getByRole("radiogroup", { name: "World" });
    expect(within(group).getAllByRole("radio")).toHaveLength(3);
    // Axes still carry scope, in the transposed orientation too.
    expect(cmp.querySelectorAll('th[scope="row"]').length).toBeGreaterThan(6);
  });
});

describe("section 06 — the human checkpoint", () => {
  it("issues no network request at all, ever", async () => {
    const fetchSpy = vi.fn(() =>
      Promise.reject(new Error("the checkpoint must never call the API")),
    );
    vi.stubGlobal("fetch", fetchSpy);

    const { container, user } = renderApp("/");
    const appr = section(container, "appr");

    // Operate every control the section has.
    await user.click(within(appr).getByRole("button", { name: /Change the action/ }));
    await user.click(within(appr).getByRole("button", { name: /Reset/ }));
    await user.click(within(appr).getByRole("button", { name: "APPROVE EXACT ACTION" }));
    await user.click(within(appr).getByRole("button", { name: "REJECT" }));

    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("shows a truncated real sha256 of the reviewed action", () => {
    const { container } = renderApp("/");
    const hash = section(container, "appr").querySelector(".bp-appr__fp-hash");

    expect(hash?.textContent).toBe("555150ab72d3…6551");
  });

  it("recomputes the fingerprint and invalidates the approval when the action changes", async () => {
    const { container, user } = renderApp("/");
    const appr = section(container, "appr");

    await user.click(
      within(appr).getByRole("button", { name: /Change the action/ }),
    );

    // A different action, therefore a different hash.
    expect(appr.querySelector(".bp-appr__fp-hash")?.textContent).toBe(
      "6dca77350f38…fce9",
    );
    expect(appr).toHaveTextContent("CHECKOUT_V2");
    expect(appr).toHaveTextContent("APPROVAL INVALIDATED");

    // Exactly one binding breaks — the one that depends on the content.
    expect(appr.querySelectorAll(".bp-appr__bindings li[data-failed]"))
      .toHaveLength(1);
    expect(appr).toHaveTextContent("BROKEN");

    // Both decisions become unavailable, stated in words as well as styling,
    // and stay reachable by keyboard so the reason can be read.
    for (const name of ["REJECT", "APPROVE EXACT ACTION"]) {
      const button = within(appr).getByRole("button", { name });
      expect(button).toHaveAttribute("aria-disabled", "true");
      expect(button).not.toHaveAttribute("disabled");
    }
    expect(appr).toHaveTextContent("Both decisions are unavailable");
  });

  it("restores the reviewed action on reset", async () => {
    const { container, user } = renderApp("/");
    const appr = section(container, "appr");

    await user.click(within(appr).getByRole("button", { name: /Change the action/ }));
    await user.click(within(appr).getByRole("button", { name: /Reset/ }));

    expect(appr.querySelector(".bp-appr__fp-hash")?.textContent).toBe(
      "555150ab72d3…6551",
    );
    expect(appr).not.toHaveTextContent("APPROVAL INVALIDATED");
  });
});

describe("section 07 — commit and verify", () => {
  it("separates issuing the mutation from proving it", () => {
    const { container } = renderApp("/");
    const cv = section(container, "cv");

    expect(cv).toHaveTextContent("PRICING_V2");
    expect(cv).toHaveTextContent("true");
    expect(cv).toHaveTextContent("false");
    expect(cv).toHaveTextContent(
      "The mutation was issued. That is all a commit proves",
    );
    // Four gates, in order.
    expect(cv.querySelectorAll(".bp-cv__gates li")).toHaveLength(4);
  });

  it("never announces the sequence to a screen reader", () => {
    const { container } = renderApp("/");
    expect(section(container, "cv").querySelector("[aria-live]")).toBeNull();
  });

  it("is already resolved when motion is withheld", () => {
    stubMedia(["prefers-reduced-motion"]);
    const { container } = renderApp("/");
    const cv = section(container, "cv");

    expect(cv).toHaveTextContent("RUN SUCCEEDED");
    expect(cv.querySelectorAll(".bp-cv__gates li[data-done]")).toHaveLength(4);
  });
});

describe("section 08 — authority architecture", () => {
  it("makes every node a real focusable button", () => {
    const { container } = renderApp("/");
    const nodes = section(container, "arch").querySelectorAll(".bp-arch__node");

    expect(nodes).toHaveLength(6);
    for (const node of nodes) {
      expect(node.tagName).toBe("BUTTON");
      expect(node).toHaveAttribute("aria-pressed");
    }
  });

  it("always states what a component may NOT do", async () => {
    const { container, user } = renderApp("/");
    const arch = section(container, "arch");

    await user.click(within(arch).getByRole("button", { name: /DOPPELGÄNGER/ }));
    expect(arch.querySelector("dd.bp-arch__negative")).toHaveTextContent(
      "It cannot veto, cannot set a threshold",
    );

    await user.click(within(arch).getByRole("button", { name: /^HUMAN/ }));
    expect(arch.querySelector("dd.bp-arch__negative")).toHaveTextContent(
      "cannot override a veto",
    );
  });

  it("states all six components in text for a reader who never operates it", () => {
    const { container } = renderApp("/");
    const fallback = section(container, "arch").querySelector(".sr-only");

    for (const label of [
      "TRUEFORGE",
      "DOPPELGÄNGER",
      "BRANCHPOINT",
      "HUMAN",
      "COMMIT OPERATOR",
      "VERIFIER",
    ]) {
      expect(fallback).toHaveTextContent(label);
    }
    expect(fallback).toHaveTextContent("Does not hold:");
  });
});

describe("section 09 — the close", () => {
  it("sends the reader on without repeating the hero", () => {
    const { container } = renderApp("/");
    const close = section(container, "close");

    expect(close).toHaveTextContent("Rehearse before reality.");
    // The hero's headline may not be repeated here.
    expect(close).not.toHaveTextContent(/branches before they get permissions/i);

    expect(within(close).getByRole("link", { name: /SEE LIVE DEMO/ }))
      .toHaveAttribute("href", "/runs");
    expect(within(close).getByRole("link", { name: /HOW IT WORKS/ }))
      .toHaveAttribute("href", "/how-it-works");
  });
});

describe("the page as a whole", () => {
  it("never announces anything while the reader scrolls", () => {
    const { container } = renderApp("/");
    expect(container.querySelector("[aria-live]")).toBeNull();
  });

  it("quotes only the engine's values, never the offline fixture's", () => {
    const { container } = renderApp("/");
    const text = container.textContent ?? "";

    for (const stale of ["2.1%", "610ms", "16.2%", "1.9s", "12.4k"]) {
      expect(text).not.toContain(stale);
    }
  });
});
