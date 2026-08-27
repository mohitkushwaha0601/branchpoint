/**
 * Section 03 — WORLD EXPLORER.
 *
 * A real tablist over three worlds, not three cards side by side. The cards
 * version was rejected on purpose: three equal boxes imply three comparable
 * things, and the single most informative fact about this run is that the three
 * worlds are *not* comparable in shape. α's verdict rests on three pieces of
 * evidence, β's on six, γ's on four. A grid would flatten that into decoration.
 *
 * The tablist also buys the reader a choice. Section 02 told them what happened;
 * this is the first surface where they can go and check.
 */

import { useRef, useState } from "react";

import {
  EVIDENCE_NOTE,
  WORLDS,
  evidenceFor,
  supersededFor,
  type CanonicalWorld,
} from "../../../data/canonicalIncident";
import { useReducedMotion } from "../../hero/heroMedia";
import { SelectionChip, VerdictChip } from "../VerdictChip";
import { EvidenceList } from "./EvidenceList";

function tabId(world: CanonicalWorld) {
  return `bp-wtab-${world.id}`;
}

/**
 * One panel, not three.
 *
 * Only the selected world's pane is rendered, so per-world panel ids would make
 * two of the three tabs point `aria-controls` at an element that does not
 * exist — a dangling reference that assistive technology has no way to follow.
 * A single-panel tablist is the standard shape for exactly this case: every tab
 * controls the one pane, and the pane names the active tab back.
 */
const PANEL_ID = "bp-wx-panel";

/** The action and the four measured outcomes for one world. */
function WorldPlates({ world }: { world: CanonicalWorld }) {
  const metrics = [
    world.metrics.errorRate,
    world.metrics.p95,
    world.metrics.affectedUsers,
    world.metrics.costDelta,
  ];

  return (
    <div className="bp-wx__left">
      <div className="bp-wx__action">
        <span className="bp-wx__action-kind">{world.action.kind}</span>
        <span className="bp-wx__action-body">
          {world.action.parameter} <span aria-hidden="true">·</span>{" "}
          {world.action.from} → {world.action.to}
        </span>
        <span className="bp-wx__action-target">on {world.action.target}</span>
      </div>

      <dl className="bp-wx__metrics">
        {metrics.map((metric) => (
          <div className="bp-wx__metric" key={metric.label}>
            <dt>{metric.label}</dt>
            <dd>{metric.value}</dd>
          </div>
        ))}
      </dl>

      <p className="bp-wx__regression" data-active={world.regressionActive ? "" : undefined}>
        {world.regressionActive
          ? "The regression is still active in this world: v2.41 is deployed and the flag still routes through it."
          : "The regression cannot run in this world."}
      </p>
    </div>
  );
}

export function WorldExplorer() {
  const [selected, setSelected] = useState(0);
  const reduced = useReducedMotion();
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);

  const world = WORLDS[selected] ?? WORLDS[0]!;
  const rows = evidenceFor(world.id);

  function focusTab(next: number) {
    const wrapped = (next + WORLDS.length) % WORLDS.length;
    setSelected(wrapped);
    tabRefs.current[wrapped]?.focus();
  }

  return (
    <section className="bp-sec bp-sec--wx" aria-labelledby="bp-wx-title">
      <div className="bp-sec__inner">
        <p className="bp-eyebrow">03 — World explorer</p>
        <h2 id="bp-wx-title" className="bp-sec__title">
          Three candidates. <br />
          One survives selection.
        </h2>
        <p className="bp-lead bp-sec__lead">
          Every world ran against its own sealed snapshot, and every world
          produced its own evidence. The three lists are different lengths
          because the three worlds are not the same shape — not because one was
          examined harder than another.
        </p>

        <div
          className="bp-wx__tabs"
          role="tablist"
          aria-label="Counterfactual worlds"
        >
          {WORLDS.map((entry, index) => {
            const active = index === selected;
            return (
              <button
                key={entry.id}
                ref={(node) => {
                  tabRefs.current[index] = node;
                }}
                type="button"
                role="tab"
                id={tabId(entry)}
                aria-selected={active}
                aria-controls={PANEL_ID}
                tabIndex={active ? 0 : -1}
                className="bp-wx__tab"
                data-active={active ? "" : undefined}
                data-verdict={entry.verdict}
                onClick={() => setSelected(index)}
                onKeyDown={(event) => {
                  if (event.key === "ArrowRight") {
                    event.preventDefault();
                    focusTab(index + 1);
                  } else if (event.key === "ArrowLeft") {
                    event.preventDefault();
                    focusTab(index - 1);
                  } else if (event.key === "Home") {
                    event.preventDefault();
                    focusTab(0);
                  } else if (event.key === "End") {
                    event.preventDefault();
                    focusTab(WORLDS.length - 1);
                  }
                }}
              >
                <span className="bp-wx__tab-glyph" aria-hidden="true">
                  {entry.glyph}
                </span>
                <span className="bp-wx__tab-name">{entry.shortName}</span>
                <span className="bp-wx__tab-count">
                  {evidenceFor(entry.id).length} evidence
                </span>
              </button>
            );
          })}
        </div>

        <div
          className="bp-wx__panel"
          role="tabpanel"
          id={PANEL_ID}
          aria-labelledby={tabId(world)}
          tabIndex={0}
          // Keyed on the world so the pane genuinely remounts: the evidence
          // list's own disclosure state should not survive a world change.
          key={world.id}
          data-reduced={reduced ? "" : undefined}
        >
          <div className="bp-wx__panel-head">
            <h3 className="bp-wx__panel-title">
              <span aria-hidden="true">{world.glyph}</span> {world.label} ·{" "}
              {world.shortName}
            </h3>
            <div className="bp-wx__chips">
              <VerdictChip verdict={world.verdict} />
              <SelectionChip selection={world.selection} />
            </div>
          </div>

          <p className="bp-wx__reason">{world.verdictReason}</p>

          <div className="bp-wx__body">
            <WorldPlates world={world} />
            <EvidenceList
              rows={rows}
              note={EVIDENCE_NOTE[world.id] ?? ""}
              superseded={supersededFor(world.id)}
            />
          </div>
        </div>

        <p className="bp-sec__kicker" data-tone="muted">
          γ survived. γ also lost. Those are different questions decided by
          different parts of the system, and the site never merges them: a world
          can miss the goal entirely and still be safe to ship.
        </p>
      </div>
    </section>
  );
}
