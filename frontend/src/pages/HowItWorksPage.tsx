/**
 * Placeholder.
 *
 * The hero links here, so the route has to exist and has to be honest about
 * what it is. The real ten-stage page is Phase 3.
 */

import { Link } from "react-router-dom";

import { MarketingShell } from "../components/marketing/MarketingShell";

export function HowItWorksPage() {
  return (
    <MarketingShell>
      <div className="mx-auto max-w-[62ch] px-[var(--bp-gutter)] pt-[calc(var(--bp-header-h)+96px)] pb-24">
        <p className="bp-eyebrow">How it works</p>
        <h1 className="bp-display mt-4">Not written yet.</h1>
        <p className="bp-lead mt-5">
          This page will walk the ten stages of a run and show exactly where
          creative agents stop having authority. It is not built yet, and saying
          otherwise would be the opposite of the point.
        </p>
        <p className="bp-lead mt-4">
          The system itself is real and running. You can watch it decide.
        </p>
        <div className="mt-8">
          <Link className="bp-cta bp-cta--primary" to="/runs">
            SEE LIVE DEMO
          </Link>
        </div>
      </div>
    </MarketingShell>
  );
}
