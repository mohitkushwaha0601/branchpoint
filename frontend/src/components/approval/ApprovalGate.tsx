/**
 * The human checkpoint, sitting where the trunk ends.
 *
 * It restates exactly what is being approved — one world, one action id, one
 * fingerprint — because the whole safety argument is that a human approves a
 * specific bound action rather than a general intention. Those three values are
 * read back from the run's own binding and sent as confirmation; the browser
 * has no way to name a different action, and never asks for a capability.
 *
 * Nothing here is optimistic. Pressing Approve records a decision; whether the
 * commit succeeded, and whether verification passed, is read from the run on
 * the next poll and nowhere else.
 */

import { AlertTriangle, Check, Diamond, Loader, X } from "lucide-react";

import { useRunView } from "../../app/runView";
import type { Run } from "../../types/run";

function CommitProgress({ run }: { run: Run }) {
  const stage =
    run.status === "SUCCEEDED"
      ? { label: "Committed and independently verified", tone: "text-ok", done: true }
      : run.status === "VERIFYING"
        ? { label: "Verifying reality independently…", tone: "text-run", done: false }
        : run.status === "COMMITTING" || run.status === "APPROVED"
          ? { label: "Committing the approved action…", tone: "text-run", done: false }
          : run.status === "FAILED"
            ? {
                label: run.failureReason || "Run failed after approval",
                tone: "text-fail",
                done: true,
              }
            : null;

  if (stage === null) return null;

  return (
    <footer role="status" className="border-t border-edge-muted px-4 py-3">
      <p className={`flex items-center gap-2 text-[12px] ${stage.tone}`}>
        {stage.done ? (
          run.status === "SUCCEEDED" ? (
            <Check className="h-4 w-4" strokeWidth={2.75} aria-hidden="true" />
          ) : (
            <AlertTriangle className="h-4 w-4" strokeWidth={2.5} aria-hidden="true" />
          )
        ) : (
          <Loader className="h-4 w-4 bp-pulse" strokeWidth={2.5} aria-hidden="true" />
        )}
        {stage.label}
      </p>
      <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-0.5">
        <div className="flex items-baseline justify-between gap-3">
          <dt className="text-[11px] text-fg-faint">Commit</dt>
          <dd className="font-mono text-[11px] text-fg-dim">
            {run.commitStatus ?? "—"}
          </dd>
        </div>
        <div className="flex items-baseline justify-between gap-3">
          <dt className="text-[11px] text-fg-faint">Verification</dt>
          <dd className="font-mono text-[11px] text-fg-dim">
            {run.verificationStatus ?? "—"}
          </dd>
        </div>
      </dl>
    </footer>
  );
}

