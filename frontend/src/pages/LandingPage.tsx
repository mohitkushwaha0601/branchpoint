/** The public landing page. Phase 1A is the hero and nothing else. */

import { Hero } from "../components/hero/Hero";
import { MarketingShell } from "../components/marketing/MarketingShell";

export function LandingPage() {
  return (
    <MarketingShell>
      <Hero />
      {/* Placeholder for the sections that land in Phase 2. It exists so the
          scroll container's behaviour can be inspected. */}
      <div className="h-[70vh] bg-[#07090d]" aria-hidden="true" />
    </MarketingShell>
  );
}
