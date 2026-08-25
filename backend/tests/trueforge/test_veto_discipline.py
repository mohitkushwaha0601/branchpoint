"""Veto discipline: an attacker may not invent the requirement it then violates.

A counterexample is the only thing that can veto a world, so the criterion it
asserts has to belong to BRANCHPOINT rather than to the model proposing it.
These tests pin both halves of that: an invented threshold is rejected before
replay, and every genuinely declared invariant still bites exactly as hard as
it did before.

Relative quality — partial recovery, cost, blast radius, one world simply being
better than another — stays with the comparator. Nothing here may promote it
into a veto.
"""

import pytest

from app.application.world_engine.comparator import compare_worlds
from app.domain.actions.models import ActionType
from app.domain.evidence.models import EvidenceKind, EvidenceSeverity
from app.domain.worlds.models import CounterexampleStatus, WorldVerdict
from app.domain.worlds.verdicts import derive_verdict
from app.infrastructure.demo.actions import apply_action
from app.infrastructure.demo.counterexample import (
    AssertionKind,
    CounterexampleAssertion,
    CounterexampleOperation,
    CounterexampleSpec,
    CounterexampleType,
    OrderSelector,
    SpecValidationError,
    reproduce,
    validate_spec,
)
from app.infrastructure.demo.invariants import (
    CHECK_INVARIANTS,
    METRIC_INVARIANTS,
    DeclaredInvariant,
)
from app.infrastructure.demo.metrics import (
    RECOVERY_SLO_ERROR_RATE_THRESHOLD,
    RECOVERY_SLO_P95_MS_THRESHOLD,
    compute_metrics,
)
from app.infrastructure.demo.scenario import load_initial_state
from tests.factories import (
    completed_world,
    make_action,
    make_counterexample,
    make_evidence,
    make_outcome,
)

REALITY = load_initial_state()
ALPHA = apply_action(
    REALITY, make_action("a", action_type=ActionType.ROLLBACK, parameters={"version": "v2.40"})
)
BETA = apply_action(
    REALITY,
    make_action(
        "b", action_type=ActionType.FEATURE_FLAG_DISABLE, parameters={"flag_key": "PRICING_V2"}
    ),
)
GAMMA = apply_action(
    REALITY, make_action("g", action_type=ActionType.SCALE, parameters={"target_replicas": 12})
)


def metric_spec(
    world_id: str,
    *,
    invariant: DeclaredInvariant | None = None,
    metric: str | None = None,
    threshold: float | None = None,
    kind: AssertionKind = AssertionKind.METRIC_AT_MOST,
) -> CounterexampleSpec:
    """Build a numeric counterexample exactly as an adversary would submit one."""
    return CounterexampleSpec(
        counterexample_type=CounterexampleType.METRIC,
        target_world_id=world_id,
        operation=CounterexampleOperation.ASSERT_METRIC,
        assertion=CounterexampleAssertion(
            kind=kind, invariant=invariant, metric=metric, threshold=threshold
        ),
        expected="the world meets the asserted bound",
        rationale="probe",
    )


def invariant_check_spec(
    world_id: str, invariant: DeclaredInvariant, *, selector: OrderSelector | None = None
) -> CounterexampleSpec:
    """Build a counterexample asserting one declared check invariant."""
    return CounterexampleSpec(
        counterexample_type=CounterexampleType.INVARIANT,
        target_world_id=world_id,
        operation=CounterexampleOperation.EXECUTE_CHECK,
        assertion=CounterexampleAssertion(kind=AssertionKind.CHECK_PASSES, invariant=invariant),
        setup=selector or OrderSelector(),
        expected="the declared invariant holds",
        rationale="probe",
    )


# ----- invented criteria are rejected before replay --------------------------


def test_arbitrary_error_rate_perfection_threshold_is_rejected() -> None:
    """`checkout_error_rate <= 0` is the attacker's own criterion, not BRANCHPOINT's."""
    spec = metric_spec("world_beta", metric="checkout_error_rate", threshold=0.0)

    with pytest.raises(SpecValidationError, match="may not assert"):
        validate_spec(spec)


def test_arbitrary_latency_perfection_threshold_is_rejected() -> None:
    """`checkout_p95_ms <= 0` likewise: no world could ever satisfy it."""
    spec = metric_spec("world_beta", metric="checkout_p95_ms", threshold=0.0)

    with pytest.raises(SpecValidationError, match="may not assert"):
        validate_spec(spec)


