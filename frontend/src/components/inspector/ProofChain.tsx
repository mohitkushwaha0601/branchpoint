/**
 * Why BRANCHPOINT rejected an action, as a chain rather than a log.
 *
 * Four stages, each driven by a structured field and none by prose:
 *
 *   suspected      ← non-machine-verifiable evidence, branded DOPPELGÄNGER
 *                    only when `source` says so
 *   verified       ← machine-verifiable evidence the veto/counterexample
 *                    actually cites, not merely any that exists
 *   reproduced     ← counterexample.reproduced / .authoritative
 *   vetoed         ← world.veto
 *
 * `verdict_reason` is never read here. That is deliberate and load-bearing: the
 * whole point of the structured contract is that this panel cannot be fooled by
 * a summary string, and a test proves it by feeding in a nonsense one.
 *
 * A stage appears as *reached* only when the selected world actually holds the
 * data for it. A deterministic demo world has no DOPPELGÄNGER, so it is shown a
 * three-stage chain with the exploratory step explicitly not present — never a
 * fabricated one.
 */

import { ArrowDown, Check, CircleSlash, Diamond, Search, X } from "lucide-react";
import type { ComponentType } from "react";

import type {
  CounterexampleDto,
  EvidenceDto,
  WorldInspectionDto,
} from "../../api/types";
import { AuthorityBadge } from "../run/StatusBadge";

/** How far a stage got, which is not the same as whether it succeeded. */
type StageState =
  /** Happened, and counts toward the conclusion. */
  | "REACHED"
  /** Did not happen for this world. Stated, never implied. */
  | "ABSENT"
  /** Happened but carries no authority — a claim without qualifying evidence. */
  | "UNSUPPORTED";

interface Stage {
  key: string;
  title: string;
  state: StageState;
  /** The word under the title: EXPLORATORY, VERIFIED, REPRODUCED, VETOED. */
  verdict: string;
  detail: string;
  Icon: ComponentType<{ className?: string; strokeWidth?: number }>;
}

/**
 * Whether an evidence record actually came from the DOPPELGÄNGER.
 *
 * Branding is a claim about provenance, so it is read from `source` — the field
 * that states provenance — and never inferred from `machine_verifiable`. Plenty
 * of things are non-machine-verifiable without an adversarial agent having run:
 * a human note is exploratory too, and calling it DOPPELGÄNGER would invent an
 * agent that was never involved.
 *
 * The backend emits exactly one such source today
 * (`SANDBOX_EVIDENCE_SOURCE = "trueforge-doppelganger"`). Matching the marker
 * word rather than that exact string keeps a future `doppelganger-subagent`
 * correctly branded, while `manual-note`, `demo-world-executor`, and
 * `hero-adversarial-tester` stay out.
 */
function isDoppelgangerSource(source: string): boolean {
  return source.toLowerCase().includes("doppelganger");
}

function claimsOf(evidence: EvidenceDto[], limit = 2): string {
  const names = evidence.map((item) => item.claim.split(":")[0]!.trim());
  const shown = names.slice(0, limit).join(", ");
  return names.length > limit ? `${shown} +${names.length - limit} more` : shown;
}

/**
 * Build the chain from the inspection payload.
 *
 * Exported for tests, which assert on the derivation rather than on pixels.
 */
