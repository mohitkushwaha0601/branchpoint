/**
 * One job row inside a world, in the shape a CI log renders them:
 * glyph, label, duration. Clickable and keyboard-operable — activating a row
 * points the inspector at that step.
 */

import type { PipelineStage } from "../../types/run";
import { StatusIcon, pipelineDescriptor } from "../run/StatusBadge";

export function PipelineNode({
  stage,
  selected,
  onSelect,
  onFocusChange,
}: {
  stage: PipelineStage;
  selected: boolean;
  onSelect: () => void;
  onFocusChange: (focused: boolean) => void;
}) {
  const descriptor = pipelineDescriptor(stage.status);
  return (
    <button
      type="button"
      onClick={(event) => {
        // The lane behind this row also selects on click. Without this the
        // bubbled click would re-select the world and clear the step that was
        // just chosen.
        event.stopPropagation();
        onSelect();
      }}
      onFocus={() => onFocusChange(true)}
      onBlur={() => onFocusChange(false)}
      aria-pressed={selected}
      className={`flex w-full items-center gap-2 rounded-md border px-1.5 py-[3px] text-left transition-colors ${
        selected
          ? "border-edge bg-raised"
          : "border-transparent hover:border-edge-muted hover:bg-raised/60"
      }`}
    >
      <StatusIcon descriptor={descriptor} />
      <span
        className={`flex-1 truncate text-[12px] ${
          stage.status === "failed" ? "text-fg" : "text-fg-dim"
        }`}
      >
        {stage.label}
      </span>
      {stage.duration ? (
        <span className="font-mono text-[11px] tabular-nums text-fg-faint">
          {stage.duration}
        </span>
      ) : null}
    </button>
  );
}