@pytest.mark.parametrize("threshold", [0.0, 0.001, 0.019, 1e-9])
def test_no_threshold_but_the_declared_one_is_accepted(threshold: float) -> None:
    """Nudging the bound in the attacker's favour is rejected however small the nudge."""
    spec = metric_spec(
        "world_beta", invariant=DeclaredInvariant.RECOVERY_ERROR_RATE_SLO, threshold=threshold
    )

    with pytest.raises(SpecValidationError, match="may not assert"):
        validate_spec(spec)


def test_restating_the_declared_threshold_exactly_is_permitted() -> None:
    """A faithful restatement is not an invention, so it survives validation."""
    spec = metric_spec(
        "world_gamma",
        invariant=DeclaredInvariant.RECOVERY_ERROR_RATE_SLO,
        threshold=RECOVERY_SLO_ERROR_RATE_THRESHOLD,
    )

    validate_spec(spec)


@pytest.mark.parametrize(
    "metric", ["affected_users", "daily_infra_cost_usd", "pricing_timeout_rate"]
)
def test_metrics_without_a_declared_bound_cannot_ground_a_veto(metric: str) -> None:
    """Observable and comparable, but not by itself grounds for a veto."""
    spec = metric_spec("world_beta", metric=metric, threshold=0.0)

    with pytest.raises(SpecValidationError, match="declares no threshold"):
        validate_spec(spec)


def test_a_declared_bound_cannot_be_flipped_to_the_other_direction() -> None:
    """An AT_MOST SLO asserted as AT_LEAST would invert what recovery means."""
    spec = metric_spec(
        "world_gamma",
        invariant=DeclaredInvariant.RECOVERY_ERROR_RATE_SLO,
        kind=AssertionKind.METRIC_AT_LEAST,
    )

    with pytest.raises(SpecValidationError, match="binds as"):
        validate_spec(spec)


def test_replay_reports_the_declared_threshold_not_the_attackers_words() -> None:
    """The evidence a veto rests on cites BRANCHPOINT's bound, by name."""
    spec = metric_spec("world_beta", invariant=DeclaredInvariant.RECOVERY_ERROR_RATE_SLO)

    result = reproduce(spec, BETA)

    assert result.reproduced is False
    assert str(RECOVERY_SLO_ERROR_RATE_THRESHOLD) in result.evidence[0].expected
    assert str(DeclaredInvariant.RECOVERY_ERROR_RATE_SLO) in result.evidence[0].expected


# ----- genuinely declared invariants still bite ------------------------------


def test_the_configured_recovery_error_rate_slo_can_reproduce() -> None:
    """Gamma really does miss the declared SLO, so the veto path still works."""
    metrics = compute_metrics(GAMMA)
    assert metrics.checkout_error_rate > RECOVERY_SLO_ERROR_RATE_THRESHOLD

    result = reproduce(
        metric_spec("world_gamma", invariant=DeclaredInvariant.RECOVERY_ERROR_RATE_SLO), GAMMA
    )

    assert result.reproduced is True
    assert result.evidence[0].disqualifies is True


def test_the_configured_recovery_latency_slo_can_reproduce() -> None:
    metrics = compute_metrics(GAMMA)
    assert metrics.checkout_p95_ms > RECOVERY_SLO_P95_MS_THRESHOLD

    result = reproduce(
        metric_spec("world_gamma", invariant=DeclaredInvariant.RECOVERY_LATENCY_SLO), GAMMA
    )

    assert result.reproduced is True


def test_schema_compatibility_failure_can_still_veto_alpha() -> None:
    """The compatibility invariant is unaffected by threshold discipline."""
    result = reproduce(
        invariant_check_spec("world_alpha", DeclaredInvariant.SCHEMA_COMPATIBILITY), ALPHA
    )

    assert result.reproduced is True
    assert result.evidence[0].disqualifies is True


def test_payment_idempotency_failure_can_still_veto_alpha() -> None:
    result = reproduce(
        invariant_check_spec("world_alpha", DeclaredInvariant.PAYMENT_IDEMPOTENCY), ALPHA
    )

    assert result.reproduced is True
    assert result.evidence[0].disqualifies is True


