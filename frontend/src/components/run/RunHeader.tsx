/**
 * Run identity, incident readings, and current reality.
 *
 * Deliberately not a grid of KPI cards: these are two dense definition lists
 * under one title, the way a CI run header states its facts and moves on.
 */

import type { Run } from "../../types/run";
import { StatusBadge, runStatusDescriptor } from "./StatusBadge";

function FactList({
  heading,
  facts,
  note,
}: {
  heading: string;
  facts: { label: string; value: string }[];
  note?: string;
}) {
  return (
    <section aria-label={heading} className="min-w-0 flex-1">
      <h3 className="mb-1.5 flex flex-wrap items-baseline gap-x-2 font-mono text-[10px] font-semibold tracking-[0.14em] text-fg-faint">
        {heading}
        {note ? <span className="font-normal tracking-normal">— {note}</span> : null}
      </h3>
      <dl className="divide-y divide-edge-muted border-t border-edge-muted">
        {facts.map((fact) => (
          <div
            key={fact.label}
            className="flex items-baseline justify-between gap-4 py-1"
          >
            <dt className="truncate text-[12px] text-fg-dim">{fact.label}</dt>
            <dd className="font-mono text-[12px] tabular-nums text-fg">
              {fact.value}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

export function RunHeader({ run }: { run: Run }) {
  const vetoed = run.worlds.filter((w) => w.verdict === "VETOED").length;
  const survivors = run.worlds.filter((w) => w.verdict === "SURVIVED").length;

  // Read live from the reality endpoint. Saying "UNCHANGED" is a claim, so it
  // is made only while the run has committed nothing.
  const realityNote = run.realityCommitted ? "COMMITTED" : "UNCHANGED";

  return (
    <div className="border-b border-edge px-5 py-4">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <h1 className="text-[18px] leading-tight font-semibold text-fg">
          {run.title}
        </h1>
        <code className="rounded border border-edge bg-raised px-1.5 py-0.5 font-mono text-[11px] text-fg-dim">
          {run.runId}
        </code>
        <StatusBadge descriptor={runStatusDescriptor(run.status)} size="md" />
        <span className="ml-auto font-mono text-[11px] text-fg-faint">
          started {run.startedAt} · {run.elapsed}
        </span>
      </div>

      <p className="mt-1.5 flex flex-wrap items-center gap-x-3 font-mono text-[11px] text-fg-dim">
        <span>{run.worlds.length} worlds</span>
        <span aria-hidden="true" className="text-edge">
          |
        </span>
        <span>
          {vetoed} veto{vetoed === 1 ? "" : "s"}
        </span>
        <span aria-hidden="true" className="text-edge">
          |
        </span>
        <span>
          {survivors} survivor{survivors === 1 ? "" : "s"}
        </span>
      </p>

      {run.reality.facts.length === 0 ? (
        <p className="mt-3 text-[12px] text-fg-faint">
          Current reality unavailable.
        </p>
      ) : null}

      <div className="mt-4 flex flex-wrap gap-x-10 gap-y-4">
        <FactList
          heading="OBSERVED METRICS"
          facts={run.incident.metrics.map((m) => ({
            label: m.label,
            value: m.value,
          }))}
          note={realityNote}
        />
        <FactList
          heading="CURRENT REALITY"
          facts={run.reality.facts}
          note={realityNote}
        />
      </div>
    </div>
  );
}
