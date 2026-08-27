/**
 * The public landing page.
 *
 * The hero makes a promise — agents get branches before they get permissions —
 * and the nine sections below have one job: make that promise survive contact
 * with a sceptic. They run as an argument, not as a feature list:
 *
 *   01 the trap        a proposal that passes every number you would check
 *   02 manyworlds      so stop checking numbers and execute the alternatives
 *   03 world explorer  what each world actually did, and what it proved
 *   04 the attack      a guess is not a finding; authority transfers on screen
 *   05 comparison      arithmetic on real axes, with no score anywhere
 *   06 checkpoint      a recommendation is not permission
 *   07 commit & verify permission changed; reality still has to be re-read
 *   08 architecture    who holds which authority, and who explicitly does not
 *   09 close           rehearse before reality
 *
 * Interaction mode changes at every step by design — toggle, sticky scene, tabs,
 * sticky reveal, matrix, operable demo, timed sequence, selector map, static.
 * The one thing this page must never become is ten identical cards.
 *
 * The hero above is frozen at `e0e9213` and is not touched here.
 */

import { Hero } from "../components/hero/Hero";
import { MarketingShell } from "../components/marketing/MarketingShell";
import { ApprovalFingerprint } from "../components/marketing/sections/ApprovalFingerprint";
import { AttackReplay } from "../components/marketing/sections/AttackReplay";
import { AuthorityArchitecture } from "../components/marketing/sections/AuthorityArchitecture";
import { ClosingCta } from "../components/marketing/sections/ClosingCta";
import { CommitVerify } from "../components/marketing/sections/CommitVerify";
import { ComparisonMatrix } from "../components/marketing/sections/ComparisonMatrix";
import { ManyworldsSection } from "../components/marketing/sections/ManyworldsSection";
import { ProblemSection } from "../components/marketing/sections/ProblemSection";
import { WorldExplorer } from "../components/marketing/sections/WorldExplorer";

import "../styles/marketing-sections.css";
import "../styles/marketing-argument.css";

export function LandingPage() {
  return (
    <MarketingShell>
      <Hero />
      <ProblemSection />
      <ManyworldsSection />
      <WorldExplorer />
      <AttackReplay />
      <ComparisonMatrix />
      <ApprovalFingerprint />
      <CommitVerify />
      <AuthorityArchitecture />
      <ClosingCta />
    </MarketingShell>
  );
}
