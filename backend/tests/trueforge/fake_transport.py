"""A fake TrueForge transport.

Serves scripted responses through the *real* :class:`TrueForgeClient`, so tests
exercise the actual request building, response translation, retry, and
fail-closed logic rather than a stand-in. No model is ever called, so the whole
suite runs offline and free.

Responses mirror the shapes captured from the live TrueForge 0.1.4 OpenAPI
spec: ``{"data": {...}}`` envelopes, ``state.status``, ``state.output``,
``state.required_actions``, and ``{"data": [events]}``.
"""

import json
from typing import Any

import httpx

from app.infrastructure.trueforge.client import TrueForgeClient


def model_message_event(text: str, *, thread_id: str = "main", event_id: str = "evt_1") -> dict:
    """Build a ``model.message`` event carrying a final reply."""
    return {
        "type": "model.message",
        "id": event_id,
        "created_at": "2026-08-25T12:00:00Z",
        "thread_id": thread_id,
        "content": text,
        # Present upstream and deliberately never consumed by BRANCHPOINT.
        "reasoning_content": "PRIVATE CHAIN OF THOUGHT THAT MUST NOT LEAK",
    }


def thread_created_event(thread_id: str, title: str = "DOPPELGANGER") -> dict:
    """Build a ``thread.created`` event — TrueForge's real subagent signal."""
    return {
        "type": "thread.created",
        "id": f"evt_thread_{thread_id}",
        "created_at": "2026-08-25T12:00:01Z",
        "thread_id": thread_id,
        "title": title,
        "agent_info": {"name": "doppelganger"},
        "parent": {"thread_id": "main"},
    }


def sandbox_created_event(sandbox_id: str = "sbx_1") -> dict:
    """Build a ``sandbox.created`` event."""
    return {
        "type": "sandbox.created",
        "id": "evt_sandbox_1",
        "created_at": "2026-08-25T12:00:02Z",
        "sandbox_id": sandbox_id,
        "thread_id": None,
    }


def sandbox_exec_event(
    tool_call_id: str = "call_exec_1",
    *,
    command: str = "python3 /tmp/probe.py",
    thread_id: str = "thread_doppel_1",
    event_id: str = "evt_exec_1",
) -> dict:
    """Build a call to TrueForge's built-in sandbox ``exec`` tool.

    Not an MCP tool: ``tool_info.type`` is TrueForge's own ``truefoundry-system``,
    exactly as the sandbox capability appears on a live event stream. Pair it
    with :func:`tool_response_event` on the same ``tool_call_id`` to script a
    completed sandbox execution.
    """
    return {
        "type": "model.message",
        "id": event_id,
        "created_at": "2026-08-25T12:00:02Z",
        "thread_id": thread_id,
        "content": "",
        "tool_calls": [
            {
                "id": tool_call_id,
                "function": {"name": "exec", "arguments": json.dumps({"command": command})},
                "tool_info": {"type": "truefoundry-system", "name": "exec"},
            }
        ],
    }


def tool_response_event(tool_call_id: str, content: str, thread_id: str = "main") -> dict:
    """Build a ``tool.response`` event."""
    return {
        "type": "tool.response",
        "id": f"evt_tool_{tool_call_id}",
        "created_at": "2026-08-25T12:00:03Z",
        "thread_id": thread_id,
        "tool_call_id": tool_call_id,
        "content": content,
    }


class FakeTurn:
    """One scripted turn outcome."""

    def __init__(
        self,
        *,
        output: str = "",
        status: str = "done",
        events: list[dict] | None = None,
        required_actions: list[dict] | None = None,
        error: str = "",
    ) -> None:
        self.output = output
        self.status = status
        self.events = events or []
        self.required_actions = required_actions or []
        self.error = error

    def state(self) -> dict:
        """Render this turn's ``state`` exactly as TrueForge would."""
        if self.status == "done":
            return {
                "status": "done",
                "output": model_message_event(self.output) if self.output else None,
                "required_actions": self.required_actions,
                "completed_at": "2026-08-25T12:00:10Z",
            }
        return {"status": self.status, "error": self.error, "reason": self.error}


