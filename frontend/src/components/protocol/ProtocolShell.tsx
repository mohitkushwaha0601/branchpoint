/**
 * `/how-it-works` — the protocol instrument.
 *
 * The landing page sells the idea; this page proves the system, so it does not
 * repeat a single landing section. Instead it takes one run —
 * `run_dbfa98c87f06` — and walks it through all nine stages **without ever
 * resetting the example**. A reader should be able to trace the final
 * verification back to the first metric without the numbers changing under
 * them.
 *
 * ## Desktop
 *
 * Three columns: a sticky stage rail, a scroll-advanced viewport, and a sticky
 * evidence + authority inspector. The rail and the inspector are independently
 * sticky and the centre column is what moves — which is the point of the
 * layout: the evidence chain stays on screen and visibly *grows* as the run
 * proceeds. It is never filtered and never cleared.
 *
 * ## Mobile
 *
 * The three-column instrument cannot survive 390 px, and squashing it produces
 * three unreadable columns rather than one readable page. So it becomes a 56 px
 * sticky header carrying `05 / 09 · ATTACK` and the current authority band —
 * the two things a reader must never lose — then one visualisation, then the
 * evidence, then the authority, then a next-stage affordance. One stage per
 * screenful, ordinary vertical scroll, no pinning and no horizontal snap.
 */

import { Link } from "react-router-dom";

import {
  PROTOCOL_STAGES,
  RUN_ID,
  authorityBand,
  evidenceThrough,
  type ChainRow,
} from "../../data/canonicalIncident";
import { useMobileHero, useReducedMotion } from "../hero/heroMedia";
import { AuthorityChip } from "../marketing/AuthorityChip";
import { StageViewport } from "./stages";
import { useStageProgress } from "./useStageProgress";

/* --------------------------------------------------------------- the rail */

function StageRail({
  current,
  onGo,
}: {
  current: number;
  onGo: (index: number) => void;
}) {
  return (
    <nav className="bp-pr__rail" aria-label="Protocol stages">
      <p className="bp-pr__rail-title">PROTOCOL</p>
      <ol className="bp-pr__rail-list">
        {PROTOCOL_STAGES.map((stage, index) => {
          const state =
            index === current ? "on" : index < current ? "done" : "next";
          return (
            <li key={stage.id} data-state={state}>
              <button
                type="button"
                className="bp-pr__rail-item"
                aria-current={index === current ? "step" : undefined}
                onClick={() => onGo(index)}
              >
                <span className="bp-pr__rail-num">{stage.number}</span>
                <span className="bp-pr__rail-name">{stage.name}</span>
              </button>
              {stage.acts === undefined ? null : (
                <ul className="bp-pr__rail-acts">
                  {stage.acts.map((act) => (
                    <li key={act}>{act}</li>
                  ))}
                </ul>
              )}
            </li>
          );
        })}
      </ol>

      <div className="bp-pr__rail-key">
        <p className="bp-pr__rail-title">AUTHORITY</p>
        <ul>
          <li>
            <span aria-hidden="true">░</span> exploratory
          </li>
          <li>
            <span aria-hidden="true">■</span> deterministic
          </li>
          <li>
            <span aria-hidden="true">▲</span> permission
          </li>
        </ul>
      </div>
    </nav>
  );
}

/* ---------------------------------------------------------- the inspector */

function EvidencePanel({ rows }: { rows: readonly ChainRow[] }) {
  return (
    <div className="bp-pr__evidence">
      <div className="bp-pr__panel-head">
        <span className="bp-pr__panel-title">EVIDENCE</span>
        <span className="bp-pr__panel-count">{rows.length}</span>
      </div>

      {rows.length === 0 ? (
        <p className="bp-pr__empty">
          No evidence yet. Nothing has been checked, so nothing has been
          established.
        </p>
      ) : (
        <ol className="bp-pr__rows">
          {rows.map((row) => (
            <li key={row.id} data-outcome={row.outcome}>
              <span className="bp-pr__row-mark" aria-hidden="true">
                {row.machineVerifiable ? "■" : "░"}
              </span>
              <span className="bp-pr__row-claim">
                {row.worldGlyph === undefined ? null : (
                  <span className="bp-pr__row-world" aria-hidden="true">
                    {row.worldGlyph}{" "}
                  </span>
                )}
                {row.claim}
              </span>
              <span className="bp-pr__row-outcome">{row.outcome}</span>
              <span className="bp-pr__row-auth">
                machine_verifiable = {String(row.machineVerifiable)}
              </span>
            </li>
          ))}
        </ol>
      )}

      <p className="bp-pr__accumulates">
        This chain only grows. Nothing recorded at an earlier stage is removed,
        replaced or re-ordered.
      </p>
    </div>
  );
}

