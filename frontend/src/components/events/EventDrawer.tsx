/**
 * Bottom drawer: the run's own log, plus the other streams a reviewer reaches
 * for. Collapsed it is a 40px status strip; expanded it is 220px of scrollback.
 *
 * Events that belong to a world are buttons — activating one selects that world
 * everywhere else in the view, which is how the log and the graph stay in sync.
 */

import { ChevronDown, ChevronUp } from "lucide-react";
import { useState } from "react";

import { useRunView } from "../../app/runView";
import type { HarnessTraceState } from "../../hooks/useHarnessTrace";
import type { RunEvent } from "../../types/run";
import { AuthorityBadge } from "../run/StatusBadge";
import { HarnessTrace } from "./HarnessTrace";

/**
 * Harness leads, because it is the tab that answers "did TrueForge really do
 * this?". It replaces the old Agents / MCP / Sandbox tabs outright: those three
 * described capabilities in prose, and this one shows the runtime's own record
 * of exercising them.
 */
const TABS = ["Harness", "Events", "Evidence"] as const;
type Tab = (typeof TABS)[number];

const CHANNEL_TONE: Record<RunEvent["channel"], string> = {
  OBSERVE: "text-fg-dim",
  PLAN: "text-fg-dim",
  FORK: "text-run",
  DOPPEL: "text-warn",
  REPLAY: "text-ok",
  VERDICT: "text-fail",
  COMPARE: "text-run",
  APPROVE: "text-gate",
};

