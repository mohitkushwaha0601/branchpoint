/**
 * The TRUEFORGE HARNESS view: what the agent runtime actually did.
 *
 * Every row here came from TrueForge's own event log, normalized and redacted
 * by the backend. Nothing is inferred from BRANCHPOINT's run status, and
 * nothing is invented — a run whose harness emitted no sandbox event shows no
 * sandbox row, however loudly a model said it used one.
 *
 * The badge on each row names the TrueForge feature that produced it, which is
 * what separates a harness row from a BRANCHPOINT domain event: the Events tab
 * is BRANCHPOINT's own timeline, this one is the runtime's.
 */

import {
  Boxes,
  Check,
  CircleDashed,
  Diamond,
  GitBranch,
  Loader,
  Plug,
  Terminal,
  X,
} from "lucide-react";
import type { ComponentType } from "react";

import type {
  HarnessCategoryDto,
  HarnessStatusDto,
  HarnessTraceDto,
  HarnessTraceEntryDto,
} from "../../api/types";
import { formatEventTime } from "../../adapters/eventAdapter";

interface CategoryStyle {
  label: string;
  Icon: ComponentType<{ className?: string; strokeWidth?: number }>;
  tone: string;
}

/** One badge per TrueForge feature, so the capability being exercised is legible. */
const CATEGORY: Record<HarnessCategoryDto, CategoryStyle> = {
  SESSION: { label: "SESSION", Icon: Plug, tone: "text-fg-dim" },
  MCP_TOOL: { label: "MCP", Icon: Plug, tone: "text-run" },
  SANDBOX_CREATED: { label: "SANDBOX", Icon: Boxes, tone: "text-warn" },
  SANDBOX_EXEC: { label: "EXEC", Icon: Terminal, tone: "text-warn" },
  SUBAGENT_CREATED: { label: "SUBAGENT", Icon: GitBranch, tone: "text-gate" },
  SUBAGENT_COMPLETED: { label: "SUBAGENT", Icon: GitBranch, tone: "text-gate" },
  APPROVAL_REQUIRED: { label: "APPROVAL", Icon: Diamond, tone: "text-gate" },
  APPROVAL_RESUMED: { label: "APPROVAL", Icon: Diamond, tone: "text-ok" },
  MODEL_TURN: { label: "MODEL", Icon: Loader, tone: "text-fg-dim" },
};

function StatusGlyph({ status }: { status: HarnessStatusDto }) {
  if (status === "OK") {
    return (
      <span className="text-ok">
        <Check className="h-3.5 w-3.5" strokeWidth={2.75} aria-hidden="true" />
        <span className="sr-only">succeeded</span>
      </span>
    );
  }
  if (status === "FAILED") {
    return (
      <span className="text-fail">
        <X className="h-3.5 w-3.5" strokeWidth={2.75} aria-hidden="true" />
        <span className="sr-only">failed</span>
      </span>
    );
  }
  if (status === "PENDING") {
    return (
      <span className="text-gate">
        <Diamond className="h-3.5 w-3.5" strokeWidth={2.5} aria-hidden="true" />
        <span className="sr-only">waiting</span>
      </span>
    );
  }
  return (
    <span className="text-fg-faint">
      <CircleDashed className="h-3.5 w-3.5" aria-hidden="true" />
      <span className="sr-only">recorded</span>
    </span>
  );
}

/** The detail a row carries beyond its summary — ids and exit codes, no payloads. */
function rowDetail(entry: HarnessTraceEntryDto): string {
  if (entry.sandbox_id) return entry.sandbox_id;
  if (entry.exit_code !== null) return `exitCode ${entry.exit_code}`;
  if (entry.mcp_server) return entry.mcp_server;
  return "";
}