function AuthorityPanel({ stageIndex }: { stageIndex: number }) {
  const stage = PROTOCOL_STAGES[stageIndex] ?? PROTOCOL_STAGES[0]!;
  const spec = authorityBand(stage.band);

  return (
    <div className="bp-pr__authority">
      <div className="bp-pr__panel-head">
        <span className="bp-pr__panel-title">AUTHORITY THIS STAGE</span>
      </div>

      <AuthorityChip band={stage.band} size="sm" />

      <dl className="bp-pr__auth-list">
        <dt>who</dt>
        <dd>{spec.who}</dd>
        <dt>can</dt>
        <dd>{spec.may.join(" · ")}</dd>
        <dt>cannot</dt>
        <dd className="bp-pr__auth-cannot">{spec.mayNot.join(" · ")}</dd>
      </dl>

      <p className="bp-pr__auth-note">{stage.authorityNote}</p>
    </div>
  );
}

/* ------------------------------------------------------------- the shell */

export function ProtocolShell() {
  const mobile = useMobileHero();
  const reduced = useReducedMotion();
  // Reduced motion does not disable stage tracking — it is not an animation,
  // it is which stage you are reading. Only the smooth scroll goes away, and
  // `scrollIntoView` below honours the preference through CSS.
  const { stage, trackRef, goTo } = useStageProgress(
    PROTOCOL_STAGES.length,
    true,
  );

  const current = PROTOCOL_STAGES[stage] ?? PROTOCOL_STAGES[0]!;
  const rows = evidenceThrough(current.id);

  return (
    <div className="bp-pr" data-mobile={mobile ? "" : undefined}>
      <header className="bp-pr__intro">
        <div className="bp-pr__intro-inner">
          <p className="bp-eyebrow">How it works</p>
          <h1 className="bp-display bp-pr__title">
            One run, nine stages, <br />
            and one place authority moves.
          </h1>
          <p className="bp-lead bp-pr__lead">
            Below is a single BRANCHPOINT run — {RUN_ID} — from the first metric
            to the final verification. The example never resets and the evidence
            never clears, so every conclusion on this page can be traced back to
            the observation that produced it.
          </p>
          <div className="bp-pr__intro-ctas">
            <Link className="bp-cta bp-cta--primary" to="/runs">
              SEE LIVE DEMO
            </Link>
            <Link className="bp-cta bp-cta--ghost" to="/">
              BACK TO OVERVIEW
            </Link>
          </div>
        </div>
      </header>

      {/* Mobile: the two things a reader must never lose, always on screen. */}
      <div className="bp-pr__compact" aria-hidden="true">
        <span className="bp-pr__compact-num">
          {current.number} / 09
        </span>
        <span className="bp-pr__compact-name">{current.name}</span>
        <span className="bp-pr__compact-band">{current.band}</span>
      </div>

      <div className="bp-pr__layout">
        <div className="bp-pr__rail-col">
          <StageRail current={stage} onGo={goTo} />
        </div>

        <div className="bp-pr__viewport" ref={trackRef}>
          {PROTOCOL_STAGES.map((entry, index) => {
            const rowsHere = evidenceThrough(entry.id);
            return (
              <section
                key={entry.id}
                className="bp-stg"
                data-stage={index}
                data-active={index === stage ? "" : undefined}
                data-reduced={reduced ? "" : undefined}
                aria-labelledby={`bp-stg-${entry.id}`}
              >
                <header className="bp-stg__head">
                  <span className="bp-stg__num">
                    {entry.number} / 09
                  </span>
                  <h2 className="bp-stg__name" id={`bp-stg-${entry.id}`}>
                    {entry.name}
                  </h2>
                  <AuthorityChip band={entry.band} size="sm" />
                </header>

                <p className="bp-stg__thesis">{entry.thesis}</p>
                <p className="bp-stg__viewport-note">{entry.viewport}</p>

                <StageViewport id={entry.id} />

                <p className="bp-stg__transition">
                  <span className="bp-stg__transition-kind">NEXT</span>
                  {entry.transition}
                </p>

                {/*
                  The phone has no sticky inspector, so each stage carries its
                  own evidence and authority blocks inline. On desktop these are
                  hidden — the sticky inspector is showing the same rows.
                */}
                <div className="bp-stg__inline">
                  <EvidencePanel rows={rowsHere} />
                  <AuthorityPanel stageIndex={index} />
                </div>

                {index < PROTOCOL_STAGES.length - 1 ? (
                  <button
                    type="button"
                    className="bp-stg__next"
                    onClick={() => goTo(index + 1)}
                  >
                    <span aria-hidden="true">▼</span> NEXT STAGE ·{" "}
                    {PROTOCOL_STAGES[index + 1]!.name}
                  </button>
                ) : (
                  <div className="bp-stg__end">
                    <Link className="bp-cta bp-cta--primary" to="/runs">
                      SEE LIVE DEMO
                    </Link>
                    <Link className="bp-cta bp-cta--ghost" to="/">
                      BACK TO OVERVIEW
                    </Link>
                  </div>
                )}
              </section>
            );
          })}
        </div>

        <div className="bp-pr__inspector-col">
          <div className="bp-pr__inspector">
            <p className="bp-pr__inspector-run">
              {RUN_ID} · stage {current.number} / 09
            </p>
            <EvidencePanel rows={rows} />
            <AuthorityPanel stageIndex={stage} />
          </div>
        </div>
      </div>
    </div>
  );
}
