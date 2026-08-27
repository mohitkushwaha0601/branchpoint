/**
 * Section 01 — the trap.
 *
 * One proposal, read two ways. In the headline reading the rollback goes
 * straight to production and every number says ship it; in the evidence reading
 * the same proposal is intercepted, and the same four plates become the two
 * checks that failed. Same geometry, opposite conclusion — the point is that
 * nothing about the *action* changed, only what was allowed to decide.
 *
 * Why this is one surface and not two columns: a side-by-side "without us / with
 * us" comparison lets the reader treat the bad outcome as someone else's
 * problem. Making it a single path they flip forces the two readings to be about
 * the same action.
 *
 * α is deliberately allowed to look good first. It recovers checkout to 1.8% and
 * 190 ms — the fastest world in the run, inside the declared SLO. The section
 * only works if that success registers before the evidence lands.
 */

import { useState } from "react";

import {
  DECLARED_BOUNDS,
  WITNESS_ORDER,
  WORLD_ALPHA,
  disqualifyingChecks,
} from "../../../data/canonicalIncident";
import { useReducedMotion } from "../../hero/heroMedia";
import { useSeenOnce } from "../useScrollActs";

type Reading = "headline" | "evidence";

const CRITICAL = disqualifyingChecks(WORLD_ALPHA);

/** The four plates that make the rollback look finished. */
const HEADLINE_PLATES = [
  {
    label: WORLD_ALPHA.metrics.errorRate.label,
    value: WORLD_ALPHA.metrics.errorRate.value,
    note: `was ${(0.413 * 100).toFixed(1)}%`,
  },
  {
    label: WORLD_ALPHA.metrics.p95.label,
    value: WORLD_ALPHA.metrics.p95.value,
    note: "was 4.8s",
  },
  {
    label: WORLD_ALPHA.metrics.affectedUsers.label,
    value: WORLD_ALPHA.metrics.affectedUsers.value,
    note: "was 8,000",
  },
  {
    label: WORLD_ALPHA.metrics.costDelta.label,
    value: WORLD_ALPHA.metrics.costDelta.value,
    note: "no new spend",
  },
] as const;