class FakeTrueForge:
    """Scripted TrueForge server backing a real ``TrueForgeClient``."""

    def __init__(
        self, turns: list[FakeTurn] | None = None, *, models: list[dict] | None = None
    ) -> None:
        self.turns = list(turns or [])
        #: What ``GET /api/v1/models`` serves. An empty list is TrueForge with
        #: no model provider configured, which several gates depend on.
        self.models = [{"name": "fake/model"}] if models is None else list(models)
        self.created_sessions: list[dict[str, Any]] = []
        self.turn_requests: list[dict[str, Any]] = []
        self.requests: list[tuple[str, str]] = []
        self._turn_index = 0
        self._turn_by_id: dict[str, FakeTurn] = {}
        self.fail_next_transport = 0

    def queue(self, turn: FakeTurn) -> None:
        """Append another scripted turn."""
        self.turns.append(turn)

    def client(self, **kwargs: Any) -> TrueForgeClient:
        """Return a real client wired to this fake over an in-memory transport."""
        transport = httpx.MockTransport(self._handle)
        http_client = httpx.AsyncClient(transport=transport, base_url="http://trueforge.test")
        return TrueForgeClient(
            base_url="http://trueforge.test",
            http_client=http_client,
            poll_interval_seconds=0.0,
            **kwargs,
        )

    def _handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.requests.append((request.method, path))

        if self.fail_next_transport > 0:
            self.fail_next_transport -= 1
            raise httpx.ConnectError("simulated transport failure", request=request)

        if path == "/api/v1/capabilities":
            return httpx.Response(200, json={"data": {"sandbox": {"enabled": True}}})

        if path == "/api/v1/models":
            return httpx.Response(200, json={"data": self.models})

        if path == "/api/v1/sessions" and request.method == "POST":
            body = json.loads(request.content)
            self.created_sessions.append(body)
            index = len(self.created_sessions)
            return httpx.Response(200, json={"data": {"id": f"sess_{index}"}})

        if path.startswith("/api/v1/sessions/") and path.endswith("/turns"):
            body = json.loads(request.content)
            self.turn_requests.append(body)
            if self._turn_index >= len(self.turns):
                raise AssertionError("fake TrueForge ran out of scripted turns")
            turn = self.turns[self._turn_index]
            self._turn_index += 1
            turn_id = f"turn_{self._turn_index}"
            self._turn_by_id[turn_id] = turn
            return httpx.Response(200, json={"data": {"id": turn_id}})

        # Session-level events. TrueForge 0.1.4 wraps each one in a
        # {"turn_id": ..., "event": {...}} envelope here, unlike the per-turn
        # log below — serving the bare event would let a parser that ignores
        # the envelope pass in tests and fail against the real harness, which
        # is exactly what happened.
        if (
            path.startswith("/api/v1/sessions/")
            and path.endswith("/events")
            and ("/turns/" not in path)
        ):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"turn_id": turn_id, "event": event}
                        for turn_id, turn in self._turn_by_id.items()
                        for event in turn.events
                    ]
                },
            )

        # Per-turn events: bare event objects, no envelope.
        if path.endswith("/events"):
            turn_id = path.split("/turns/")[1].split("/")[0]
            turn = self._turn_by_id.get(turn_id)
            return httpx.Response(200, json={"data": turn.events if turn else []})

        if "/turns/" in path:
            turn_id = path.rsplit("/", 1)[1]
            turn = self._turn_by_id.get(turn_id)
            if turn is None:
                return httpx.Response(404, json={"error": {"message": "no such turn"}})
            return httpx.Response(
                200, json={"data": {"id": turn_id, "session_id": "sess_1", "state": turn.state()}}
            )

        if path.startswith("/api/v1/sessions/"):
            session_id = path.rsplit("/", 1)[1]
            known = {f"sess_{i + 1}" for i in range(len(self.created_sessions))}
            if session_id not in known:
                return httpx.Response(404, json={"error": {"message": "no such session"}})
            return httpx.Response(200, json={"data": {"id": session_id, "title": None}})

        return httpx.Response(404, json={"error": {"message": f"unhandled path {path}"}})
