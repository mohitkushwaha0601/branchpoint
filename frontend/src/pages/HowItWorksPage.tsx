/**
 * `/how-it-works`.
 *
 * Landing sells the idea; this proves the system. It duplicates no landing
 * section — the one overlap, the approval card, appears here as a static
 * binding record and is operable only on the landing page, where the reader has
 * already been told why it matters.
 */

import { MarketingShell } from "../components/marketing/MarketingShell";
import { ProtocolShell } from "../components/protocol/ProtocolShell";

import "../styles/marketing-sections.css";
import "../styles/marketing-argument.css";
import "../styles/protocol.css";

export function HowItWorksPage() {
  return (
    <MarketingShell>
      <ProtocolShell />
    </MarketingShell>
  );
}
