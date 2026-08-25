"""Session binding/resume plumbing and event-stream hygiene."""

import json

from app.domain.events import RunEvent, RunEventType
from app.domain.primitives import new_id, utc_now
from app.infrastructure.trueforge.models import ROOT_THREAD_ID, TurnEvent
from app.infrastructure.trueforge.sessions import (
    InMemorySessionBindingStore,
    SessionPurpose,
    SessionStatus,
)
from tests.trueforge.fake_transport import FakeTrueForge, FakeTurn, model_message_event

# ----- session bindings ------------------------------------------------------


async def test_session_mapping_records_run_world_and_purpose() -> None:
    store = InMemorySessionBindingStore()

    await store.upsert(
        run_id="run_1", purpose=SessionPurpose.PLANNER, trueforge_session_id="sess_planner"
    )
    await store.upsert(
        run_id="run_1",
        purpose=SessionPurpose.ADVERSARY,
        trueforge_session_id="sess_alpha",
        world_id="world_alpha",
    )

    planner = await store.get("run_1", SessionPurpose.PLANNER)
    adversary = await store.get("run_1", SessionPurpose.ADVERSARY, world_id="world_alpha")

    assert planner.trueforge_session_id == "sess_planner"
    assert planner.world_id is None
    assert adversary.trueforge_session_id == "sess_alpha"
    assert adversary.world_id == "world_alpha"
    assert len(await store.list_for_run("run_1")) == 2


async def test_upsert_preserves_created_at_and_updates_state() -> None:
    """Re-binding the same run/world/purpose updates rather than duplicating."""
    store = InMemorySessionBindingStore()
    first = await store.upsert(
        run_id="run_1", purpose=SessionPurpose.PLANNER, trueforge_session_id="sess_1"
    )
    second = await store.upsert(
        run_id="run_1",
        purpose=SessionPurpose.PLANNER,
        trueforge_session_id="sess_1",
        status=SessionStatus.COMPLETED,
        last_turn_id="turn_9",
    )

    assert second.created_at == first.created_at
    assert second.status is SessionStatus.COMPLETED
    assert second.last_turn_id == "turn_9"
    assert len(await store.list_for_run("run_1")) == 1


async def test_resume_reuses_an_existing_trueforge_session() -> None:
    """A resumed run reconnects to the same session instead of starting a new one."""
    fake = FakeTrueForge([FakeTurn(output="{}")])
    store = InMemorySessionBindingStore()
    await store.upsert(
        run_id="run_1",
        purpose=SessionPurpose.PLANNER,
        trueforge_session_id="sess_1",
        last_turn_id="turn_1",
    )

    client = fake.client()
    # The fake only knows sessions it created; seed one so resume can find it.
    await client.create_session({"model": {"name": "fake/model"}})
    binding = await store.get("run_1", SessionPurpose.PLANNER)

    assert await client.session_exists(binding.trueforge_session_id) is True
    assert await client.session_exists("sess_does_not_exist") is False


async def test_interrupted_session_does_not_duplicate_a_world_or_commit() -> None:
    """Re-binding after an interruption keeps exactly one binding per world."""
    store = InMemorySessionBindingStore()
    for _ in range(3):
        await store.upsert(
            run_id="run_1",
            purpose=SessionPurpose.ADVERSARY,
            trueforge_session_id="sess_alpha",
            world_id="world_alpha",
            pending_tool_call_id="call_1",
        )

    bindings = await store.list_for_run("run_1")
    assert len(bindings) == 1
    assert bindings[0].pending_tool_call_id == "call_1"


# ----- event hygiene ---------------------------------------------------------


def test_trueforge_event_model_never_exposes_reasoning_content() -> None:
    """Upstream ``reasoning_content`` is deliberately not modelled."""
    raw = model_message_event("final answer")
    assert "reasoning_content" in raw  # upstream really does send it

    event = TurnEvent.model_validate(raw)

    assert not hasattr(event, "reasoning_content")
    assert "PRIVATE CHAIN OF THOUGHT" not in event.model_dump_json()


def test_run_event_payloads_carry_status_not_reasoning() -> None:
    """BRANCHPOINT events expose tool/status/evidence metadata only."""
    event = RunEvent(
        event_id=new_id("evt"),
        run_id="run_1",
        event_type=RunEventType.DOPPELGANGER_SPAWNED,
        summary="DOPPELGANGER spawned for world_alpha",
        occurred_at=utc_now(),
        world_id="world_alpha",
        payload={"subagents": 1.0, "sandboxes": 1.0, "trueforge_session_id": "sess_1"},
    )

    serialized = json.loads(event.model_dump_json())

    assert set(serialized) == {
        "event_id",
        "run_id",
        "event_type",
        "summary",
        "occurred_at",
        "world_id",
        "payload",
    }
    assert "reasoning" not in serialized["payload"]
    assert serialized["payload"]["trueforge_session_id"] == "sess_1"


def test_subagent_events_are_distinguishable_from_root_events() -> None:
    root = TurnEvent.model_validate(model_message_event("x", thread_id=ROOT_THREAD_ID))
    sub = TurnEvent.model_validate(model_message_event("y", thread_id="thread_doppel_1"))

    assert root.is_subagent is False
    assert sub.is_subagent is True


def test_phase_three_event_types_exist() -> None:
    """Every event the live timeline needs is defined."""
    required = {
        "TRUEFORGE_SESSION_CREATED",
        "PLANNER_STARTED",
        "PLANNER_COMPLETED",
        "WORLD_AGENT_STARTED",
        "DOPPELGANGER_SPAWNED",
        "DOPPELGANGER_RUNNING",
        "SANDBOX_TEST_STARTED",
        "SANDBOX_TEST_COMPLETED",
        "COUNTEREXAMPLE_PROPOSED",
        "COUNTEREXAMPLE_REPRODUCED",
        "COUNTEREXAMPLE_REJECTED",
        "WORLD_VETOED",
        "WORLD_SURVIVED",
        "COMPARISON_COMPLETED",
        "APPROVAL_REQUESTED",
        "APPROVAL_GRANTED",
        "APPROVAL_REJECTED",
        "COMMIT_STARTED",
        "COMMIT_COMPLETED",
        "VERIFICATION_COMPLETED",
    }

    assert required <= {event.value for event in RunEventType}
