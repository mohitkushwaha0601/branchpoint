/**
 * The fork itself: one production twin on the left, three isolated worlds on
 * the right, and the branches that connect them.
 *
 * Purely presentational — it takes an act index and draws that act. All of the
 * meaning it carries visually is also stated as text by `ManyworldsSection`, so
 * this whole subtree is `aria-hidden`.
 *
 * The branches are drawn with `stroke-dashoffset`, which is the one honest way
 * to animate a path being *drawn* rather than faded in. Each path sets its own
 * dash length via a CSS custom property so a single rule can drive all three.
 */

import { ACT } from "./acts";

/**
 * Geometry in source units; the SVG scales to its box.
 *
 * Lane boxes are 112 tall and the last one must clear the viewBox: 290 + 112
 * plus the 6-unit isolation ring lands at 408, inside the 440 height. Getting
 * this wrong clips the bottom lane's cost line, which is the one number γ's
 * whole argument rests on.
 *
 * Every branch leaves the twin at y=216, the vertical centre of both the twin
 * and the middle lane.
 */
const VIEW_H = 440;
const LANE_H = 112;
const LANES = [
  { id: "alpha", glyph: "α", y: 30, path: "M 246 216 C 344 216, 354 86, 452 86" },
  { id: "beta", glyph: "β", y: 160, path: "M 246 216 C 344 216, 354 216, 452 216" },
  { id: "gamma", glyph: "γ", y: 290, path: "M 246 216 C 344 216, 354 346, 452 346" },
] as const;

type LaneTone = "pending" | "running" | "ok" | "fail" | "weak";

export interface LaneState {
  readonly id: string;
  readonly glyph: string;
  readonly action: string;
  readonly primary: string;
  readonly secondary: string;
  readonly status: string;
  readonly tone: LaneTone;
}

export function ForkScene({
  act,
  lanes,
}: {
  act: number;
  lanes: readonly LaneState[];
}) {
  const forked = act >= ACT.FORK;

  return (
    <svg
      className="bp-fork"
      viewBox={`0 0 980 ${VIEW_H}`}
      preserveAspectRatio="xMidYMid meet"
      aria-hidden="true"
      focusable="false"
    >
      {/* branches — drawn at FORK, then held */}
      <g className="bp-fork__branches" data-drawn={forked ? "" : undefined}>
        {LANES.map((lane) => (
          <path
            key={lane.id}
            className="bp-fork__branch"
            d={lane.path}
            data-lane={lane.id}
          />
        ))}
      </g>

      {/* production twin */}
      <g
        className="bp-fork__twin"
        data-state={forked ? "forked" : "whole"}
      >
        <rect x="40" y="152" width="206" height="128" rx="4" />
        <text className="bp-fork__kind" x="60" y="180">
          PRODUCTION TWIN
        </text>
        <text className="bp-fork__twin-main" x="60" y="215">
          v2.41
        </text>
        <text className="bp-fork__twin-sub" x="60" y="240">
          PRICING_V2 on · 4 replicas
        </text>
        <text className="bp-fork__twin-sub" x="60" y="261">
          41.3% error · 4.8s p95
        </text>
      </g>

      {/* the three worlds */}
      {LANES.map((lane, index) => {
        const state = lanes[index];
        if (state === undefined) return null;
        return (
          <g
            key={lane.id}
            className="bp-fork__world"
            data-visible={forked ? "" : undefined}
            data-tone={state.tone}
            style={{ ["--i" as string]: String(index) }}
          >
            <rect x="452" y={lane.y} width="488" height={LANE_H} rx="4" />
            {/* isolation ring — the world is a sealed snapshot, and this is the
                only visual that says so */}
            <rect
              className="bp-fork__ring"
              x="446"
              y={lane.y - 6}
              width="500"
              height={LANE_H + 12}
              rx="6"
              data-on={act >= ACT.EXECUTE ? "" : undefined}
            />
            <text className="bp-fork__glyph" x="476" y={lane.y + 44}>
              {state.glyph}
            </text>
            <text className="bp-fork__action" x="516" y={lane.y + 30}>
              {state.action}
            </text>
            <text className="bp-fork__primary" x="516" y={lane.y + 62}>
              {state.primary}
            </text>
            <text className="bp-fork__secondary" x="516" y={lane.y + 84}>
              {state.secondary}
            </text>
            <text
              className="bp-fork__status"
              x="920"
              y={lane.y + 62}
              textAnchor="end"
            >
              {state.status}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
