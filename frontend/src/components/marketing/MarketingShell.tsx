/**
 * The public site's shell.
 *
 * Mission Control keeps `html`/`body` at `overflow: hidden` because its own
 * panes own scrolling. Rather than move that ownership globally — which would
 * make every Mission Control route depend on the marketing site existing — the
 * marketing routes scroll inside their own container.
 */

import type { ReactNode } from "react";

import "../../styles/marketing.css";

import { MarketingHeader } from "./MarketingHeader";

export function MarketingShell({ children }: { children: ReactNode }) {
  return (
    <div className="bp-marketing">
      <a className="bp-skip" href="#bp-main">
        Skip to content
      </a>
      <MarketingHeader />
      <main id="bp-main">{children}</main>
    </div>
  );
}