function EventsTab() {
  const { run, selectedWorldId, selectWorld } = useRunView();
  if (run.events.length === 0) {
    return (
      <p className="px-2 font-mono text-[11px] text-fg-faint">
        No events yet.
      </p>
    );
  }
  return (
    <ul className="font-mono text-[11px] leading-[1.7]">
      {run.events.map((event) => {
        const linked = event.worldId !== undefined;
        const selected = linked && event.worldId === selectedWorldId;
        const row = (
          <>
            <span className="text-fg-faint tabular-nums">{event.timestamp}</span>
            <span
              className={`inline-block w-[64px] font-semibold ${CHANNEL_TONE[event.channel]}`}
            >
              {event.channel}
            </span>
            <span className="text-fg-dim">{event.message}</span>
          </>
        );
        return (
          <li key={event.eventId}>
            {linked ? (
              <button
                type="button"
                onClick={() => selectWorld(event.worldId!)}
                aria-pressed={selected}
                className={`flex w-full items-baseline gap-3 rounded px-2 text-left transition-colors ${
                  selected ? "bg-raised" : "hover:bg-raised/60"
                }`}
              >
                {row}
              </button>
            ) : (
              <span className="flex items-baseline gap-3 px-2">{row}</span>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function EvidenceTab() {
  const { run } = useRunView();
  const all = run.worlds.flatMap((world) =>
    world.evidence.map((item) => ({ world, item })),
  );
  // Live runs carry counts, not rows: say which, rather than showing an empty
  // table that reads as "this run produced no evidence".
  if (all.length === 0) {
    return (
      <div className="px-2 font-mono text-[11px] text-fg-dim">
        <p>Detailed evidence unavailable from current API.</p>
        <table className="mt-2 w-full">
          <thead>
            <tr className="text-left text-fg-faint">
              <th className="px-2 py-0.5 font-normal">world</th>
              <th className="px-2 py-0.5 font-normal">evidence items</th>
              <th className="px-2 py-0.5 font-normal">reproduced</th>
            </tr>
          </thead>
          <tbody>
            {run.worlds.map((world) => (
              <tr key={world.worldId}>
                <td className="px-2 py-0.5">{world.worldId}</td>
                <td className="px-2 py-0.5">{world.evidenceCount}</td>
                <td
                  className={`px-2 py-0.5 ${
                    world.reproducedCounterexamples > 0 ? "text-fail" : "text-ok"
                  }`}
                >
                  {world.reproducedCounterexamples}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }
  return (
    <table className="w-full font-mono text-[11px]">
      <thead>
        <tr className="text-left text-fg-faint">
          <th className="px-2 py-0.5 font-normal">world</th>
          <th className="px-2 py-0.5 font-normal">claim</th>
          <th className="px-2 py-0.5 font-normal">authority</th>
          <th className="px-2 py-0.5 font-normal">outcome</th>
        </tr>
      </thead>
      <tbody>
        {all.map(({ world, item }) => (
          <tr key={item.evidenceId} className="text-fg-dim">
            <td className="px-2 py-0.5">{world.worldId}</td>
            <td className="px-2 py-0.5">{item.claim}</td>
            <td className="px-2 py-0.5">
              <AuthorityBadge authority={item.authority} />
            </td>
            <td
              className={`px-2 py-0.5 ${
                item.outcome === "FAIL"
                  ? "text-fail"
                  : item.outcome === "PASS"
                    ? "text-ok"
                    : "text-fg-faint"
              }`}
            >
              {item.outcome}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/**
 * Which TrueForge sessions a run bound, read from its own event timeline.
 *
 * The backend emits one `TRUEFORGE_SESSION_CREATED` event per binding, so this
 * is real. Per-agent tool inventories and sandbox configuration are not exposed
 * over HTTP and are therefore not claimed here.
 */



export function EventDrawer({ harness }: { harness?: HarnessTraceState }) {
  const [expanded, setExpanded] = useState(false);
  const [tab, setTab] = useState<Tab>("Harness");
  const { run, selectedWorldId, selectWorld } = useRunView();

  return (
    <div className="shrink-0 border-t border-edge bg-surface">
      <div className="flex h-[var(--drawer-collapsed)] items-center gap-1 px-2">
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          aria-expanded={expanded}
          aria-controls="event-drawer-body"
          className="flex items-center gap-1.5 rounded-md px-2 py-1 text-fg-dim hover:bg-raised hover:text-fg"
        >
          {expanded ? (
            <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
          ) : (
            <ChevronUp className="h-3.5 w-3.5" aria-hidden="true" />
          )}
          <span className="font-mono text-[10px] font-semibold tracking-[0.12em]">
            {expanded ? "HIDE" : "SHOW"}
          </span>
        </button>

        <div role="tablist" aria-label="Run streams" className="flex items-center gap-0.5">
          {TABS.map((name) => (
            <button
              key={name}
              type="button"
              role="tab"
              aria-selected={tab === name}
              // Names the region each tab governs, so a screen reader can move
              // from the tab to its content rather than hunting for it.
              aria-controls="event-drawer-body"
              onClick={() => {
                setTab(name);
                setExpanded(true);
              }}
              className={`rounded-md px-2.5 py-1 text-[12px] transition-colors ${
                tab === name && expanded
                  ? "bg-raised text-fg"
                  : "text-fg-dim hover:bg-raised/60 hover:text-fg"
              }`}
            >
              {name}
            </button>
          ))}
        </div>

        <span className="ml-auto pr-2 font-mono text-[10px] text-fg-faint">
          {Array.isArray(harness?.trace?.entries)
            ? `${harness.trace.entries.length} harness · ${run.events.length} events`
            : `${run.events.length} events`}
        </span>
      </div>

      {expanded ? (
        <div
          id="event-drawer-body"
          role="tabpanel"
          aria-label={tab}
          className="h-[var(--drawer-expanded)] overflow-y-auto border-t border-edge-muted px-2 py-2"
        >
          {tab === "Harness" ? (
            <HarnessTrace
              trace={harness?.trace ?? null}
              unreachable={harness?.error?.isUnreachable ?? false}
              selectedWorldId={selectedWorldId}
              onSelectWorld={selectWorld}
            />
          ) : null}
          {tab === "Events" ? <EventsTab /> : null}
          {tab === "Evidence" ? <EvidenceTab /> : null}
        </div>
      ) : null}
    </div>
  );
}
