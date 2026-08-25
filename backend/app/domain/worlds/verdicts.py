"""Evidence rules that decide whether a world survives.

These rules encode the central BRANCHPOINT principle: evidence beats confidence.
A world is only vetoed by something a machine can check, and it can only survive
if machine-verifiable evidence exists at all.
"""

from collections.abc import Mapping

from app.domain.evidence.models import Evidence, EvidenceKind, EvidenceSeverity
from app.domain.worlds.models import Counterexample, CounterexampleStatus, World, WorldVerdict

#: Evidence kinds whose machine-verifiable failure disqualifies a world outright.
DISQUALIFYING_EVIDENCE_KINDS: frozenset[EvidenceKind] = frozenset(
    {EvidenceKind.INVARIANT, EvidenceKind.DATA_INTEGRITY}
)


def counterexample_vetoes(
    counterexample: Counterexample, evidence_by_id: Mapping[str, Evidence]
) -> bool:
    """Whether an attack may veto a world.

    Requires both a reproduction *and* machine-verifiable failing evidence.
    Text criticism, however confident, never vetoes.
    """
    if counterexample.status is not CounterexampleStatus.REPRODUCED:
        return False
    return any(
        (item := evidence_by_id.get(evidence_id)) is not None and item.disqualifies
        for evidence_id in counterexample.evidence_ids
    )


def vetoing_counterexamples(world: World) -> tuple[Counterexample, ...]:
    """Return the attacks that are substantiated well enough to veto ``world``."""
    index = world.evidence_by_id
    return tuple(
        counterexample
        for counterexample in world.counterexamples
        if counterexample_vetoes(counterexample, index)
    )


def disqualifying_evidence(world: World) -> tuple[Evidence, ...]:
    """Return machine-verifiable failing evidence that disqualifies ``world`` on its own."""
    return tuple(
        item
        for item in world.evidence
        if item.disqualifies
        and (
            item.kind in DISQUALIFYING_EVIDENCE_KINDS or item.severity is EvidenceSeverity.CRITICAL
        )
    )


def derive_verdict(world: World) -> tuple[WorldVerdict, str]:
    """Derive a world's verdict and a human-readable reason from its evidence."""
    if world.outcome is None:
        return WorldVerdict.INCONCLUSIVE, "world produced no execution outcome"

    if not world.outcome.succeeded:
        return WorldVerdict.EXECUTION_FAILED, "counterfactual execution failed"

    vetoing = vetoing_counterexamples(world)
    if vetoing:
        titles = ", ".join(counterexample.title for counterexample in vetoing)
        return WorldVerdict.VETOED, f"reproduced counterexample: {titles}"

    failing = disqualifying_evidence(world)
    if failing:
        claims = ", ".join(item.claim for item in failing)
        return WorldVerdict.VETOED, f"machine-verifiable failure: {claims}"

    if not world.outcome.invariants_preserved:
        return WorldVerdict.VETOED, "execution did not preserve invariants"

    if not any(item.machine_verifiable for item in world.evidence):
        return WorldVerdict.INCONCLUSIVE, "no machine-verifiable evidence was produced"

    return WorldVerdict.SURVIVED, "no reproduced counterexample and no failing verifiable evidence"
