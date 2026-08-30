/**
 * Section 08 — AUTHORITY ARCHITECTURE.
 *
 * Section 04 argued the boundary; this states it. Six components, and for each
 * one three lines: what it does, what authority it holds, and what authority it
 * explicitly does not hold. The third line is the section — a diagram that only
 * says what things *can* do is an architecture diagram, and this is a security
 * one.
 *
 * ## Every node is a button
 *
 * Hover is never the only path. The topology is an inline SVG for the lines,
 * but the nodes themselves are real `<button>` elements laid over it, so the
 * whole map is tab-navigable, tappable at 44 px, and works with no pointer at
 * all. The SVG is `aria-hidden`; the buttons carry the names.
 */

import { useState } from "react";

import { ARCHITECTURE_NODES } from "../../../data/canonicalIncident";
import { AuthorityChip } from "../AuthorityChip";

export function AuthorityArchitecture() {
  const [activeId, setActiveId] = useState(ARCHITECTURE_NODES[2]!.id);
  const active =
    ARCHITECTURE_NODES.find((node) => node.id === activeId) ??
    ARCHITECTURE_NODES[0]!;

  return (
    <section className="bp-sec bp-sec--arch" aria-labelledby="bp-arch-title">
      <div className="bp-sec__inner">
        <p className="bp-eyebrow">08 — Authority architecture</p>
        <h2 id="bp-arch-title" className="bp-sec__title">
          Who is allowed to be sure.
        </h2>
        <p className="bp-lead bp-sec__lead">
          Six components, three bands of authority, and one rule: nothing may
          conclude more than it can prove. Select any component to see what it is
          not permitted to do.
        </p>

        <div className="bp-arch__layout">
          <div className="bp-arch__map">
            {/* Lines only. Everything nameable is a real control below. */}
            <svg
              className="bp-arch__lines"
              viewBox="0 0 100 260"
              preserveAspectRatio="none"
              aria-hidden="true"
            >
              <path className="bp-arch__line" d="M50 26 V52" />
              <path className="bp-arch__line" d="M50 78 V104" />
              <path className="bp-arch__line" d="M50 130 V156" />
              <path className="bp-arch__line" d="M50 182 V208" />
              <path className="bp-arch__line" d="M50 234 V252" />
            </svg>

            <ul className="bp-arch__nodes">
              {ARCHITECTURE_NODES.map((node) => {
                const on = node.id === active.id;
                return (
                  <li key={node.id}>
                    <button
                      type="button"
                      className="bp-arch__node"
                      data-band={node.band}
                      data-on={on ? "" : undefined}
                      aria-pressed={on}
                      onClick={() => setActiveId(node.id)}
                      onFocus={() => setActiveId(node.id)}
                      onMouseEnter={() => setActiveId(node.id)}
                    >
                      <span className="bp-arch__node-name">{node.label}</span>
                      <span className="bp-arch__node-band">{node.band}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>

          {/* Fixed min-height: swapping panels must never move the map. */}
          <div className="bp-arch__panel">
            <header className="bp-arch__panel-head">
              <h3 className="bp-arch__panel-title">{active.label}</h3>
              <AuthorityChip band={active.band} size="sm" />
            </header>

            <dl className="bp-arch__panel-list">
              <dt>does</dt>
              <dd>{active.does}</dd>
              <dt>holds</dt>
              <dd>{active.holds}</dd>
              <dt className="bp-arch__negative">does not hold</dt>
              <dd className="bp-arch__negative">{active.lacks}</dd>
            </dl>

            {active.fact === undefined ? null : (
              <p className="bp-arch__fact">{active.fact}</p>
            )}
          </div>
        </div>

        {/*
          The map is a selector, so only one node's text is on screen at a time.
          This is all six, always present, never announced — the section has to
          be readable by someone who never operates it.
        */}
        <div className="sr-only">
          <h3>Every component and its authority</h3>
          <dl>
            {ARCHITECTURE_NODES.map((node) => (
              <div key={node.id}>
                <dt>
                  {node.label} — {node.band}
                </dt>
                <dd>
                  Does: {node.does} Holds: {node.holds} Does not hold:{" "}
                  {node.lacks}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      </div>
    </section>
  );
}
