/**
 * The public landing page.
 *
 * Phase 1A shipped the hero. Phase 2B adds the first two sections below it —
 * the trap, then Manyworlds. The page deliberately ends after those with a
 * continuation marker rather than a footer: the rest of the argument (world
 * explorer, the attack, comparison, the checkpoint) is not built yet, and
 * pretending otherwise would be the opposite of the point.
 */

import { Hero } from "../components/hero/Hero";
import { MarketingShell } from "../components/marketing/MarketingShell";
import { ManyworldsSection } from "../components/marketing/sections/ManyworldsSection";
import { ProblemSection } from "../components/marketing/sections/ProblemSection";

import "../styles/marketing-sections.css";

export function LandingPage() {
  return (
    <MarketingShell>
      <Hero />
      <ProblemSection />
      <ManyworldsSection />

      {/* Where Phase 2C picks up. Honest about being unfinished. */}
      <div className="bp-next">
        <div className="bp-next__inner">
          <span className="bp-next__label">Next</span>
          <span className="bp-next__value">Inspect the worlds</span>
        </div>
      </div>
    </MarketingShell>
  );
}