def test_a_data_integrity_breach_can_still_veto() -> None:
    """A world whose orders store is actually corrupt is vetoed on that alone."""
    corrupted = BETA.model_copy(
        update={"orders": (*BETA.orders, BETA.orders[0])}  # duplicate order id
    )

    assert (
        reproduce(
            invariant_check_spec("world_beta", DeclaredInvariant.DATA_INTEGRITY), BETA
        ).reproduced
        is False
    )
    assert (
        reproduce(
            invariant_check_spec("world_beta", DeclaredInvariant.DATA_INTEGRITY), corrupted
        ).reproduced
        is True
    )


def test_self_asserting_compatibility_operations_are_untouched() -> None:
    """The RETRY_PAYMENT / DESERIALIZE_ORDER path needs no invariant name."""
    spec = CounterexampleSpec(
        counterexample_type=CounterexampleType.COMPATIBILITY,
        target_world_id="world_alpha",
        operation=CounterexampleOperation.RETRY_PAYMENT,
        assertion=CounterexampleAssertion(kind=AssertionKind.CHECK_PASSES),
        setup=OrderSelector(created_under_version="v2.41", min_schema_version=41),
        expected="payment retry stays idempotent",
        rationale="probe",
    )

    assert reproduce(spec, ALPHA).reproduced is True
    assert (
        reproduce(spec.model_copy(update={"target_world_id": "world_beta"}), BETA).reproduced
        is False
    )


def test_a_named_invariant_survives_a_redundant_check_name() -> None:
    """Regression: decoration alongside a named invariant must not void a finding.

    A live adversary derived the schema-compatibility breach correctly and then
    also filled in ``check_name``. Rejecting the pair threw the whole
    counterexample away as malformed and the world went unvetoed. The invariant
    is authoritative; the extra field is ignored.
    """
    spec = CounterexampleSpec(
        counterexample_type=CounterexampleType.COMPATIBILITY,
        target_world_id="world_alpha",
        operation=CounterexampleOperation.DESERIALIZE_ORDER,
        assertion=CounterexampleAssertion(
            kind=AssertionKind.CHECK_PASSES,
            invariant=DeclaredInvariant.SCHEMA_COMPATIBILITY,
            check_name="modern_checkout",
        ),
        setup=OrderSelector(created_under_version="v2.41", min_schema_version=41),
        expected="an existing schema-41 order still deserializes after the rollback",
        rationale="the rolled-back deployment predates the schema those records use",
    )

    validate_spec(spec)
    result = reproduce(spec, ALPHA)

    assert result.reproduced is True
    assert result.evidence[0].disqualifies is True


def test_a_threshold_is_still_refused_alongside_a_named_invariant() -> None:
    """Decoration is forgiven; a competing criterion is not."""
    spec = metric_spec(
        "world_beta",
        invariant=DeclaredInvariant.RECOVERY_ERROR_RATE_SLO,
        threshold=0.0,
    )

    with pytest.raises(SpecValidationError, match="may not assert"):
        validate_spec(spec)


# ----- relative quality never becomes a veto ---------------------------------


def test_beta_cannot_be_over_vetoed_with_invented_perfection_thresholds() -> None:
    """Every perfection bound an attacker might reach for fails validation."""
    invented = [
        metric_spec("world_beta", metric="checkout_error_rate", threshold=0.0),
        metric_spec("world_beta", metric="checkout_p95_ms", threshold=0.0),
        metric_spec("world_beta", metric="affected_users", threshold=0.0),
        metric_spec("world_beta", metric="pricing_timeout_rate", threshold=0.0),
        metric_spec("world_beta", metric="daily_infra_cost_usd", threshold=0.0),
    ]

    for spec in invented:
        with pytest.raises(SpecValidationError):
            validate_spec(spec)


def test_beta_survives_every_declared_invariant() -> None:
    """Nothing BRANCHPOINT declares is violated by beta, so nothing can veto it."""
    for invariant in CHECK_INVARIANTS:
        assert reproduce(invariant_check_spec("world_beta", invariant), BETA).reproduced is False
    for invariant in METRIC_INVARIANTS:
        assert reproduce(metric_spec("world_beta", invariant=invariant), BETA).reproduced is False


