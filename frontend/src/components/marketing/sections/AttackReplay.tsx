/**
 * Section 04 — THE ATTACK. The darkest section, and the argument's hinge.
 *
 * Three beats, and the middle one is the whole product:
 *
 *   1. DOPPELGÄNGER forms a hypothesis in a sandbox. It is stamped
 *      EXPLORATORY · NO AUTHORITY and it is worth nothing.
 *   2. The hypothesis is narrowed into a typed CounterexampleSpec and crosses a
 *      labelled rule. Above the rule nothing may conclude anything.
 *   3. BRANCHPOINT replays the spec against world α's own snapshot. Now, and
 *      only now, there is evidence — and the veto.
 *
 * ## Legible without colour
 *
 * The card's border goes dim → blue as it crosses, but the crossing is carried
 * by *position* and by real text: the rule prints its own label, the card prints
 * its band, and the two halves are separately headed. Greyscale loses the tint
 * and nothing else. The blueprint calls this out as the section's acceptance
 * test, so nothing here may depend on the tint alone.
 *
 * ## Never "DOPPELGÄNGER vetoed α"
 *
 * The adversary chose which declared invariant to test. BRANCHPOINT's
 * deterministic replay decided what the answer meant. Those are different
 * sentences and the section exists to keep them apart.
 */

import {
  ATTACK,
  WITNESS_ORDER,
  WORLD_ALPHA,
  evidenceFor,
} from "../../../data/canonicalIncident";
import { useMobileHero, useReducedMotion } from "../../hero/heroMedia";
import { AuthorityChip } from "../AuthorityChip";
import { useScrollActs } from "../useScrollActs";

const BEAT = { HYPOTHESIS: 0, HANDOFF: 1, REPLAY: 2 } as const;

const BEATS = [
  {
    id: "hypothesis",
    label: "Hypothesis",
    caption:
      "DOPPELGÄNGER reads world α and runs throwaway code in a sandbox. It produces a sentence, and a sentence is not a finding.",
  },
  {
    id: "handoff",
    label: "Handoff",
    caption:
      "The hypothesis is narrowed into a typed CounterexampleSpec. That is the only thing BRANCHPOINT accepts, and it accepts it as a question — not as an answer.",
  },
  {
    id: "replay",
    label: "Replay",
    caption:
      "BRANCHPOINT replays the spec against world α's own snapshot. Reproduced, with disqualifying evidence behind it. Only now is anything vetoed.",
  },
] as const;

/** The exploratory half. Present at every beat; it just stops mattering. */
function HypothesisCard({ crossed }: { crossed: boolean }) {
  return (
    <article className="bp-atk__card bp-atk__card--hyp" data-crossed={crossed ? "" : undefined}>
      <header className="bp-atk__card-head">
        <span className="bp-atk__who">DOPPELGÄNGER</span>
        <span className="bp-atk__sbx">sandbox {ATTACK.sandboxId}</span>
      </header>

      <p className="bp-atk__hypothesis">&ldquo;{ATTACK.hypothesis}&rdquo;</p>

      <dl className="bp-atk__counters">
        <div>
          <dt>exec calls</dt>
          <dd>{ATTACK.execCalls}</dd>
        </div>
        <div>
          <dt>hypotheses</dt>
          <dd>{ATTACK.hypotheses}</dd>
        </div>
        <div>
          <dt>evidence written</dt>
          <dd>0</dd>
        </div>
      </dl>

      <footer className="bp-atk__card-foot">
        <AuthorityChip band="EXPLORATORY" suffix="· NO AUTHORITY" />
      </footer>
    </article>
  );
}

/**
 * The rule. A real element with real text on it, not an SVG path with a tooltip:
 * a reader who cannot see the drawing must still be told what the line means.
 */
function AuthorityRule({ crossed }: { crossed: boolean }) {
  return (
    <div className="bp-atk__rule" data-crossed={crossed ? "" : undefined}>
      <span className="bp-atk__rule-label">
        CounterexampleSpec · typed · validated
      </span>
      <span className="bp-atk__rule-note">
        Nothing above this line may conclude anything.
      </span>
    </div>
  );
}

/** The deterministic half. Empty until the replay beat — deliberately. */
function ReplayCard({ landed }: { landed: boolean }) {
  const rows = evidenceFor(WORLD_ALPHA.id).filter((entry) => entry.machineVerifiable);

  return (
    <article className="bp-atk__card bp-atk__card--replay" data-landed={landed ? "" : undefined}>
      <header className="bp-atk__card-head">
        <span className="bp-atk__who">BRANCHPOINT REPLAY</span>
        <span className="bp-atk__sbx">against world α&rsquo;s own snapshot</span>
      </header>

      {landed ? (
        <>
          <ul className="bp-atk__checks">
            {rows.map((entry) => (
              <li key={entry.id}>
                <span className="bp-atk__check-mark" aria-hidden="true">
                  ■
                </span>
                <span className="bp-atk__check-name">{entry.claim}</span>
                <span className="bp-atk__check-outcome">
                  {entry.outcome} · {entry.severity}
                </span>
                <span className="bp-atk__check-observed">{entry.observed}</span>
              </li>
            ))}
          </ul>

          <p className="bp-atk__status">
            <span className="bp-atk__status-chip">{ATTACK.status}</span>
            <span className="bp-atk__status-rule">{ATTACK.vetoRule}</span>
          </p>

          <p className="bp-atk__verdict">WORLD α · {ATTACK.verdict}</p>
        </>
      ) : (
        <p className="bp-atk__waiting">
          Nothing has been replayed yet. No evidence exists on this side of the
          line.
        </p>
      )}

      <footer className="bp-atk__card-foot">
        <AuthorityChip band="DETERMINISTIC" suffix="· MAY VETO" />
      </footer>
    </article>
  );
}