export function buildProofChain(inspection: WorldInspectionDto): Stage[] {
  const { world } = inspection;
  // Defensive rather than trusting: a chain that throws mid-render would take
  // the whole run page with it, and this is supporting detail.
  const evidence = Array.isArray(inspection.evidence) ? inspection.evidence : [];
  const counterexamples = Array.isArray(inspection.counterexamples)
    ? inspection.counterexamples
    : [];

  const exploratory = evidence.filter((item) => !item.machine_verifiable);
  const doppelganger = exploratory.filter((item) => isDoppelgangerSource(item.source));
  const verified = evidence.filter((item) => item.machine_verifiable);
  const disqualifying = verified.filter((item) => item.disqualifying);

  // A counterexample that claims reproduction is not the same as one BRANCHPOINT
  // accepts. Both are tracked, and the difference is shown.
  const reproduced: CounterexampleDto | undefined =
    counterexamples.find((item) => item.authoritative) ??
    counterexamples.find((item) => item.reproduced);

  const veto = world?.veto ?? null;

  // The records the conclusion actually rests on. Showing an unrelated passing
  // check as "the replay proof" would overstate what was verified, so when the
  // backend has stated the linkage, only linked records are used.
  const linkedIds = new Set<string>([
    ...(veto?.evidence_ids ?? []),
    ...(reproduced?.supporting_evidence_ids ?? []),
  ]);
  const linked = verified.filter((item) => linkedIds.has(item.evidence_id));
  const proof = linked.length > 0 ? linked : disqualifying;

  const stages: Stage[] = [];

  // ----- 1. what something suspected, and what that something was ------------
  //
  // Three outcomes, not two: the DOPPELGÄNGER ran, *something else* exploratory
  // was recorded, or nothing was. Collapsing the middle case into the first
  // would credit an agent that never ran.
  const suspected = doppelganger.length > 0 ? doppelganger : exploratory;
  stages.push(
    suspected.length > 0
      ? {
          key: "exploratory",
          title: doppelganger.length > 0 ? "DOPPELGÄNGER" : "EXPLORATORY EVIDENCE",
          state: "REACHED",
          verdict: "EXPLORATORY",
          detail:
            (doppelganger.length > 0 ? reproduced?.hypothesis : "") ||
            suspected[0]?.claim ||
            "exploratory finding recorded",
          Icon: Search,
        }
      : {
          key: "exploratory",
          title: "DOPPELGÄNGER",
          state: "ABSENT",
          verdict: "NOT PRESENT",
          detail: "No exploratory agent evidence for this world.",
          Icon: CircleSlash,
        },
  );

  // ----- 2. what BRANCHPOINT verified itself ---------------------------------
  stages.push(
    verified.length > 0
      ? {
          key: "verified",
          title: "BRANCHPOINT REPLAY",
          state: "REACHED",
          verdict: "VERIFIED",
          detail:
            proof.length > 0
              ? `${claimsOf(proof)} failed`
              : `${verified.length} machine-verifiable check${
                  verified.length === 1 ? "" : "s"
                }, none failing`,
          Icon: Check,
        }
      : {
          key: "verified",
          title: "BRANCHPOINT REPLAY",
          state: "ABSENT",
          verdict: "NOT PRESENT",
          detail: "No machine-verifiable evidence for this world.",
          Icon: CircleSlash,
        },
  );

  // ----- 3. whether an attack actually reproduced -----------------------------
  if (reproduced === undefined) {
    stages.push({
      key: "reproduced",
      title: "COUNTEREXAMPLE",
      state: "ABSENT",
      verdict: "NONE REPRODUCED",
      detail: "No counterexample was reproduced against this world.",
      Icon: CircleSlash,
    });
  } else if (reproduced.authoritative) {
    stages.push({
      key: "reproduced",
      title: "COUNTEREXAMPLE",
      state: "REACHED",
      verdict: "REPRODUCED",
      detail:
        reproduced.title ||
        `${reproduced.supporting_evidence_ids.length} supporting record(s)`,
      Icon: X,
    });
  } else {
    stages.push({
      key: "reproduced",
      title: "COUNTEREXAMPLE",
      state: "UNSUPPORTED",
      verdict: reproduced.reproduced ? "CLAIMED, UNSUPPORTED" : reproduced.status,
      detail:
        "Not backed by machine-verifiable failing evidence, so it vetoes nothing.",
      Icon: CircleSlash,
    });
  }

  // ----- 4. the conclusion, from the structured veto only ---------------------
  stages.push(
    veto !== null
      ? {
          key: "veto",
          title: "VERDICT",
          state: "REACHED",
          verdict: "VETOED",
          detail:
            veto.basis === "REPRODUCED_COUNTEREXAMPLE"
              ? `${veto.summary} — reproduced counterexample`
              : `${veto.summary} — machine-verifiable failure`,
          Icon: X,
        }
      : {
          key: "veto",
          title: "VERDICT",
          state: "ABSENT",
          verdict:
            world?.verdict === "SURVIVED" ? "WORLD SURVIVED" : (world?.verdict ?? "PENDING"),
          detail: "No authoritative counterexample. Nothing vetoed this world.",
          Icon: world?.verdict === "SURVIVED" ? Check : Diamond,
        },
  );

  return stages;
}

const STATE_STYLE: Record<StageState, { border: string; text: string }> = {
  REACHED: { border: "border-edge", text: "text-fg" },
  ABSENT: { border: "border-edge-muted", text: "text-fg-faint" },
  UNSUPPORTED: { border: "border-warn-dim", text: "text-warn" },
};

