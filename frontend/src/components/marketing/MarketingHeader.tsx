/**
 * The public site's header.
 *
 * Deliberately not `AppHeader`: Mission Control's nav advertises a disabled tab
 * and a backend health pill, neither of which means anything to someone who has
 * just arrived. This one sits inside the scene with no bar behind it.
 */

import { GitBranch } from "lucide-react";
import { Link } from "react-router-dom";

export function MarketingHeader() {
  return (
    <header className="bp-mheader">
      <Link
        to="/"
        className="flex items-center gap-2 text-fg no-underline"
        aria-label="BRANCHPOINT home"
      >
        <GitBranch className="h-4 w-4 text-run" aria-hidden="true" />
        <span className="font-mono text-[13px] font-semibold tracking-[0.14em]">
          BRANCHPOINT
        </span>
      </Link>

      <nav aria-label="Primary" className="flex items-center gap-6">
        <Link className="bp-mheader__link" to="/how-it-works">
          How it works
        </Link>
      </nav>

      <div className="ml-auto flex items-center">
        <Link className="bp-cta bp-cta--ghost" to="/runs">
          SEE LIVE DEMO
        </Link>
      </div>
    </header>
  );
}
