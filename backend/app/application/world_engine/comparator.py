"""Deterministic comparison of completed worlds.

There is no model ranking and no weighted "trust score" here. Worlds are
disqualified by evidence and ordered by explicit, explainable rules. When the
best worlds are indistinguishable on the available evidence the tie is reported
rather than broken.
"""

from collections.abc import Sequence

from app.domain.comparison.models import (
    ComparisonResult,
    RejectedWorld,
    RejectionReason,
    WorldRanking,
)
from app.domain.evidence.models import EvidenceKind, EvidenceSeverity
from app.domain.worlds.models import ExecutionOutcome, World, WorldVerdict
from app.domain.worlds.verdicts import vetoing_counterexamples

#: Ranking dimensions in priority order, applied lexicographically.
RANKING_DIMENSIONS: tuple[str, ...] = (
    "goal achieved",
    "goal attainment",
    "invariants preserved",
    "regressions detected",
    "blast radius",
    "reversibility",
    "measured cost impact",
)

_FLOAT_PRECISION = 6


def _ordering_key(outcome: ExecutionOutcome) -> tuple[float, ...]:
    """Return the lexicographic ordering key for an eligible world (lower is better)."""
    return (
        0.0 if outcome.goal_achieved else 1.0,
        -round(outcome.goal_attainment, _FLOAT_PRECISION),
        0.0 if outcome.invariants_preserved else 1.0,
        float(outcome.regressions_detected),
        float(outcome.blast_radius),
        0.0 if outcome.reversible else 1.0,
        round(outcome.cost_delta, _FLOAT_PRECISION),
    )


def _rejection_for(world: World) -> RejectedWorld | None:
    """Return the disqualification for ``world``, or ``None`` when it is eligible."""
    reasons: list[RejectionReason] = []
    evidence_ids: list[str] = []
    details: list[str] = []

    outcome = world.outcome
    if world.verdict is None:
        return RejectedWorld(
            world_id=world.world_id,
            reasons=(RejectionReason.NOT_EVALUATED,),
            detail="world has no verdict",
        )

    if world.verdict is WorldVerdict.EXECUTION_FAILED or outcome is None or not outcome.succeeded:
        return RejectedWorld(
            world_id=world.world_id,
            reasons=(RejectionReason.EXECUTION_FAILED,),
            detail=world.verdict_reason or "counterfactual execution failed",
        )

    vetoing = vetoing_counterexamples(world)
    if vetoing:
        reasons.append(RejectionReason.ADVERSARIAL_VETO)
        evidence_ids.extend(
            evidence_id for attack in vetoing for evidence_id in attack.evidence_ids
        )
        details.append(
            "reproduced counterexample: " + ", ".join(attack.title for attack in vetoing)
        )

    for item in world.evidence:
        if not item.disqualifies:
            continue
        if item.kind is EvidenceKind.INVARIANT:
            reasons.append(RejectionReason.INVARIANT_VIOLATION)
            evidence_ids.append(item.evidence_id)
            details.append(f"invariant failed: {item.claim}")
        elif (
            item.kind is EvidenceKind.DATA_INTEGRITY and item.severity is EvidenceSeverity.CRITICAL
        ):
            reasons.append(RejectionReason.CRITICAL_DATA_INTEGRITY_FAILURE)
            evidence_ids.append(item.evidence_id)
            details.append(f"critical data-integrity failure: {item.claim}")

    if not outcome.invariants_preserved:
        reasons.append(RejectionReason.INVARIANT_VIOLATION)
        details.append("execution did not preserve invariants")

    if world.verdict is WorldVerdict.INCONCLUSIVE:
        reasons.append(RejectionReason.INCONCLUSIVE_VERDICT)
        details.append("verdict is inconclusive")

    if world.verdict is WorldVerdict.VETOED and not reasons:
        reasons.append(RejectionReason.ADVERSARIAL_VETO)
        details.append(world.verdict_reason or "world was vetoed")

    if not reasons:
        return None

    return RejectedWorld(
        world_id=world.world_id,
        reasons=tuple(dict.fromkeys(reasons)),
        detail="; ".join(dict.fromkeys(details)),
        evidence_ids=tuple(dict.fromkeys(evidence_ids)),
    )


def compare_worlds(worlds: Sequence[World]) -> ComparisonResult:
    """Compare completed worlds and recommend at most one of them."""
    rejected: list[RejectedWorld] = []
    eligible: list[World] = []

    for world in worlds:
        rejection = _rejection_for(world)
        if rejection is None:
            eligible.append(world)
        else:
            rejected.append(rejection)

    if not eligible:
        return ComparisonResult(
            rejected_worlds=tuple(rejected),
            evidence_ids=tuple(
                evidence_id for item in rejected for evidence_id in item.evidence_ids
            ),
            summary=(
                f"No world survived: all {len(worlds)} world(s) were disqualified by evidence."
                if worlds
                else "No worlds were available to compare."
            ),
        )

    keyed = sorted(
        ((_ordering_key(world.outcome), world) for world in eligible),  # type: ignore[arg-type]
        key=lambda pair: (pair[0], pair[1].world_id),
    )

    rankings: list[WorldRanking] = []
    rank = 0
    previous_key: tuple[float, ...] | None = None
    for position, (key, world) in enumerate(keyed, start=1):
        if key != previous_key:
            rank = position
            previous_key = key
        outcome = world.outcome
        assert outcome is not None  # eligible worlds always carry an outcome
        rankings.append(
            WorldRanking(
                world_id=world.world_id,
                rank=rank,
                goal_achieved=outcome.goal_achieved,
                goal_attainment=outcome.goal_attainment,
                invariants_preserved=outcome.invariants_preserved,
                regressions_detected=outcome.regressions_detected,
                blast_radius=outcome.blast_radius,
                reversible=outcome.reversible,
                cost_delta=outcome.cost_delta,
                evidence_ids=tuple(item.evidence_id for item in world.evidence),
            )
        )

    best_key = keyed[0][0]
    tied = tuple(world.world_id for key, world in keyed if key == best_key)
    recommended = tied[0] if len(tied) == 1 else None

    if recommended is not None:
        summary = (
            f"{recommended} ranked first of {len(eligible)} eligible world(s) "
            f"by {', '.join(RANKING_DIMENSIONS)}; {len(rejected)} world(s) disqualified."
        )
    else:
        summary = (
            f"{len(tied)} worlds are tied on all deterministic evidence "
            f"({', '.join(tied)}); no world is recommended."
        )

    return ComparisonResult(
        recommended_world_id=recommended,
        eligible_world_ids=tuple(world.world_id for _, world in keyed),
        tied_world_ids=tied if recommended is None else (),
        rejected_worlds=tuple(rejected),
        rankings=tuple(rankings),
        evidence_ids=tuple(
            dict.fromkeys(
                [evidence_id for ranking in rankings for evidence_id in ranking.evidence_ids]
                + [evidence_id for item in rejected for evidence_id in item.evidence_ids]
            )
        ),
        summary=summary,
    )