export function ApprovalGate() {
  const {
    run,
    approving,
    approvalError,
    approvalSubmitted,
    approve,
    dismissApprovalError,
  } = useRunView();
  const { approval } = run;
  const world = run.worlds.find((candidate) => candidate.worldId === approval.worldId);

  // No binding yet, and nothing to show: the run has not reached the gate.
  if (approval.worldId === "" || world === undefined) return null;

  const pending = run.status === "AWAITING_APPROVAL";

  return (
    <section
      aria-labelledby="approval-heading"
      className="mx-5 mb-6 rounded-panel border border-gate-dim bg-surface"
    >
      <header className="flex items-center gap-2 border-b border-edge-muted px-4 py-2.5">
        <Diamond className="h-3.5 w-3.5 text-gate" aria-hidden="true" />
        <h2
          id="approval-heading"
          className="font-mono text-[11px] font-semibold tracking-[0.12em] text-gate"
        >
          {pending ? "MANUAL APPROVAL REQUIRED" : "HUMAN APPROVAL"}
        </h2>
      </header>

      <div className="grid gap-5 px-4 py-4 md:grid-cols-2">
        <div>
          <p className="font-mono text-[10px] font-semibold tracking-[0.14em] text-fg-faint">
            RECOMMENDED WORLD
          </p>
          <p className="mt-1 text-[13px] text-fg">
            {world.label.replace("WORLD ", "World ")} — {world.name}
          </p>
          <ul className="mt-3 space-y-1">
            {approval.checks.map((check) => (
              <li key={check.label} className="flex items-center gap-2">
                {check.satisfied ? (
                  <Check
                    className="h-3.5 w-3.5 shrink-0 text-ok"
                    strokeWidth={2.75}
                    aria-hidden="true"
                  />
                ) : (
                  <X
                    className="h-3.5 w-3.5 shrink-0 text-fail"
                    strokeWidth={2.75}
                    aria-hidden="true"
                  />
                )}
                <span className="text-[12px] text-fg-dim">
                  {check.label}
                  <span className="sr-only">
                    {check.satisfied ? " — satisfied" : " — not satisfied"}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </div>

        <div>
          <p className="font-mono text-[10px] font-semibold tracking-[0.14em] text-fg-faint">
            BOUND ACTION
          </p>
          <p className="mt-1 text-[13px] text-fg">{world.name}</p>
          <dl className="mt-3 space-y-0.5">
            <div className="flex items-baseline justify-between gap-3">
              <dt className="text-[11px] text-fg-faint">World id</dt>
              <dd className="font-mono text-[11px] text-fg-dim">
                {approval.worldId}
              </dd>
            </div>
            <div className="flex items-baseline justify-between gap-3">
              <dt className="text-[11px] text-fg-faint">Action id</dt>
              <dd className="font-mono text-[11px] text-fg-dim">
                {approval.actionId}
              </dd>
            </div>
            <div className="flex items-baseline justify-between gap-3">
              <dt className="text-[11px] text-fg-faint">Fingerprint</dt>
              <dd className="font-mono text-[11px] text-fg-dim">
                {approval.actionFingerprint || "—"}
              </dd>
            </div>
          </dl>
          <p className="mt-2 text-[11px] leading-relaxed text-fg-faint">
            These three values are sent back as confirmation. BRANCHPOINT commits
            the action they identify and nothing else.
          </p>
        </div>
      </div>

      {approvalError !== null ? (
        <div
          role="alert"
          className="mx-4 mb-3 rounded-md border border-fail-dim bg-fail/10 px-3 py-2"
        >
          <p className="text-[12px] text-fail">
            {approvalError.isConflict
              ? "This approval no longer matches the run. Re-read the recommendation before deciding again."
              : approvalError.isNotFound
                ? "This run no longer exists on the backend."
                : approvalError.detail}
          </p>
          <button
            type="button"
            onClick={dismissApprovalError}
            className="mt-1.5 rounded-md border border-edge bg-raised px-2 py-0.5 text-[11px] text-fg-dim hover:text-fg"
          >
            Dismiss
          </button>
        </div>
      ) : null}

      {pending && !approvalSubmitted ? (
        <footer className="flex flex-wrap items-center justify-end gap-2 border-t border-edge-muted px-4 py-3">
          <p className="mr-auto text-[11px] text-fg-faint">
            Rejection is not exposed by the current API — see the run detail to
            abandon it.
          </p>
          <button
            type="button"
            disabled
            title="No reject endpoint is available in this backend version"
            className="cursor-not-allowed rounded-md border border-edge bg-raised px-3 py-1.5 text-[12px] text-fg-faint"
          >
            Reject
          </button>
          <button
            type="button"
            onClick={approve}
            disabled={approving}
            className="inline-flex items-center gap-2 rounded-md border border-ok-dim bg-ok/15 px-3 py-1.5 text-[12px] font-medium text-ok transition-colors hover:bg-ok/25 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {approving ? (
              <Loader className="h-3.5 w-3.5 bp-pulse" strokeWidth={2.5} aria-hidden="true" />
            ) : null}
            {approving ? "Submitting…" : "Approve & Commit"}
          </button>
        </footer>
      ) : (
        <CommitProgress run={run} />
      )}
    </section>
  );
}
