"""TrueForge candidate planner: validation, rejection, retry, and safety."""

import json

import pytest

from app.domain.actions.models import ActionType, CandidateAction
from app.infrastructure.trueforge.errors import PlanValidationError, TurnFailedError
from app.infrastructure.trueforge.planner import (
    PLANNER_TOOLS,
    TrueForgeCandidatePlanner,
    extract_json_object,
)
from app.infrastructure.trueforge.sessions import (
    InMemorySessionBindingStore,
    SessionPurpose,
    SessionStatus,
)
from app.mcp.server import DESTRUCTIVE_TOOL_NAMES
from tests.factories import make_incident, make_observed_state
from tests.trueforge.fake_transport import FakeTrueForge, FakeTurn

VALID_PLAN = {
    "diagnosis": "Pricing regression is driving checkout errors.",
    "candidates": [
        {
            "name": "Roll back pricing-service to v2.40",
            "description": "Redeploy the previous version.",
            "action_family": "SET_DEPLOYMENT_VERSION",
            "service": "pricing-service",
            "parameters": {"version": "v2.40"},
            "expected_outcome": "Errors recover",
            "risk_class": "HIGH",
            "reversible": True,
            "rationale": "The error rate rose right after this version shipped.",
        },
        {
            "name": "Disable PRICING_V2",
            "description": "Route checkout to the legacy pricing path.",
            "action_family": "SET_FEATURE_FLAG",
            "service": "pricing-service",
            "parameters": {"flag_key": "PRICING_V2"},
            "expected_outcome": "Errors recover",
            "risk_class": "LOW",
            "reversible": True,
            "rationale": "The flag gates the suspect code path.",
        },
        {
            "name": "Scale pricing-service to 12",
            "description": "Add capacity.",
            "action_family": "SCALE_SERVICE",
            "service": "pricing-service",
            "parameters": {"target_replicas": 12},
            "expected_outcome": "Errors improve",
            "risk_class": "MEDIUM",
            "reversible": True,
            "rationale": "Timeout rate suggests saturation.",
        },
    ],
}


def build_planner(
    fake: FakeTrueForge, **kwargs
) -> tuple[TrueForgeCandidatePlanner, InMemorySessionBindingStore]:
    """Wire a planner onto a fake TrueForge."""
    bindings = InMemorySessionBindingStore()
    planner = TrueForgeCandidatePlanner(
        fake.client(),
        model="fake/model",
        bindings=bindings,
        read_only_tools=PLANNER_TOOLS,
        **kwargs,
    )
    return planner, bindings


async def test_planner_output_validates_into_candidate_actions() -> None:
    fake = FakeTrueForge([FakeTurn(output=json.dumps(VALID_PLAN))])
    planner, _ = build_planner(fake)

    actions = await planner.plan(make_incident(), make_observed_state(), run_id="run_1")

    assert len(actions) == 3
    assert all(isinstance(action, CandidateAction) for action in actions)
    types = {action.action_type for action in actions}
    assert types == {ActionType.ROLLBACK, ActionType.FEATURE_FLAG_DISABLE, ActionType.SCALE}
    rollback = next(a for a in actions if a.action_type is ActionType.ROLLBACK)
    assert rollback.parameters == {"version": "v2.40"}


async def test_invalid_planner_action_is_rejected() -> None:
    """A candidate missing its required typed parameter is rejected, not repaired."""
    broken = json.loads(json.dumps(VALID_PLAN))
    broken["candidates"][0]["parameters"] = {}
    fake = FakeTrueForge([FakeTurn(output=json.dumps(broken))] * 3)
    planner, _ = build_planner(fake)

    with pytest.raises(PlanValidationError, match="version"):
        await planner.plan(make_incident(), make_observed_state(), run_id="run_1")


async def test_unsupported_action_family_is_rejected() -> None:
    """An action outside the three permitted families never becomes executable."""
    rogue = json.loads(json.dumps(VALID_PLAN))
    rogue["candidates"][0]["action_family"] = "RUN_SHELL_COMMAND"
    rogue["candidates"][0]["parameters"] = {"cmd": "rm -rf /"}
    fake = FakeTrueForge([FakeTurn(output=json.dumps(rogue))] * 3)
    planner, _ = build_planner(fake)

    with pytest.raises(PlanValidationError):
        await planner.plan(make_incident(), make_observed_state(), run_id="run_1")


async def test_planner_retries_are_bounded_and_feed_back_the_problem() -> None:
    """Bad output retries with explicit feedback, then gives up deterministically."""
    fake = FakeTrueForge([FakeTurn(output="not json at all")] * 5)
    planner, _ = build_planner(fake, max_retries=2)

    with pytest.raises(PlanValidationError):
        await planner.plan(make_incident(), make_observed_state(), run_id="run_1")

    # exactly max_retries + 1 attempts, never unbounded
    assert len(fake.turn_requests) == 3
    retry_text = str(fake.turn_requests[1])
    assert "rejected by BRANCHPOINT's validator" in retry_text


async def test_planner_recovers_on_a_bounded_retry() -> None:
    fake = FakeTrueForge([FakeTurn(output="oops, prose"), FakeTurn(output=json.dumps(VALID_PLAN))])
    planner, _ = build_planner(fake)

    actions = await planner.plan(make_incident(), make_observed_state(), run_id="run_1")

    assert len(actions) == 3
    assert len(fake.turn_requests) == 2


