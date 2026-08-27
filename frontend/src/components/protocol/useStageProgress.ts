/**
 * Which of the nine stages the reader is currently on.
 *
 * ## The same trap as the landing page, and it fails the same way
 *
 * `html`/`body` are `overflow: hidden` — Mission Control owns them — and the
 * public site scrolls inside `.bp-marketing`. An `IntersectionObserver` created
 * with the default root observes the viewport, which is not the thing that
 * scrolls here, so it silently never fires. There is no error and no warning:
 * the rail simply never advances. Every observer in this module therefore
 * resolves its root from the DOM and passes it explicitly.
 *
 * ## Why not a scroll handler
 *
 * There are nine discrete states and nothing to interpolate between them, so
 * there is nothing a scroll position buys that a sentinel does not. React state
 * changes nine times over the whole page rather than once per frame, and there
 * is no `requestAnimationFrame` loop to throttle or clean up.
 */

import { useCallback, useEffect, useState } from "react";

import { findScrollRoot } from "../marketing/useScrollActs";

export interface StageProgress {
  /** Index of the stage crossing the reading line. */
  readonly stage: number;
  /** Attach to the element containing the `[data-stage]` sections. */
  readonly trackRef: (node: HTMLElement | null) => void;
  /** Scroll one stage section into view. Used by the rail and the next affordance. */
  readonly goTo: (index: number) => void;
}

export function useStageProgress(
  count: number,
  enabled: boolean,
): StageProgress {
  const [node, setNode] = useState<HTMLElement | null>(null);
  const [stage, setStage] = useState(0);

  const trackRef = useCallback((next: HTMLElement | null) => setNode(next), []);

  useEffect(() => {
    if (!enabled || node === null) return;
    // jsdom ships no IntersectionObserver. Bail rather than shim: every stage's
    // content is in the DOM either way, so the page stays complete.
    if (typeof IntersectionObserver !== "function") return;

    const root = findScrollRoot(node);
    if (root === null) return;

    const sections = node.querySelectorAll<HTMLElement>("[data-stage]");
    if (sections.length === 0) return;

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          const index = Number(
            (entry.target as HTMLElement).dataset["stage"] ?? "0",
          );
          setStage((prev) => (prev === index ? prev : index));
        }
      },
      {
        root,
        // A reading line a third of the way down the scroller: a stage becomes
        // current when its top passes the point a reader is actually looking at,
        // not when its midpoint does.
        rootMargin: "-33% 0px -60% 0px",
        threshold: 0,
      },
    );

    for (const section of sections) observer.observe(section);
    return () => observer.disconnect();
  }, [enabled, node]);

  const goTo = useCallback(
    (index: number) => {
      const target = node?.querySelector<HTMLElement>(
        `[data-stage="${index}"]`,
      );
      // A smooth scroll is motion, and a reader who asked for none should get
      // an instant jump rather than a 600 ms glide they did not consent to.
      const reduced =
        typeof window.matchMedia === "function" &&
        window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      target?.scrollIntoView({
        block: "start",
        behavior: reduced ? "auto" : "smooth",
      });
    },
    [node],
  );

  return { stage: Math.min(stage, count - 1), trackRef, goTo };
}
