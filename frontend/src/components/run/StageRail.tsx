/**
 * The nine-stage pipeline, read left to right like a CI run's stage bar.
 *
 * The current stage — approval — is the only animated element in the product,
 * and its animation is suppressed under `prefers-reduced-motion`. It is also
 * marked `aria-current="step"`, so the "you are here" signal survives with no
 * colour and no motion at all.
 */

import { Fragment } from "react";

import type { Stage } from "../../types/run";
import { StatusIcon, stageDescriptor } from "./StatusBadge";

const TEXT_BY_STATUS = {
  complete: "text-fg-dim",
  current: "text-gate",
  pending: "text-fg-faint",
  failed: "text-fail",
} as const;

export function StageRail({ stages }: { stages: Stage[] }) {
  return (
    <nav
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
