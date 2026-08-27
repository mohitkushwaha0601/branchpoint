/**
 * Section 02 — MANYWORLDS. The second hero moment.
 *
 * Five acts, driven by scroll position inside `.bp-marketing` (never the
 * window — see `useScrollActs`). Reality, then the fork, then isolated
 * execution, then outcomes, then the verdicts settling.
 *
 * ## Why outcomes and verdicts are separate acts
 *
 * At the outcomes act, α shows 1.8% / 190 ms — the best headline numbers on
 * screen — and carries no verdict yet. Only at the settle act does it turn red.
 * If the verdict arrived with the metrics, the reader would never experience
 * α looking like the right answer, and the whole argument of the page depends on
 * that experience. It costs one act.
 *
 * ## Where the sticky scene is not used
 *
 * Reduced motion and the phone layout both render every act as a static stack
 * instead. Nothing is behind the animation: each act's caption is real text in
 * an ordered list either way, and the world outcomes are a real table.
 */

import {
  INITIAL_REALITY,
  WORLDS,
  type CanonicalWorld,
} from "../../../data/canonicalIncident";
import { useMobileHero, useReducedMotion } from "../../hero/heroMedia";
import { useScrollActs } from "../useScrollActs";
import { ACT } from "./acts";
import { ForkScene, type LaneState } from "./ForkScene";

const ACTS = [
  {
    id: "reality",
    label: "Reality",
    caption: "One production system, one chance to be wrong.",
  },
  {
    id: "fork",
    label: "Fork",
    caption: "Three candidate actions become three separate worlds.",
  },
  {
    id: "execute",
    label: "Execute",
    caption:
      "Each world applies its action to its own sealed snapshot. Nothing here can reach production.",
  },
  {
    id: "outcomes",
    label: "Outcomes",
    caption: "Measured, not predicted. The rollback looks like the winner.",
  },
  {
    id: "settle",
    label: "Verdicts",
    caption: "Evidence decides. The fastest world is the one that cannot ship.",
  },
] as const;

function laneFor(world: CanonicalWorld, act: number): LaneState {
  const action = `${world.action.parameter} ${world.action.from} → ${world.action.to}`;

  if (act < ACT.EXECUTE) {
    return {
      id: world.id,
      glyph: world.glyph,
      action,
      primary: world.shortName,
      secondary: "",
      status: "",
      tone: "pending",
    };
  }

  if (act === ACT.EXECUTE) {
    return {
      id: world.id,
      glyph: world.glyph,
      action,
      primary: "Executing",
      secondary: "isolated snapshot",
      status: "···",
      tone: "running",
    };
  }

  const metrics = `${world.metrics.errorRate.value} error · ${world.metrics.p95.value} p95`;
  const cost =
    world.metrics.costDelta.raw > 0
      ? `${world.metrics.costDelta.value}`
      : "no new spend";

  // Outcomes act: numbers only, no verdicts. Alpha is allowed to look best.
  if (act === ACT.OUTCOMES) {
    return {
      id: world.id,
      glyph: world.glyph,
      action,
      primary: metrics,
      secondary: cost,
      status: "",
      tone: "pending",
    };
  }

  return {
    id: world.id,
    glyph: world.glyph,
    action,
    primary: metrics,
    secondary:
      world.id === "world_gamma"
        ? "root cause still deployed"
        : world.id === "world_alpha"
          ? "2 critical checks failed"
          : cost,
    status:
      world.selection === "RECOMMENDED"
        ? "SURVIVED · RECOMMENDED"
        : world.verdict === "VETOED"
          ? "VETOED"
          : "SURVIVED · NOT SELECTED",
    tone:
      world.verdict === "VETOED"
        ? "fail"
        : world.selection === "RECOMMENDED"
          ? "ok"
          : "weak",
  };
}

/**
 * The static presentation: every act, stacked.
 *
 * Not the desktop scene shrunk. The fork diagram is 980 units wide and its
 * labels would land at about five pixels on a phone; scaling it down produces
 * unreadable metrics, and letting it overflow produces a decorative diagram the
 * reader can only see half of. So on this layout the same act data is rendered
 * as type instead — the production twin, then one row per world showing exactly
 * what that act has revealed so far.
 *
 * `showWorlds` is what makes the fork legible without a picture: nothing is
 * listed until the act that actually forks.
 */
