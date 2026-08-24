"""Evidence rules: what may and may not veto a world.

These tests encode the central BRANCHPOINT principle — evidence beats
confidence. A DOPPELGÄNGER cannot veto a world by asserting that it looks
unsafe.
"""

import pytest
from pydantic import ValidationError

from app.domain.evidence.models import Evidence, EvidenceKind, EvidenceSeverity
from app.domain.worlds.lifecycle import WorldStatus
from app.domain.worlds.models import CounterexampleStatus, WorldVerdict
from app.domain.worlds.verdicts import counterexample_vetoes, derive_verdict
from tests.factories import (
    FIXED_TIME,
    completed_world,
    make_counterexample,
    make_evidence,
    make_outcome,
)


def test_reproduced_counterexample_with_verifiable_evidence_vetoes() -> None:
    failing = make_evidence(
        "attack_evidence",
        kind=EvidenceKind.TEST_RESULT,
        passed=False,
        machine_verifiable=True,
        severity=EvidenceSeverity.HIGH,
        claim="order rows survive the migration replay",
    )
    world = completed_world(
        attack_evidence=(failing,),
        counterexamples=(
            make_counterexample(
                "attack_1",
                "world_1",
                status=CounterexampleStatus.REPRODUCED,
                evidence_ids=("attack_evidence",),
            ),
        ),
    )

    assert world.verdict is WorldVerdict.VETOED
    assert world.status is WorldStatus.VETOED
    assert "Migration replay regression" in world.verdict_reason


def test_textual_criticism_cannot_veto_a_world() -> None:
    opinion = make_evidence(
        "opinion_1",
        kind=EvidenceKind.COUNTEREXAMPLE,
        passed=None,
        machine_verifiable=False,
        severity=EvidenceSeverity.CRITICAL,
        claim="this rollback feels dangerous",
    )
    world = completed_world(
        attack_evidence=(opinion,),
        counterexamples=(
            make_counterexample(
                "attack_1",
                "world_1",
                status=CounterexampleStatus.REPRODUCED,
                evidence_ids=("opinion_1",),
                title="Looks risky",
            ),
        ),
    )

    assert world.verdict is WorldVerdict.SURVIVED
    assert world.status is WorldStatus.SURVIVED


@pytest.mark.parametrize(
    "status",
    [
        CounterexampleStatus.PROPOSED,
        CounterexampleStatus.EXECUTED,
        CounterexampleStatus.NOT_REPRODUCED,
        CounterexampleStatus.ERROR,
    ],
)
def test_only_reproduced_counterexamples_can_veto(status: CounterexampleStatus) -> None:
    failing = make_evidence(
        "attack_evidence",
        kind=EvidenceKind.TEST_RESULT,
        passed=False,
        machine_verifiable=True,
    )
    counterexample = make_counterexample(
        "attack_1", "world_1", status=status, evidence_ids=("attack_evidence",)
    )

    assert not counterexample_vetoes(counterexample, {"attack_evidence": failing})

    world = completed_world(attack_evidence=(failing,), counterexamples=(counterexample,))
    assert world.verdict is WorldVerdict.SURVIVED


def test_counterexample_referencing_unknown_evidence_cannot_veto() -> None:
    counterexample = make_counterexample(
        "attack_1",
        "world_1",
        status=CounterexampleStatus.REPRODUCED,
        evidence_ids=("does_not_exist",),
    )

    assert not counterexample_vetoes(counterexample, {})


def test_machine_verifiable_evidence_must_record_an_outcome() -> None:
    with pytest.raises(ValidationError):
        Evidence(
            evidence_id="bad_1",
            kind=EvidenceKind.TEST_RESULT,
            source="test",
            claim="something was checked",
            machine_verifiable=True,
            passed=None,
        )


def test_only_machine_verifiable_failures_disqualify() -> None:
    unverifiable = make_evidence("soft_1", passed=False, machine_verifiable=False)
    verifiable = make_evidence("hard_1", passed=False, machine_verifiable=True)

    assert not unverifiable.disqualifies
    assert verifiable.disqualifies


def test_failing_invariant_evidence_vetoes_without_any_attack() -> None:
    world = completed_world(
        execution_evidence=(
            make_evidence(
                "invariant_1",
                kind=EvidenceKind.INVARIANT,
                passed=False,
                machine_verifiable=True,
                claim="no order is charged twice",
            ),
        )
    )

    assert world.verdict is WorldVerdict.VETOED
    assert "no order is charged twice" in world.verdict_reason


def test_failed_execution_yields_execution_failed_verdict() -> None:
    world = completed_world(outcome=make_outcome(succeeded=False))

    assert world.verdict is WorldVerdict.EXECUTION_FAILED
    assert world.status is WorldStatus.FAILED


def test_world_without_machine_verifiable_evidence_is_inconclusive() -> None:
    world = completed_world(
        execution_evidence=(make_evidence("soft_1", passed=True, machine_verifiable=False),)
    )

    assert world.verdict is WorldVerdict.INCONCLUSIVE
    assert world.status is WorldStatus.FAILED


def test_surviving_world_reports_why_it_survived() -> None:
    world = completed_world()

    assert world.verdict is WorldVerdict.SURVIVED
    assert world.verdict_reason
    assert world.updated_at == FIXED_TIME


def test_world_with_no_outcome_is_inconclusive() -> None:
    from app.domain.worlds.models import World
    from tests.factories import make_action

    world = World.create(
        world_id="world_x", run_id="run_1", candidate_action=make_action(), at=FIXED_TIME
    )

    verdict, reason = derive_verdict(world)

    assert verdict is WorldVerdict.INCONCLUSIVE
    assert "no execution outcome" in reason
