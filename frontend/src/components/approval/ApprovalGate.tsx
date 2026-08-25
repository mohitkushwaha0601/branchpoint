/**
 * The human checkpoint, sitting where the trunk ends.
 *
 * It restates exactly what is being approved — one world, one action, one
 * fingerprint — because the whole safety argument is that a human approves a
 * specific bound action rather than a general intention. Phase 4.1 is visual
 * only: deciding here changes local view state and calls no backend.
 */

import { Check, Diamond, X } from "lucide-react";

import { useRunView } from "../../app/runView";

export function ApprovalGate() {
  const { run, approvalDecision, decideApproval, resetApproval } = useRunView();
  const { approval } = run;
  const world = run.worlds.find((w) => w.worldId === approval.worldId);

  if (!approval.required || world === undefined) return null;

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
          MANUAL APPROVAL REQUIRED
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
            ACTION
          </p>
          <p className="mt-1 font-mono text-[13px] text-fg">
            {world.action.parameter}
          </p>
          <p className="font-mono text-[13px] tabular-nums">
            <span className="text-fg-faint">{world.action.from}</span>
            <span className="px-1.5 text-fg-faint" aria-label="changes to">
              →
            </span>
            <span className="text-fg">{world.action.to}</span>
          </p>
          <dl className="mt-3 space-y-0.5">
            <div className="flex items-baseline justify-between gap-3">
              <dt className="text-[11px] text-fg-faint">Action id</dt>
              <dd className="font-mono text-[11px] text-fg-dim">
                {approval.actionId}
              </dd>
            </div>
            <div className="flex items-baseline justify-between gap-3">
              <dt className="text-[11px] text-fg-faint">Fingerprint</dt>
              <dd className="font-mono text-[11px] text-fg-dim">
                {approval.actionFingerprint}
              </dd>
            </div>
          </dl>
        </div>
      </div>

      {approvalDecision === null ? (
        <footer className="flex items-center justify-end gap-2 border-t border-edge-muted px-4 py-3">
          <button
            type="button"
            onClick={() => decideApproval("REJECTED")}
            className="rounded-md border border-edge bg-raised px-3 py-1.5 text-[12px] text-fg-dim transition-colors hover:border-fail-dim hover:text-fail"
          >
            Reject
          </button>
          <button
            type="button"
            onClick={() => decideApproval("APPROVED")}
            className="rounded-md border border-ok-dim bg-ok/15 px-3 py-1.5 text-[12px] font-medium text-ok transition-colors hover:bg-ok/25"
          >
            Approve &amp; Commit
          </button>
        </footer>
      ) : (
        <footer
          role="status"
          className="border-t border-edge-muted px-4 py-3"
        >
          <p className="flex items-center gap-2 text-[12px]">
            {approvalDecision === "APPROVED" ? (
              <>
                <Check
                  className="h-4 w-4 text-ok"
                  strokeWidth={2.75}
                  aria-hidden="true"
                />
                <span className="text-fg">
                  Approval recorded for {world.name}.
                </span>
              </>
            ) : (
              <>
                <X
                  className="h-4 w-4 text-fail"
                  strokeWidth={2.75}
                  aria-hidden="true"
                />
                <span className="text-fg">
                  Rejection recorded. Nothing will be committed.
                </span>
              </>
            )}
          </p>
          <p className="mt-1 font-mono text-[11px] text-fg-faint">
            Visual only in Phase 4.1 — no commit was issued and reality is
            unchanged.
          </p>
          <button
            type="button"
            onClick={resetApproval}
            className="mt-2 rounded-md border border-edge bg-raised px-2.5 py-1 text-[11px] text-fg-dim hover:text-fg"
          >
            Undo
          </button>
        </footer>
      )}
    </section>
  );
}