function StackedActs() {
  return (
    <ol className="bp-mw__stack">
      {ACTS.map((act, index) => {
        const showWorlds = index >= ACT.FORK;
        return (
          <li className="bp-mw__stack-item" key={act.id}>
            <p className="bp-eyebrow">
              {String(index + 1).padStart(2, "0")} — {act.label}
            </p>
            <p className="bp-mw__caption">{act.caption}</p>

            <div className="bp-mw__panel">
              {/* The twin is established once. Repeating it under every act
                  turns five beats into five copies of the same box. */}
              {showWorlds ? null : (
                <div className="bp-mw__twin">
                  <span className="bp-mw__twin-kind">Production twin</span>
                  <span className="bp-mw__twin-main">
                    {INITIAL_REALITY.version}
                  </span>
                  <span className="bp-mw__twin-sub">
                    {INITIAL_REALITY.flagKey} on · {INITIAL_REALITY.replicas}{" "}
                    replicas
                  </span>
                  <span className="bp-mw__twin-sub">
                    {INITIAL_REALITY.metrics.errorRate.value} error ·{" "}
                    {INITIAL_REALITY.metrics.p95.value} p95
                  </span>
                </div>
              )}

              {showWorlds ? (
                <ul className="bp-mw__lanes">
                  {WORLDS.map((world) => {
                    const lane = laneFor(world, index);
                    return (
                      <li
                        className="bp-mw__lane"
                        key={world.id}
                        data-tone={lane.tone}
                      >
                        <span className="bp-mw__lane-glyph">{lane.glyph}</span>
                        <span className="bp-mw__lane-body">
                          <span className="bp-mw__lane-action">
                            {lane.action}
                          </span>
                          <span className="bp-mw__lane-primary">
                            {lane.primary}
                          </span>
                          {lane.secondary === "" ? null : (
                            <span className="bp-mw__lane-secondary">
                              {lane.secondary}
                            </span>
                          )}
                        </span>
                        {lane.status === "" ? null : (
                          <span className="bp-mw__lane-status">
                            {lane.status}
                          </span>
                        )}
                      </li>
                    );
                  })}
                </ul>
              ) : null}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

export function ManyworldsSection() {
  const reduced = useReducedMotion();
  const mobile = useMobileHero();
  const animated = !reduced && !mobile;

  const { act, trackRef } = useScrollActs(ACTS.length, animated);
  const current = ACTS[act] ?? ACTS[ACTS.length - 1]!;
  const lanes = WORLDS.map((world) => laneFor(world, act));

  return (
    <section className="bp-sec bp-sec--mw" aria-labelledby="bp-mw-title">
      <div className="bp-sec__inner">
        <p className="bp-eyebrow">02 — Manyworlds</p>
        <h2 id="bp-mw-title" className="bp-sec__title">
          Don&rsquo;t predict what might happen. <br />
          Execute what could.
        </h2>
        <p className="bp-lead bp-sec__lead">
          BRANCHPOINT forks {INITIAL_REALITY.service} into one isolated world
          per candidate action and runs all three for real. The numbers below
          were measured, not estimated.
        </p>
      </div>

      {animated ? (
        <div className="bp-mw__track" ref={trackRef}>
          <div className="bp-mw__sticky">
            <div className="bp-sec__inner bp-mw__frame">
              {/* act rail — a progress indicator, not a stepper control */}
              <ol className="bp-mw__rail" aria-hidden="true">
                {ACTS.map((entry, index) => (
                  <li
                    key={entry.id}
                    className="bp-mw__rail-item"
                    data-state={
                      index === act ? "on" : index < act ? "done" : undefined
                    }
                  >
                    <span className="bp-mw__rail-num">
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    <span className="bp-mw__rail-label">{entry.label}</span>
                  </li>
                ))}
              </ol>

              <div className="bp-mw__stage">
                <ForkScene act={act} lanes={lanes} />
              </div>

              <p className="bp-mw__caption" data-act={act}>
                {current.caption}
              </p>
            </div>
          </div>

          {/* Scroll regions. Each is one act tall; whichever crosses the middle
              of the scroller is the active act. */}
          {ACTS.map((entry, index) => (
            <div
              key={entry.id}
              className="bp-mw__region"
              data-act={index}
              aria-hidden="true"
            />
          ))}

          {/* Holds the scene pinned after the final act has arrived. Without
              it the sticky frame releases within ~100px of the verdicts
              appearing, so the payoff slides away exactly as it lands. Carries
              no `data-act`, so the last act simply stays current. */}
          <div className="bp-mw__tail" aria-hidden="true" />
        </div>
      ) : (
        <div className="bp-sec__inner">
          <StackedActs />
        </div>
      )}

      {/*
        The scene is decorative in every mode. This is the run, as text: the
        same claims, always present, never announced, and true with no motion
        and no SVG at all.
      */}
      <div className="bp-sec__inner">
        <table className="bp-mw__table">
          <caption>
            Three counterfactual worlds, each executed against its own isolated
            snapshot of production.
          </caption>
          <thead>
            <tr>
              <th scope="col">World</th>
              <th scope="col">Action</th>
              <th scope="col">Checkout error</th>
              <th scope="col">p95</th>
              <th scope="col">Cost</th>
              <th scope="col">Outcome</th>
            </tr>
          </thead>
          <tbody>
            {WORLDS.map((world) => (
              <tr key={world.id} data-verdict={world.verdict}>
                <th scope="row">{world.label}</th>
                <td>
                  {world.action.parameter} {world.action.from} →{" "}
                  {world.action.to}
                </td>
                <td className="bp-num">{world.metrics.errorRate.value}</td>
                <td className="bp-num">{world.metrics.p95.value}</td>
                <td className="bp-num">{world.metrics.costDelta.value}</td>
                <td>
                  {world.verdict}
                  {world.selection === "RECOMMENDED" ? " · RECOMMENDED" : null}
                  {world.selection === "NOT_SELECTED"
                    ? " · NOT SELECTED"
                    : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        <p className="bp-sec__kicker" data-tone="muted">
          γ adds eight replicas and still cannot get below{" "}
          {WORLDS[2]?.metrics.errorRate.value}. The regression is v2.41&rsquo;s
          own code, and it is still deployed and still enabled — you cannot
          scale your way out of code that is still running.
        </p>
      </div>
    </section>
  );
}
