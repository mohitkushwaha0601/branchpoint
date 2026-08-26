/**
 * The nine-stage pipeline, read left to right like a CI run's stage bar.
 *
 * The current stage — approval — is the only animated element in the product,
 * and its animation is suppressed under `prefers-reduced-motion`. It is also
 * marked `aria-current="step"`, so the "you are here" signal survives with no
 * colour and no motion at all.
 */

import { Fragment, useEffect, useRef } from "react";

import type { Stage } from "../../types/run";
import { StatusIcon, stageDescriptor } from "./StatusBadge";

const TEXT_BY_STATUS = {
  complete: "text-fg-dim",
  current: "text-gate",
  pending: "text-fg-faint",
  failed: "text-fail",
} as const;

export function StageRail({ stages }: { stages: Stage[] }) {
  const railRef = useRef<HTMLElement>(null);
  const currentStageId = stages.find((stage) => stage.status === "current")?.id;
  // The rail scrolls horizontally and hides its scrollbar, so when the panes
  // narrow it (an Inspector docked at 1024 clips COMMIT and VERIFY) there is no
  // affordance saying more stages exist. Keeping the current stage in view as
  // the run advances is the behaviour that actually matters: the rail follows
  // the run instead of stranding the reader at OBSERVE.
  useEffect(() => {
    const rail = railRef.current;
    if (rail === null || currentStageId === undefined) return;
    const node = rail.querySelector('[aria-current="step"]');
    // Guarded because jsdom does not implement scrollIntoView, and a purely
    // cosmetic scroll must never be the thing that throws in a render pass.
    if (typeof node?.scrollIntoView === "function") {
      node.scrollIntoView({ block: "nearest", inline: "nearest" });
    }
  }, [currentStageId]);

  return (
    <nav
      ref={railRef}
      aria-label="Run stages"
      className="flex items-center overflow-x-auto border-b border-edge bg-surface px-5 py-1.5 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
    >
      {stages.map((stage, index) => {
        const descriptor = stageDescriptor(stage.status);
        const current = stage.status === "current";
        return (
          <Fragment key={stage.id}>
            {index > 0 ? (
              <span
                aria-hidden="true"
                className={`h-px w-3 shrink-0 ${
                  stage.status === "pending" ? "bg-edge-muted" : "bg-edge"
                }`}
              />
            ) : null}
            <span
              aria-current={current ? "step" : undefined}
              title={stage.detail ? `${stage.label} — ${stage.detail}` : stage.label}
              className={`flex shrink-0 items-center gap-1 rounded-md border px-1.5 py-0.5 whitespace-nowrap ${
                current
                  ? "border-gate-dim bg-gate/10"
                  : "border-transparent bg-transparent"
              }`}
            >
              <span className={current ? "bp-pulse" : undefined}>
                <StatusIcon descriptor={descriptor} />
              </span>
              <span
                className={`font-mono text-[10px] font-semibold tracking-[0.06em] ${TEXT_BY_STATUS[stage.status]}`}
              >
                {stage.label.toUpperCase()}
              </span>
              {stage.detail ? (
                <span
                  className={`font-mono text-[10px] text-fg-faint ${
                    current ? "" : "hidden 2xl:inline"
                  }`}
                >
                  {stage.detail}
                </span>
              ) : null}
            </span>
          </Fragment>
        );
      })}
    </nav>
  );
}
