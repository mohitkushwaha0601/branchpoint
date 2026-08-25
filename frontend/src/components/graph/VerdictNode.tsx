/**
 * The node where a branch terminates: the verdict BRANCHPOINT reached.
 *
 * Rendered as a graph node rather than a chip because it is where the branch
 * physically ends — vetoed branches stop here, the recommended one carries on
 * down the trunk toward approval.
 */

import { Check, Star, X } from "lucide-react";

import type { WorldVerdict } from "../../types/run";

export function VerdictNode({
  verdict,
  recommended,
  active,
}: {
  verdict: WorldVerdict;
  recommended: boolean;
  active: boolean;
}) {
  const vetoed = verdict === "VETOED";
  const Glyph = vetoed ? X : Check;

  return (
    <div className="flex flex-col items-center gap-1">
      <span
        className={`inline-flex h-7 w-7 items-center justify-center rounded-full border-2 transition-colors ${
          vetoed
            ? "border-fail-dim bg-fail/15 text-fail"
            : "border-ok-dim bg-ok/15 text-ok"
        } ${active ? "ring-2 ring-run/40" : ""}`}
      >
        <Glyph className="h-4 w-4" strokeWidth={3} aria-hidden="true" />
        <span className="sr-only">{verdict}</span>
      </span>
      {recommended ? (
        <span className="inline-flex items-center gap-1 rounded-md border border-run-dim bg-run/10 px-1.5 py-[2px] font-mono text-[9px] font-semibold tracking-[0.06em] whitespace-nowrap text-run">
          <Star className="h-2.5 w-2.5" strokeWidth={2.75} aria-hidden="true" />
          RECOMMENDED
        </span>
      ) : null}
    </div>
  );
}
