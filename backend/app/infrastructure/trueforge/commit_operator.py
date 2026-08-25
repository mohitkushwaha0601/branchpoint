"""The sanctioned destructive path: one approved commit, driven through TrueForge.

This adapter exists so that mutating reality goes through exactly the same
agent/MCP surface an operator sees in TrueForge — never a back-door Python call
into the demo engine. It is deliberately the least capable agent in the system:
one enabled tool, no sandbox, no subagents, and a tiny iteration budget.

The human decision has already been made and recorded in BRANCHPOINT before
this runs. What happens here is *transport-level*: TrueForge pauses the
destructive tool call, and BRANCHPOINT resumes it on behalf of the approval it
already holds — but only after checking that the paused call is the sanctioned
commit tool, invoked with exactly the run, world, and action a human approved.
A call that differs in any of those is denied, not allowed, so a model cannot
substitute an action after approval.

That check is the outermost of four independent layers. Below it sit the MCP
tool's own approval check, Phase 1's ``assert_commit_allowed``, and the
one-time capability — none of which trust this one.
"""

from app.application.ports import CommitOperatorReport
from app.domain.runs.models import BranchpointRun
from app.domain.worlds.models import World
from app.infrastructure.trueforge.client import TrueForgeClient
from app.infrastructure.trueforge.errors import (
    ToolCallResolutionError,
    TrueForgeError,
    TurnFailedError,
)
from app.infrastructure.trueforge.models import (
    PendingApproval,
    ToolCallForm,
    TurnResult,
    TurnStatus,
)
from app.infrastructure.trueforge.sessions import (
    InMemorySessionBindingStore,
    SessionPurpose,
    SessionStatus,
)
from app.mcp.server import COMMIT_TOOL_NAME

#: The commit operator's entire tool inventory: one destructive tool, nothing
#: else. It needs no read tools — BRANCHPOINT tells it the exact identifiers in
#: the prompt, and it has no decision left to make.
COMMIT_OPERATOR_TOOLS: tuple[str, ...] = (COMMIT_TOOL_NAME,)

#: Instructions for the commit operator.
#:
#: Deliberately colocated with the spec it configures rather than added to
#: ``prompts.py``, which holds the planner and DOPPELGÄNGER prompts and is not
#: touched by this path.
COMMIT_OPERATOR_INSTRUCTIONS = """\
You are the BRANCHPOINT commit operator.

A human has already reviewed one counterfactual world and explicitly approved
its action. Your only job is to invoke that one approved commit. You do not
decide what to commit, you do not choose a different world, and you do not
change any argument you are given.

Call `branchpoint_commit_recommended_world` exactly once, with exactly the
run_id, world_id, and expected_action_id given to you. Then reply with a single
short sentence describing what the tool returned.

The call will pause for approval. That is expected. Do not retry it, do not
call it a second time, and do not attempt any other tool.

If the tool returns an error, do not try to work around it: report the error
verbatim and stop. An error means a safety gate refused the commit, and that
refusal is correct.
"""


class CommitNotExecutedError(TrueForgeError):
    """Raised when the operator session ended without the commit tool running."""


class UnsanctionedToolCallError(TrueForgeError):
    """Raised when the paused tool call is not the exact approved commit.

    The call is denied before this is raised, so the turn does not stay parked
    waiting for an approval that is never coming.
    """


