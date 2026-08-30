/**
 * A world's verdict and, separately, where it landed in the comparison.
 *
 * Deliberately two chips and not one. `SURVIVED` is a safety result and
 * `RECOMMENDED` is a quality result; γ is `SURVIVED` and still loses. Fusing
 * them into a single green "winner" badge would contradict the comparison
 * section, which is the trap the blueprint calls out by name.
 */

import type { Selection, Verdict } from "../../data/canonicalIncident";

const MARK: Record<Verdict, string> = {
  SURVIVED: "■",
  VETOED: "■",
  INCONCLUSIVE: "░",
};

export function VerdictChip({ verdict }: { verdict: Verdict }) {
  return (
    <span className="bp-verdict" data-verdict={verdict}>
      <span className="bp-verdict__mark" aria-hidden="true">
        {MARK[verdict]}
      </span>
      {verdict}
    </span>
  );
}

const SELECTION_LABEL: Record<Selection, string> = {
  RECOMMENDED: "RECOMMENDED",
  NOT_SELECTED: "NOT SELECTED",
  DISQUALIFIED: "DISQUALIFIED BEFORE RANKING",
};

export function SelectionChip({ selection }: { selection: Selection }) {
  return (
    <span className="bp-selection" data-selection={selection}>
      {SELECTION_LABEL[selection]}
    </span>
  );
}
