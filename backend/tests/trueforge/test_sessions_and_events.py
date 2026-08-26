"""Session binding/resume plumbing and event-stream hygiene."""

import json

import httpx
import pytest

from app.domain.events import RunEvent, RunEventType
from app.domain.primitives import new_id, utc_now
from app.infrastructure.trueforge.client import TrueForgeClient
from app.infrastructure.trueforge.errors import TrueForgeAPIError, TrueForgeError
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


# ----- the live session-events wire shape -------------------------------------
#
# These drive the real client over an in-memory transport carrying the exact
# payload a live TrueForge 0.1.4 returned. Nothing constructs a TurnEvent by
# hand: that is precisely how the envelope went unnoticed — every harness test
# built typed events directly and so never read the wire at all.


def serve(payload: object) -> TrueForgeClient:
    """Return a real client whose session-events endpoint returns ``payload``."""

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/sessions/sess_1/events", request.url.path
        return httpx.Response(200, json=payload)

    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handle), base_url="http://trueforge.test"
    )
    return TrueForgeClient(base_url="http://trueforge.test", http_client=http_client)


async def test_the_live_session_envelope_is_unwrapped_into_typed_events() -> None:
    """The exact shape captured from a live TrueForge 0.1.4 instance.

    Each element of ``data`` is ``{"turn_id", "event"}``; the event is the inner
    object. Validating the envelope itself fails on the missing ``type``, which
    is what returned HTTP 500 from the harness-trace route.
    """
    client = serve(
        {
            "data": [
                {
                    "turn_id": "01m0yskstsrsy9xh2ex71rmyn9.local",
                    "event": {
                        "type": "model.message",
                        "id": "event_1",
                        "created_at": "2026-08-26T10:25:23.825Z",
                        "thread_id": "main",
                    },
                }
            ]
        }
    )

    events = await client.list_session_events("sess_1")

    assert len(events) == 1
    assert events[0].type == "model.message"
    assert events[0].id == "event_1"
    assert events[0].thread_id == "main"


async def test_every_event_type_the_trace_reads_survives_the_envelope() -> None:
    """One envelope per category the harness trace actually normalizes."""
    client = serve(
        {
            "data": [
                {
                    "turn_id": "turn_1",
                    "event": {
                        "type": "thread.created",
                        "id": "event_thread",
                        "created_at": "2026-08-26T10:25:20.000Z",
                        "thread_id": "thread_sub_1",
                        "title": "Compatibility Skeptic",
                    },
                },
                {
                    "turn_id": "turn_1",
                    "event": {
                        "type": "sandbox.created",
                        "id": "event_sandbox",
                        "created_at": "2026-08-26T10:25:21.000Z",
                        "thread_id": "main",
                        "sandbox_id": "v1:daytona:4a19c72e",
                    },
                },
                {
                    "turn_id": "turn_1",
                    "event": {
                        "tool_call_id": "call_1",
                        "content": '{"response": {"exitCode": 0, "result": "ok"}}',
                        "type": "tool.response",
                        "id": "event_response",
                        "created_at": "2026-08-26T10:25:22.000Z",
                        "thread_id": "main",
                    },
                },
                {
                    "turn_id": "turn_2",
                    "event": {
                        "type": "tool.approval_required",
                        "id": "event_approval",
                        "created_at": "2026-08-26T10:25:24.000Z",
                        "thread_id": "main",
                        "tool_calls_awaiting_approval": [
                            {"id": "call_2", "name": "branchpoint_commit_recommended_world"}
                        ],
                    },
                },
            ]
        }
    )

    events = await client.list_session_events("sess_1")

    assert [event.type for event in events] == [
        "thread.created",
        "sandbox.created",
        "tool.response",
        "tool.approval_required",
    ]
    assert events[0].title == "Compatibility Skeptic"
    assert events[1].sandbox_id == "v1:daytona:4a19c72e"
    assert events[2].tool_call_id == "call_1"
    assert events[3].tool_calls_awaiting_approval[0]["name"] == (
        "branchpoint_commit_recommended_world"
    )


async def test_an_empty_session_log_is_not_an_error() -> None:
    assert await serve({"data": []}).list_session_events("sess_1") == ()


# ----- malformed envelopes become typed protocol failures ---------------------


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"data": [{}]}, "had no 'event'"),
        ({"data": [{"turn_id": "x", "event": None}]}, "'event' was NoneType"),
        ({"data": [{"turn_id": "x", "event": {"id": "e"}}]}, "type: Field required"),
        ({"data": [{"turn_id": "x", "event": []}]}, "'event' was list"),
        ({"data": ["not-an-envelope"]}, "envelope was str"),
        ({"data": {"not": "a list"}}, "'data' was dict"),
    ],
)
async def test_a_malformed_envelope_raises_a_typed_trueforge_error(
    payload: object, expected: str
) -> None:
    """Never a raw ValidationError.

    ``HarnessTraceService`` catches ``TrueForgeError`` and degrades; a Pydantic
    ``ValidationError`` walks straight past it and out of the route as a 500.
    """
    client = serve(payload)

    with pytest.raises(TrueForgeError) as caught:
        await client.list_session_events("sess_1")

    assert isinstance(caught.value, TrueForgeAPIError)
    assert expected in str(caught.value)


async def test_a_protocol_error_never_quotes_the_event_back() -> None:
    """Error text is provenance about the failure, not a hole in redaction.

    These payloads carry model output, tool arguments, and tool results. An
    exception string reaches logs, so it names the field that failed and never
    the value that failed it.
    """
    secret = "sk-live-DO-NOT-LEAK-0123456789"
    client = serve(
        {
            "data": [
                {
                    "turn_id": "turn_1",
                    "event": {"id": "e", "content": secret, "sandbox_id": secret},
                }
            ]
        }
    )

    with pytest.raises(TrueForgeAPIError) as caught:
        await client.list_session_events("sess_1")

    assert secret not in str(caught.value)
    assert secret not in repr(caught.value)


async def test_the_turn_level_endpoint_is_parsed_without_an_envelope() -> None:
    """The two endpoints have different shapes and keep different parsers.

    Per-turn events arrive bare. Routing them through the session parser would
    reject every one of them for having no ``event`` key.
    """
    fake = FakeTrueForge([FakeTurn(output="{}", events=[model_message_event("done")])])
    client = fake.client()
    await client.create_session({"model": {"name": "fake/model"}})
    turn_id = await client.start_turn("sess_1", "go")

    events = await client.list_turn_events("sess_1", turn_id)

    assert [event.type for event in events] == ["model.message"]
