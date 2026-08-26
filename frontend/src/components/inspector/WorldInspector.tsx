/**
 * Everything known about one world, in the order a reviewer needs it:
 * verdict, the action itself, what it did, what attacked it, what was replayed.
 */

import type { PipelineStage, World } from "../../types/run";
import {
  RecommendedBadge,
  StatusBadge,
  StatusIcon,
  pipelineDescriptor,
  verdictDescriptor,
} from "../run/StatusBadge";
import type { WorldInspectionState } from "../../hooks/useWorldInspection";
import { EvidenceInspector } from "./EvidenceInspector";
import { ProofChain, SupportingEvidence } from "./ProofChain";

function Section({
  heading,
  children,
}: {
  heading: string;
  children: React.ReactNode;
}) {
  return (
    <section className="border-t border-edge-muted px-4 py-3">
      <h4 className="mb-2 font-mono text-[10px] font-semibold tracking-[0.14em] text-fg-faint">
        {heading}
      </h4>
      {children}
    </section>
  );
}

export function WorldInspector({
  world,
  selectedStage,
  recommended,
  comparatorNote,
  inspection,
}: {
  world: World;
  selectedStage: PipelineStage | null;
  recommended: boolean;
  comparatorNote: string;
  /**
   * Detail fetched for this world, kept separate from the summary above it.
   * Absent on the offline fixture route and whenever the fetch failed — in both
   * cases the summary and verdict remain fully usable.
   */
  inspection?: WorldInspectionState;
}) {
  const detail = inspection?.data ?? null;
  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
      <div className="px-4 pt-4 pb-3">
        <p className="font-mono text-[10px] font-semibold tracking-[0.14em] text-fg-faint">
          {world.label}
        </p>
        <h3 className="mt-0.5 text-[15px] font-semibold text-fg">
          {world.name}
        </h3>
        <code className="mt-1 block font-mono text-[10px] text-fg-faint">
          {world.worldId}
        </code>
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <StatusBadge descriptor={verdictDescriptor(world.verdict)} size="md" />
          {recommended ? <RecommendedBadge /> : null}
        </div>
        {world.verdict === "VETOED" ? (
          <p className="mt-2 text-[12px] text-fg-dim">{world.verdictReason}</p>
        ) : null}
      </div>

      {detail !== null ? <ProofChain inspection={detail} /> : null}

      {detail === null && inspection?.loading ? (
        <Section heading="PROOF CHAIN">
          <p className="flex items-center gap-2 text-[11px] text-fg-dim">
            <span
              className="h-1.5 w-1.5 rounded-full bg-run bp-pulse"
              aria-hidden="true"
            />
            Loading evidence…
          </p>
        </Section>
      ) : null}

      {detail === null && inspection?.error ? (
        <Section heading="PROOF CHAIN">
          <p className="text-[11px] leading-relaxed text-fg-dim">
            Evidence detail unavailable.
          </p>
          <p className="mt-1 text-[11px] leading-relaxed text-fg-faint">
            The verdict and summary above are unaffected.
          </p>
        </Section>
      ) : null}

      {selectedStage ? (
        <Section heading="SELECTED STEP">
          <div className="flex items-center gap-2">
            <StatusIcon descriptor={pipelineDescriptor(selectedStage.status)} />
            <span className="flex-1 text-[12px] text-fg">
              {selectedStage.label}
            </span>
            <span className="font-mono text-[11px] text-fg-faint">
              {selectedStage.duration}
            </span>
          </div>
          <p className="mt-1.5 text-[11px] leading-relaxed text-fg-dim">
            {selectedStage.detail}
          </p>
        </Section>
      ) : null}

      <Section heading="ACTION">
        {detail === null ? (
          /* No fetched detail: the offline fixture route, or a failed fetch.
             The view model's own action is shown when it has one — a fixture
             carries real values — and a live world's is empty, which renders as
             nothing rather than as an invented transition. */
          <>
            <p className="font-mono text-[12px] text-fg">
              {world.action.parameter || world.action.target || world.action.name}
            </p>
            {world.action.from && world.action.to ? (
              <p className="mt-0.5 font-mono text-[12px] tabular-nums">
                <span className="text-fg-faint">{world.action.from}</span>
                <span className="px-1.5 text-fg-faint" aria-label="changes to">
                  →
                </span>
                <span className="text-fg">{world.action.to}</span>
              </p>
            ) : (
              <p className="mt-1 text-[11px] leading-relaxed text-fg-faint">
                Action detail loads with the world&rsquo;s evidence.
              </p>
            )}
          </>
        ) : (
          <>
            <p className="font-mono text-[12px] text-fg">
              {detail.action.target_service}
            </p>
            <p className="mt-0.5 text-[12px] text-fg-dim">{detail.action.name}</p>
            {/* What the action would actually change, verbatim from the stored
                CandidateAction. Not a before/after: the backend records the
                target value, and inventing the "from" side would be fiction. */}
            <dl className="mt-2 space-y-0.5">
              {Object.entries(detail.action.parameters).map(([key, value]) => (
                <div key={key} className="flex items-baseline justify-between gap-3">
                  <dt className="font-mono text-[11px] text-fg-faint">{key}</dt>
                  <dd className="font-mono text-[11px] text-fg">{String(value)}</dd>
                </div>
              ))}
              {Object.keys(detail.action.parameters).length === 0 ? (
                <p className="text-[11px] text-fg-faint">
                  This action family takes no parameters.
                </p>
              ) : null}
            </dl>
            <dl className="mt-2 space-y-0.5 border-t border-edge-muted pt-1.5">
              <div className="flex items-baseline justify-between gap-3">
                <dt className="text-[11px] text-fg-faint">Type</dt>
                <dd className="font-mono text-[11px] text-fg-dim">
                  {detail.action.action_type}
                </dd>
              </div>
              <div className="flex items-baseline justify-between gap-3">
                <dt className="text-[11px] text-fg-faint">Risk</dt>
                <dd className="font-mono text-[11px] text-fg-dim">
                  {detail.action.risk_class}
                </dd>
              </div>
              <div className="flex items-baseline justify-between gap-3">
                <dt className="text-[11px] text-fg-faint">Reversible</dt>
                <dd className="font-mono text-[11px] text-fg-dim">
                  {detail.action.reversible ? "yes" : "no"}
                </dd>
              </div>
              <div className="flex items-baseline justify-between gap-3">
                <dt className="text-[11px] text-fg-faint">Fingerprint</dt>
                <dd className="truncate font-mono text-[11px] text-fg-dim">
                  {detail.action.action_fingerprint.slice(0, 16)}
                </dd>
              </div>
            </dl>
          </>
        )}
      </Section>

      <Section heading="RESULT">
        {detail?.outcome != null ? (
          <>
            {/* The engine's own one-line measurement, which is where a real
                before/after lives when there is one. */}
            <p className="font-mono text-[11px] leading-snug text-fg-dim">
              {detail.outcome.summary}
            </p>
            <dl className="mt-1.5 space-y-0.5 border-t border-edge-muted pt-1.5">
              {(
                [
                  ["Goal achieved", detail.outcome.goal_achieved ? "yes" : "no"],
                  [
                    "Goal attainment",
                    `${(detail.outcome.goal_attainment * 100).toFixed(0)}%`,
                  ],
                  [
                    "Invariants preserved",
                    detail.outcome.invariants_preserved ? "yes" : "no",
                  ],
                  ["Regressions", String(detail.outcome.regressions_detected)],
                  ["Blast radius", String(detail.outcome.blast_radius)],
                  ["Cost delta", `$${detail.outcome.cost_delta.toLocaleString()}`],
                ] as const
              ).map(([label, value]) => (
                <div key={label} className="flex items-baseline justify-between gap-3">
                  <dt className="text-[11px] text-fg-faint">{label}</dt>
                  <dd className="font-mono text-[11px] text-fg-dim">{value}</dd>
                </div>
              ))}
            </dl>
          </>
        ) : detail !== null ? (
          <p className="text-[11px] leading-relaxed text-fg-faint">
            This world has not executed yet, so nothing has been measured.
          </p>
        ) : (
          <p className="text-[11px] leading-relaxed text-fg-faint">
            Measurements load with the world&rsquo;s evidence.
          </p>
        )}
      </Section>

      <Section heading="DOPPELGÄNGER">
        <dl className="space-y-0.5">
          <div className="flex items-baseline justify-between gap-3">
            <dt className="text-[11px] text-fg-faint">Sandbox</dt>
            <dd className="font-mono text-[11px] text-fg-dim">
              {world.evidence.length > 0 ? world.sandbox.status : "—"}
            </dd>
          </div>
          <div className="flex items-baseline justify-between gap-3">
            <dt className="text-[11px] text-fg-faint">
              Reproduced counterexamples
            </dt>
            <dd
              className={`font-mono text-[11px] ${
                world.reproducedCounterexamples > 0 ? "text-fail" : "text-fg-dim"
              }`}
            >
              {world.reproducedCounterexamples}
            </dd>
          </div>
          <div className="flex items-baseline justify-between gap-3">
            <dt className="text-[11px] text-fg-faint">Evidence items</dt>
            <dd className="font-mono text-[11px] text-fg-dim">
              {world.evidenceCount}
            </dd>
          </div>
        </dl>
      </Section>

      {detail !== null ? (
        <SupportingEvidence evidence={detail.evidence} />
      ) : (
        <div className="border-t border-edge-muted px-4 py-3">
          <EvidenceInspector
            evidence={world.evidence}
            detailAvailable={world.evidence.length > 0}
          />
        </div>
      )}

      <footer className="mt-auto border-t border-edge-muted px-4 py-3">
        <p className="text-[11px] leading-relaxed text-fg-faint">
          {comparatorNote}
        </p>
      </footer>
    </div>
  );
}
