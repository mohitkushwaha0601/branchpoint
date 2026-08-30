/**
 * The hero's narrative conductor.
 *
 * The monitor's own states are baked into the video now, so the HTML message
 * stack has to read the video's clock instead of running an independent timer.
 * A `timeupdate` listener maps `currentTime` onto one of four semantic states;
 * React only re-renders when that state actually changes, never per frame and
 * never through `requestAnimationFrame` — there are only four states to reach,
 * so the browser's own ~250ms `timeupdate` cadence is more than enough.
 *
 * The cutpoints below were found by extracting the baked-monitor footage frame
 * by frame (0.25s resolution, cropped to the monitor) and reading off the
 * crossfade midpoints between on-screen states. Both the desktop (1280x720)
 * and portrait (720x1280) exports were composited from the same 19.833s/24fps
 * timeline and land on identical midpoints, so one table drives both worlds —
 * proven by inspection, not assumed.
 */

import { useEffect, useState } from "react";

export interface HeroVideoCutpoint {
  /** Seconds into the loop at which the monitor reaches this state. */
  readonly at: number;
  readonly step: number;
}

export const HERO_VIDEO_CUTPOINTS: readonly HeroVideoCutpoint[] = [
  { at: 0, step: 0 }, // BRANCHPOINT — REHEARSAL ACTIVE, α β γ
  { at: 3.9, step: 1 }, // WORLD α — REPLAY FAILED, VETOED
  { at: 7.3, step: 2 }, // WORLD β — SURVIVED, RECOMMENDED
  { at: 10.6, step: 3 }, // HUMAN CHECKPOINT — AWAITING APPROVAL
] as const;

/** The state the story rests on wherever no video plays. */
export const HERO_VIDEO_LAST_STEP = 3;

/** The semantic step the monitor is showing at a given point in its loop. */
export function stepAtVideoTime(time: number): number {
  let step = HERO_VIDEO_CUTPOINTS[0]!.step;
  for (const cut of HERO_VIDEO_CUTPOINTS) {
    if (time < cut.at) break;
    step = cut.step;
  }
  return step;
}

export interface HeroVideoNarrative {
  readonly step: number;
  /** Ref callback for the `<video>` element whose clock drives `step`. */
  readonly attach: (node: HTMLVideoElement | null) => void;
}

/**
 * `HTMLMediaElement.NETWORK_NO_SOURCE`, inlined because jsdom does not expose
 * the constant. The element reaches this state only once every `<source>` has
 * been tried and rejected, which is what separates a dead video from one that
 * is merely still loading.
 */
const NETWORK_NO_SOURCE = 3;

/**
 * `active` is false wherever no `<video>` exists at all — reduced motion or
 * Save-Data — in which case the story rests on the state its poster already
 * shows, the same state a completed rehearsal ends on.
 *
 * A video that is *requested* and then fails has to reach that same resting
 * state, and by a different route: no `timeupdate` ever arrives, so the step
 * would otherwise stay pinned at the first beat while the poster underneath it
 * shows the last one — the stack claiming "Production intercepted" over a
 * monitor reading AWAITING APPROVAL. The failure is observed rather than
 * assumed: a `<source>` that fails does not bubble its error and the media
 * element fires none of its own, so the listener is registered for the capture
 * phase and confirmed against `networkState`.
 *
 * The failed element is remembered by identity, not as a boolean, so switching
 * worlds (desktop ↔ portrait) mounts a new element that starts clean with no
 * reset to perform.
 */
export function useHeroVideoNarrative(active: boolean): HeroVideoNarrative {
  const [node, setNode] = useState<HTMLVideoElement | null>(null);
  const [failedNode, setFailedNode] = useState<HTMLVideoElement | null>(null);
  const [liveStep, setLiveStep] = useState(0);

  useEffect(() => {
    if (!active || node === null) return;

    const onTimeUpdate = () => {
      setLiveStep((prev) => {
        const next = stepAtVideoTime(node.currentTime);
        return prev === next ? prev : next;
      });
    };

    const onError = () => {
      if (node.networkState === NETWORK_NO_SOURCE) setFailedNode(node);
    };

    onTimeUpdate();
    node.addEventListener("timeupdate", onTimeUpdate);
    node.addEventListener("error", onError, true);
    return () => {
      node.removeEventListener("timeupdate", onTimeUpdate);
      node.removeEventListener("error", onError, true);
    };
  }, [active, node]);

  const dead = node !== null && failedNode === node;

  return {
    step: active && !dead ? liveStep : HERO_VIDEO_LAST_STEP,
    attach: setNode,
  };
}
