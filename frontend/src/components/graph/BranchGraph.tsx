/**
 * The main visual: one fork, three branches, one trunk continuing to approval.
 *
 * Content is CSS Grid; the wires are a measured SVG overlay. The layout runs
 * fork ─ lane ─ verdict across three columns, so the vetoed branches visibly
 * stop at their verdict node while the recommended one carries on downward.
 */

import { GitFork, ListOrdered, Star } from "lucide-react";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import { useRunView } from "../../app/runView";
import type { World } from "../../types/run";
import {
  BranchConnector,
  type ConnectorTone,
  type GraphGeometry,
} from "./BranchConnector";
import { VerdictNode } from "./VerdictNode";
import { WorldLane } from "./WorldLane";

const EMPTY_GEOMETRY: GraphGeometry = {
  width: 0,
  height: 0,
  fork: { x: 0, y: 0 },
  lanes: [],
  merge: null,
};

function toneFor(world: World | undefined): ConnectorTone {
  if (world === undefined) return "muted";
  return world.verdict === "VETOED" ? "fail" : "ok";
}

export function BranchGraph() {
  const {
    run,
    selectedWorldId,
    selectedStageId,
    hoveredWorldId,
    selectWorld,
    selectStage,
    setHoveredWorldId,
  } = useRunView();

  const containerRef = useRef<HTMLDivElement>(null);
  const forkRef = useRef<HTMLDivElement>(null);
  const trunkRef = useRef<HTMLDivElement>(null);
  const laneRefs = useRef(new Map<string, HTMLDivElement>());
  const verdictRefs = useRef(new Map<string, HTMLDivElement>());
  const [geometry, setGeometry] = useState<GraphGeometry>(EMPTY_GEOMETRY);

  const measure = useCallback(() => {
    const container = containerRef.current;
    const fork = forkRef.current;
    if (container === null || fork === null) return;

    const base = container.getBoundingClientRect();
    if (base.width === 0) return;

    const centerOf = (el: Element) => {
      const box = el.getBoundingClientRect();
      return {
        x: box.left - base.left + box.width / 2,
        y: box.top - base.top + box.height / 2,
      };
    };

    const forkBox = fork.getBoundingClientRect();
    const forkPoint = {
      x: forkBox.right - base.left,
      y: forkBox.top - base.top + forkBox.height / 2,
    };

    const lanes = run.worlds.flatMap((world) => {
      const laneEl = laneRefs.current.get(world.worldId);
      const verdictEl = verdictRefs.current.get(world.worldId);
      if (laneEl === undefined || verdictEl === undefined) return [];
      const laneBox = laneEl.getBoundingClientRect();
      return [
        {
          worldId: world.worldId,
          entry: {
            x: laneBox.left - base.left,
            y: laneBox.top - base.top + laneBox.height / 2,
          },
          exit: centerOf(verdictEl),
        },
      ];
    });

    const recommendedId = run.comparison.recommendedWorldId;
    const winner = lanes.find((lane) => lane.worldId === recommendedId);
    const trunk = trunkRef.current;
    const merge =
      winner !== undefined && trunk !== null && recommendedId !== null
        ? {
            worldId: recommendedId,
            from: winner.exit,
            to: (() => {
              const box = trunk.getBoundingClientRect();
              return { x: box.left - base.left + 20, y: box.top - base.top };
            })(),
          }
        : null;

    setGeometry({
      width: base.width,
      height: base.height,
      fork: forkPoint,
      lanes,
      merge,
    });
  }, [run]);

  useLayoutEffect(measure, [measure]);

  useEffect(() => {
    const container = containerRef.current;
    if (container === null || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(container);
    for (const el of laneRefs.current.values()) observer.observe(el);
    return () => observer.disconnect();
  }, [measure]);

  const activeWorldId = hoveredWorldId ?? selectedWorldId;
  const worldById = (id: string) => run.worlds.find((w) => w.worldId === id);
  const recommended = worldById(run.comparison.recommendedWorldId ?? "");

  // A run is watchable from the moment it is created. Before it forks there is
  // no graph to draw, so the trunk says what it is waiting for instead of
  // rendering an empty fan.
  if (run.worlds.length === 0) {
    return (
      <div className="px-5 py-5">
        <h2 className="mb-3 flex items-center gap-2 font-mono text-[10px] font-semibold tracking-[0.14em] text-fg-faint">
          <GitFork className="h-3.5 w-3.5" aria-hidden="true" />
          COUNTERFACTUAL BRANCHES
        </h2>
        <div className="flex items-center gap-3 rounded-panel border border-edge bg-surface px-4 py-3">
          <span className="h-2 w-2 shrink-0 rounded-full bg-run bp-pulse" aria-hidden="true" />
          <p className="text-[12px] text-fg-dim">
            Waiting for worlds…
            <span className="ml-2 text-fg-faint">
              branches appear as BRANCHPOINT forks them.
            </span>
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="px-5 py-5">
      <h2 className="mb-3 flex items-center gap-2 font-mono text-[10px] font-semibold tracking-[0.14em] text-fg-faint">
        <GitFork className="h-3.5 w-3.5" aria-hidden="true" />
        COUNTERFACTUAL BRANCHES
      </h2>

      <div ref={containerRef} className="relative">
        <BranchConnector
          geometry={geometry}
          activeWorldId={activeWorldId}
          toneForWorld={(id) => toneFor(worldById(id))}
        />

        <div className="grid grid-cols-[92px_minmax(0,1fr)_auto] items-center gap-x-4 gap-y-3">
          <div
            ref={forkRef}
            // Rows here are implicit (each world renders through `contents`),
            // and `row-span-full` resolves against the *explicit* grid — it
            // would pin the fork to row 1 and skew the fan. Spelling the span
            // out keeps the fork centred on the lanes it feeds.
            style={{ gridRow: `1 / ${run.worlds.length + 1}` }}
            className="col-start-1 self-center justify-self-start"
          >
            <div className="flex flex-col items-start gap-1.5">
              <span className="rounded-md border border-run-dim bg-run/10 px-2 py-1 font-mono text-[10px] font-semibold tracking-[0.1em] text-run">
                FORK
              </span>
              <span className="font-mono text-[10px] text-fg-faint">
                {run.worlds.length} worlds
              </span>
            </div>
          </div>

          {run.worlds.map((world) => (
            <div
              key={world.worldId}
              className="contents"
              data-world-id={world.worldId}
            >
              <div
                ref={(el) => {
                  if (el) laneRefs.current.set(world.worldId, el);
                  else laneRefs.current.delete(world.worldId);
                }}
                className="col-start-2 min-w-0"
              >
                <WorldLane
                  world={world}
                  selected={world.worldId === selectedWorldId}
                  active={world.worldId === activeWorldId}
                  selectedStageId={
                    world.worldId === selectedWorldId ? selectedStageId : null
                  }
                  onSelectWorld={() => selectWorld(world.worldId)}
                  onSelectStage={(stageId) =>
                    selectStage(world.worldId, stageId)
                  }
                  onHoverChange={(hovered) =>
                    setHoveredWorldId(hovered ? world.worldId : null)
                  }
                />
              </div>
              <div
                ref={(el) => {
                  if (el) verdictRefs.current.set(world.worldId, el);
                  else verdictRefs.current.delete(world.worldId);
                }}
                className="col-start-3 self-center"
              >
                <VerdictNode
                  verdict={world.verdict}
                  recommended={world.recommended}
                  active={world.worldId === activeWorldId}
                />
              </div>
            </div>
          ))}
        </div>

        <div className="mt-4 pl-[92px]">
          <div ref={trunkRef} className="flex w-fit flex-col gap-2">
            {recommended === undefined ? (
              <span className="inline-flex w-fit items-center gap-2.5 rounded-md border border-edge bg-surface px-2.5 py-1.5 text-fg-faint">
                <ListOrdered className="h-3.5 w-3.5" aria-hidden="true" />
                <span className="font-mono text-[10px] font-semibold tracking-[0.1em]">
                  COMPARATOR
                </span>
                <span className="text-[12px]">Waiting for comparison…</span>
              </span>
            ) : (
              <>
                <TrunkNode
                  icon={<ListOrdered className="h-3.5 w-3.5" aria-hidden="true" />}
                  label="COMPARATOR"
                  detail={run.comparison.summary || "Deterministic ranking complete."}
                />
                <TrunkNode
                  icon={<Star className="h-3.5 w-3.5" aria-hidden="true" />}
                  label="RECOMMENDED"
                  detail={recommended.name}
                  emphasis
                />
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function TrunkNode({
  icon,
  label,
  detail,
  emphasis = false,
}: {
  icon: React.ReactNode;
  label: string;
  detail: string;
  emphasis?: boolean;
}) {
  return (
    <div
      className={`inline-flex w-fit items-center gap-2.5 rounded-md border px-2.5 py-1.5 ${
        emphasis
          ? "border-ok-dim bg-ok/10 text-ok"
          : "border-edge bg-surface text-fg-dim"
      }`}
    >
      {icon}
      <span className="font-mono text-[10px] font-semibold tracking-[0.1em]">
        {label}
      </span>
      <span
        className={`text-[12px] ${emphasis ? "text-fg" : "text-fg-faint"}`}
      >
        {detail}
      </span>
    </div>
  );
}
