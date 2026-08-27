/**
 * Section 09 — CLOSE.
 *
 * Quiet on purpose. The page has just spent nine viewports arguing; the close
 * does not argue again, does not repeat the hero's headline, and carries no
 * artwork beyond a single hairline branch mark echoing the fork from 02 at very
 * low opacity.
 *
 * The two destinations are deliberately unequal. `SEE LIVE DEMO` goes to the
 * running system, because the strongest thing this product can say is *go and
 * watch it decide*. `HOW IT WORKS` is the patient route for the reader who
 * wants the whole protocol.
 */

import { Link } from "react-router-dom";

import { RUN_ID } from "../../../data/canonicalIncident";

export function ClosingCta() {
  return (
    <section className="bp-sec bp-sec--close" aria-labelledby="bp-close-title">
      {/* The fork mark from section 02, at 20% and inert. */}
      <svg
        className="bp-close__mark"
        viewBox="0 0 240 120"
        fill="none"
        aria-hidden="true"
      >
        <path d="M4 60 H84" />
        <path d="M84 60 C120 60 120 18 156 18 H236" />
        <path d="M84 60 H236" />
        <path d="M84 60 C120 60 120 102 156 102 H236" />
      </svg>

      <div className="bp-sec__inner bp-close__inner">
        <p className="bp-eyebrow">09 — Close</p>
        <h2 id="bp-close-title" className="bp-close__title">
          Rehearse before reality.
        </h2>
        <p className="bp-lead bp-close__lead">
          Every consequential action gets executed somewhere it cannot hurt
          anyone, attacked by something trying to break it, and decided by
          evidence a machine can re-check. Then — and only then — a human is
          asked one question with one answer.
        </p>

        <div className="bp-close__ctas">
          <Link className="bp-cta bp-cta--primary" to="/runs">
            SEE LIVE DEMO
          </Link>
          <Link className="bp-cta bp-cta--ghost" to="/how-it-works">
            HOW IT WORKS
          </Link>
        </div>

        <p className="bp-close__meta">
          The run quoted throughout this page is {RUN_ID}. Every number on it
          came out of the engine, not out of a slide.
        </p>
      </div>
    </section>
  );
}