function TraceRow({
  entry,
  selected,
  onSelectWorld,
}: {
  entry: HarnessTraceEntryDto;
  selected: boolean;
  onSelectWorld: (worldId: string) => void;
}) {
  const style = CATEGORY[entry.category];
  const detail = rowDetail(entry);
  const linked = entry.world_id !== null;

  const body = (
    <>
      <span className="w-[62px] shrink-0 text-fg-faint tabular-nums">
        {formatEventTime(entry.timestamp)}
      </span>
      <span
        className={`inline-flex w-[92px] shrink-0 items-center gap-1.5 ${style.tone}`}
      >
        <style.Icon className="h-3 w-3" strokeWidth={2.5} aria-hidden="true" />
        <span className="font-semibold tracking-[0.06em]">{style.label}</span>
      </span>
      <StatusGlyph status={entry.status} />
      <span className="min-w-0 flex-1 truncate text-fg-dim">{entry.summary}</span>
      {detail ? (
        <span className="shrink-0 text-fg-faint">{detail}</span>
      ) : null}
    </>
  );

  return (
    <li>
      {linked ? (
        <button
          type="button"
          onClick={() => onSelectWorld(entry.world_id!)}
          aria-pressed={selected}
          className={`flex w-full items-center gap-2.5 rounded px-2 py-[1px] text-left transition-colors ${
            selected ? "bg-raised" : "hover:bg-raised/60"
          }`}
        >
          {body}
        </button>
      ) : (
        <span className="flex items-center gap-2.5 px-2 py-[1px]">{body}</span>
      )}
    </li>
  );
}

export function HarnessTrace({
  trace,
  unreachable,
  selectedWorldId,
  onSelectWorld,
}: {
  trace: HarnessTraceDto | null;
  /** The BRANCHPOINT backend itself could not be reached. */
  unreachable: boolean;
  selectedWorldId: string;
  onSelectWorld: (worldId: string) => void;
}) {
  if (unreachable || trace === null) {
    return (
      <p className="px-2 font-mono text-[11px] text-fg-faint">
        {unreachable
          ? "BRANCHPOINT backend unreachable — no harness trace."
          : "Loading TrueForge harness trace…"}
      </p>
    );
  }

  const offline = trace.trueforge_status !== "available";
  // A supporting view must never take the run page down. If the payload is not
  // the shape we expect, show nothing rather than throwing mid-render.
  const sessions = Array.isArray(trace.sessions) ? trace.sessions : [];
  const entries = Array.isArray(trace.entries) ? trace.entries : [];

  return (
    <div className="font-mono text-[11px] leading-[1.75]">
      <div className="mb-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 px-2">
        <span className="font-semibold tracking-[0.12em] text-fg-faint">
          TRUEFORGE HARNESS
        </span>
        {offline ? (
          <span className="inline-flex items-center gap-1.5 rounded-md border border-warn-dim bg-warn/10 px-1.5 py-[1px] text-[10px] text-warn">
            <X className="h-3 w-3" strokeWidth={2.5} aria-hidden="true" />
            TRUEFORGE UNREACHABLE
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5 rounded-md border border-ok-dim bg-ok/10 px-1.5 py-[1px] text-[10px] text-ok">
            <Check className="h-3 w-3" strokeWidth={2.75} aria-hidden="true" />
            SESSION CONTINUITY · RESTORED
          </span>
        )}
        <span className="text-fg-faint">{trace.detail}</span>
      </div>

      {sessions.length > 0 ? (
        <ul className="mb-2 border-y border-edge-muted px-2 py-1">
          {sessions.map((session) => (
            <li
              key={session.trueforge_session_id}
              className="flex items-center gap-2.5"
            >
              <span className="w-[92px] shrink-0 font-semibold tracking-[0.06em] text-fg-faint">
                {session.purpose}
              </span>
              <span className="text-fg-dim">{session.trueforge_session_id}</span>
              {session.world_id ? (
                <span className="text-fg-faint">{session.world_id}</span>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}

      {entries.length === 0 ? (
        <p className="px-2 text-fg-faint">
          {offline
            ? "TrueForge could not be read. Session bindings above are BRANCHPOINT's own record."
            : "No TrueForge harness activity recorded yet."}
        </p>
      ) : (
        <ul>
          {entries.map((entry) => (
            <TraceRow
              key={entry.trace_id}
              entry={entry}
              selected={entry.world_id === selectedWorldId}
              onSelectWorld={onSelectWorld}
            />
          ))}
        </ul>
      )}
    </div>
  );
}
