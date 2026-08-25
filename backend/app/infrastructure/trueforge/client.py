"""HTTP client for the TrueForge v0.1.4 REST API.

Verified against a live TrueForge 0.1.4 standalone instance and its published
OpenAPI spec. Only the endpoints BRANCHPOINT actually needs are wrapped:
sessions, turns (create/execute, inspect, resume-after-approval), turn events,
and MCP server registration.

Turns are created with ``stream: false``, so TrueForge returns the running turn
immediately and we poll its terminal state. That keeps this client free of SSE
parsing: BRANCHPOINT does not render a live chat, it needs the finished result
and the event log, both of which are available over plain REST.
"""

import asyncio
from typing import Any

import httpx

from app.infrastructure.trueforge.errors import (
    TrueForgeAPIError,
    TrueForgeUnavailableError,
    TurnFailedError,
)
from app.infrastructure.trueforge.models import (
    EVENT_TOOL_APPROVAL_REQUIRED,
    PendingApproval,
    TurnEvent,
    TurnResult,
    TurnStatus,
)

#: TrueForge 0.1.4 standalone binds the IPv6 loopback ([::1]) only, so a
#: literal 127.0.0.1 does not reach it. "localhost" resolves to ::1 first
#: and works on both stacks.
DEFAULT_BASE_URL = "http://localhost:8790"
DEFAULT_TIMEOUT_SECONDS = 120.0
DEFAULT_POLL_INTERVAL_SECONDS = 1.0
DEFAULT_TURN_TIMEOUT_SECONDS = 600.0

#: Bounded transport retry for transient failures. Never unbounded.
DEFAULT_TRANSPORT_RETRIES = 2


