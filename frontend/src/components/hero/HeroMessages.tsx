/**
 * The status stack, standing on the deck beside the workstation.
 *
 * Every card is mounted from the start and positioned by its *slot* — how many
 * messages have arrived since it did. A card below the newest sits waiting at
 * `+10px` and transparent; slots 0 to 2 are the visible stack; anything older
 * keeps travelling upward as it fades. So a new beat is a single number change
 * and CSS does the rest: the arriving card rises into place while the ones
 * above it move up to make room and the fourth-oldest fades out — no mount and
 * unmount, no measurement, no layout thrash.
 *
 * Cards are a fixed height so that slot arithmetic is exact, which is why the
 * optional state chip sits on the label row rather than becoming a third line.
 */

import {
  MESSAGE_BEATS,
  type HeroTone,
  type MessageBeat,
} from "./heroNarrative";
import { MESSAGES, fromBottom, messageOffset, px } from "./heroScene";

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

/** How many cards stand in the stack at once. */
const VISIBLE = 3;
/** How far a card waits below the stack before it arrives, in source pixels. */
const ARRIVE_FROM = 10;

function Card({
  beat,
  slot,
}: {
  beat: MessageBeat;
  slot: number;
}) {
  const waiting = slot < 0;
  const retired = slot >= VISIBLE;
  const lift = waiting ? -ARRIVE_FROM : messageOffset(slot);

  // Visibility is an attribute, not an inline style: an inline `opacity` wins
  // against every stylesheet rule, which silently defeated the narrower
  // breakpoints' attempt to show fewer cards.
  const state = waiting ? "waiting" : retired ? "retired" : "visible";

  return (
    <div
      className="bp-msg"
      data-state={state}
      data-slot={slot}
      style={{
        height: px(MESSAGES.cardHeight),
        transform: `translateY(${px(-lift)})`,
      }}
    >
      <div className="bp-msg__head">
        <span className={`bp-msg__dot ${TONE_DOT[beat.tone]}`} />
        <span className={`bp-msg__label ${TONE_TEXT[beat.tone]}`}>
          {beat.label}
        </span>
        {beat.status !== undefined ? (
          <span className={`bp-msg__status ${TONE_TEXT[beat.tone]}`}>
            {beat.status}
          </span>
        ) : null}
      </div>
      <div className="bp-msg__body">{beat.body}</div>
    </div>
  );
}

export function HeroMessages({ step }: { step: number }) {
  return (
    <div
      className="bp-hero__messages"
      style={{
        left: px(MESSAGES.left),
        bottom: fromBottom(MESSAGES.bottom),
        width: px(MESSAGES.width),
        height: px(MESSAGES.cardHeight),
      }}
      aria-hidden="true"
    >
      {MESSAGE_BEATS.map((beat, index) => (
        <Card key={beat.id} beat={beat} slot={step - index} />
      ))}
    </div>
  );
}
