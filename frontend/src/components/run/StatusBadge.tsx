/**
 * The one place status is turned into pixels.
 *
 * Every badge pairs a glyph with a word. Colour reinforces the meaning but
 * never carries it alone — a VETOED world reads as "✕ VETOED" in monochrome,
 * to a screen reader, and to anyone who cannot separate red from green.
 */

import {
  AlertTriangle,
  Check,
  CircleDashed,
  Diamond,
  Loader,
  Minus,
  Star,
  X,
} from "lucide-react";
import type { ComponentType } from "react";

import type {
  PipelineStatus,
  RunStatus,
  StageStatus,
  WorldVerdict,
} from "../../types/run";

export type Tone = "ok" | "fail" | "run" | "warn" | "gate" | "muted";

const TONE_TEXT: Record<Tone, string> = {
  ok: "text-ok",
  fail: "text-fail",
  run: "text-run",
  warn: "text-warn",
  gate: "text-gate",
  muted: "text-fg-faint",
};

const TONE_CHIP: Record<Tone, string> = {
  ok: "border-ok-dim bg-ok/10 text-ok",
  fail: "border-fail-dim bg-fail/10 text-fail",
  run: "border-run-dim bg-run/10 text-run",
  warn: "border-warn-dim bg-warn/10 text-warn",
  gate: "border-gate-dim bg-gate/10 text-gate",
  muted: "border-edge bg-raised text-fg-dim",
};

interface Descriptor {
  tone: Tone;
  Icon: ComponentType<{ className?: string; strokeWidth?: number }>;
  label: string;
}

const RUN_STATUS: Record<RunStatus, Descriptor> = {
  RUNNING: { tone: "run", Icon: Loader, label: "RUNNING" },
  AWAITING_APPROVAL: {
    tone: "gate",
    Icon: Diamond,
    label: "AWAITING APPROVAL",
  },
  SUCCEEDED: { tone: "ok", Icon: Check, label: "SUCCEEDED" },
  REJECTED: { tone: "fail", Icon: X, label: "REJECTED" },
  FAILED: { tone: "fail", Icon: AlertTriangle, label: "FAILED" },
};

const VERDICT: Record<WorldVerdict, Descriptor> = {
  SURVIVED: { tone: "ok", Icon: Check, label: "SURVIVED" },
  VETOED: { tone: "fail", Icon: X, label: "VETOED" },
  INCONCLUSIVE: { tone: "warn", Icon: AlertTriangle, label: "INCONCLUSIVE" },
};

const PIPELINE: Record<PipelineStatus, Descriptor> = {
  passed: { tone: "ok", Icon: Check, label: "passed" },
  failed: { tone: "fail", Icon: X, label: "failed" },
  running: { tone: "run", Icon: Loader, label: "running" },
  skipped: { tone: "muted", Icon: Minus, label: "skipped" },
};

const STAGE: Record<StageStatus, Descriptor> = {
  complete: { tone: "ok", Icon: Check, label: "complete" },
  current: { tone: "gate", Icon: Diamond, label: "current" },
  pending: { tone: "muted", Icon: CircleDashed, label: "pending" },
  failed: { tone: "fail", Icon: X, label: "failed" },
};

export function runStatusDescriptor(status: RunStatus): Descriptor {
  return RUN_STATUS[status];
}
export function verdictDescriptor(verdict: WorldVerdict): Descriptor {
  return VERDICT[verdict];
}
export function pipelineDescriptor(status: PipelineStatus): Descriptor {
  return PIPELINE[status];
}
export function stageDescriptor(status: StageStatus): Descriptor {
  return STAGE[status];
}

/**
 * A small status icon. Its accessible name is the status word, so the meaning
 * survives with no colour at all.
 *
 * Pass `decorative` where the same word is already visible next to it —
 * otherwise a screen reader reads the status twice.
 */
export function StatusIcon({
  descriptor,
  className = "",
  decorative = false,
}: {
  descriptor: Descriptor;
  className?: string;
  decorative?: boolean;
}) {
  const { Icon, tone, label } = descriptor;
  return (
    <span className={`inline-flex ${TONE_TEXT[tone]} ${className}`}>
      <Icon className="h-3.5 w-3.5" strokeWidth={2.5} aria-hidden="true" />
      {decorative ? null : <span className="sr-only">{label}</span>}
    </span>
  );
}

export function StatusBadge({
  descriptor,
  size = "sm",
}: {
  descriptor: Descriptor;
  size?: "sm" | "md";
}) {
  const { Icon, tone, label } = descriptor;
  const scale =
    size === "md" ? "text-[11px] px-2 py-[3px]" : "text-[10px] px-1.5 py-[1px]";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-md border font-mono font-medium tracking-[0.06em] whitespace-nowrap ${TONE_CHIP[tone]} ${scale}`}
    >
      <Icon className="h-3 w-3" strokeWidth={2.75} aria-hidden="true" />
      {label}
    </span>
  );
}

/** The comparator's pick. Distinct from a verdict on purpose. */
export function RecommendedBadge() {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-md border border-run-dim bg-run/10 px-1.5 py-[1px] font-mono text-[10px] font-medium tracking-[0.06em] whitespace-nowrap text-run">
      <Star className="h-3 w-3" strokeWidth={2.75} aria-hidden="true" />
      RECOMMENDED
    </span>
  );
}

/**
 * Evidence provenance. The single most important label in the product: sandbox
 * output is EXPLORATORY and proves nothing, BRANCHPOINT replay is VERIFIED and
 * is the only thing a verdict may rest on.
 */
export function AuthorityBadge({
  authority,
}: {
  authority: "EXPLORATORY" | "VERIFIED";
}) {
  const verified = authority === "VERIFIED";
  return (
    <span
      className={`inline-flex items-center rounded-md border px-1.5 py-[1px] font-mono text-[10px] font-medium tracking-[0.06em] whitespace-nowrap ${
        verified
          ? "border-ok-dim bg-ok/10 text-ok"
          : "border-edge bg-raised text-fg-dim"
      }`}
      title={
        verified
          ? "Produced by BRANCHPOINT's deterministic replay. Authoritative."
          : "Produced inside the DOPPELGÄNGER sandbox. Never authoritative."
      }
    >
      {authority}
    </span>
  );
}
