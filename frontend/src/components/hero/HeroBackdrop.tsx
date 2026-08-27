/**
 * The world and the monitor: one baked-monitor loop, in whichever cut fits the
 * viewport.
 *
 * There are two shot-for-purpose worlds, not one world cropped two ways — a
 * 16:9 landscape cut for the desktop composition, and a 9:16 portrait cut whose
 * sky, island and workstation were framed for a phone. Both now carry the
 * monitor's on-screen narrative (REHEARSAL ACTIVE → VETOED → RECOMMENDED →
 * AWAITING APPROVAL) baked directly into the footage, so there is no separate
 * HTML terminal welded on top of it.
 *
 * The right cut is chosen in JavaScript rather than by `<source media>` so
 * that **only the chosen one is ever in the DOM**, and therefore only its bytes
 * are ever fetched. A browser given both would speculatively pull the wrong
 * one.
 *
 * `videoRef` is a plain callback ref, not an object ref: it feeds
 * `useHeroVideoNarrative`, which needs to know the moment the element mounts
 * or unmounts (on a world change, or when reduced motion/Save-Data withholds
 * video entirely) so it can attach or drop its `timeupdate` listener.
 *
 * The matching poster is a separate `<img>`, never removed: what paints first,
 * what stays if the video fails, and the whole environment under reduced
 * motion or Save-Data. Because it already shows the HUMAN CHECKPOINT state,
 * the hero still reads as complete with no video at all.
 */

import { useState } from "react";

import { useAmbientVideo, useMobileHero } from "./heroMedia";

const DESKTOP = {
  poster: "/hero/branchpoint-desktop-monitor-poster.webp",
  webm: "/hero/branchpoint-desktop-monitor.webm",
  mp4: "/hero/branchpoint-desktop-monitor.mp4",
} as const;

const MOBILE = {
  poster: "/hero/branchpoint-mobile-monitor-poster.webp",
  webm: "/hero/branchpoint-mobile-monitor.webm",
  mp4: "/hero/branchpoint-mobile-monitor.mp4",
} as const;

export function HeroBackdrop({
  videoRef,
}: {
  videoRef: (node: HTMLVideoElement | null) => void;
}) {
  const mobile = useMobileHero();
  const ambient = useAmbientVideo();
  const [playing, setPlaying] = useState(false);
  const world = mobile ? MOBILE : DESKTOP;

  return (
    <div className="bp-hero__backdrop" aria-hidden="true">
      <img
        className="bp-hero__poster"
        src={world.poster}
        alt=""
        decoding="async"
        fetchPriority="high"
      />

      {ambient ? (
        <video
          // Remount on the world change so the element never keeps a decoded
          // buffer of the cut it is no longer showing.
          key={mobile ? "mobile" : "desktop"}
          ref={videoRef}
          className="bp-hero__video"
          data-playing={playing ? "" : undefined}
          aria-hidden="true"
          autoPlay
          muted
          loop
          playsInline
          preload="metadata"
          poster={world.poster}
          onPlaying={() => setPlaying(true)}
        >
          <source src={world.webm} type="video/webm" />
          <source src={world.mp4} type="video/mp4" />
        </video>
      ) : null}

      {/* Keeps the copy readable however the sky drifts, and deepens the
          negative space each composition was framed around. The desktop cut
          fades left-to-right across the copy column; the portrait cut fades
          top-down, because that is where its copy sits. */}
      <div className="bp-hero__scrim" />
    </div>
  );
}
