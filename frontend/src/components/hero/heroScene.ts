/**
 * Scene space.
 *
 * The desktop hero's environment is a 1280x720 baked-monitor loop — the world
 * and the monitor's on-screen state are both part of the footage now. The one
 * thing still drawn in HTML is the status stack, standing beside the desk, and
 * it has to stay welded to that physical spot in the footage while the artwork
 * is cropped differently at every viewport.
 *
 * So there is exactly one coordinate system: **source pixels of the media**.
 * `.bp-hero__scene` in `marketing.css` is a real box holding the media's exact
 * 16:9 ratio, sized to cover the hero and anchored bottom-right — which is what
 * `object-fit: cover` with `object-position: 100% 100%` does, but as a box, so
 * a coordinate inside it still means something. From that box the stylesheet
 * derives `--bp-px`: the rendered length of one source pixel. `px(n)` turns a
 * source-pixel number into that length.
 *
 * Because the box holds the source ratio exactly, one `--bp-px` serves both
 * axes. The stack's position below was measured by overlaying it on the
 * running page at 1440x900 and reading the result back off a 2x screenshot —
 * never estimated.
 *
 * The mobile hero has no scene-anchored UI at all (one card, positioned in
 * viewport units), so none of this applies there.
 */

export const SOURCE_WIDTH = 1280;
export const SOURCE_HEIGHT = 720;

/** `n` source pixels, as a rendered CSS length. */
export function px(n: number): string {
  return `calc(${n} * var(--bp-px))`;
}

/** `n` source pixels measured up from the bottom of the scene box. */
export function fromBottom(n: number): string {
  return px(SOURCE_HEIGHT - n);
}

/**
 * The status stack, standing beside the workstation over the dark deck.
 *
 * Bottom-anchored: new messages arrive at the bottom and push older ones up, so
 * the stack grows out of the desk rather than down from the sky. Left of the
 * monitor and right of the copy column, with real clearance on both sides.
 *
 * Cards are a fixed height so the slot arithmetic that drives the push is exact
 * and needs no measurement: card `i` sits `slot * (height + gap)` above the
 * anchor, and `slot` is just how many messages have arrived since it did.
 */
export const MESSAGES = {
  left: 700,
  /** Source-space y of the stack's baseline — clear of the keyboard at 575. */
  bottom: 570,
  width: 196,
  cardHeight: 42,
  gap: 8,
} as const;

/** How far above the stack's baseline the card in `slot` sits, in source px. */
export function messageOffset(slot: number): number {
  return slot * (MESSAGES.cardHeight + MESSAGES.gap);
}