function ReadingToggle({
  reading,
  onChange,
}: {
  reading: Reading;
  onChange: (next: Reading) => void;
}) {
  const options: readonly { id: Reading; label: string }[] = [
    { id: "headline", label: "HEADLINE VIEW" },
    { id: "evidence", label: "EVIDENCE VIEW" },
  ];

  return (
    <div
      className="bp-seg"
      role="radiogroup"
      aria-label="How to read this proposal"
    >
      {options.map((option) => {
        const active = option.id === reading;
        return (
          <button
            key={option.id}
            type="button"
            role="radio"
            aria-checked={active}
            className="bp-seg__option"
            data-active={active ? "" : undefined}
            // Arrow keys move between radios in a group; only the checked one
            // is a tab stop.
            tabIndex={active ? 0 : -1}
            onKeyDown={(event) => {
              if (
                event.key === "ArrowRight" ||
                event.key === "ArrowLeft" ||
                event.key === "ArrowUp" ||
                event.key === "ArrowDown"
              ) {
                event.preventDefault();
                onChange(reading === "headline" ? "evidence" : "headline");
              }
            }}
            onClick={() => onChange(option.id)}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

export function ProblemSection() {
  const reduced = useReducedMotion();
  // Reduced motion starts on the conclusion rather than the setup: a reader who
  // will not see the flip should not be left holding only the false-green half.
  const [reading, setReading] = useState<Reading>(
    reduced ? "evidence" : "headline",
  );
  const [touched, setTouched] = useState(false);

  // One unattended flip, the first time the section is reached. It shows the
  // reader that the surface has a second state without demanding a click; after
  // that the control is entirely theirs.
  const seenRef = useSeenOnce(!reduced && !touched, () => {
    setReading((prev) => (prev === "headline" ? "evidence" : prev));
  });

  const choose = (next: Reading) => {
    setTouched(true);
    setReading(next);
  };

  const evidence = reading === "evidence";

  return (
    <section
      className="bp-sec bp-sec--problem"
      aria-labelledby="bp-problem-title"
      data-reading={reading}
    >
      <div className="bp-sec__inner">
        <p className="bp-eyebrow">01 — The trap</p>

        <h2 id="bp-problem-title" className="bp-sec__title">
          {/* The space before the break matters: the phone layout hides
              `br`, and without it the two lines fuse into one word. */}
          An agent can be confident <br />
          and still be wrong.
        </h2>

        <p className="bp-lead bp-sec__lead">
          Rolling pricing-service back to v2.40 restores checkout to{" "}
          <strong>{WORLD_ALPHA.metrics.errorRate.value}</strong> error and{" "}
          <strong>{WORLD_ALPHA.metrics.p95.value}</strong> — the fastest result
          in the run, inside every bound BRANCHPOINT declared. It still charges a
          customer twice.
        </p>

        <ReadingToggle reading={reading} onChange={choose} />

        {/* The proposal path. In the headline reading it runs straight into
            production; in the evidence reading BRANCHPOINT stands in the middle
            of it. Decorative — every node is also stated in text below. */}
        <div className="bp-path" ref={seenRef} aria-hidden="true">
          <div className="bp-path__node">
            <span className="bp-path__kind">PROPOSAL</span>
            <span className="bp-path__body">
              {WORLD_ALPHA.action.target} {WORLD_ALPHA.action.from} →{" "}
              {WORLD_ALPHA.action.to}
            </span>
          </div>

          <div className="bp-path__link">
            <span className="bp-path__gate" data-on={evidence ? "" : undefined}>
              BRANCHPOINT
            </span>
          </div>

          <div className="bp-path__node bp-path__node--end" data-tone={evidence ? "fail" : "ok"}>
            <span className="bp-path__kind">
              {evidence ? "VERDICT" : "OUTCOME"}
            </span>
            <span className="bp-path__body">
              {evidence ? "VETOED" : "Ship to production"}
            </span>
          </div>
        </div>

        {/* Fixed min-height so flipping the reading never moves the page. */}
        <div className="bp-plates" data-count={evidence ? 2 : 4}>
          {evidence
            ? CRITICAL.map((check) => (
                <div className="bp-plate bp-plate--check" key={check.name}>
                  <span className="bp-plate__label">
                    <span className="bp-plate__sev">CRITICAL</span>
                    {check.name}
                  </span>
                  <span className="bp-plate__value bp-plate__value--fail">
                    FAIL
                  </span>
                  <span className="bp-plate__note">
                    expected&nbsp;{check.expected}
                  </span>
                  <span className="bp-plate__note bp-plate__note--observed">
                    observed&nbsp;{check.observed}
                  </span>
                </div>
              ))
            : HEADLINE_PLATES.map((plate) => (
                <div className="bp-plate" key={plate.label}>
                  <span className="bp-plate__label">{plate.label}</span>
                  <span className="bp-plate__value">{plate.value}</span>
                  <span className="bp-plate__note">{plate.note}</span>
                </div>
              ))}
        </div>

        <p className="bp-sec__kicker" data-tone={evidence ? "fail" : "muted"}>
          {evidence ? (
            <>
              Order {WITNESS_ORDER.orderId} was written under schema{" "}
              {WITNESS_ORDER.schemaVersion}. Under v2.40 its retry key degrades
              from <code>{WITNESS_ORDER.originalKey}</code> to{" "}
              <code>{WITNESS_ORDER.degradedKey}</code>, so the retry is charged
              as a new payment.
            </>
          ) : (
            <>
              Every declared bound is met: error under{" "}
              {(DECLARED_BOUNDS.recoveryErrorRate * 100).toFixed(0)}%, p95 under{" "}
              {DECLARED_BOUNDS.recoveryP95Ms}ms.
            </>
          )}
        </p>

        {/*
          The path and plates above are decorative and flip as the reader
          toggles. This block never changes, is never announced, and states the
          whole argument for anyone who cannot see the interaction at all.
        */}
        <div className="sr-only">
          <h3>What the rollback actually did</h3>
          <ul>
            <li>
              Checkout error recovered to {WORLD_ALPHA.metrics.errorRate.value}{" "}
              and p95 latency to {WORLD_ALPHA.metrics.p95.value}, both inside
              BRANCHPOINT&rsquo;s declared recovery bounds.
            </li>
            {CRITICAL.map((check) => (
              <li key={check.name}>
                The check {check.name} failed with critical severity. Expected{" "}
                {check.expected}. Observed {check.observed}.
              </li>
            ))}
            <li>
              World alpha was {WORLD_ALPHA.verdict}. Headline metrics recover;
              critical evidence still fails.
            </li>
          </ul>
        </div>
      </div>
    </section>
  );
}