function StageRow({ stage, last }: { stage: Stage; last: boolean }) {
  const style = STATE_STYLE[stage.state];
  const vetoed = stage.key === "veto" && stage.state === "REACHED";

  return (
    <li>
      <div
        className={`rounded-md border px-2.5 py-1.5 ${
          vetoed ? "border-fail-dim bg-fail/10" : `${style.border} bg-surface`
        }`}
      >
        <div className="flex items-center gap-2">
          <stage.Icon
            className={`h-3.5 w-3.5 shrink-0 ${
              vetoed ? "text-fail" : style.text
            }`}
            strokeWidth={2.5}
            aria-hidden="true"
          />
          <span className="font-mono text-[10px] font-semibold tracking-[0.1em] text-fg-faint">
            {stage.title}
          </span>
        </div>
        <p
          className={`mt-0.5 font-mono text-[11px] font-semibold tracking-[0.06em] ${
            vetoed ? "text-fail" : style.text
          }`}
        >
          {stage.verdict}
        </p>
        <p className="mt-0.5 text-[11px] leading-snug text-fg-dim">
          {stage.detail}
        </p>
      </div>
      {last ? null : (
        <div className="flex justify-center py-0.5" aria-hidden="true">
          <ArrowDown className="h-3 w-3 text-fg-faint" strokeWidth={2} />
        </div>
      )}
    </li>
  );
}

export function ProofChain({ inspection }: { inspection: WorldInspectionDto }) {
  const stages = buildProofChain(inspection);

  return (
    <section
      aria-label="Proof chain"
      className="border-t border-edge-muted px-4 py-3"
    >
      <h4 className="mb-2 font-mono text-[10px] font-semibold tracking-[0.14em] text-fg-faint">
        PROOF CHAIN
      </h4>
      <ol>
        {stages.map((stage, index) => (
          <StageRow
            key={stage.key}
            stage={stage}
            last={index === stages.length - 1}
          />
        ))}
      </ol>
    </section>
  );
}

/**
 * The records behind the chain, grouped by what they are allowed to prove.
 *
 * Secondary to the chain by design: the story is the four stages, and this is
 * the receipts a skeptic scrolls to.
 */
export function SupportingEvidence({
  evidence,
}: {
  evidence: EvidenceDto[];
}) {
  const rows = Array.isArray(evidence) ? evidence : [];
  const exploratory = rows.filter((item) => !item.machine_verifiable);
  const verified = rows.filter((item) => item.machine_verifiable);

  return (
    <section
      aria-label="Supporting evidence"
      className="border-t border-edge-muted px-4 py-3"
    >
      <h4 className="mb-2 font-mono text-[10px] font-semibold tracking-[0.14em] text-fg-faint">
        SUPPORTING EVIDENCE
      </h4>

      {verified.length > 0 ? (
        <div className="mb-3">
          <div className="mb-1 flex items-center gap-2">
            <span className="font-mono text-[10px] tracking-[0.1em] text-fg-faint">
              MACHINE VERIFIED
            </span>
            <AuthorityBadge authority="VERIFIED" />
          </div>
          <ul className="divide-y divide-edge-muted border-t border-edge-muted">
            {verified.map((item) => (
              <li
                key={item.evidence_id}
                className="flex items-baseline justify-between gap-3 py-[3px]"
              >
                <span className="min-w-0 truncate font-mono text-[11px] text-fg-dim">
                  {item.claim}
                </span>
                <span
                  className={`shrink-0 font-mono text-[11px] font-medium ${
                    item.disqualifying
                      ? "text-fail"
                      : item.passed
                        ? "text-ok"
                        : "text-fg-faint"
                  }`}
                >
                  {item.passed === null ? "—" : item.passed ? "PASS" : "FAIL"}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <div>
        <div className="mb-1 flex items-center gap-2">
          <span className="font-mono text-[10px] tracking-[0.1em] text-fg-faint">
            EXPLORATORY
          </span>
          <AuthorityBadge authority="EXPLORATORY" />
        </div>
        {exploratory.length === 0 ? (
          <p className="text-[11px] leading-relaxed text-fg-faint">
            No exploratory agent evidence for this world.
          </p>
        ) : (
          <ul>
            {exploratory.map((item) => (
              <li key={item.evidence_id} className="py-[3px]">
                <p className="font-mono text-[11px] text-fg-dim">{item.claim}</p>
                <p className="font-mono text-[10px] text-fg-faint">
                  {item.source}
                  {item.observed === null ? "" : ` · ${String(item.observed)}`}
                </p>
              </li>
            ))}
          </ul>
        )}
        <p className="mt-1 text-[11px] leading-relaxed text-fg-faint">
          Exploratory records can suggest a failure. Only BRANCHPOINT&rsquo;s own
          replay can verify one.
        </p>
      </div>
    </section>
  );
}
