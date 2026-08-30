/**
 * Section 06 — HUMAN CHECKPOINT.
 *
 * The one section a visitor can operate, and the only one that demonstrates a
 * security property rather than describing it: change the action after it was
 * reviewed and the approval stops being valid, because the approval was never
 * bound to "the recommendation" — it was bound to a content hash.
 *
 * ## This surface never touches the network
 *
 * It imports no API client, constructs no request and issues no fetch. Both
 * fingerprints are constants computed offline with the same construction as
 * `CandidateAction.fingerprint()`. A test asserts that rendering and operating
 * this section issues no fetch at all; if that assertion ever fails, something
 * has gone badly wrong, not merely become untidy.
 *
 * ## The per-glyph roll
 *
 * The one flourish on the page, and it earns its place: the reader has to *see*
 * that the hash is a function of the content, not a label attached to it.
 * Reduced motion swaps the two strings with no roll and loses nothing, because
 * the invalidated state is stated in words either way.
 */

import { useState } from "react";

import { APPROVAL, WORLD_BETA } from "../../../data/canonicalIncident";
import { useReducedMotion } from "../../hero/heroMedia";
import { AuthorityChip } from "../AuthorityChip";

/** 12 leading + 4 trailing hex, the blueprint's truncation. */
function truncate(hash: string) {
  return `${hash.slice(0, 12)}…${hash.slice(-4)}`;
}

function Fingerprint({ hash, rolled }: { hash: string; rolled: boolean }) {
  const shown = truncate(hash);
  return (
    <p className="bp-appr__fp">
      <span className="bp-appr__fp-label">ACTION FINGERPRINT</span>
      <span className="bp-appr__fp-algo">sha256</span>
      <span className="bp-appr__fp-hash" data-rolled={rolled ? "" : undefined}>
        {[...shown].map((glyph, index) => (
          <span
            key={`${index}-${glyph}`}
            className="bp-appr__fp-glyph"
            style={{ ["--i" as string]: String(index) }}
          >
            {glyph}
          </span>
        ))}
      </span>
      <span className="bp-appr__fp-note">
        64 hex characters over the canonical action JSON. Any change to the
        action — including one parameter — changes the whole hash.
      </span>
    </p>
  );
}

export function ApprovalFingerprint() {
  const reduced = useReducedMotion();
  const [mutated, setMutated] = useState(false);
  const [decision, setDecision] = useState<"none" | "approved" | "rejected">(
    "none",
  );

  const flagKey = mutated ? APPROVAL.mutatedFlagKey : APPROVAL.reviewedFlagKey;
  const hash = mutated
    ? APPROVAL.mutatedFingerprint
    : APPROVAL.reviewedFingerprint;
  const invalid = mutated;

  return (
    <section className="bp-sec bp-sec--appr" aria-labelledby="bp-appr-title">
      <div className="bp-sec__inner">
        <p className="bp-eyebrow">06 — Human checkpoint</p>
        <h2 id="bp-appr-title" className="bp-sec__title">
          A recommendation is not permission.
        </h2>
        <p className="bp-lead bp-sec__lead">
          BRANCHPOINT can prove which world is safest. It cannot authorise
          anything. Below is the card a human is actually shown — and it is bound
          to one exact action, by content.
        </p>

        <div
          className="bp-appr__card"
          data-invalid={invalid ? "" : undefined}
          data-reduced={reduced ? "" : undefined}
        >
          <header className="bp-appr__head">
            <div>
              <span className="bp-appr__world">{APPROVAL.worldLabel}</span>
              <span className="bp-appr__run">{APPROVAL.runId}</span>
            </div>
            <AuthorityChip band="PERMISSION" size="sm" />
          </header>

          <div className="bp-appr__action">
            <span className="bp-appr__action-kind">{APPROVAL.actionName}</span>
            <span className="bp-appr__action-body">
              <span
                className="bp-appr__flag"
                data-mutated={mutated ? "" : undefined}
              >
                {flagKey}
              </span>{" "}
              {APPROVAL.from} → {APPROVAL.to}
            </span>
            <span className="bp-appr__action-meta">
              {APPROVAL.actionId} · {APPROVAL.actionType} · risk{" "}
              {APPROVAL.riskClass} · reversible
            </span>
          </div>

          <Fingerprint hash={hash} rolled={mutated && !reduced} />

          <ul className="bp-appr__bindings">
            {APPROVAL.bindings.map((binding) => {
              // Only the fingerprint binding depends on the action's content;
              // the other four were established upstream and stay true.
              const failed =
                invalid && binding.key === APPROVAL.fingerprintBindingKey;
              return (
                <li key={binding.key} data-failed={failed ? "" : undefined}>
                  <span className="bp-appr__bind-mark" aria-hidden="true">
                    {failed ? "✗" : "✓"}
                  </span>
                  <span className="bp-appr__bind-label">{binding.label}</span>
                  <span className="bp-appr__bind-state">
                    {failed ? "BROKEN" : "BOUND"}
                  </span>
                </li>
              );
            })}
          </ul>

          {invalid ? (
            <p className="bp-appr__stamp">{APPROVAL.invalidatedLabel}</p>
          ) : null}

          <div className="bp-appr__buttons">
            <button
              type="button"
              className="bp-appr__btn bp-appr__btn--reject"
              aria-disabled={invalid}
              onClick={() => {
                if (invalid) return;
                setDecision("rejected");
              }}
            >
              REJECT
            </button>
            <button
              type="button"
              className="bp-appr__btn bp-appr__btn--approve"
              aria-disabled={invalid}
              onClick={() => {
                if (invalid) return;
                setDecision("approved");
              }}
            >
              APPROVE EXACT ACTION
            </button>
          </div>

          <p className="bp-appr__decision">
            {invalid
              ? "Both decisions are unavailable: there is no longer an action this approval binds."
              : decision === "approved"
                ? "Approved. A one-time capability is issued for this fingerprint and nothing else."
                : decision === "rejected"
                  ? "Rejected. Nothing is committed, and the run ends here."
                  : "No decision taken. Nothing has been committed."}
          </p>
        </div>

        <div className="bp-appr__controls">
          <button
            type="button"
            className="bp-appr__mutate"
            onClick={() => {
              setMutated(true);
              setDecision("none");
            }}
            aria-disabled={mutated}
          >
            Change the action → {APPROVAL.mutatedFlagKey}
          </button>
          <button
            type="button"
            className="bp-appr__reset"
            onClick={() => {
              setMutated(false);
              setDecision("none");
            }}
            aria-disabled={!mutated}
          >
            ⟲ Reset to the reviewed action
          </button>
        </div>

        <p className="bp-sec__kicker" data-tone={invalid ? "fail" : "muted"}>
          {invalid ? (
            APPROVAL.invalidatedNote
          ) : (
            <>
              The approval binds {WORLD_BETA.label}, action{" "}
              {APPROVAL.actionId}, and the hash of that action&rsquo;s contents.
              Change one parameter and the binding breaks. Try it.
            </>
          )}
        </p>

        {/* Never announced, always true, and complete without the interaction. */}
        <div className="sr-only">
          <h3>What the approval binds</h3>
          <p>
            An approval in BRANCHPOINT names a run, a world, an action id and a
            SHA-256 fingerprint of the action&rsquo;s canonical JSON. Before a
            commit, assert_commit_allowed re-computes that fingerprint. If the
            action changed after it was approved, the commit is refused: an
            approval is not transferable to a different action.
          </p>
        </div>
      </div>
    </section>
  );
}
