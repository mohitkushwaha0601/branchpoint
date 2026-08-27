/**
 * Section 07 — COMMIT & VERIFY.
 *
 * Two bands, and the gap between them is the argument. The upper band changes
 * reality once. The lower band goes and looks again, without reading what the
 * commit claimed. A commit proves that a mutation was *issued*; only the re-read
 * proves anything about the world.
 *
 * ## Why a timed sequence and not scroll
 *
 * The four gates and the three verification pairs happen in an order, and the
 * order is the content. Tying them to scroll would let a reader arrive at the
 * end without seeing that anything was sequential. So the section starts one
 * `setTimeout` chain the first time it is seen, runs it once, and cleans it up
 * on unmount.
 *
 * The result region is deliberately **not** `aria-live`: it is static content
 * that happens to animate, and announcing it would interrupt a screen reader
 * with information already present in the DOM.
 */

import { useEffect, useState } from "react";

import {
  COMMIT,
  COMMIT_GATES,
  VERIFICATION,
  VERIFY_NOTE,
} from "../../../data/canonicalIncident";
import { useReducedMotion } from "../../hero/heroMedia";
import { AuthorityChip } from "../AuthorityChip";
import { useSeenOnce } from "../useScrollActs";

/** Gates, then the mutation, then one step per verification pair. */
const STEPS = COMMIT_GATES.length + 1 + VERIFICATION.length;
const STEP_MS = 620;

export function CommitVerify() {
  const reduced = useReducedMotion();
  // Reduced motion lands on the conclusion: everything resolved, nothing moved.
  const [step, setStep] = useState(reduced ? STEPS : 0);
  const [started, setStarted] = useState(reduced);

  const seenRef = useSeenOnce(!reduced && !started, () => setStarted(true));

  useEffect(() => {
    if (!started || reduced) return;
    if (step >= STEPS) return;

    const timer = window.setTimeout(() => setStep((prev) => prev + 1), STEP_MS);
    // Cleared on unmount and on every re-run, so a reader who scrolls away
    // mid-sequence leaves no timer behind.
    return () => window.clearTimeout(timer);
  }, [started, reduced, step]);

  const gatesDone = Math.min(step, COMMIT_GATES.length);
  const mutated = step > COMMIT_GATES.length;
  const verified = Math.max(0, step - COMMIT_GATES.length - 1);

  return (
    <section className="bp-sec bp-sec--cv" aria-labelledby="bp-cv-title">
      <div className="bp-sec__inner" ref={seenRef}>
        <p className="bp-eyebrow">07 — Commit &amp; verify</p>
        <h2 id="bp-cv-title" className="bp-sec__title">
          Approval changes permission. <br />
          Verification proves reality.
        </h2>
        <p className="bp-lead bp-sec__lead">
          Two separate things happen here, and collapsing them is how systems
          come to believe their own change log.
        </p>

        <div className="bp-cv__bands">
          <div className="bp-cv__band bp-cv__band--commit">
            <header className="bp-cv__band-head">
              <span className="bp-cv__band-num">08</span>
              <h3 className="bp-cv__band-title">COMMIT</h3>
              <AuthorityChip band="DETERMINISTIC" size="sm" />
            </header>

            <ol className="bp-cv__gates">
              {COMMIT_GATES.map((gate, index) => (
                <li
                  key={gate.key}
                  data-done={index < gatesDone ? "" : undefined}
                >
                  <span className="bp-cv__gate-mark" aria-hidden="true">
                    {index < gatesDone ? "✓" : "·"}
                  </span>
                  <span className="bp-cv__gate-label">{gate.label}</span>
                  <span className="bp-cv__gate-detail">{gate.detail}</span>
                </li>
              ))}
            </ol>

            <p className="bp-cv__mutation" data-done={mutated ? "" : undefined}>
              <span className="bp-cv__mutation-key">{COMMIT.mutation.key}</span>
              <span className="bp-cv__mutation-change">
                {COMMIT.mutation.from}{" "}
                <span aria-hidden="true">→</span> {COMMIT.mutation.to}
              </span>
              <span className="bp-cv__mutation-state">
                {mutated ? "ISSUED · capability spent" : "capability issued"}
              </span>
            </p>

            <p className="bp-cv__note">{COMMIT.capabilityNote}</p>
          </div>

          <div className="bp-cv__band bp-cv__band--verify">
            <header className="bp-cv__band-head">
              <span className="bp-cv__band-num">09</span>
              <h3 className="bp-cv__band-title">VERIFY</h3>
              <AuthorityChip band="DETERMINISTIC" size="sm" />
            </header>

            <table className="bp-cv__pairs">
              <caption>
                An independent re-read of production. Expected against actual.
              </caption>
              <thead>
                <tr>
                  <th scope="col">check</th>
                  <th scope="col">expected</th>
                  <th scope="col">actual</th>
                  <th scope="col">
                    <span className="sr-only">result</span>
                    <span aria-hidden="true">·</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {VERIFICATION.map((pair, index) => {
                  const done = index < verified;
                  return (
                    <tr key={pair.key} data-done={done ? "" : undefined}>
                      <th scope="row">{pair.key}</th>
                      <td className="bp-num">{pair.expected}</td>
                      <td className="bp-num">{done ? pair.actual : "—"}</td>
                      <td className="bp-cv__tick">{done ? "✓" : ""}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>

            <p
              className="bp-cv__status"
              data-done={verified >= VERIFICATION.length ? "" : undefined}
            >
              {verified >= VERIFICATION.length
                ? "RUN SUCCEEDED"
                : "VERIFYING…"}
            </p>

            <p className="bp-cv__note">{VERIFY_NOTE}</p>
          </div>
        </div>

        <p className="bp-sec__kicker" data-tone="muted">
          {COMMIT.kicker}
        </p>
      </div>
    </section>
  );
}
