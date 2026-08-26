/**
 * The small, developer-tool-shaped loading and error affordances.
 *
 * No full-page spinners: a run is watchable while it is still assembling, so
 * the shell stays on screen and the parts that are still arriving say so.
 */

import { AlertTriangle, RefreshCw } from "lucide-react";

/** A live-activity dot. Present only while something is actually in flight. */
export function ActivityDot({ label }: { label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="h-1.5 w-1.5 rounded-full bg-run bp-pulse" aria-hidden="true" />
      <span className="font-mono text-[10px] tracking-[0.06em] text-fg-dim">
        {label}
      </span>
    </span>
  );
}

export function InlineWaiting({ label }: { label: string }) {
  return (
    <p className="flex items-center gap-2 text-[12px] text-fg-dim">
      <span className="h-1.5 w-1.5 rounded-full bg-run bp-pulse" aria-hidden="true" />
      {label}
    </p>
  );
}

/**
 * A compact error banner with a retry.
 *
 * Failed live data is never replaced with fixture data — the banner says what
 * went wrong and the navigation stays usable.
 */
export function ErrorBanner({
  title,
  detail,
  onRetry,
}: {
  title: string;
  detail?: string;
  onRetry?: () => void;
}) {
  return (
    <div
      role="alert"
      className="flex flex-wrap items-center gap-3 border-b border-fail-dim bg-fail/10 px-5 py-2"
    >
      <AlertTriangle className="h-4 w-4 shrink-0 text-fail" aria-hidden="true" />
      <span className="text-[12px] text-fg">{title}</span>
      {detail ? (
        <span className="font-mono text-[11px] text-fg-dim">{detail}</span>
      ) : null}
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="ml-auto inline-flex items-center gap-1.5 rounded-md border border-edge bg-raised px-2 py-1 text-[11px] text-fg-dim hover:text-fg"
        >
          <RefreshCw className="h-3 w-3" aria-hidden="true" />
          Retry
        </button>
      ) : null}
    </div>
  );
}
