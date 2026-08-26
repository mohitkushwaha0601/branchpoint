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

/** Empty means the API did not carry the value, and says so on screen. */
function dash(value: string): string {
  return value === "" ? "—" : value;
}

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

function Transition({
  label,
  from,
  to,
}: {
  label: string;
  from: string;
  to: string;
}) {
  return (
    <div className="py-1">
      <p className="text-[11px] text-fg-dim">{label}</p>
      <p className="font-mono text-[12px] tabular-nums">
        <span className="text-fg-faint">{from}</span>
        <span className="px-1.5 text-fg-faint" aria-label="changes to">
          →
        </span>
        <span className="text-fg">{to}</span>
      </p>
    </div>
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
        <p className="text-[12px] text-fg">{world.action.name}</p>
        {world.action.parameter ? (
          <Transition
            label={world.action.parameter}
            from={world.action.from}
            to={world.action.to}
          />
        ) : (
          <p className="mt-1 text-[11px] leading-relaxed text-fg-faint">
            Parameter values are not exposed per world by the current API.
          </p>
        )}
        <dl className="mt-2 space-y-0.5">
          <div className="flex items-baseline justify-between gap-3">
            <dt className="text-[11px] text-fg-faint">Action id</dt>
            <dd className="font-mono text-[11px] text-fg-dim">
              {dash(world.action.actionId)}
            </dd>
          </div>
          <div className="flex items-baseline justify-between gap-3">
            <dt className="text-[11px] text-fg-faint">Fingerprint</dt>
            <dd className="font-mono text-[11px] text-fg-dim">
              {dash(world.action.fingerprint)}
            </dd>
          </div>
          <div className="flex items-baseline justify-between gap-3">
            <dt className="text-[11px] text-fg-faint">Reversible</dt>
            <dd className="font-mono text-[11px] text-fg-dim">
              {world.action.reversible === null
                ? "—"
                : world.action.reversible
                  ? "yes"
                  : "no"}
            </dd>
          </div>
        </dl>
      </Section>

      <Section heading="RESULT">
        {world.outcome.results.length > 0 ? (
          world.outcome.results.map((result) => (
            <Transition
              key={result.label}
              label={result.label}
              from={result.from ?? "—"}
              to={result.to ?? result.value}
            />
          ))
        ) : (
          <p className="text-[11px] leading-relaxed text-fg-faint">
            Per-world before/after metrics are not exposed by the current API.
          </p>
        )}
        <dl className="mt-1.5 space-y-0.5 border-t border-edge-muted pt-1.5">
          <div className="flex items-baseline justify-between gap-3">
            <dt className="text-[11px] text-fg-faint">Goal achieved</dt>
            <dd className="font-mono text-[11px] text-fg-dim">
              {world.outcome.goalAchieved ? "yes" : "no"}
            </dd>
          </div>
          <div className="flex items-baseline justify-between gap-3">
            <dt className="text-[11px] text-fg-faint">Blast radius</dt>
            <dd className="font-mono text-[11px] text-fg-dim">
              {world.outcome.blastRadius}
            </dd>
          </div>
          <div className="flex items-baseline justify-between gap-3">
            <dt className="text-[11px] text-fg-faint">Cost delta</dt>
            <dd className="font-mono text-[11px] text-fg-dim">
              ${world.outcome.costDelta.toLocaleString()}
            </dd>
          </div>
        </dl>
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
