"""``CandidatePlanner`` backed by a real TrueForge agent.

The agent investigates production through BRANCHPOINT's read-only MCP tools and
proposes remediations. Nothing it returns is trusted: its output is parsed as
one bounded JSON object and validated into ``CandidateAction`` objects, and
anything outside the three permitted action families is rejected outright.

A rejected plan is fed back to the same session as validation feedback for a
small, fixed number of retries. Materially different actions are never silently
repaired into valid ones.
"""

import json
from collections.abc import Sequence
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.domain.actions.models import (
    ActionSource,
    ActionSourceKind,
    ActionTarget,
    ActionType,
    CandidateAction,
    RiskClass,
)
from app.domain.incidents.models import Incident, ObservedState
from app.domain.primitives import new_id
from app.infrastructure.demo.actions import (
    FLAG_KEY_PARAM,
    TARGET_REPLICAS_PARAM,
    VERSION_PARAM,
)
from app.infrastructure.trueforge.client import TrueForgeClient
from app.infrastructure.trueforge.errors import (
    PlanValidationError,
    StructuredOutputError,
    TurnFailedError,
)
from app.infrastructure.trueforge.models import TurnResult, TurnStatus
from app.infrastructure.trueforge.prompts import PLANNER_INSTRUCTIONS
from app.infrastructure.trueforge.sessions import (
    InMemorySessionBindingStore,
    SessionPurpose,
    SessionStatus,
)

#: Bounded formatting/validation retries. Small and deterministic by design.
MAX_PLAN_RETRIES = 2

#: How many distinct candidates a plan must contain to be usable.
MIN_CANDIDATES = 2
MAX_CANDIDATES = 5


class ActionFamily(StrEnum):
    """The only action families a planner may propose."""

    SET_DEPLOYMENT_VERSION = "SET_DEPLOYMENT_VERSION"
    SET_FEATURE_FLAG = "SET_FEATURE_FLAG"
    SCALE_SERVICE = "SCALE_SERVICE"


#: Maps a permitted family onto the Phase 1 domain action type it becomes.
_FAMILY_TO_ACTION_TYPE: dict[ActionFamily, ActionType] = {
    ActionFamily.SET_DEPLOYMENT_VERSION: ActionType.ROLLBACK,
    ActionFamily.SET_FEATURE_FLAG: ActionType.FEATURE_FLAG_DISABLE,
    ActionFamily.SCALE_SERVICE: ActionType.SCALE,
}


class ProposedCandidate(BaseModel):
    """One candidate exactly as the agent proposed it, before validation."""

    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=1000)
    action_family: ActionFamily
    service: str = Field(min_length=1, max_length=100)
    parameters: dict[str, str | float | bool | int | None] = Field(default_factory=dict)
    expected_outcome: str = Field(default="", max_length=1000)
    risk_class: RiskClass = RiskClass.MEDIUM
    reversible: bool = True
    rationale: str = Field(default="", max_length=2000)


class ProposedPlan(BaseModel):
    """The whole bounded JSON object a planner turn must produce."""

    model_config = ConfigDict(extra="ignore")

    diagnosis: str = Field(default="", max_length=2000)
    candidates: list[ProposedCandidate] = Field(default_factory=list)


def extract_json_object(text: str) -> dict:
    """Pull exactly one JSON object out of a model reply.

    Tolerates a code fence or incidental surrounding prose, because that is a
    formatting slip rather than a semantic one. It never *interprets* prose:
    if there is no parseable object, this raises and the caller retries with
    explicit feedback.
    """
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("```")[1] if "```" in stripped[3:] else stripped[3:]
        if stripped.lstrip().startswith("json"):
            stripped = stripped.lstrip()[4:]
        stripped = stripped.strip("`").strip()

    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        start, end = stripped.find("{"), stripped.rfind("}")
        if start == -1 or end <= start:
            raise StructuredOutputError(
                "reply contained no JSON object",
                "Your reply must be exactly one JSON object and nothing else.",
            ) from None
        try:
            parsed = json.loads(stripped[start : end + 1])
        except json.JSONDecodeError as exc:
            raise StructuredOutputError(
                f"reply was not valid JSON: {exc}",
                f"Your JSON did not parse ({exc}). Reply with one valid JSON object only.",
            ) from exc

    if not isinstance(parsed, dict):
        raise StructuredOutputError(
            "reply JSON was not an object",
            "Your reply must be a single JSON object, not a list or scalar.",
        )
    return parsed


