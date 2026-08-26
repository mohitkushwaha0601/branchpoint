/**
 * The wires of the branch graph, drawn as one SVG overlay.
 *
 * Geometry is measured from the laid-out DOM rather than assumed, so lanes can
 * grow with their content and the connectors still meet them. No graph library
 * is involved: three cubic paths out of the fork, one down the trunk.
 */

export interface Point {
  x: number;
  y: number;
}

export interface LaneGeometry {
  worldId: string;
  /** Where the branch meets the lane. */
  entry: Point;
  /** Where the branch terminates, at the verdict node. */
  exit: Point;
}

export interface GraphGeometry {
  width: number;
  height: number;
  fork: Point;
  lanes: LaneGeometry[];
  /** Present only for the branch that continues toward approval. */
  merge: { worldId: string; from: Point; to: Point } | null;
}

export type ConnectorTone = "ok" | "fail" | "muted";

const STROKE: Record<ConnectorTone, string> = {
  ok: "var(--success)",
  fail: "var(--failure)",
  muted: "var(--border)",
};

/** Elbow-then-curve, the shape a commit graph uses to fan out. */
function branchPath(from: Point, to: Point): string {
  const runOut = Math.min(26, Math.max(8, (to.x - from.x) * 0.3));
  const startX = from.x + runOut;
  const control = Math.max(12, (to.x - startX) * 0.55);
  if (Math.abs(to.y - from.y) < 1) {
    return `M ${from.x} ${from.y} L ${to.x} ${to.y}`;
  }
  return [
    `M ${from.x} ${from.y}`,
    `L ${startX} ${from.y}`,
    `C ${startX + control} ${from.y} ${to.x - control} ${to.y} ${to.x} ${to.y}`,
  ].join(" ");
}

/**
 * Drops out of the winning verdict node and merges back onto the trunk.
 *
 * Orthogonal with rounded corners rather than one long diagonal: a right-angle
 * turn reads as a graph edge, a diagonal sweep across three lanes reads as a
 * stray line.
 */
function mergePath(from: Point, to: Point): string {
  const r = 10;
  const laneY = to.y - 22;
  const goingLeft = to.x < from.x;
  const turn = goingLeft ? -r : r;
  return [
    `M ${from.x} ${from.y}`,
    `L ${from.x} ${laneY - r}`,
    `Q ${from.x} ${laneY} ${from.x + turn} ${laneY}`,
    `L ${to.x - turn} ${laneY}`,
    `Q ${to.x} ${laneY} ${to.x} ${laneY + r}`,
    `L ${to.x} ${to.y}`,
  ].join(" ");
}

export function BranchConnector({
  geometry,
  activeWorldId,
  toneForWorld,
}: {
  geometry: GraphGeometry;
  /** Selected or hovered world — its wire is drawn bright, the rest recede. */
  activeWorldId: string | null;
  toneForWorld: (worldId: string) => ConnectorTone;
}) {
  // jsdom and the first paint both report a zero-size box. Nothing useful can
  // be drawn from that, and a degenerate path is worse than no path.
  if (geometry.width <= 0 || geometry.height <= 0) return null;

  return (
    <svg
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 h-full w-full"
      width={geometry.width}
      height={geometry.height}
      viewBox={`0 0 ${geometry.width} ${geometry.height}`}
      fill="none"
    >
      {geometry.lanes.map((lane) => {
        const active = lane.worldId === activeWorldId;
        return (
          <path
            key={lane.worldId}
            d={branchPath(geometry.fork, lane.entry)}
            stroke={active ? STROKE[toneForWorld(lane.worldId)] : "var(--border)"}
            strokeWidth={active ? 2 : 1.5}
            strokeLinecap="round"
            opacity={active ? 1 : 0.75}
          />
        );
      })}

      {geometry.merge ? (
        <path
          d={mergePath(geometry.merge.from, geometry.merge.to)}
          stroke="var(--success)"
          strokeWidth={2}
          strokeLinecap="round"
          strokeDasharray="1 0"
        />
      ) : null}

      <circle
        cx={geometry.fork.x}
        cy={geometry.fork.y}
        r={5}
        fill="var(--bg)"
        stroke="var(--running)"
        strokeWidth={2}
      />
    </svg>
  );
}
