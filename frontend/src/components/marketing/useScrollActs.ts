/**
 * Scroll-driven act tracking for the marketing sections.
 *
 * ## The trap this exists to avoid
 *
 * Mission Control owns `html`/`body` and keeps them at `overflow: hidden`; the
 * public site scrolls inside `.bp-marketing` instead (see `MarketingShell`).
 * So `window.scrollY` never changes on this page, a `window` scroll listener
 * never fires, and — the quiet one — an `IntersectionObserver` created with the
 * default root observes the *viewport*, which is not the thing that scrolls.
 * Any of those three mistakes fails **silently**: no error, no warning, just a
 * section that never advances.
 *
 * Everything here therefore resolves the scroll container from the DOM
 * (`closest('.bp-marketing')`) and passes it as the observer `root`.
 *
 * ## Why an observer and not a scroll handler
 *
 * There are only a handful of discrete acts to reach, so there is nothing to
 * interpolate. `rootMargin: "-50% 0px -50% 0px"` collapses the root to a
 * one-pixel line across the middle of the scroller; whichever act region
 * crosses that line is the active act. React state changes once per act — not
 * once per pixel — and there is no scroll handler, no `requestAnimationFrame`
 * loop and nothing to throttle.
 */

import { useCallback, useEffect, useState } from "react";

/** The class `MarketingShell` puts on the real scroll container. */
const SCROLL_ROOT = ".bp-marketing";

/**
 * Resolve the element that actually scrolls.
 *
 * Returns `null` rather than falling back to the viewport: a wrong root is
 * worse than no observer, because it produces plausible-looking behaviour that
 * is subtly wrong, and in tests it would hide exactly the bug this module is
 * built to prevent.
 */
export function findScrollRoot(node: Element): Element | null {
  return node.closest(SCROLL_ROOT);
}

export interface ScrollActs {
  /** Index of the act currently crossing the middle of the scroller. */
  readonly act: number;
  /** Attach to the element containing the `[data-act]` regions. */
  readonly trackRef: (node: HTMLElement | null) => void;
}

/**
 * Track which act is on screen.
 *
 * `enabled` is false wherever the scene is rendered as a static stack instead —
 * reduced motion and the phone layout — in which case the hook settles on
 * `restingAct` and never observes anything.
 *
 * `restingAct` defaults to the last act: where the animation cannot run, the
 * reader should be given the section's conclusion rather than its opening
 * frame. That rule is set out in the blueprint's accessibility contract.
 */
export function useScrollActs(
  actCount: number,
  enabled: boolean,
  restingAct: number = actCount - 1,
): ScrollActs {
  const [node, setNode] = useState<HTMLElement | null>(null);
  const [act, setAct] = useState(0);

  const trackRef = useCallback((next: HTMLElement | null) => setNode(next), []);

  useEffect(() => {
    if (!enabled || node === null) return;
    // jsdom has no IntersectionObserver. Bail to the resting act rather than
    // shimming one: the semantic content is in the DOM either way.
    if (typeof IntersectionObserver !== "function") return;

    const root = findScrollRoot(node);
    if (root === null) return;

    const regions = node.querySelectorAll<HTMLElement>("[data-act]");
    if (regions.length === 0) return;

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          const index = Number(
            (entry.target as HTMLElement).dataset["act"] ?? "0",
          );
          setAct((prev) => (prev === index ? prev : index));
        }
      },
      {
        root,
        // Collapse the root to a line across the middle of the scroller, so
        // exactly one act region can be intersecting at a time.
        rootMargin: "-50% 0px -50% 0px",
        threshold: 0,
      },
    );

    for (const region of regions) observer.observe(region);
    return () => observer.disconnect();
  }, [enabled, node]);

  return { act: enabled ? act : restingAct, trackRef };
}

/**
 * Fire once, the first time an element is scrolled into view.
 *
 * Used for the single auto-advance in the problem section: the reader sees the
 * headline reading, then it flips to the evidence reading on its own, once.
 * After that the control is theirs. Same root discipline as above.
 *
 * `threshold` is how much of the element has to be showing. It defaults to the
 * 0.55 the problem section wants — that flip should not happen until the reader
 * is actually looking at it — but an entrance animation needs to start as its
 * scene *arrives*, not once it has already settled, so those callers pass
 * something much smaller.
 */
export function useSeenOnce(
  enabled: boolean,
  onSeen: () => void,
  threshold = 0.55,
): (node: HTMLElement | null) => void {
  const [node, setNode] = useState<HTMLElement | null>(null);
  const ref = useCallback((next: HTMLElement | null) => setNode(next), []);

  useEffect(() => {
    if (!enabled || node === null) return;
    if (typeof IntersectionObserver !== "function") return;

    const root = findScrollRoot(node);
    if (root === null) return;

    let done = false;
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (done || !entry.isIntersecting) continue;
          done = true;
          onSeen();
          observer.disconnect();
        }
      },
      { root, threshold },
    );

    observer.observe(node);
    return () => observer.disconnect();
    // `onSeen` is intentionally not a dependency: it is a one-shot trigger and
    // re-subscribing on every render would re-arm it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, node, threshold]);

  return ref;
}
