"""Applies a Phase 1 ``CandidateAction`` to demo production state.

This is the only place a ``CandidateAction`` is interpreted as a concrete state
mutation. It is a pure function: same state + same action always produces the
same resulting state, and nothing here inspects the action's *name* to decide
what happens — only its ``action_type`` and typed ``parameters``.
"""

from app.domain.actions.models import ActionType, CandidateAction
from app.domain.primitives import evolve, utc_now
from app.infrastructure.demo.state import DemoProductionState
from app.infrastructure.demo.workload import deployment_supports_payment_revision

#: Parameter keys each supported action type reads from ``CandidateAction.parameters``.
VERSION_PARAM = "version"
FLAG_KEY_PARAM = "flag_key"
TARGET_REPLICAS_PARAM = "target_replicas"

#: The only feature flag and service this demo models.
PRICING_FLAG_KEY = "PRICING_V2"
PRICING_SERVICE = "pricing-service"


class DemoActionError(Exception):
    """Base class for demo action application errors."""


class UnsupportedActionTypeError(DemoActionError):
    """Raised when an action's type has no demo mutation defined for it."""

    def __init__(self, action_type: ActionType) -> None:
        super().__init__(f"no demo mutation is defined for action type {action_type}")
        self.action_type = action_type


class InvalidActionParametersError(DemoActionError):
    """Raised when an action's parameters are missing or malformed for its type."""


def apply_action(state: DemoProductionState, action: CandidateAction) -> DemoProductionState:
    """Return the state that results from applying ``action`` to ``state``."""
    if action.action_type is ActionType.ROLLBACK:
        return _apply_rollback(state, action)
    if action.action_type is ActionType.FEATURE_FLAG_DISABLE:
        return _apply_flag_disable(state, action)
    if action.action_type is ActionType.SCALE:
        return _apply_scale(state, action)
    raise UnsupportedActionTypeError(action.action_type)


def _apply_rollback(state: DemoProductionState, action: CandidateAction) -> DemoProductionState:
    target_version = action.parameters.get(VERSION_PARAM)
    if not isinstance(target_version, str) or not target_version:
        raise InvalidActionParametersError(
            f"ROLLBACK requires a string '{VERSION_PARAM}' parameter"
        )
    return evolve(
        state,
        pricing_deployment=evolve(
            state.pricing_deployment,
            version=target_version,
            previous_version=state.pricing_deployment.version,
            deployed_at=utc_now(),
        ),
    )


def _apply_flag_disable(state: DemoProductionState, action: CandidateAction) -> DemoProductionState:
    flag_key = action.parameters.get(FLAG_KEY_PARAM)
    if flag_key != state.pricing_flag.key:
        raise InvalidActionParametersError(
            f"FEATURE_FLAG_DISABLE requires '{FLAG_KEY_PARAM}' == {state.pricing_flag.key!r}"
        )
    return evolve(state, pricing_flag=evolve(state.pricing_flag, enabled=False))


def _apply_scale(state: DemoProductionState, action: CandidateAction) -> DemoProductionState:
    target_replicas = action.parameters.get(TARGET_REPLICAS_PARAM)
    if not isinstance(target_replicas, int | float) or target_replicas < 1:
        raise InvalidActionParametersError(
            f"SCALE requires a positive numeric '{TARGET_REPLICAS_PARAM}' parameter"
        )
    return evolve(
        state, pricing_capacity=evolve(state.pricing_capacity, replicas=int(target_replicas))
    )


def compute_blast_radius(before: DemoProductionState, after: DemoProductionState) -> int:
    """Measure how much of production an action touched, from a structural state diff.

    This is not authored per action type: it counts what actually changed.
    Rolling the deployment back touches every order whose interpretation flips
    from compatible to incompatible; scaling touches every replica added or
    removed; a flag flip touches only the flag itself.
    """
    before_compatible = deployment_supports_payment_revision(before.pricing_deployment.version)
    after_compatible = deployment_supports_payment_revision(after.pricing_deployment.version)
    orders_flipped = 0
    if before_compatible != after_compatible:
        orders_flipped = sum(1 for order in after.orders if order.payment_revision is not None)

    replica_delta = abs(after.pricing_capacity.replicas - before.pricing_capacity.replicas)
    flag_changed = 1 if before.pricing_flag.enabled != after.pricing_flag.enabled else 0

    return orders_flipped + replica_delta + flag_changed