class TrueForgeCommitOperator:
    """Real ``CommitOperator`` port implementation backed by TrueForge."""

    def __init__(
        self,
        client: TrueForgeClient,
        *,
        model: str,
        bindings: InMemorySessionBindingStore,
        mcp_server_name: str = "branchpoint",
    ) -> None:
        self._client = client
        self._model = model
        self._bindings = bindings
        self._mcp_server_name = mcp_server_name

    def agent_spec(self) -> dict:
        """Build the inline TrueForge agent spec for the commit operator.

        Approval is required for the one tool this agent has, so the destructive
        call cannot execute without BRANCHPOINT explicitly resuming it. The
        ``@write``/``@destructive`` selectors are listed alongside the literal
        tool name as belt and braces: if a future tool were ever enabled here,
        it would still land on the approval gate rather than run unattended.
        """
        return {
            "model": {"name": self._model},
            "instructions": COMMIT_OPERATOR_INSTRUCTIONS,
            "mcp_servers": [
                {
                    "name": self._mcp_server_name,
                    "enable_tools": list(COMMIT_OPERATOR_TOOLS),
                    "preload_tools": list(COMMIT_OPERATOR_TOOLS),
                    "require_approval_for_tools": [
                        "@write",
                        "@destructive",
                        *COMMIT_OPERATOR_TOOLS,
                    ],
                }
            ],
            "config": {
                "sandbox": {"enabled": False},
                "dynamic_sub_agents": {"enabled": False},
                "iteration_limit": 6,
            },
        }

    async def commit(self, run: BranchpointRun, world: World) -> CommitOperatorReport:
        """Drive the approved commit for ``world`` and report what happened.

        Returns once the destructive tool has run (or failed). The run's own
        commit receipt and verification result — not anything the model said —
        are what the caller reads to decide the outcome.
        """
        action_id = world.candidate_action.action_id
        session_id = await self._client.create_session(self.agent_spec())
        await self._bindings.upsert(
            run_id=run.run_id,
            world_id=world.world_id,
            purpose=SessionPurpose.COMMIT_OPERATOR,
            trueforge_session_id=session_id,
            status=SessionStatus.ACTIVE,
        )

        result = await self._client.run_turn(
            session_id,
            "A human has approved this commit. Call "
            f"{COMMIT_TOOL_NAME} exactly once with "
            f'run_id="{run.run_id}", world_id="{world.world_id}", '
            f'expected_action_id="{action_id}". Change nothing.',
        )
        await self._record_turn(run, world, session_id, result)
        _assert_turn_usable(result)

        if not result.is_paused_for_approval:
            await self._fail_binding(run, world, session_id)
            raise CommitNotExecutedError(
                f"commit operator turn {result.turn_id} ended without reaching the "
                "destructive approval gate; nothing was committed"
            )

        pending = result.pending_approvals[0]
        try:
            self._assert_sanctioned(result, pending, run.run_id, world.world_id, action_id)
        except UnsanctionedToolCallError:
            await self._deny(session_id, pending, "does not match the approved commit")
            await self._fail_binding(run, world, session_id)
            raise

        resumed_id = await self._client.resume_turn_with_approval(
            session_id,
            thread_id=pending.thread_id,
            tool_call_id=pending.tool_call_id,
            approved=True,
        )
        resumed = await self._client.await_turn(session_id, resumed_id)
        await self._record_turn(run, world, session_id, resumed, status=SessionStatus.COMPLETED)
        _assert_turn_usable(resumed)

        return CommitOperatorReport(
            session_id=session_id,
            turn_id=resumed.turn_id,
            tool_called=COMMIT_TOOL_NAME in resumed.tools_called(),
            detail=f"{COMMIT_TOOL_NAME} approved and resumed in session {session_id}",
        )

    def _assert_sanctioned(
        self,
        result: TurnResult,
        pending: PendingApproval,
        run_id: str,
        world_id: str,
        action_id: str,
    ) -> None:
        """Refuse anything but the exact approved commit call.

        Works only with the *resolved effective invocation*: which tool will
        really run, on which server, with which arguments. TrueForge may
        express that call directly or through its ``call_tool`` deferred
        wrapper, and both reach here as the same three facts — so this check
        cannot be fooled by approving a wrapper whose target it never read.
        """
        call = result.paused_tool_call(pending)
        if call is None:
            raise UnsanctionedToolCallError(
                f"paused tool call {pending.tool_call_id or '<unnamed>'} could not be "
                f"resolved from source event {pending.source_event_id or '<missing>'}; "
                "refusing it"
            )

        try:
            invocation = call.resolve()
        except ToolCallResolutionError as exc:
            raise UnsanctionedToolCallError(
                f"paused tool call {call.id} could not be resolved: {exc}"
            ) from exc

        if invocation.effective_tool_name != COMMIT_TOOL_NAME:
            raise UnsanctionedToolCallError(
                f"paused tool call effectively targets {invocation.effective_tool_name!r} "
                f"(as {invocation.raw_function_name!r}), "
                f"not the sanctioned {COMMIT_TOOL_NAME!r}"
            )

        # A deferred wrapper always names its server, so it is always checked.
        # A direct call is checked whenever TrueForge stated one.
        if invocation.form is ToolCallForm.DEFERRED or invocation.effective_server_name:
            if invocation.effective_server_name != self._mcp_server_name:
                raise UnsanctionedToolCallError(
                    f"paused commit call targets MCP server "
                    f"{invocation.effective_server_name!r}, "
                    f"not {self._mcp_server_name!r}"
                )

        _assert_commit_input(
            invocation.effective_arguments,
            {"run_id": run_id, "world_id": world_id, "expected_action_id": action_id},
        )

    async def _deny(self, session_id: str, pending: PendingApproval, reason: str) -> None:
        """Deny a paused tool call, best effort — the raise that follows is the outcome."""
        try:
            await self._client.resume_turn_with_approval(
                session_id,
                thread_id=pending.thread_id,
                tool_call_id=pending.tool_call_id,
                approved=False,
                reason=reason,
            )
        except TrueForgeError:
            pass

    async def _record_turn(
        self,
        run: BranchpointRun,
        world: World,
        session_id: str,
        result: TurnResult,
        *,
        status: SessionStatus = SessionStatus.ACTIVE,
    ) -> None:
        pending = result.pending_approvals[0] if result.pending_approvals else None
        await self._bindings.upsert(
            run_id=run.run_id,
            world_id=world.world_id,
            purpose=SessionPurpose.COMMIT_OPERATOR,
            trueforge_session_id=session_id,
            status=status,
            last_turn_id=result.turn_id,
            pending_thread_id=pending.thread_id if pending else None,
            pending_tool_call_id=pending.tool_call_id if pending else None,
        )

    async def _fail_binding(self, run: BranchpointRun, world: World, session_id: str) -> None:
        await self._bindings.upsert(
            run_id=run.run_id,
            world_id=world.world_id,
            purpose=SessionPurpose.COMMIT_OPERATOR,
            trueforge_session_id=session_id,
            status=SessionStatus.FAILED,
        )


def _assert_commit_input(arguments: dict[str, object], approved: dict[str, str]) -> None:
    """Require the effective commit input to be exactly what a human approved.

    Exact means exact: the same three keys, all strings, all equal. No extra
    argument, no missing one, no renamed one, and nothing coerced on the way in.
    """
    if set(arguments) != set(approved):
        raise UnsanctionedToolCallError(
            f"paused commit call takes {sorted(arguments)}, "
            f"but an approved commit takes exactly {sorted(approved)}"
        )

    non_strings = sorted(key for key, value in arguments.items() if not isinstance(value, str))
    if non_strings:
        raise UnsanctionedToolCallError(
            f"paused commit call arguments {non_strings} are not strings"
        )

    for field, approved_value in approved.items():
        if arguments[field] != approved_value:
            raise UnsanctionedToolCallError(
                f"paused commit call targets {field}={arguments[field]!r}, "
                f"but the human approved {approved_value!r}"
            )


def _assert_turn_usable(result: TurnResult) -> None:
    """Fail closed on a turn that errored or was cancelled."""
    if result.status in (TurnStatus.ERROR, TurnStatus.CANCELLED):
        raise TurnFailedError(result.turn_id, result.status, result.error_detail)