def _validate_parameters(candidate: ProposedCandidate) -> dict[str, str | float | bool]:
    """Translate a proposed candidate's parameters into the exact demo contract.

    Each family accepts exactly one typed parameter. Extra keys are dropped
    rather than forwarded, so a model cannot smuggle anything through.
    """
    family = candidate.action_family
    params = candidate.parameters

    if family is ActionFamily.SET_DEPLOYMENT_VERSION:
        version = params.get(VERSION_PARAM) or params.get("target_version")
        if not isinstance(version, str) or not version.strip():
            raise PlanValidationError(
                f"candidate {candidate.name!r} needs a string '{VERSION_PARAM}' parameter",
                f'{family} requires parameters like {{"{VERSION_PARAM}": "<version>"}}.',
            )
        return {VERSION_PARAM: version.strip()}

    if family is ActionFamily.SET_FEATURE_FLAG:
        flag_key = params.get(FLAG_KEY_PARAM) or params.get("key")
        if not isinstance(flag_key, str) or not flag_key.strip():
            raise PlanValidationError(
                f"candidate {candidate.name!r} needs a string '{FLAG_KEY_PARAM}' parameter",
                f'{family} requires parameters like {{"{FLAG_KEY_PARAM}": "<FLAG_NAME>"}}.',
            )
        return {FLAG_KEY_PARAM: flag_key.strip()}

    replicas = params.get(TARGET_REPLICAS_PARAM) or params.get("replicas")
    if isinstance(replicas, bool) or not isinstance(replicas, int | float):
        raise PlanValidationError(
            f"candidate {candidate.name!r} needs a numeric '{TARGET_REPLICAS_PARAM}' parameter",
            f'{family} requires parameters like {{"{TARGET_REPLICAS_PARAM}": 12}}.',
        )
    if not 1 <= int(replicas) <= 50:
        raise PlanValidationError(
            f"candidate {candidate.name!r} requested {int(replicas)} replicas, outside 1-50",
            f"{TARGET_REPLICAS_PARAM} must be between 1 and 50.",
        )
    return {TARGET_REPLICAS_PARAM: float(int(replicas))}


def validate_plan(plan: ProposedPlan) -> tuple[CandidateAction, ...]:
    """Validate a proposed plan into domain ``CandidateAction`` objects.

    Raises :class:`PlanValidationError` with agent-facing feedback rather than
    repairing anything that is materially different from what was asked for.
    """
    if not plan.candidates:
        raise PlanValidationError(
            "plan contained no candidates", "You must propose candidate actions."
        )
    if len(plan.candidates) < MIN_CANDIDATES:
        raise PlanValidationError(
            f"plan contained only {len(plan.candidates)} candidate(s)",
            f"Propose at least {MIN_CANDIDATES} materially different candidates.",
        )
    if len(plan.candidates) > MAX_CANDIDATES:
        raise PlanValidationError(
            f"plan contained {len(plan.candidates)} candidates",
            f"Propose at most {MAX_CANDIDATES} candidates.",
        )

    actions: list[CandidateAction] = []
    seen_families: set[ActionFamily] = set()
    for candidate in plan.candidates:
        parameters = _validate_parameters(candidate)
        actions.append(
            CandidateAction(
                action_id=new_id("action"),
                name=candidate.name,
                description=candidate.description or candidate.name,
                action_type=_FAMILY_TO_ACTION_TYPE[candidate.action_family],
                target=ActionTarget(service=candidate.service),
                expected_outcome=candidate.expected_outcome or "unstated",
                risk_class=candidate.risk_class,
                reversible=candidate.reversible,
                source=ActionSource(
                    kind=ActionSourceKind.PLANNER,
                    name="trueforge-planner",
                    rationale=candidate.rationale,
                ),
                parameters=parameters,
            )
        )
        seen_families.add(candidate.action_family)

    if len(seen_families) < MIN_CANDIDATES:
        raise PlanValidationError(
            "plan proposed variations of the same lever",
            "Your candidates must use materially different mechanisms, "
            "not several variations of one action family.",
        )
    return tuple(actions)