/** The typed spec itself, shown as it crosses. */
function SpecBlock() {
  const spec = ATTACK.spec;
  return (
    <div className="bp-atk__spec">
      <span className="bp-atk__spec-title">CounterexampleSpec</span>
      <dl className="bp-atk__spec-list">
        <dt>type</dt>
        <dd>{spec.counterexample_type}</dd>
        <dt>operation</dt>
        <dd>{spec.operation}</dd>
        <dt>assertion</dt>
        <dd>{spec.assertion.kind}</dd>
        <dt>target</dt>
        <dd>{spec.target_world_id}</dd>
        <dt>setup</dt>
        <dd>
          created_under_version={spec.setup.created_under_version} ·
          min_schema_version={spec.setup.min_schema_version}
        </dd>
      </dl>
      <p className="bp-atk__spec-note">{ATTACK.specNote}</p>
    </div>
  );
}

function Scene({ beat }: { beat: number }) {
  return (
    <div className="bp-atk__scene" data-beat={beat}>
      <div className="bp-atk__half bp-atk__half--above">
        <p className="bp-atk__half-label">Above the line · exploratory</p>
        <HypothesisCard crossed={beat >= BEAT.HANDOFF} />
        {beat >= BEAT.HANDOFF ? <SpecBlock /> : null}
      </div>

      <AuthorityRule crossed={beat >= BEAT.HANDOFF} />

      <div className="bp-atk__half bp-atk__half--below">
        <p className="bp-atk__half-label">Below the line · deterministic</p>
        <ReplayCard landed={beat >= BEAT.REPLAY} />
      </div>
    </div>
  );
}

export function AttackReplay() {
  const reduced = useReducedMotion();
  const mobile = useMobileHero();
  const animated = !reduced && !mobile;

  // Reduced motion and the phone both land on the conclusion, never the setup.
  const { act, trackRef } = useScrollActs(BEATS.length, animated, BEAT.REPLAY);
  const beat = animated ? act : BEAT.REPLAY;
  const current = BEATS[beat] ?? BEATS[BEATS.length - 1]!;

  return (
    <section className="bp-sec bp-sec--atk" aria-labelledby="bp-atk-title">
      <div className="bp-sec__inner">
        <p className="bp-eyebrow">04 — The attack</p>
        <h2 id="bp-atk-title" className="bp-sec__title">
          The candidate survived. <br />
          Now try to break it.
        </h2>
        <p className="bp-lead bp-sec__lead">
          An adversarial agent gets a sandbox, a copy of the world and no
          authority whatsoever. It can guess. It cannot conclude. Everything it
          produces has to cross one line before it means anything.
        </p>
      </div>

      {animated ? (
        <div className="bp-atk__track" ref={trackRef}>
          <div className="bp-atk__sticky">
            <div className="bp-sec__inner bp-atk__frame">
              <ol className="bp-atk__rail" aria-hidden="true">
                {BEATS.map((entry, index) => (
                  <li
                    key={entry.id}
                    className="bp-atk__rail-item"
                    data-state={
                      index === beat ? "on" : index < beat ? "done" : undefined
                    }
                  >
                    <span className="bp-atk__rail-num">
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    <span className="bp-atk__rail-label">{entry.label}</span>
                  </li>
                ))}
              </ol>

              <Scene beat={beat} />

              <p className="bp-atk__caption">{current.caption}</p>
            </div>
          </div>

          {BEATS.map((entry, index) => (
            <div
              key={entry.id}
              className="bp-atk__region"
              data-act={index}
              aria-hidden="true"
            />
          ))}
          {/* Dwell on the verdict rather than releasing the pin as it lands. */}
          <div className="bp-atk__tail" aria-hidden="true" />
        </div>
      ) : (
        <div className="bp-sec__inner">
          <ol className="bp-atk__stack">
            {BEATS.map((entry, index) => (
              <li key={entry.id} className="bp-atk__stack-item">
                <p className="bp-eyebrow">
                  {String(index + 1).padStart(2, "0")} — {entry.label}
                </p>
                <p className="bp-atk__caption">{entry.caption}</p>
                {index === BEAT.HYPOTHESIS ? <HypothesisCard crossed /> : null}
                {index === BEAT.HANDOFF ? (
                  <>
                    <AuthorityRule crossed />
                    <SpecBlock />
                  </>
                ) : null}
                {index === BEAT.REPLAY ? <ReplayCard landed /> : null}
              </li>
            ))}
          </ol>
        </div>
      )}

      {/*
        The scene animates; this does not. It is the same claim in plain text,
        never announced, and complete on its own — which is also what makes the
        section legible with no colour and no motion at all.
      */}
      <div className="bp-sec__inner">
        <div className="bp-atk__ledger">
          <h3 className="bp-atk__ledger-title">Where the authority moved</h3>
          <dl className="bp-atk__ledger-list">
            <dt>DOPPELGÄNGER produced</dt>
            <dd>
              one hypothesis and one typed spec, recorded with
              machine_verifiable = false. It vetoed nothing and could not have.
            </dd>
            <dt>BRANCHPOINT produced</dt>
            <dd>
              two machine-verifiable failures on {WITNESS_ORDER.orderId},
              severity CRITICAL, kind DATA_INTEGRITY.
            </dd>
            <dt>The veto required</dt>
            <dd>{ATTACK.vetoRule}</dd>
            <dt>Result</dt>
            <dd>
              World α is {ATTACK.verdict} — by BRANCHPOINT&rsquo;s replay, not by
              the adversary that suggested where to look.
            </dd>
          </dl>
        </div>
      </div>
    </section>
  );
}
