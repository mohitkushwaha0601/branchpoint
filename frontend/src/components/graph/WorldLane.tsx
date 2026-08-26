/**
 * One counterfactual world, rendered as a lane on the branch.
 *
 * Kept deliberately dense. A lane that grows into a tall panel stops reading as
 * part of a graph, so everything here is one line where it can be: identity,
 * jobs, verdict, and then the two evidence voices side by side.
 *
 * Those two voices are the point of the lane. What the DOPPELGÄNGER thinks is
 * EXPLORATORY and quoted; what BRANCHPOINT replayed is VERIFIED, and it is the
 * only column the verdict rests on.
 */

import type { World } from "../../types/run";
import {
  AuthorityBadge,
  StatusIcon,
  verdictDescriptor,
} from "../run/StatusBadge";
import { PipelineNode } from "./PipelineNode";

/**
 * What to say when the adversary's own words are not in the payload this lane
 * renders from.
 *
 * They are not missing from the product: the run summary carries counts, and
 * the hypothesis lives on `GET /runs/{id}/worlds/{world_id}`, which the
 * Inspector fetches when a world is opened. So this says where to find it
 * rather than reporting an API deficiency that does not exist.
 */
const CX_LABEL: Record<string, string> = {
  REPRODUCED: "Counterexample proposed. Open this world to read the hypothesis.",
  NOT_REPRODUCED:
    "Counterexample proposed, not reproduced. Open this world to read it.",
  ERROR: "Proposed counterexample was rejected as malformed.",
  NONE_PROPOSED: "No replayable counterexample proposed.",
};

export function WorldLane({
  world,
  selected,
  active,
  selectedStageId,
  onSelectWorld,
  onSelectStage,
  onHoverChange,
}: {
  world: World;
  selected: boolean;
  /** Selected or hovered: the lane and its wire are highlighted together. */
  active: boolean;
  selectedStageId: string | null;
  onSelectWorld: () => void;
  onSelectStage: (stageId: string) => void;
  onHoverChange: (hovered: boolean) => void;
}) {
  const replay = world.evidence.filter((item) => item.authority === "VERIFIED");
  const failing = replay.filter((item) => item.outcome === "FAIL");
  const shown = failing.length > 0 ? failing : replay.slice(0, 2);
  const verdict = verdictDescriptor(world.verdict);

  return (
    <section
      aria-label={`${world.label} — ${world.name}`}
      style={{ containerType: "inline-size" }}
      onMouseEnter={() => onHoverChange(true)}
      onMouseLeave={() => onHoverChange(false)}
      onClick={onSelectWorld}
      className={`rounded-panel border transition-colors ${
        selected
          ? "border-run/60 bg-raised"
          : active
            ? "border-edge bg-surface"
            : "border-edge bg-surface"
      }`}
    >
      <header className="flex items-baseline gap-2.5 border-b border-edge-muted px-3 py-1.5">
        <button
          type="button"
          onClick={onSelectWorld}
          onFocus={() => onHoverChange(true)}
          onBlur={() => onHoverChange(false)}
          aria-pressed={selected}
          className="flex min-w-0 items-baseline gap-2.5 text-left"
        >
          <span className="shrink-0 font-mono text-[10px] font-semibold tracking-[0.14em] text-fg-faint">
            {world.label}
          </span>
          <span className="truncate text-[13px] font-semibold text-fg">
            {world.name}
          </span>
        </button>
        <code
          title={world.worldId}
          className="ml-auto max-w-[40%] truncate font-mono text-[10px] text-fg-faint"
        >
          {world.worldId}
        </code>
      </header>

      <div className="max-w-[340px] px-1.5 py-1">
        {world.pipeline.map((stage) => (
          <PipelineNode
            key={stage.id}
            stage={stage}
            selected={selectedStageId === stage.id}
            onSelect={() => onSelectStage(stage.id)}
            onFocusChange={onHoverChange}
          />
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-edge-muted px-3 py-1.5">
        <span
          className={`inline-flex items-center gap-1.5 font-mono text-[11px] font-semibold tracking-[0.08em] ${
            world.verdict === "VETOED" ? "text-fail" : "text-ok"
          }`}
        >
          <StatusIcon descriptor={verdict} decorative />
          {world.verdict}
        </span>

        {world.verdict === "VETOED" && world.verdictReason ? (
          <span className="text-[12px] text-fg-dim">{world.verdictReason}</span>
        ) : null}

        {(world.verdict === "VETOED" ? [] : world.outcome.results).map((result) => (
          <span
            key={result.label}
            className="font-mono text-[11px] tabular-nums text-fg-faint"
          >
            {result.label.toLowerCase()} {result.from}
            <span className="px-1" aria-label="changes to">
              →
            </span>
            <span className="text-fg-dim">{result.to}</span>
          </span>
        ))}

        {world.notes.map((note) => (
          <span key={note} className="text-[12px] text-fg-dim">
            {note}
          </span>
        ))}
      </div>

      <div className="grid gap-x-4 gap-y-1.5 border-t border-edge-muted px-3 py-1.5 @[26rem]:grid-cols-2">
        <section aria-label="DOPPELGÄNGER evidence" className="min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="font-mono text-[10px] font-semibold tracking-[0.1em] text-fg-faint">
              DOPPELGÄNGER
            </span>
            <AuthorityBadge authority="EXPLORATORY" />
          </div>
          {world.counterexample.hypothesis ? (
            <p className="mt-0.5 text-[11px] leading-snug text-fg-dim italic">
              &ldquo;{world.counterexample.hypothesis}&rdquo;
            </p>
          ) : (
            <p className="mt-0.5 text-[11px] leading-snug text-fg-faint">
              {CX_LABEL[world.counterexample.status]}
            </p>
          )}
        </section>

        <section aria-label="BRANCHPOINT replay evidence" className="min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="font-mono text-[10px] font-semibold tracking-[0.1em] text-fg-faint">
              BRANCHPOINT
            </span>
            <AuthorityBadge authority="VERIFIED" />
          </div>
          <div className="mt-0.5">
            {world.evidence.length > 0 ? (
              <>
                {shown.map((item) => (
                  <div
                    key={item.evidenceId}
                    className="flex items-baseline justify-between gap-3 font-mono text-[11px] leading-snug"
                  >
                    <span className="truncate text-fg-dim">{item.claim}</span>
                    <span
                      className={item.outcome === "FAIL" ? "text-fail" : "text-ok"}
                    >
                      {item.outcome}
                    </span>
                  </div>
                ))}
                {failing.length === 0 ? (
                  <p className="text-[11px] leading-snug text-fg-faint">
                    all {replay.length} declared invariants pass
                  </p>
                ) : null}
              </>
            ) : (
              /* Counts are live and authoritative. The rows behind them are on
                 the world-detail resource the Inspector fetches on selection,
                 so the lane shows the counts it actually has rather than an
                 empty table that would read as "this world produced nothing". */
              <>
                <div className="flex items-baseline justify-between gap-3 font-mono text-[11px] leading-snug">
                  <span className="text-fg-dim">reproduced counterexamples</span>
                  <span
                    className={
                      world.reproducedCounterexamples > 0 ? "text-fail" : "text-ok"
                    }
                  >
                    {world.reproducedCounterexamples}
                  </span>
                </div>
                <div className="flex items-baseline justify-between gap-3 font-mono text-[11px] leading-snug">
                  <span className="text-fg-dim">evidence items</span>
                  <span className="text-fg-dim">{world.evidenceCount}</span>
                </div>
              </>
            )}
          </div>
        </section>
      </div>
    </section>
  );
}
