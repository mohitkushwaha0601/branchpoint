/**
 * Section 05 — DETERMINISTIC COMPARISON.
 *
 * The absence is the content. There is no score, no weighting and no confidence
 * anywhere in `WorldRanking`, so there is none here either: the rows are the
 * comparator's own field names and the values are what it computed. A progress
 * ring or a 0–100 gauge would silently contradict the product.
 *
 * α is present and struck through. Removing its column would lose the point —
 * that a world can be the best on every headline axis and still be removed
 * before ranking begins.
 *
 * ## Mobile
 *
 * A three-column matrix at 390 px is unreadable, so the table *transposes*: the
 * reader picks one world with a segmented control and the axes list down the
 * page. It stays a real `<table>` with a `<caption>` and `scope` attributes in
 * both orientations — a transposed matrix that stops being a table stops being
 * navigable by a screen reader.
 */

import { useState } from "react";

import {
  COMPARISON,
  COMPARISON_AXES,
  COMPARISON_VALUES,
  WORLDS,
} from "../../../data/canonicalIncident";
import { useMobileHero } from "../../hero/heroMedia";

type WorldKey = keyof typeof COMPARISON_VALUES;

const CAPTION =
  "Deterministic comparison of the three worlds on the comparator's own axes. No score is computed at any point.";

function AxisLabel({ field, explain }: { field: string; explain: string }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        className="bp-cmp__axis"
        aria-expanded={open}
        onClick={() => setOpen((prev) => !prev)}
      >
        <span className="bp-cmp__axis-name">{field}</span>
        <span className="bp-cmp__axis-hint" aria-hidden="true">
          {open ? "−" : "?"}
        </span>
      </button>
      {open ? <span className="bp-cmp__axis-explain">{explain}</span> : null}
    </>
  );
}

/** Desktop: worlds across the top, axes down the side. */
function Matrix() {
  return (
    <table className="bp-cmp__table">
      <caption>{CAPTION}</caption>
      <thead>
        <tr>
          <th scope="col">axis</th>
          {WORLDS.map((world) => (
            <th
              key={world.id}
              scope="col"
              data-rejected={world.verdict === "VETOED" ? "" : undefined}
            >
              <span className="bp-cmp__world">
                <span aria-hidden="true">{world.glyph}</span> {world.shortName}
              </span>
              {world.verdict === "VETOED" ? (
                <span className="bp-cmp__reject">
                  {COMPARISON.rejectionReason}
                </span>
              ) : null}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {COMPARISON_AXES.map((axis) => (
          <tr key={axis.key}>
            <th scope="row">
              <AxisLabel field={axis.field} explain={axis.explain} />
            </th>
            {WORLDS.map((world) => (
              <td
                key={world.id}
                className="bp-num"
                data-rejected={world.verdict === "VETOED" ? "" : undefined}
              >
                {COMPARISON_VALUES[world.id as WorldKey][axis.key]}
              </td>
            ))}
          </tr>
        ))}
        <tr className="bp-cmp__rank">
          <th scope="row">rank</th>
          {WORLDS.map((world) => (
            <td key={world.id} className="bp-num">
              {COMPARISON.ranks[world.id as WorldKey]}
              {world.id === COMPARISON.recommendedWorldId ? (
                <span className="bp-cmp__rec">RECOMMENDED</span>
              ) : null}
            </td>
          ))}
        </tr>
      </tbody>
    </table>
  );
}

/** Mobile: one world at a time, axes down the page. Still a table. */
function Transposed() {
  const [index, setIndex] = useState(1); // β, the world that wins
  const world = WORLDS[index] ?? WORLDS[0]!;
  const values = COMPARISON_VALUES[world.id as WorldKey];

  return (
    <>
      <div className="bp-seg bp-cmp__seg" role="radiogroup" aria-label="World">
        {WORLDS.map((entry, i) => {
          const active = i === index;
          return (
            <button
              key={entry.id}
              type="button"
              role="radio"
              aria-checked={active}
              tabIndex={active ? 0 : -1}
              className="bp-seg__option"
              data-active={active ? "" : undefined}
              onClick={() => setIndex(i)}
              onKeyDown={(event) => {
                if (event.key === "ArrowRight" || event.key === "ArrowDown") {
                  event.preventDefault();
                  setIndex((i + 1) % WORLDS.length);
                } else if (
                  event.key === "ArrowLeft" ||
                  event.key === "ArrowUp"
                ) {
                  event.preventDefault();
                  setIndex((i - 1 + WORLDS.length) % WORLDS.length);
                }
              }}
            >
              <span aria-hidden="true">{entry.glyph}</span> {entry.shortName}
            </button>
          );
        })}
      </div>

      {world.verdict === "VETOED" ? (
        <p className="bp-cmp__reject bp-cmp__reject--block">
          {COMPARISON.rejectionReason} — {COMPARISON.rejectedDetail}
        </p>
      ) : null}

      <table className="bp-cmp__table bp-cmp__table--transposed">
        <caption>
          {CAPTION} Showing {world.label}.
        </caption>
        <tbody>
          {COMPARISON_AXES.map((axis) => (
            <tr key={axis.key}>
              <th scope="row">{axis.field}</th>
              <td
                className="bp-num"
                data-rejected={world.verdict === "VETOED" ? "" : undefined}
              >
                {values[axis.key]}
              </td>
            </tr>
          ))}
          <tr className="bp-cmp__rank">
            <th scope="row">rank</th>
            <td className="bp-num">
              {COMPARISON.ranks[world.id as WorldKey]}
              {world.id === COMPARISON.recommendedWorldId ? (
                <span className="bp-cmp__rec">RECOMMENDED</span>
              ) : null}
            </td>
          </tr>
        </tbody>
      </table>

      <ul className="bp-cmp__explains">
        {COMPARISON_AXES.map((axis) => (
          <li key={axis.key}>
            <span className="bp-cmp__axis-name">{axis.field}</span>{" "}
            {axis.explain}
          </li>
        ))}
      </ul>
    </>
  );
}

export function ComparisonMatrix() {
  const mobile = useMobileHero();

  return (
    <section className="bp-sec bp-sec--cmp" aria-labelledby="bp-cmp-title">
      <div className="bp-sec__inner">
        <p className="bp-eyebrow">05 — Deterministic comparison</p>
        <h2 id="bp-cmp-title" className="bp-sec__title">
          No score. Arithmetic.
        </h2>
        <p className="bp-lead bp-sec__lead">
          α was removed before ranking began. What is left is a comparison on
          fields the comparator actually has — and it does not have a confidence
          number to give you.
        </p>

        <div className="bp-cmp__wrap">{mobile ? <Transposed /> : <Matrix />}</div>

        <p className="bp-cmp__foot">{COMPARISON.scoreNote}</p>
        <p className="bp-cmp__foot bp-cmp__foot--tie">{COMPARISON.tieNote}</p>

        <p className="bp-sec__kicker" data-tone="muted">
          A vetoed world is disqualified before ranking begins — so α&rsquo;s
          0.94 goal attainment and its $0 cost never compete with anything. That
          ordering is not a courtesy. It is what stops a good number from
          outvoting a reproduced failure.
        </p>
      </div>
    </section>
  );
}
