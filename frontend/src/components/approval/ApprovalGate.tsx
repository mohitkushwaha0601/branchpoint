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

import { AlertTriangle, Check, Diamond, Loader, UserX, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { useRunView } from "../../app/runView";
import type { Run } from "../../types/run";

/**
 * The outcome of a human refusing the recommendation.
 *
 * Deliberately not the veto treatment. A veto is BRANCHPOINT saying the action
 * is unsafe, proved by machine-verifiable evidence; this is a person declining
 * to act on something BRANCHPOINT found survivable. Same run, different layer —
 * so it gets its own word, its own icon, and the neutral governance colour
 * rather than the failure red a veto owns.
 */
function HumanRejection({ run }: { run: Run }) {
  const { approval } = run;
  return (
    <footer role="status" className="shrink-0 border-t border-edge-muted px-4 py-3">
      <p className="flex items-center gap-2">
        <UserX className="h-4 w-4 text-gate" strokeWidth={2.5} aria-hidden="true" />
        <span className="font-mono text-[11px] font-semibold tracking-[0.1em] text-gate">
          HUMAN DECISION · REJECTED
        </span>
      </p>
      <p className="mt-1.5 font-mono text-[12px] text-fg">
        {approval.actor ?? "—"}
      </p>
      {run.rejectionReason ? (
        <p className="mt-0.5 text-[12px] leading-relaxed text-fg-dim italic">
          &ldquo;{run.rejectionReason}&rdquo;
        </p>
      ) : null}
      <p className="mt-2 text-[11px] leading-relaxed text-fg-faint">
        An operator declined to proceed. Nothing was committed and reality is
        unchanged. This is a governance decision, not an adversarial veto —
        world {approval.worldId} still survived BRANCHPOINT&rsquo;s own checks.
      </p>
    </footer>
  );
}

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
    <footer role="status" className="shrink-0 border-t border-edge-muted px-4 py-3">
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
    reject,
    dismissApprovalError,
  } = useRunView();
  // An inline panel rather than a modal: the app has no dialog primitive, and
  // the reason belongs next to what is being refused.
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  // Opening the panel is a request for input, so the caret goes there rather
  // than leaving a keyboard user to find it.
  const reasonRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (rejecting) reasonRef.current?.focus();
  }, [rejecting]);
  // Escape backs out of the reason panel, the way it would leave a dialog.
  // Only while the panel is open, so it never swallows the key otherwise.
  useEffect(() => {
    if (!rejecting) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setRejecting(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [rejecting]);
  const { approval } = run;
  const world = run.worlds.find((candidate) => candidate.worldId === approval.worldId);

  // No binding yet, and nothing to show: the run has not reached the gate.
  if (approval.worldId === "" || world === undefined) return null;

  const pending = run.status === "AWAITING_APPROVAL";
  const humanRejected = run.approval.status === "REJECTED";

  return (
    <section
      aria-labelledby="approval-heading"
      /* While a decision is outstanding the gate pins to the bottom of the
         canvas. It is the point of the whole run, and it used to sit ~500px
         below the fold behind three world lanes — reachable only by scrolling
         past the very evidence it is asking you to act on. Pinned, the branches
         still scroll above it and the decision is never hunted for. Sticky
         keeps it inside `main`, so the drawer (a flex sibling) still cannot
         cover it, and growing the reason panel expands upward from the pin. */
      className={`mx-5 rounded-panel border border-gate-dim bg-surface ${
        pending
          ? // Capped at 70% of the canvas so the gate can never swallow the
            // branch graph on a short viewport with the drawer expanded. The
            // header and the decision row are outside the scroll area, so the
            // buttons stay put no matter how the detail block is sized.
            "sticky bottom-0 z-20 mb-5 flex max-h-[55%] flex-col shadow-[0_-8px_24px_-12px_rgba(0,0,0,0.9)]"
          : "mb-6"
      }`}
    >
      <header className="flex shrink-0 items-center gap-2 border-b border-edge-muted px-4 py-2">
        <Diamond className="h-3.5 w-3.5 text-gate" aria-hidden="true" />
        <h2
          id="approval-heading"
          className="font-mono text-[11px] font-semibold tracking-[0.12em] text-gate"
        >
          {pending ? "HUMAN CHECKPOINT" : "HUMAN DECISION"}
        </h2>
      </header>

      <div className="grid min-h-0 gap-x-5 gap-y-3 overflow-y-auto px-4 py-3 md:grid-cols-2">
        <div>
          <p className="font-mono text-[10px] font-semibold tracking-[0.14em] text-fg-faint">
            RECOMMENDED WORLD
          </p>
          {/* Subordinate by construction: the comparator ranks, a person
              decides. Said in words so the hierarchy survives a screenshot. */}
          <p className="mt-0.5 text-[11px] text-fg-faint">
            A deterministic recommendation. Not permission.
          </p>
          <p className="mt-1 text-[13px] text-fg">
            {world.label.replace("WORLD ", "World ")} — {world.name}
          </p>
          {/* One column on purpose. Two fitted in ~35px less height but broke
              "No reproduced counterexamples" and "Deterministic comparator
              recommendation" across lines, and a ragged safety checklist is a
              worse trade than a slightly taller panel. */}
          <ul className="mt-2 space-y-0.5">
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
          <dl className="mt-2 space-y-0.5">
            <div className="flex items-baseline justify-between gap-3">
              <dt className="shrink-0 text-[11px] text-fg-faint">World id</dt>
              <dd className="truncate font-mono text-[11px] text-fg-dim">
                {approval.worldId}
              </dd>
            </div>
            <div className="flex items-baseline justify-between gap-3">
              <dt className="shrink-0 text-[11px] text-fg-faint">Action id</dt>
              <dd className="truncate font-mono text-[11px] text-fg-dim">
                {approval.actionId}
              </dd>
            </div>
            {/* On its own line and allowed to break: the fingerprint is a
                64-character SHA-256, and as a right-aligned cell it ran off the
                column and was clipped mid-hash. It is the one value here whose
                exact characters are the point, so it gets the full width and
                wraps rather than being silently truncated. */}
            <div className="pt-0.5">
              <dt className="text-[11px] text-fg-faint">Fingerprint</dt>
              <dd className="font-mono text-[11px] leading-snug break-all text-fg-dim">
                {approval.actionFingerprint || "—"}
              </dd>
            </div>
          </dl>
          <p className="mt-1.5 text-[11px] leading-snug text-fg-faint">
            Sent back as confirmation. BRANCHPOINT commits the action they
            identify and nothing else.
          </p>
        </div>
      </div>

      {approvalError !== null ? (
        <div
          role="alert"
          className="mx-4 mb-3 rounded-md border border-fail-dim bg-fail/10 px-3 py-2"
        >
          {/* The backend's own detail, not a canned line: a 409 can mean a
              stale binding on approval or a wrong lifecycle state on rejection,
              and only the server knows which. */}
          <p className="text-[12px] text-fail">
            {approvalError.isNotFound
              ? "This run no longer exists on the backend."
              : approvalError.detail}
          </p>
          {approvalError.isConflict ? (
            <p className="mt-1 text-[11px] leading-relaxed text-fg-dim">
              Re-read the run before deciding again.
            </p>
          ) : null}
          <button
            type="button"
            onClick={dismissApprovalError}
            className="mt-1.5 rounded-md border border-edge bg-raised px-2 py-0.5 text-[11px] text-fg-dim hover:text-fg"
          >
            Dismiss
          </button>
        </div>
      ) : null}

      {humanRejected ? (
        <HumanRejection run={run} />
      ) : pending && !approvalSubmitted ? (
        rejecting ? (
          <footer className="shrink-0 border-t border-edge-muted px-4 py-3">
            <label
              htmlFor="rejection-reason"
              className="font-mono text-[10px] font-semibold tracking-[0.14em] text-fg-faint"
            >
              WHY ARE YOU DECLINING?
            </label>
            <input
              id="rejection-reason"
              ref={reasonRef}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              maxLength={500}
              autoComplete="off"
              placeholder="Optional — recorded on the run"
              className="mt-1.5 w-full rounded-md border border-edge bg-canvas px-2.5 py-1.5 font-mono text-[12px] text-fg placeholder:text-fg-faint"
            />
            <div className="mt-2 flex flex-wrap items-center justify-end gap-2">
              <p className="mr-auto text-[11px] text-fg-faint">
                Records a human decision. Nothing is committed.
              </p>
              <button
                type="button"
                onClick={() => setRejecting(false)}
                disabled={approving}
                className="rounded-md border border-edge bg-raised px-3 py-1.5 text-[12px] text-fg-dim hover:text-fg disabled:opacity-60"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => reject(reason)}
                disabled={approving}
                /* Fixed footprint: "Confirm rejection" and "Submitting…" are
                   very different widths, and a control that shrinks under the
                   cursor at the moment it is pressed reads as a glitch. */
                className="inline-flex min-w-[148px] items-center justify-center gap-2 rounded-md border border-gate-dim bg-gate/15 px-3 py-1.5 text-[12px] font-medium text-gate transition-colors hover:bg-gate/25 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {approving ? (
                  <Loader className="h-3.5 w-3.5 bp-pulse" strokeWidth={2.5} aria-hidden="true" />
                ) : null}
                {approving ? "Submitting…" : "Confirm rejection"}
              </button>
            </div>
          </footer>
        ) : (
          <footer className="flex shrink-0 flex-wrap items-center justify-end gap-2 border-t border-edge-muted px-4 py-3">
            <p className="mr-auto font-mono text-[10px] font-semibold tracking-[0.12em] text-fg-faint">
              AWAITING HUMAN DECISION
            </p>
            <button
              type="button"
              onClick={() => setRejecting(true)}
              disabled={approving}
              className="rounded-md border border-edge bg-raised px-3 py-1.5 text-[12px] text-fg-dim transition-colors hover:border-gate-dim hover:text-gate disabled:opacity-60"
            >
              Reject
            </button>
            <button
              type="button"
              onClick={approve}
              disabled={approving}
              /* Same fixed footprint, for the same reason. */
              className="inline-flex min-w-[148px] items-center justify-center gap-2 rounded-md border border-ok-dim bg-ok/15 px-3 py-1.5 text-[12px] font-medium text-ok transition-colors hover:bg-ok/25 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {approving ? (
                <Loader className="h-3.5 w-3.5 bp-pulse" strokeWidth={2.5} aria-hidden="true" />
              ) : null}
              {approving ? "Submitting…" : "Approve & Commit"}
            </button>
          </footer>
        )
      ) : (
        <CommitProgress run={run} />
      )}
    </section>
  );
}
