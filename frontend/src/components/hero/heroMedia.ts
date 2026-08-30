/**
 * What the reader's device and preferences allow the hero to do.
 *
 * Each of these is decided *before* the thing it gates is rendered, rather than
 * by starting something and then stopping it. When video is withheld no
 * `<video>` element exists, so there is nothing to autoplay, nothing to cancel,
 * and no media bytes fetched; when the narrative is withheld no timers are ever
 * scheduled.
 */

import { useEffect, useState } from "react";

const REDUCED_MOTION = "(prefers-reduced-motion: reduce)";
/**
 * The hero has two worlds, and this is the line between them.
 *
 * Below it the page uses the dedicated 9:16 portrait footage full-bleed, with
 * one narrative card. Above it the 16:9 desktop footage carries the baked
 * monitor, alongside the crisp HTML status stack.
 *
 * 640px, chosen from layout rather than device class: the portrait media covers
 * without vertical cropping only while the viewport is taller than 9:16, which
 * every phone is and no tablet is. It is a media query, never user-agent
 * sniffing.
 */
const MOBILE = "(max-width: 639px)";

function list(query: string): MediaQueryList | null {
  // jsdom ships no matchMedia. Falling back to "no match" gives the
  // desktop-without-reduced-motion default, which is also what the tests assert
  // against unless they stub it.
  if (typeof window.matchMedia !== "function") return null;
  return window.matchMedia(query);
}

function matches(query: string): boolean {
  return list(query)?.matches === true;
}

/** Subscribes to one media query and re-renders when it flips. */
function useMediaQuery(query: string): boolean {
  const [value, setValue] = useState(() => matches(query));

  useEffect(() => {
    const mql = list(query);
    if (mql === null) return;

    const sync = () => setValue(mql.matches);
    mql.addEventListener("change", sync);
    // The query can have flipped between first render and this effect.
    sync();

    return () => mql.removeEventListener("change", sync);
  }, [query]);

  return value;
}

export function useReducedMotion(): boolean {
  return useMediaQuery(REDUCED_MOTION);
}

/** True where the hero switches to the dedicated portrait world. */
export function useMobileHero(): boolean {
  return useMediaQuery(MOBILE);
}

interface SaveDataConnection {
  readonly saveData?: boolean;
}

function prefersToSaveData(): boolean {
  const connection = (navigator as Navigator & { connection?: SaveDataConnection })
    .connection;
  return connection?.saveData === true;
}

/**
 * Whether to play the ambient loop.
 *
 * Withheld for reduced motion and for Save-Data. Phones still get it — they get
 * their *own* portrait cut, composed and baked for that viewport rather than
 * cropped down from the desktop one.
 */
export function useAmbientVideo(): boolean {
  const reduced = useReducedMotion();
  const [saveData] = useState(prefersToSaveData);
  return !reduced && !saveData;
}
