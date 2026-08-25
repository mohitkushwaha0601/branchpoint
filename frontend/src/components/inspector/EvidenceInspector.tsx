/**
 * Evidence, grouped by who produced it.
 *
 * The grouping is the point. Sandbox findings sit under an EXPLORATORY heading
 * that says in words that they prove nothing; replay results sit under VERIFIED
 * and are the only rows that carry PASS/FAIL weight.
 */

import type { Evidence } from "../../types/run";
import { AuthorityBadge } from "../run/StatusBadge";

function EvidenceRow({ item }: { item: Evidence }) {
  const tone =
    item.outcome === "FAIL"
      ? "text-fail"
      : item.outcome === "PASS"
        ? "text-ok"
        : "text-fg-faint";
  return (
    <li className="flex items-baseline justify-between gap-3 py-[3px]">
      <span className="min-w-0 truncate font-mono text-[11px] text-fg-dim">
        {item.claim}
      </span>
      <span className={`font-mono text-[11px] font-medium ${tone}`}>
        {item.outcome}
      </span>
    </li>
  );
}

export function EvidenceInspector({
  evidence,
  detailAvailable = true,
}: {
  evidence: Evidence[];
  /**
   * Whether `evidence` holds real rows. The current HTTP API exposes per-world
   * counts but not the rows themselves; when that is the case the panel says so
   * rather than showing an empty list that reads like "no evidence exists".
   */
  detailAvailable?: boolean;
}) {
  const exploratory = evidence.filter((i) => i.authority === "EXPLORATORY");
  const verified = evidence.filter((i) => i.authority === "VERIFIED");

  if (!detailAvailable) {
    return (
      <div className="space-y-3">
        <h4 className="font-mono text-[10px] font-semibold tracking-[0.14em] text-fg-faint">
          EVIDENCE
        </h4>
        <p className="text-[11px] leading-relaxed text-fg-dim">
          Detailed evidence unavailable from current API.
        </p>
        <p className="text-[11px] leading-relaxed text-fg-faint">
          The counts above are live and authoritative. The authority boundary is
          unchanged either way: only BRANCHPOINT&rsquo;s own replay can reproduce
          a counterexample, and nothing the DOPPELGÄNGER produced in its sandbox
          can.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <section>
        <div className="flex items-center gap-2">
          <h4 className="font-mono text-[10px] font-semibold tracking-[0.14em] text-fg-faint">
            DOPPELGÄNGER
          </h4>
          <AuthorityBadge authority="EXPLORATORY" />
        </div>
        <p className="mt-1 text-[11px] leading-relaxed text-fg-faint">
          Sandbox output. Recorded for provenance; it can never justify a
          verdict.
        </p>
        <ul className="mt-1.5">
          {exploratory.map((item) => (
            <li key={item.evidenceId} className="py-[3px]">
              <p className="font-mono text-[11px] text-fg-dim">{item.claim}</p>
              {item.observed ? (
                <p className="font-mono text-[10px] text-fg-faint">
                  {item.observed}
                </p>
              ) : null}
            </li>
          ))}
          {exploratory.length === 0 ? (
            <li className="py-[3px] font-mono text-[11px] text-fg-faint">
              No sandbox activity recorded
            </li>
          ) : null}
        </ul>
      </section>

      <section>
        <div className="flex items-center gap-2">
          <h4 className="font-mono text-[10px] font-semibold tracking-[0.14em] text-fg-faint">
            REPLAY
          </h4>
          <AuthorityBadge authority="VERIFIED" />
        </div>
        <p className="mt-1 text-[11px] leading-relaxed text-fg-faint">
          Replayed by BRANCHPOINT against this world&rsquo;s own snapshot.
        </p>
        <ul className="mt-1.5 divide-y divide-edge-muted border-t border-edge-muted">
          {verified.map((item) => (
            <EvidenceRow key={item.evidenceId} item={item} />
          ))}
        </ul>
      </section>
    </div>
  );
}
