/**
 * The public landing page.
 *
 * These cover the things that would actually break: the index route's contract,
 * the fact that the page needs no backend, that Mission Control's global scroll
 * ownership is untouched, that the hero's meaning survives with no video and no
 * animation, and the architectural rule this final pass was built around — the
 * monitor's narrative is pixels baked into the video, and the crisp HTML status
 * stack beside it reads the video's own clock rather than running an
 * independent timer.
 */

import { act, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  HERO_VIDEO_CUTPOINTS,
  HERO_VIDEO_LAST_STEP,
  stepAtVideoTime,
} from "../components/hero/useHeroNarrative";
import { renderApp } from "./renderRun";

afterEach(() => vi.unstubAllGlobals());

/**
 * jsdom has no media queries of its own, so the hooks' "no match" fallback — a
 * desktop reader who has not asked for reduced motion — is what most tests see.
 * These stubs are how the withheld cases get exercised.
 */
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

describe("landing page", () => {
  it("renders one h1 carrying the product line", () => {
    renderApp("/");

    const headings = screen.getAllByRole("heading", { level: 1 });
    expect(headings).toHaveLength(1);
    expect(headings[0]).toHaveTextContent(
      "Agents get branches before they get permissions.",
    );
  });

  it("sends the primary call to action into live Mission Control", () => {
    renderApp("/");

    // The header and the hero both offer it; every one of them must land in
    // real Mission Control, never in a second demo.
    const ctas = screen.getAllByRole("link", { name: /SEE LIVE DEMO/ });
    expect(ctas.length).toBeGreaterThan(0);
    for (const cta of ctas) {
      expect(cta).toHaveAttribute("href", "/runs");
    }
    expect(
      screen.getByRole("link", { name: /HOW IT WORKS/ }),
    ).toHaveAttribute("href", "/how-it-works");
  });

  it("renders with no backend at all", () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    renderApp("/");

    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
    // Unlike every Mission Control route, the landing page never calls the API.
    // It has to survive a dead backend, because that is when people arrive.
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("leaves Mission Control's global scroll ownership alone", () => {
    const bodyBefore = document.body.getAttribute("style");
    const htmlBefore = document.documentElement.getAttribute("style");

    renderApp("/");

    // The marketing route scrolls inside its own shell. If this ever starts
    // mutating html/body, Mission Control's fixed layout is the thing that pays.
    expect(document.body.getAttribute("style")).toBe(bodyBefore);
    expect(document.documentElement.getAttribute("style")).toBe(htmlBefore);
    expect(document.querySelector(".bp-marketing")).not.toBeNull();
  });

  it("offers a skip link ahead of the header", () => {
    renderApp("/");

    const skip = screen.getByRole("link", { name: /Skip to content/ });
    expect(skip).toHaveAttribute("href", "#bp-main");
  });
});

describe("baked-monitor backdrop", () => {
  it("offers the desktop monitor WebM first and keeps MP4 as the fallback", () => {
    const { container } = renderApp("/");

    // Order is the contract: VP9 is a third the size, and a browser takes the
    // first source it can play.
    const sources = [...container.querySelectorAll(".bp-hero__video source")];
    expect(sources.map((s) => s.getAttribute("type"))).toEqual([
      "video/webm",
      "video/mp4",
    ]);
    expect(sources[0]).toHaveAttribute(
      "src",
      "/hero/branchpoint-desktop-monitor.webm",
    );
    expect(sources[1]).toHaveAttribute(
      "src",
      "/hero/branchpoint-desktop-monitor.mp4",
    );
  });

  it("never references the retired ambient-only cut", () => {
    const { container } = renderApp("/");

    // The monitor's narrative used to live in separate HTML on top of an
    // ambient-only loop. That loop is archived outside the public tree now;
    // the runtime must reference only the baked-monitor exports.
    const media = [...container.querySelectorAll("source, video, img")]
      .flatMap((el) => [el.getAttribute("src"), el.getAttribute("poster")])
      .filter((value): value is string => value !== null);
    expect(media.length).toBeGreaterThan(0);
    for (const url of media) {
      expect(url).toContain("monitor");
    }
  });

  it("loops the world continuously, muted and silent", () => {
    const { container } = renderApp("/");
    const video = container.querySelector<HTMLVideoElement>(".bp-hero__video");

    expect(video).not.toBeNull();
    expect(video).toHaveAttribute("autoplay");
    expect(video).toHaveAttribute("playsinline");
    expect(video).toHaveAttribute("aria-hidden", "true");
    expect(video).not.toHaveAttribute("controls");
    // The monitor's narrative loops with the world — an ambient loop that ends
    // leaves the hero looking dead, which is what `loop` is here to prevent.
    expect(video).toHaveAttribute("loop");
    expect(video?.muted).toBe(true);
    // The whole file is never pulled down before the page is usable.
    expect(video).toHaveAttribute("preload", "metadata");
  });

  it("paints the approved monitor poster underneath", () => {
    const { container } = renderApp("/");

    // A real fallback, not a placeholder: its own element, so it survives the
    // video failing or being withheld entirely. The poster already shows the
    // HUMAN CHECKPOINT state, so the page still reads as complete.
    const poster = container.querySelector<HTMLImageElement>(".bp-hero__poster");
    expect(poster).toHaveAttribute(
      "src",
      "/hero/branchpoint-desktop-monitor-poster.webp",
    );
    expect(poster).toHaveAttribute("alt", "");
    expect(container.querySelector(".bp-hero__video")).toHaveAttribute(
      "poster",
      "/hero/branchpoint-desktop-monitor-poster.webp",
    );
  });
});

describe("video-time to semantic-state mapping", () => {
  it("holds BRANCHPOINT from the start of the loop", () => {
    expect(stepAtVideoTime(0)).toBe(0);
    expect(stepAtVideoTime(3.89)).toBe(0);
  });

  it("cuts to WORLD α at its measured crossfade midpoint", () => {
    expect(stepAtVideoTime(3.9)).toBe(1);
    expect(stepAtVideoTime(7.29)).toBe(1);
  });

  it("cuts to WORLD β at its measured crossfade midpoint", () => {
    expect(stepAtVideoTime(7.3)).toBe(2);
    expect(stepAtVideoTime(10.59)).toBe(2);
  });

  it("cuts to HUMAN CHECKPOINT and holds it through the loop's tail", () => {
    expect(stepAtVideoTime(10.6)).toBe(3);
    expect(stepAtVideoTime(19)).toBe(3);
    expect(stepAtVideoTime(19.8)).toBe(HERO_VIDEO_LAST_STEP);
  });

  it("returns to BRANCHPOINT the instant the loop wraps back to zero", () => {
    expect(stepAtVideoTime(0.001)).toBe(0);
  });

  it("is ordered and starts at the beginning of the loop", () => {
    expect(HERO_VIDEO_CUTPOINTS[0]?.at).toBe(0);
    for (let i = 1; i < HERO_VIDEO_CUTPOINTS.length; i += 1) {
      expect(HERO_VIDEO_CUTPOINTS[i]!.at).toBeGreaterThan(
        HERO_VIDEO_CUTPOINTS[i - 1]!.at,
      );
    }
  });
});

describe("the status stack", () => {
  it("renders beside the desk as real HTML text, never in the video", () => {
    const { container } = renderApp("/");

    // Real DOM text, not pixels in a video and not canvas.
    const stack = container.querySelector(".bp-hero__messages");
    expect(stack).not.toBeNull();
    expect(stack?.querySelectorAll(".bp-msg")).toHaveLength(4);
    expect(stack).toHaveTextContent("BRANCHPOINT");
  });

  it("states only the branchpoint structure, leaving incident and agent to the monitor", () => {
    const { container } = renderApp("/");
    const text = container.querySelector(".bp-hero__messages")?.textContent ?? "";

    for (const label of ["BRANCHPOINT", "WORLD α", "WORLD β", "HUMAN CHECKPOINT"]) {
      expect(text).toContain(label);
    }
    // The monitor already establishes these; a second HTML copy would just
    // repeat pixels the reader has already seen.
    expect(text).not.toContain("INCIDENT");
    expect(text).not.toContain("AGENT");
  });

  it("shows at most three status cards at once", () => {
    const { container } = renderApp("/");

    const cards = [...container.querySelectorAll<HTMLElement>(".bp-msg")];
    expect(cards).toHaveLength(4);
    const visible = cards.filter((c) => c.dataset["state"] === "visible");
    expect(visible.length).toBeLessThanOrEqual(3);
    for (const card of cards) {
      expect(["waiting", "visible", "retired"]).toContain(card.dataset["state"]);
    }
  });

  it("draws no terminal, no branch pipes and no external graph over the world", () => {
    const { container } = renderApp("/");

    // The monitor's own states are baked into the video; nothing here may
    // duplicate them as a second HTML terminal, and the alpha/beta/gamma
    // structure is never drawn as pipes across the sky.
    for (const selector of [
      ".bp-hero__screen",
      ".bp-term",
      ".bp-hero__graph",
      ".bp-branch",
      ".bp-branch-list",
      ".bp-events",
      ".bp-hero__events",
    ]) {
      expect(container.querySelector(selector)).toBeNull();
    }
    expect(container.querySelector(".bp-hero__viewport svg")).toBeNull();
  });

  it("withholds the stack entirely on a phone", () => {
    stubMedia(["max-width"]);
    const { container } = renderApp("/");

    // At this width the stack would be squeezed against the single mobile
    // card. It is not rendered at all — no ghost containers left behind.
    expect(container.querySelector(".bp-hero__messages")).toBeNull();
    expect(container.querySelectorAll(".bp-msg")).toHaveLength(0);
    // The world and the copy still carry the page.
    expect(container.querySelector(".bp-hero__poster")).not.toBeNull();
    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
  });
});

describe("the phone's world", () => {
  function stubPhone(extra: readonly string[] = []) {
    vi.stubGlobal("matchMedia", (query: string) => ({
      media: query,
      matches:
        query.includes("max-width") || extra.some((m) => query.includes(m)),
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }));
  }

  it("loads the dedicated portrait monitor cut and never the desktop one", () => {
    stubPhone();
    const { container } = renderApp("/");

    const sources = [...container.querySelectorAll(".bp-hero__video source")];
    expect(sources.map((el) => el.getAttribute("src"))).toEqual([
      "/hero/branchpoint-mobile-monitor.webm",
      "/hero/branchpoint-mobile-monitor.mp4",
    ]);
    expect(container.querySelector(".bp-hero__poster")).toHaveAttribute(
      "src",
      "/hero/branchpoint-mobile-monitor-poster.webp",
    );

    // The whole point of choosing in JS rather than `<source media>`: the
    // desktop cut must not be in the DOM at all, so its bytes are never
    // requested.
    const urls = [...container.querySelectorAll("source, video, img")]
      .flatMap((el) => [el.getAttribute("src"), el.getAttribute("poster")])
      .filter((v): v is string => v !== null);
    for (const url of urls) {
      expect(url).toContain("mobile");
    }
  });

  it("shows exactly one narrative card, never a stack", () => {
    stubPhone();
    const { container } = renderApp("/");

    const card = container.querySelector(".bp-hero__mobile-card");
    expect(card).not.toBeNull();
    // Four beats are mounted so the change can be a crossfade, but at most one
    // is ever visible.
    const beats = [...container.querySelectorAll<HTMLElement>(".bp-mcard")];
    expect(beats).toHaveLength(4);
    expect(beats.filter((b) => b.dataset["state"] === "visible").length)
      .toBeLessThanOrEqual(1);

    // and none of the desktop apparatus
    expect(container.querySelector(".bp-hero__messages")).toBeNull();
    expect(container.querySelector(".bp-term")).toBeNull();
  });

  it("drops the setup beats the single-card format cannot carry", () => {
    stubPhone();
    const { container } = renderApp("/");
    const text = container.querySelector(".bp-hero__mobile-card")?.textContent ?? "";

    // With no stack to hold context, INCIDENT and AGENT would be gone before
    // they paid off. The argument itself remains.
    expect(text).toContain("BRANCHPOINT");
    expect(text).toContain("WORLD α");
    expect(text).toContain("WORLD β");
    expect(text).toContain("HUMAN CHECKPOINT");
    expect(text).not.toContain("INCIDENT");
    expect(text).not.toContain("AGENT");
  });

  it("uses the mobile poster only, and rests on the checkpoint, under reduced motion", () => {
    stubPhone(["prefers-reduced-motion"]);
    const { container } = renderApp("/");

    expect(container.querySelector(".bp-hero__video")).toBeNull();
    expect(container.querySelector(".bp-hero__poster")).toHaveAttribute(
      "src",
      "/hero/branchpoint-mobile-monitor-poster.webp",
    );
    const visible = [...container.querySelectorAll<HTMLElement>(".bp-mcard")]
      .filter((b) => b.dataset["state"] === "visible")
      .map((b) => b.querySelector(".bp-mcard__label")?.textContent);
    expect(visible).toEqual(["HUMAN CHECKPOINT"]);
  });

  it("keeps the calls to action working", () => {
    stubPhone();
    renderApp("/");

    for (const cta of screen.getAllByRole("link", { name: /SEE LIVE DEMO/ })) {
      expect(cta).toHaveAttribute("href", "/runs");
    }
    expect(
      screen.getByRole("link", { name: /HOW IT WORKS/ }),
    ).toHaveAttribute("href", "/how-it-works");
  });

  it("never announces the cycling card", () => {
    stubPhone();
    const { container } = renderApp("/");

    expect(container.querySelector(".bp-hero__mobile-card")).toHaveAttribute(
      "aria-hidden",
      "true",
    );
    expect(container.querySelector("[aria-live]")).toBeNull();
    // The static description still carries the claim.
    expect(
      screen.getByText(/BRANCHPOINT rehearses multiple candidate actions/),
    ).toBeInTheDocument();
  });
});

describe("a video that fails to load", () => {
  /**
   * Reproduces what Chromium actually does when every `<source>` is blocked,
   * measured against the running page: the element fires no `error` of its own
   * and no `timeupdate` ever arrives, each `<source>` fires a non-bubbling
   * `error`, and `networkState` settles on NETWORK_NO_SOURCE (3).
   */
  function killSources(container: HTMLElement) {
    const video = container.querySelector<HTMLVideoElement>(".bp-hero__video")!;
    Object.defineProperty(video, "networkState", { value: 3, configurable: true });
    for (const source of video.querySelectorAll("source")) {
      source.dispatchEvent(new Event("error"));
    }
    return video;
  }

  it("rests on the state its poster is already showing", () => {
    const { container } = renderApp("/");

    act(() => void killSources(container));

    // The poster still shows HUMAN CHECKPOINT, so the stack must say the same
    // thing. Pinned at the first beat it would contradict the picture behind it.
    const visible = [...container.querySelectorAll<HTMLElement>(".bp-msg")]
      .filter((c) => c.dataset["state"] === "visible")
      .map((c) => c.querySelector(".bp-msg__label")?.textContent);
    expect(visible).toEqual(["WORLD α", "WORLD β", "HUMAN CHECKPOINT"]);
    expect(container.querySelector(".bp-hero__poster")).toHaveAttribute(
      "src",
      "/hero/branchpoint-desktop-monitor-poster.webp",
    );
  });

  it("keeps the hero whole, with the copy and both calls to action", () => {
    const { container } = renderApp("/");

    act(() => void killSources(container));

    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
    expect(
      screen.getAllByRole("link", { name: /SEE LIVE DEMO/ })[0],
    ).toHaveAttribute("href", "/runs");
    // The poster is its own element, so it is still there to be seen.
    expect(container.querySelector(".bp-hero__poster")).not.toBeNull();
  });

  it("ignores a source error while the element still has somewhere to go", () => {
    const { container } = renderApp("/");
    const video = container.querySelector<HTMLVideoElement>(".bp-hero__video")!;

    // NETWORK_LOADING: the WebM was rejected but the MP4 has not been tried.
    // Giving up here would abandon a video that is about to play perfectly.
    Object.defineProperty(video, "networkState", { value: 2, configurable: true });
    act(() => {
      video.querySelector("source")!.dispatchEvent(new Event("error"));
    });

    const visible = [...container.querySelectorAll<HTMLElement>(".bp-msg")]
      .filter((c) => c.dataset["state"] === "visible")
      .map((c) => c.querySelector(".bp-msg__label")?.textContent);
    expect(visible).toEqual(["BRANCHPOINT"]);
  });

  it("gives the phone's single card the same resting state", () => {
    vi.stubGlobal("matchMedia", (query: string) => ({
      media: query,
      matches: query.includes("max-width"),
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }));
    const { container } = renderApp("/");

    act(() => void killSources(container));

    const visible = [...container.querySelectorAll<HTMLElement>(".bp-mcard")]
      .filter((b) => b.dataset["state"] === "visible")
      .map((b) => b.querySelector(".bp-mcard__label")?.textContent);
    expect(visible).toEqual(["HUMAN CHECKPOINT"]);
  });
});

describe("reduced motion", () => {
  it("requests no video and holds the story's conclusion", () => {
    stubMedia(["prefers-reduced-motion"]);
    const { container } = renderApp("/");

    // Not autoplayed and then paused — never created, so no media bytes are
    // fetched and there is no motion to cancel.
    expect(container.querySelector(".bp-hero__video")).toBeNull();
    expect(container.querySelector(".bp-hero__poster")).toHaveAttribute(
      "src",
      "/hero/branchpoint-desktop-monitor-poster.webp",
    );

    // The status stack rests on the state that carries the actual claim
    // rather than cycling to reach it — the same state the poster shows.
    const visible = [...container.querySelectorAll<HTMLElement>(".bp-msg")]
      .filter((c) => c.dataset["state"] === "visible")
      .map((c) => c.querySelector(".bp-msg__label")?.textContent);
    expect(visible).toEqual(["WORLD α", "WORLD β", "HUMAN CHECKPOINT"]);
  });

  it("keeps the whole hero standing when there is no video", () => {
    stubMedia(["prefers-reduced-motion"]);
    renderApp("/");

    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
    expect(
      screen.getAllByRole("link", { name: /SEE LIVE DEMO/ })[0],
    ).toHaveAttribute("href", "/runs");
  });
});

describe("accessibility", () => {
  it("carries one static description of the run", () => {
    renderApp("/");

    // The cycling UI is decorative and aria-hidden; this sentence is the claim,
    // stated once and never changed.
    expect(
      screen.getByText(/BRANCHPOINT rehearses multiple candidate actions/),
    ).toBeInTheDocument();
  });

  it("states the whole narrative as static text", () => {
    renderApp("/");

    const narrative = screen.getByRole("list");
    const steps = within(narrative).getAllByRole("listitem");
    expect(steps.length).toBeGreaterThanOrEqual(6);
    expect(narrative).toHaveTextContent(/World alpha is VETOED/);
    expect(narrative).toHaveTextContent(/comparator recommends it/);
    expect(narrative).toHaveTextContent(/Nothing has changed in production/);
  });

  it("never announces the hero through a live region", () => {
    const { container } = renderApp("/");

    // The stack changes as the video plays; a live region here would
    // interrupt a screen reader forever for no benefit.
    expect(container.querySelector("[aria-live]")).toBeNull();
    expect(container.querySelector('[role="status"]')).toBeNull();
    expect(
      container.querySelector(".bp-hero__messages"),
    ).toHaveAttribute("aria-hidden", "true");
  });
});

describe("how it works placeholder", () => {
  it("says plainly that it is not written yet", () => {
    renderApp("/how-it-works");

    expect(
      screen.getByRole("heading", { level: 1, name: /Not written yet/ }),
    ).toBeInTheDocument();
    for (const cta of screen.getAllByRole("link", { name: /SEE LIVE DEMO/ })) {
      expect(cta).toHaveAttribute("href", "/runs");
    }
  });
});
