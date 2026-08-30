/**
 * The phone's narrative: exactly one card, one beat at a time.
 *
 * No stack. A phone has neither the width to hold three cards beside the
 * artwork nor the height to spare above it, and three stacked cards on a 390px
 * screen read as a notification pile rather than as a system talking. So the
 * story is told serially: each card rises into place, holds long enough to be
 * read on its own, and leaves before the next arrives.
 *
 * Every card is mounted and positioned in the same place; only the active one
 * is opaque. That makes the change a pure opacity/translate crossfade with no
 * layout work and nothing mounting or unmounting mid-transition.
 *
 * The card sits at the seam between the portrait frame's dark upper half, where
 * the copy lives, and its lit lower half, where the workstation is — so it
 * reads as belonging to the world rather than floating over the text.
 */

import { MOBILE_BEATS, type HeroTone } from "./heroNarrative";

const TONE_TEXT: Record<HeroTone, string> = {
  ok: "text-ok",
  fail: "text-fail",
  run: "text-run",
  gate: "text-gate",
  warn: "text-warn",
  muted: "text-fg-dim",
};

const TONE_DOT: Record<HeroTone, string> = {
  ok: "bg-ok",
  fail: "bg-fail",
  run: "bg-run",
  gate: "bg-gate",
  warn: "bg-warn",
  muted: "bg-fg-faint",
};

export function HeroMobileCard({ step }: { step: number }) {
  return (
    <div className="bp-hero__mobile-card" aria-hidden="true">
      {MOBILE_BEATS.map((beat, index) => {
        const active = index === step;
        return (
          <div
            key={beat.id}
            className="bp-mcard"
            data-state={active ? "visible" : index < step ? "past" : "waiting"}
          >
            <div className="bp-mcard__head">
              <span className={`bp-mcard__dot ${TONE_DOT[beat.tone]}`} />
              <span className={`bp-mcard__label ${TONE_TEXT[beat.tone]}`}>
                {beat.label}
              </span>
              {beat.status !== undefined ? (
                <span className={`bp-mcard__status ${TONE_TEXT[beat.tone]}`}>
                  {beat.status}
                </span>
              ) : null}
            </div>
            <div className="bp-mcard__body">{beat.body}</div>
          </div>
        );
      })}
    </div>
  );
}