async def test_planner_cannot_reach_any_mutation_tool() -> None:
    """The planner agent spec exposes read-only tools only, by literal name."""
    fake = FakeTrueForge([FakeTurn(output=json.dumps(VALID_PLAN))])
    planner, _ = build_planner(fake)

    spec = planner.agent_spec()
    enabled = set(spec["mcp_servers"][0]["enable_tools"])

    assert enabled == set(PLANNER_TOOLS)
    assert not enabled & set(DESTRUCTIVE_TOOL_NAMES)
    assert spec["config"]["sandbox"]["enabled"] is False


async def test_planner_turn_paused_for_approval_fails_closed() -> None:
    """A planner that somehow triggers an approval pause is an error, not a plan."""
    fake = FakeTrueForge(
        [
            FakeTurn(
                output="",
                required_actions=[
                    {
                        "type": "tool.approval_required",
                        "thread_id": "main",
                        "tool_calls": [{"id": "call_1", "source_event_id": "evt_1"}],
                    }
                ],
            )
        ]
    )
    planner, _ = build_planner(fake)

    with pytest.raises(TurnFailedError, match="planners may not mutate"):
        await planner.plan(make_incident(), make_observed_state(), run_id="run_1")


async def test_planner_creates_a_session_binding() -> None:
    fake = FakeTrueForge([FakeTurn(output=json.dumps(VALID_PLAN))])
    planner, bindings = build_planner(fake)

    await planner.plan(make_incident(), make_observed_state(), run_id="run_1")

    binding = await bindings.get("run_1", SessionPurpose.PLANNER)
    assert binding is not None
    assert binding.trueforge_session_id == "sess_1"
    assert binding.status is SessionStatus.COMPLETED
    assert binding.last_turn_id


async def test_planner_binds_the_run_id_it_is_given_not_the_incident_id() -> None:
    """Regression: a planner session must bind to the run, never to the incident.

    ``run_id`` now arrives through the port, so there is no fallback left to
    reach for and no binding to copy across afterwards.
    """
    fake = FakeTrueForge([FakeTurn(output=json.dumps(VALID_PLAN))])
    planner, bindings = build_planner(fake)
    incident = make_incident("incident_7")

    await planner.plan(incident, make_observed_state(), run_id="run_42")

    assert await bindings.get("incident_7", SessionPurpose.PLANNER) is None
    binding = await bindings.get("run_42", SessionPurpose.PLANNER)
    assert binding is not None
    assert binding.world_id is None
    assert [b.run_id for b in await bindings.list_for_run("run_42")] == ["run_42"]


async def test_replanning_the_same_run_does_not_duplicate_its_binding() -> None:
    """Idempotency: a second planning pass updates the run's binding in place."""
    fake = FakeTrueForge([FakeTurn(output=json.dumps(VALID_PLAN))] * 2)
    planner, bindings = build_planner(fake)

    await planner.plan(make_incident(), make_observed_state(), run_id="run_42")
    first = await bindings.get("run_42", SessionPurpose.PLANNER)
    await planner.plan(make_incident(), make_observed_state(), run_id="run_42")
    second = await bindings.get("run_42", SessionPurpose.PLANNER)

    assert len(await bindings.list_for_run("run_42")) == 1
    assert second.created_at == first.created_at
    assert second.status is SessionStatus.COMPLETED


async def test_planner_agent_spec_sends_no_temperature() -> None:
    """The configured reasoning model rejects ``temperature``; we must not send it."""
    fake = FakeTrueForge([FakeTurn(output=json.dumps(VALID_PLAN))])
    planner, _ = build_planner(fake)

    assert "params" not in planner.agent_spec()["model"]


async def test_plan_requires_materially_different_levers() -> None:
    """Three variations of one lever is a failed plan."""
    same = json.loads(json.dumps(VALID_PLAN))
    for candidate in same["candidates"]:
        candidate["action_family"] = "SCALE_SERVICE"
        candidate["parameters"] = {"target_replicas": 8}
    fake = FakeTrueForge([FakeTurn(output=json.dumps(same))] * 3)
    planner, _ = build_planner(fake)

    with pytest.raises(PlanValidationError, match="materially different|same lever"):
        await planner.plan(make_incident(), make_observed_state(), run_id="run_1")


async def test_scale_replicas_are_bounded() -> None:
    absurd = json.loads(json.dumps(VALID_PLAN))
    absurd["candidates"][2]["parameters"] = {"target_replicas": 100_000}
    fake = FakeTrueForge([FakeTurn(output=json.dumps(absurd))] * 3)
    planner, _ = build_planner(fake)

    with pytest.raises(PlanValidationError, match="1-50|between 1 and 50"):
        await planner.plan(make_incident(), make_observed_state(), run_id="run_1")


def test_extract_json_object_tolerates_a_code_fence() -> None:
    payload = extract_json_object('```json\n{"a": 1}\n```')
    assert payload == {"a": 1}


def test_extract_json_object_never_interprets_prose() -> None:
    from app.infrastructure.trueforge.errors import StructuredOutputError

    with pytest.raises(StructuredOutputError):
        extract_json_object("I think you should roll back. That is my recommendation.")
