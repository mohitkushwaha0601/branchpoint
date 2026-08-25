"""The CounterexampleSpec replay engine: the only authoritative veto input."""

from pathlib import Path

import pytest

from app.domain.actions.models import ActionType
from app.infrastructure.demo.actions import apply_action
from app.infrastructure.demo.counterexample import (
    ASSERTABLE_METRICS,
    REPLAYABLE_CHECKS,
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
from app.infrastructure.demo.scenario import load_initial_state
from tests.factories import make_action

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


def compatibility_spec(world_id: str = "world_alpha") -> CounterexampleSpec:
    return CounterexampleSpec(
        counterexample_type=CounterexampleType.COMPATIBILITY,
        target_world_id=world_id,
        operation=CounterexampleOperation.RETRY_PAYMENT,
        assertion=CounterexampleAssertion(
            kind=AssertionKind.CHECK_PASSES, check_name="data_integrity"
        ),
        setup=OrderSelector(created_under_version="v2.41", min_schema_version=41),
        expected="payment retry stays idempotent",
        rationale="older runtime may not read newer records",
    )


def test_alpha_compatibility_counterexample_reproduces() -> None:
    result = reproduce(compatibility_spec(), ALPHA)

    assert result.reproduced is True
    evidence = result.evidence[0]
    assert evidence.machine_verifiable is True
    assert evidence.passed is False
    assert evidence.disqualifies is True
    assert evidence.artifact.startswith("order:")


def test_the_same_spec_does_not_reproduce_against_beta() -> None:
    result = reproduce(compatibility_spec("world_beta"), BETA)

    assert result.reproduced is False
    assert result.evidence[0].passed is True
    assert result.evidence[0].disqualifies is False


def test_gamma_metric_counterexample_is_honest() -> None:
    """Gamma genuinely misses the recovery SLO, so a metric assertion reproduces."""
    spec = CounterexampleSpec(
        counterexample_type=CounterexampleType.METRIC,
        target_world_id="world_gamma",
        operation=CounterexampleOperation.ASSERT_METRIC,
        assertion=CounterexampleAssertion(
            kind=AssertionKind.METRIC_AT_MOST, metric="checkout_error_rate", threshold=0.02
        ),
        expected="checkout error rate at or below 2%",
        rationale="added capacity may not fully recover the SLO",
    )

    result = reproduce(spec, GAMMA)

    assert result.reproduced is True
    assert "0.07" in str(result.evidence[0].observed)


def test_same_metric_assertion_does_not_reproduce_against_beta() -> None:
    spec = CounterexampleSpec(
        counterexample_type=CounterexampleType.METRIC,
        target_world_id="world_beta",
        operation=CounterexampleOperation.ASSERT_METRIC,
        assertion=CounterexampleAssertion(
            kind=AssertionKind.METRIC_AT_MOST, metric="checkout_error_rate", threshold=0.02
        ),
        expected="checkout error rate at or below 2%",
        rationale="probe",
    )

    assert reproduce(spec, BETA).reproduced is False


@pytest.mark.parametrize(
    "check_name",
    ["__import__('os').system('rm -rf /')", "'; DROP TABLE orders; --", "../../etc/passwd", ""],
)
def test_arbitrary_check_names_are_rejected(check_name: str) -> None:
    spec = compatibility_spec().model_copy(
        update={
            "assertion": CounterexampleAssertion(
                kind=AssertionKind.CHECK_PASSES, check_name=check_name
            )
        }
    )

    with pytest.raises(SpecValidationError):
        validate_spec(spec)


@pytest.mark.parametrize("metric", ["secret_key", "os.environ", "daily_infra_cost_usd; drop"])
def test_arbitrary_metric_names_are_rejected(metric: str) -> None:
    spec = compatibility_spec().model_copy(
        update={
            "operation": CounterexampleOperation.ASSERT_METRIC,
            "assertion": CounterexampleAssertion(
                kind=AssertionKind.METRIC_AT_MOST, metric=metric, threshold=1.0
            ),
        }
    )

    with pytest.raises(SpecValidationError):
        validate_spec(spec)


def test_metric_assertion_requires_a_threshold() -> None:
    spec = compatibility_spec().model_copy(
        update={
            "operation": CounterexampleOperation.ASSERT_METRIC,
            "assertion": CounterexampleAssertion(
                kind=AssertionKind.METRIC_AT_MOST, metric="checkout_error_rate"
            ),
        }
    )

    with pytest.raises(SpecValidationError, match="threshold"):
        validate_spec(spec)


def test_replay_surface_is_a_closed_allowlist() -> None:
    """Only named checks and metrics are reachable — no dynamic lookup."""
    assert set(REPLAYABLE_CHECKS) == {
        "healthy_checkout",
        "recovery_slo",
        "data_integrity",
        "legacy_checkout",
        "modern_checkout",
    }
    assert "checkout_error_rate" in ASSERTABLE_METRICS
    assert all(isinstance(name, str) for name in ASSERTABLE_METRICS)


def test_a_selector_matching_nothing_does_not_reproduce() -> None:
    """An attack whose premise does not hold in the world is not a veto."""
    spec = compatibility_spec().model_copy(
        update={"setup": OrderSelector(order_id="order_does_not_exist")}
    )

    result = reproduce(spec, ALPHA)

    assert result.reproduced is False
    assert "no order" in str(result.evidence[0].observed)


def test_replay_never_mutates_the_state_it_is_given() -> None:
    before = ALPHA.model_copy(deep=True)

    reproduce(compatibility_spec(), ALPHA)

    assert ALPHA == before


@pytest.mark.parametrize(
    ("operation", "assertion"),
    [
        (
            CounterexampleOperation.EXECUTE_CHECK,
            CounterexampleAssertion(
                kind=AssertionKind.METRIC_AT_MOST, metric="checkout_error_rate", threshold=0.01
            ),
        ),
        (
            CounterexampleOperation.ASSERT_METRIC,
            CounterexampleAssertion(kind=AssertionKind.CHECK_PASSES, check_name="data_integrity"),
        ),
        (
            CounterexampleOperation.ASSERT_INVARIANT,
            CounterexampleAssertion(kind=AssertionKind.CHECK_PASSES, check_name="data_integrity"),
        ),
        (
            CounterexampleOperation.RETRY_PAYMENT,
            CounterexampleAssertion(
                kind=AssertionKind.METRIC_AT_LEAST, metric="checkout_error_rate", threshold=0.01
            ),
        ),
    ],
)
def test_an_assertion_the_operation_cannot_evaluate_is_rejected(
    operation: CounterexampleOperation, assertion: CounterexampleAssertion
) -> None:
    """Pairing is part of the contract, not a field the engine may ignore.

    ``reproduce`` dispatches on the operation, so an assertion the operation
    never reads would mean vetoing a world on a property the attacker never
    asserted. Both directions of the mismatch must be rejected as a spec
    problem, not surface as an internal error.
    """
    spec = compatibility_spec().model_copy(update={"operation": operation, "assertion": assertion})

    with pytest.raises(SpecValidationError, match="cannot evaluate"):
        validate_spec(spec)

    with pytest.raises(SpecValidationError, match="cannot evaluate"):
        reproduce(spec, ALPHA)


def test_a_self_asserting_compatibility_operation_needs_no_check_name() -> None:
    """RETRY_PAYMENT / DESERIALIZE_ORDER state their own property."""
    spec = compatibility_spec().model_copy(
        update={"assertion": CounterexampleAssertion(kind=AssertionKind.CHECK_PASSES)}
    )

    validate_spec(spec)
    assert reproduce(spec, ALPHA).reproduced is True
    assert reproduce(spec, BETA).reproduced is False


def test_execute_check_still_requires_a_check_name() -> None:
    spec = compatibility_spec().model_copy(
        update={
            "operation": CounterexampleOperation.EXECUTE_CHECK,
            "assertion": CounterexampleAssertion(kind=AssertionKind.CHECK_PASSES),
        }
    )

    with pytest.raises(SpecValidationError, match="check_name"):
        validate_spec(spec)


def test_validation_does_not_depend_on_assert_statements() -> None:
    """The guards must hold under ``python -O``, where ``assert`` is stripped."""
    source = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "infrastructure"
        / "demo"
        / "counterexample.py"
    ).read_text()

    assert "\n    assert " not in source
