/**
 * The three authority bands, as one component.
 *
 * Colour is never the carrier here. Every chip pairs its tint with a word
 * (`EXPLORATORY` / `DETERMINISTIC` / `PERMISSION`) and a mark (░ ■ ▲), so the
 * band survives greyscale, deuteranopia, and a screen reader that sees only
 * text. That rule is the reason this is a component rather than a class name:
 * there is exactly one place that can get it wrong.
 */

import type { AuthorityBand } from "../../data/canonicalIncident";
import { authorityBand } from "../../data/canonicalIncident";

export function AuthorityChip({
  band,
  suffix,
  size = "md",
}: {
  band: AuthorityBand;
  /** e.g. "· NO AUTHORITY" — printed after the band name, still as text. */
  suffix?: string;
  size?: "sm" | "md";
}) {
  const spec = authorityBand(band);
  return (
    <span className="bp-auth" data-band={band} data-size={size}>
      <span className="bp-auth__mark" aria-hidden="true">
        {spec.mark}
      </span>
      <span className="bp-auth__name">{band}</span>
      {suffix === undefined ? null : (
        <span className="bp-auth__suffix">{suffix}</span>
      )}
    </span>
  );
}

/**
 * The full three-line statement for one band: who, what it may do, what it may
 * never do. Used by the architecture explorer and the protocol inspector.
 */
export function AuthorityStatement({ band }: { band: AuthorityBand }) {
  const spec = authorityBand(band);
  return (
    <div className="bp-authstate">
      <p className="bp-authstate__who">{spec.who}</p>
      <dl className="bp-authstate__list">
        <dt>can</dt>
        <dd>{spec.may.join(" · ")}</dd>
        <dt>cannot</dt>
        <dd>{spec.mayNot.join(" · ")}</dd>
      </dl>
    </div>
  );
}