class TrueForgeClient:
    """Thin, typed async client for the TrueForge REST API."""

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        http_client: httpx.AsyncClient | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
        turn_timeout_seconds: float = DEFAULT_TURN_TIMEOUT_SECONDS,
        transport_retries: int = DEFAULT_TRANSPORT_RETRIES,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = http_client
        self._owns_client = http_client is None
        self._timeout = timeout_seconds
        self._poll_interval = poll_interval_seconds
        self._turn_timeout = turn_timeout_seconds
        self._transport_retries = max(0, transport_retries)

    async def __aenter__(self) -> "TrueForgeClient":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the underlying HTTP client if this instance created it."""
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout)
        return self._client

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        """Issue one request with a bounded retry on transport failures."""
        url = path if path.startswith("http") else f"{self._base_url}{path}"
        last_error: Exception | None = None

        for attempt in range(self._transport_retries + 1):
            try:
                response = await self._http().request(method, url, **kwargs)
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt < self._transport_retries:
                    await asyncio.sleep(self._poll_interval * (attempt + 1))
                    continue
                raise TrueForgeUnavailableError(
                    f"could not reach TrueForge at {self._base_url}: {exc}"
                ) from exc

            if response.status_code >= 400:
                raise TrueForgeAPIError(response.status_code, response.text[:500])
            if not response.content:
                return {}
            return response.json()

        raise TrueForgeUnavailableError(str(last_error))

    # ----- health / capabilities ---------------------------------------------

    async def capabilities(self) -> dict[str, Any]:
        """Return server capabilities. Doubles as a health probe."""
        return await self._request("GET", "/api/v1/capabilities")

    async def list_models(self) -> list[dict[str, Any]]:
        """Return models available for chat. Empty when no provider is configured."""
        payload = await self._request("GET", "/api/v1/models")
        return list(payload.get("data", []))

    # ----- MCP server registration -------------------------------------------

    async def register_mcp_server(self, *, name: str, url: str, description: str) -> dict[str, Any]:
        """Create or replace a remote MCP server registration."""
        return await self._request(
            "PUT",
            "/api/v1/settings/mcp-servers",
            json={
                "manifest": {
                    "type": "remote",
                    "name": name,
                    "url": url,
                    "description": description,
                }
            },
        )

    async def list_mcp_tools(self, name: str) -> list[dict[str, Any]]:
        """List the tools TrueForge discovers on a registered MCP server.

        Used to verify that BRANCHPOINT's annotations survive the wire and that
        TrueForge classifies read vs destructive tools the way we expect.
        """
        payload = await self._request("GET", f"/api/v1/mcp-servers/{name}/tools")
        data = payload.get("data", payload)
        if isinstance(data, dict):
            return list(data.get("tools", []))
        return list(data)

    # ----- sessions -----------------------------------------------------------

    async def create_session(self, agent_spec: dict[str, Any]) -> str:
        """Create a session from an inline agent spec and return its id."""
        payload = await self._request(
            "POST", "/api/v1/sessions", json={"agent": {"spec": agent_spec}}
        )
        session = payload.get("data", payload)
        session_id = session.get("id")
        if not session_id:
            raise TrueForgeAPIError(200, f"session response had no id: {payload}")
        return str(session_id)

    async def get_session(self, session_id: str) -> dict[str, Any]:
        """Fetch one session. Used to prove a session survived a restart."""
        payload = await self._request("GET", f"/api/v1/sessions/{session_id}")
        return dict(payload.get("data", payload))

    async def session_exists(self, session_id: str) -> bool:
        """Whether ``session_id`` still resolves in TrueForge's own persistence."""
        try:
            await self.get_session(session_id)
        except TrueForgeAPIError as exc:
            if exc.status_code == 404:
                return False
            raise
        return True

    # ----- turns --------------------------------------------------------------

    async def start_turn(self, session_id: str, message: str) -> str:
        """Create a turn from a user message and return its id (non-streaming)."""
        payload = await self._request(
            "POST",
            f"/api/v1/sessions/{session_id}/turns",
            json={
                "input": [{"type": "user.message", "content": message}],
                "stream": False,
            },
        )
        return self._turn_id_from(payload)

    async def resume_turn_with_approval(
        self,
        session_id: str,
        *,
        thread_id: str,
        tool_call_id: str,
        approved: bool,
        reason: str = "",
    ) -> str:
        """Resume a paused turn by allowing or denying one exact tool call.

        This is the human checkpoint. The decision travels as a
        ``user.tool_approval`` input item, which only an API client can supply —
        the model cannot approve its own tool call.
        """
        approval: dict[str, Any] = {"status": "allow"} if approved else {"status": "deny"}
        if not approved and reason:
            approval["reason"] = reason

        payload = await self._request(
            "POST",
            f"/api/v1/sessions/{session_id}/turns",
            json={
                "input": [
                    {
                        "type": "user.tool_approval",
                        "thread_id": thread_id,
                        "tool_call_id": tool_call_id,
                        "approval": approval,
                    }
                ],
                "stream": False,
            },
        )
        return self._turn_id_from(payload)

    @staticmethod
    def _turn_id_from(payload: dict[str, Any]) -> str:
        turn = payload.get("data", payload)
        turn_id = turn.get("id")
        if not turn_id:
            raise TrueForgeAPIError(200, f"turn response had no id: {payload}")
        return str(turn_id)

    async def get_turn(self, session_id: str, turn_id: str) -> dict[str, Any]:
        """Fetch one turn, including its state and any required actions."""
        payload = await self._request("GET", f"/api/v1/sessions/{session_id}/turns/{turn_id}")
        return dict(payload.get("data", payload))

    async def list_turn_events(self, session_id: str, turn_id: str) -> tuple[TurnEvent, ...]:
        """Fetch the event log for one turn."""
        payload = await self._request(
            "GET", f"/api/v1/sessions/{session_id}/turns/{turn_id}/events"
        )
        return tuple(TurnEvent.model_validate(item) for item in payload.get("data", []))

    async def await_turn(self, session_id: str, turn_id: str) -> TurnResult:
        """Poll until a turn reaches a terminal state, then translate it.

        A turn that pauses for human approval reaches ``done`` with pending
        ``required_actions`` — that is a normal terminal state here, not a
        failure.
        """
        deadline = asyncio.get_running_loop().time() + self._turn_timeout
        while True:
            turn = await self.get_turn(session_id, turn_id)
            state = turn.get("state", {})
            status = str(state.get("status", "running"))

            if status != TurnStatus.RUNNING:
                return await self._translate_turn(session_id, turn_id, turn)

            if asyncio.get_running_loop().time() > deadline:
                raise TurnFailedError(turn_id, "timeout", f"exceeded {self._turn_timeout}s")
            await asyncio.sleep(self._poll_interval)

    async def run_turn(self, session_id: str, message: str) -> TurnResult:
        """Start a turn and wait for it to finish."""
        turn_id = await self.start_turn(session_id, message)
        return await self.await_turn(session_id, turn_id)

    async def _translate_turn(
        self, session_id: str, turn_id: str, turn: dict[str, Any]
    ) -> TurnResult:
        state = turn.get("state", {})
        status = TurnStatus(str(state.get("status")))
        events = await self.list_turn_events(session_id, turn_id)

        output_text = ""
        output = state.get("output") or {}
        content = output.get("content")
        if isinstance(content, str):
            output_text = content
        elif isinstance(content, list):
            output_text = "".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            )

        pending = tuple(
            PendingApproval(
                thread_id=str(action.get("thread_id", "")),
                tool_call_id=str(call.get("id", "")),
                source_event_id=str(call.get("source_event_id", "")),
            )
            for action in state.get("required_actions", [])
            if action.get("type") == EVENT_TOOL_APPROVAL_REQUIRED
            for call in action.get("tool_calls", [])
        )

        return TurnResult(
            turn_id=turn_id,
            session_id=session_id,
            status=status,
            output_text=output_text,
            events=events,
            pending_approvals=pending,
            error_detail=str(state.get("error", "") or state.get("reason", "")),
        )