class TrueForgeCandidatePlanner:
    """Real ``CandidatePlanner`` port implementation backed by TrueForge."""

    def __init__(
        self,
        client: TrueForgeClient,
        *,
        model: str,
        bindings: InMemorySessionBindingStore,
        mcp_server_name: str = "branchpoint",
        read_only_tools: Sequence[str] = (),
        max_retries: int = MAX_PLAN_RETRIES,
    ) -> None:
        self._client = client
        self._model = model
        self._bindings = bindings
        self._mcp_server_name = mcp_server_name
        self._read_only_tools = tuple(read_only_tools)
        self._max_retries = max_retries

    def agent_spec(self) -> dict:
        """Build the inline TrueForge agent spec for the planner.

        Only read-only BRANCHPOINT tools are exposed, by literal name. The
        planner has no sandbox and no path to any mutation tool.
        """
        mcp_server: dict = {
            "name": self._mcp_server_name,
            "require_approval_for_tools": ["@write", "@destructive"],
        }
        if self._read_only_tools:
            mcp_server["enable_tools"] = list(self._read_only_tools)
            mcp_server["preload_tools"] = list(self._read_only_tools)
        else:
            mcp_server["enable_tools"] = ["@read-only"]

        return {
            "model": {"name": self._model},
            "instructions": PLANNER_INSTRUCTIONS,
            "mcp_servers": [mcp_server],
            "config": {
                "sandbox": {"enabled": False},
                "dynamic_sub_agents": {"enabled": False},
                "iteration_limit": 40,
            },
        }

    async def plan(
        self, incident: Incident, observed_state: ObservedState, *, run_id: str
    ) -> Sequence[CandidateAction]:
        """Run a TrueForge planning session and return validated candidate actions.

        ``run_id`` is the real ``BranchpointRun.run_id`` supplied by the
        orchestrator, so the planner session binds to the same run the world
        adversaries bind to.
        """
        session_id = await self._client.create_session(self.agent_spec())
        await self._bindings.upsert(
            run_id=run_id,
            purpose=SessionPurpose.PLANNER,
            trueforge_session_id=session_id,
            status=SessionStatus.ACTIVE,
        )

        message = (
            f"Objective: {incident.goal}\n\n"
            f"An incident has been reported: {incident.title}. "
            "Investigate the current production state with the available read-only tools "
            "and propose your candidate remediations."
        )

        feedback: str | None = None
        last_error: Exception | None = None

        for attempt in range(self._max_retries + 1):
            prompt = message if attempt == 0 else self._retry_message(feedback or "")
            result = await self._client.run_turn(session_id, prompt)
            await self._bindings.upsert(
                run_id=run_id,
                purpose=SessionPurpose.PLANNER,
                trueforge_session_id=session_id,
                last_turn_id=result.turn_id,
            )
            self._assert_turn_usable(result)

            try:
                payload = extract_json_object(result.output_text)
                plan = ProposedPlan.model_validate(payload)
                actions = validate_plan(plan)
            except (StructuredOutputError, PlanValidationError) as exc:
                last_error = exc
                feedback = exc.feedback
                continue
            except ValidationError as exc:
                last_error = exc
                feedback = f"Your JSON did not match the required shape: {exc.errors()[:3]}"
                continue

            await self._bindings.upsert(
                run_id=run_id,
                purpose=SessionPurpose.PLANNER,
                trueforge_session_id=session_id,
                status=SessionStatus.COMPLETED,
                last_turn_id=result.turn_id,
            )
            return actions

        await self._bindings.upsert(
            run_id=run_id,
            purpose=SessionPurpose.PLANNER,
            trueforge_session_id=session_id,
            status=SessionStatus.FAILED,
        )
        raise PlanValidationError(
            f"planner did not produce a valid plan after {self._max_retries + 1} attempts: "
            f"{last_error}"
        )

    @staticmethod
    def _retry_message(feedback: str) -> str:
        return (
            "Your previous reply was rejected by BRANCHPOINT's validator.\n\n"
            f"Problem: {feedback}\n\n"
            "Correct it and reply again with exactly one JSON object and nothing else."
        )

    @staticmethod
    def _assert_turn_usable(result: TurnResult) -> None:
        """Fail closed on a turn that errored, was cancelled, or paused for approval."""
        if result.status in (TurnStatus.ERROR, TurnStatus.CANCELLED):
            raise TurnFailedError(result.turn_id, result.status, result.error_detail)
        if result.is_paused_for_approval:
            raise TurnFailedError(
                result.turn_id,
                "paused",
                "planner attempted a tool call requiring approval; planners may not mutate",
            )