def test_gamma_is_not_vetoed_merely_for_being_worse_than_beta() -> None:
    """Gamma is worse on every headline metric, yet only a declared breach counts.

    Its cost, its residual affected users, and its distance from beta are all
    unassertable. Only the recovery SLO — which BRANCHPOINT declared, not the
    attacker — reproduces against it.
    """
    beta_metrics, gamma_metrics = compute_metrics(BETA), compute_metrics(GAMMA)
    assert gamma_metrics.checkout_error_rate > beta_metrics.checkout_error_rate
    assert gamma_metrics.affected_users > beta_metrics.affected_users
    assert gamma_metrics.daily_infra_cost_usd > beta_metrics.daily_infra_cost_usd

    # "worse than beta" is not expressible at all
    for metric in ("affected_users", "daily_infra_cost_usd"):
        with pytest.raises(SpecValidationError):
            validate_spec(
                metric_spec("world_gamma", metric=metric, threshold=getattr(beta_metrics, metric))
            )

    # the declared SLO, and only it, reproduces
    assert (
        reproduce(
            invariant_check_spec("world_gamma", DeclaredInvariant.SCHEMA_COMPATIBILITY), GAMMA
        ).reproduced
        is False
    )
    assert (
        reproduce(
            metric_spec("world_gamma", invariant=DeclaredInvariant.RECOVERY_ERROR_RATE_SLO), GAMMA
        ).reproduced
        is True
    )


def test_no_counterexample_can_reference_a_second_world() -> None:
    """Cross-world comparison is structurally unrepresentable in the spec language."""
    spec_fields = set(CounterexampleSpec.model_fields)
    assertion_fields = set(CounterexampleAssertion.model_fields)

    assert "target_world_id" in spec_fields
    assert not {"baseline_world_id", "compared_to", "other_world_id"} & spec_fields
    assert not {"baseline_world_id", "compared_to", "other_world_id"} & assertion_fields


def test_a_world_with_no_declared_breach_reaches_survived() -> None:
    """End of the chain: an unreproduced attack leaves the world alive."""
    world = completed_world(
        world_id="world_beta",
        counterexamples=(
            make_counterexample(
                "attack_1", "world_beta", status=CounterexampleStatus.NOT_REPRODUCED
            ),
        ),
    )

    assert world.verdict is WorldVerdict.SURVIVED
    assert derive_verdict(world)[0] is WorldVerdict.SURVIVED


def test_comparator_semantics_are_unchanged_by_veto_discipline() -> None:
    """Being worse loses on ranking, never on eligibility.

    The comparator still separates worlds purely on their measured execution
    outcome. A world that recovers only partially stays eligible and is simply
    ranked below a better one; only a reproduced breach removes a world from
    contention at all.
    """
    beta = completed_world(
        world_id="world_beta",
        action=make_action("action_beta"),
        outcome=make_outcome(goal_achieved=True, goal_attainment=1.0, blast_radius=1),
    )
    gamma = completed_world(
        world_id="world_gamma",
        action=make_action("action_gamma"),
        outcome=make_outcome(
            goal_achieved=False,
            goal_attainment=0.44,
            regressions_detected=2,
            blast_radius=4,
            cost_delta=450.0,
        ),
    )
    vetoed_evidence = make_evidence(
        "evidence_breach",
        kind=EvidenceKind.DATA_INTEGRITY,
        passed=False,
        severity=EvidenceSeverity.CRITICAL,
        world_id="world_alpha",
    )
    alpha = completed_world(
        world_id="world_alpha",
        action=make_action("action_alpha"),
        attack_evidence=(vetoed_evidence,),
        counterexamples=(
            make_counterexample(
                "attack_alpha",
                "world_alpha",
                status=CounterexampleStatus.REPRODUCED,
                evidence_ids=("evidence_breach",),
            ),
        ),
    )

    assert beta.verdict is WorldVerdict.SURVIVED
    assert gamma.verdict is WorldVerdict.SURVIVED
    assert alpha.verdict is WorldVerdict.VETOED

    comparison = compare_worlds((alpha, beta, gamma))
    ranked = [ranking.world_id for ranking in comparison.rankings]

    assert comparison.recommended_world_id == "world_beta"
    assert ranked == ["world_beta", "world_gamma"]
    assert [rejected.world_id for rejected in comparison.rejected_worlds] == ["world_alpha"]
