"""``AdversarialTester`` backed by a real TrueForge agent and its subagents.

For each world, a TrueForge session is created and instructed to delegate the
attack to a **subagent** — TrueForge's real ``dynamic_sub_agents`` mechanism —
which investigates with read-only world tools and a sandbox. Whatever the
subagent finds is exploratory only. The single authoritative step is
BRANCHPOINT replaying a typed :class:`CounterexampleSpec` against the world's
own isolated snapshot.

Fail-closed is the rule throughout: TrueForge unavailable, a model timeout, a
sandbox failure, or malformed output all raise, and the Phase 1 orchestrator
turns that into an ``INCONCLUSIVE`` world. None of them can produce
``SURVIVED``.
"""

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.domain.evidence.models import Evidence, EvidenceKind, EvidenceSeverity
from app.domain.primitives import new_id, utc_now
from app.domain.worlds.models import (
    AdversarialReport,
    Counterexample,
    CounterexampleStatus,
    World,
)
from app.infrastructure.demo.counterexample import (
    CounterexampleAssertion,
    CounterexampleSpec,
    OrderSelector,
    ReproductionResult,
    SpecValidationError,
    reproduce,
    validate_spec,
)
from app.infrastructure.demo.engine import DemoProductionEngine
from app.infrastructure.trueforge.client import TrueForgeClient
from app.infrastructure.trueforge.errors import (
    StructuredOutputError,
    TrueForgeError,
    TurnFailedError,
)
from app.infrastructure.trueforge.models import TurnResult, TurnStatus
from app.infrastructure.trueforge.planner import extract_json_object
from app.infrastructure.trueforge.prompts import doppelganger_instructions
from app.infrastructure.trueforge.sessions import (
    InMemorySessionBindingStore,
    SessionPurpose,
    SessionStatus,
)

#: World-inspection tools the DOPPELGÄNGER may use. All read-only; none can
#: reach reality, and none announces the hidden defect.
DOPPELGANGER_TOOLS: tuple[str, ...] = (
    "branchpoint_get_world",
    "branchpoint_get_world_metrics",
    "branchpoint_get_world_action",
    "branchpoint_get_world_orders_summary",
    "branchpoint_get_compatibility_context",
    "branchpoint_get_metrics",
    "branchpoint_get_deployment",
    "branchpoint_get_schema",
)


class ProposedSetup(BaseModel):
    """Order selection as proposed by the adversary."""

    model_config = ConfigDict(extra="ignore")

    created_under_version: str | None = None
    min_schema_version: int | None = None
    order_id: str | None = None


class ProposedAssertion(BaseModel):
    """Assertion as proposed by the adversary."""

    model_config = ConfigDict(extra="ignore")

    kind: str
    check_name: str | None = None
    metric: str | None = None
    threshold: float | None = None


class ProposedCounterexample(BaseModel):
    """A counterexample exactly as proposed, before BRANCHPOINT validates it."""

    model_config = ConfigDict(extra="ignore")

    counterexample_type: str
    operation: str
    expected: str = Field(min_length=1, max_length=500)
    rationale: str = Field(default="", max_length=2000)
    assertion: ProposedAssertion
    setup: ProposedSetup = Field(default_factory=ProposedSetup)


class ProposedAttack(BaseModel):
    """The whole bounded JSON object an adversarial turn must produce."""

    model_config = ConfigDict(extra="ignore")

    hypothesis: str = Field(default="", max_length=2000)
    investigated: str = Field(default="", max_length=4000)
    counterexample: ProposedCounterexample | None = None


class TrueForgeAdversarialTester:
    """Real ``AdversarialTester`` port implementation backed by TrueForge."""

    def __init__(
        self,
        client: TrueForgeClient,
        engine: DemoProductionEngine,
        *,
        model: str,
        bindings: InMemorySessionBindingStore,
        mcp_server_name: str = "branchpoint",
        sandbox_enabled: bool = True,
    ) -> None:
        self._client = client
        self._engine = engine
        self._model = model
        self._bindings = bindings
        self._mcp_server_name = mcp_server_name
        self._sandbox_enabled = sandbox_enabled

    def agent_spec(self, world_id: str) -> dict:
        """Build the inline TrueForge agent spec for one world's adversary.

        Subagents are enabled (the DOPPELGÄNGER is delegated to one) and a
        sandbox is provided for exploration. Only read-only world-inspection
        tools are exposed, by literal name — no mutation tool is reachable from
        this session at all, so the Code Mode destructive-classification issue
        cannot apply to it.
        """
        return {
            "model": {"name": self._model, "params": {"temperature": 0}},
            "instructions": doppelganger_instructions(world_id),
            "mcp_servers": [
                {
                    "name": self._mcp_server_name,
                    "enable_tools": list(DOPPELGANGER_TOOLS),
                    "preload_tools": list(DOPPELGANGER_TOOLS),
                    "require_approval_for_tools": ["@write", "@destructive"],
                }
            ],
            "config": {
                "sandbox": {"enabled": self._sandbox_enabled},
                "dynamic_sub_agents": {"enabled": True},
                "iteration_limit": 60,
            },
        }

    async def attack(self, world: World) -> AdversarialReport:
        """Attack ``world`` via a TrueForge subagent, then replay its finding.

        Any failure raises: the orchestrator converts that into an
        ``INCONCLUSIVE`` verdict, never ``SURVIVED``.
        """
        session_id = await self._client.create_session(self.agent_spec(world.world_id))
        await self._bindings.upsert(
            run_id=world.run_id,
            world_id=world.world_id,
            purpose=SessionPurpose.ADVERSARY,
            trueforge_session_id=session_id,
            status=SessionStatus.ACTIVE,
        )

        result = await self._client.run_turn(session_id, self._attack_message(world))
        await self._bindings.upsert(
            run_id=world.run_id,
            world_id=world.world_id,
            purpose=SessionPurpose.ADVERSARY,
            trueforge_session_id=session_id,
            last_turn_id=result.turn_id,
        )
        self._assert_turn_usable(result)

        attack = self._parse_attack(result)
        sandbox_evidence = self._sandbox_evidence(world, result)

        if attack.counterexample is None:
            # An honest "I found nothing replayable". Recorded, never a veto,
            # and never mistaken for proof of safety either.
            return AdversarialReport(
                counterexamples=(
                    self._counterexample(
                        world,
                        title="No replayable counterexample found",
                        hypothesis=attack.hypothesis or "adversary reported no finding",
                        status=CounterexampleStatus.NOT_REPRODUCED,
                        evidence_ids=tuple(item.evidence_id for item in sandbox_evidence),
                    ),
                ),
                evidence=sandbox_evidence,
            )

        try:
            spec = self._build_spec(world.world_id, attack.counterexample)
        except (ValidationError, SpecValidationError, ValueError) as exc:
            # Malformed spec: recorded as an ERROR attack, never a veto.
            return AdversarialReport(
                counterexamples=(
                    self._counterexample(
                        world,
                        title="Malformed counterexample rejected",
                        hypothesis=f"{attack.hypothesis} (rejected: {exc})",
                        status=CounterexampleStatus.ERROR,
                        evidence_ids=tuple(item.evidence_id for item in sandbox_evidence),
                    ),
                ),
                evidence=sandbox_evidence,
            )

        replay = await self._replay(world, spec)
        status = (
            CounterexampleStatus.REPRODUCED
            if replay.reproduced
            else CounterexampleStatus.NOT_REPRODUCED
        )
        evidence = sandbox_evidence + replay.evidence

        await self._bindings.upsert(
            run_id=world.run_id,
            world_id=world.world_id,
            purpose=SessionPurpose.ADVERSARY,
            trueforge_session_id=session_id,
            status=SessionStatus.COMPLETED,
            last_turn_id=result.turn_id,
        )

        return AdversarialReport(
            counterexamples=(
                self._counterexample(
                    world,
                    title=self._title_for(spec, replay),
                    hypothesis=attack.hypothesis or spec.rationale,
                    status=status,
                    evidence_ids=tuple(item.evidence_id for item in replay.evidence),
                    reproduction_steps=self._steps_for(spec),
                ),
            ),
            evidence=evidence,
        )

    async def _replay(self, world: World, spec: CounterexampleSpec) -> ReproductionResult:
        """Replay a spec against this world's isolated snapshot. Never reality."""
        state = await self._engine.world_state(world.world_id)
        return reproduce(spec, state)

    def _attack_message(self, world: World) -> str:
        action = world.candidate_action
        return (
            f"Attack counterfactual world `{world.world_id}`.\n\n"
            f"It applied this proposed action: {action.name} "
            f"(type {action.action_type}, target {action.target.service}, "
            f"parameters {dict(action.parameters)}).\n\n"
            "Delegate the adversarial investigation to a subagent. That subagent should "
            "inspect the world with the read-only tools, use its sandbox to test its "
            "hypothesis against the data it gathers, and report back. Then reply with "
            "the single JSON object described in your instructions."
        )

    @staticmethod
    def _parse_attack(result: TurnResult) -> ProposedAttack:
        payload = extract_json_object(result.output_text)
        try:
            return ProposedAttack.model_validate(payload)
        except ValidationError as exc:
            raise StructuredOutputError(
                f"adversary output did not match the required shape: {exc.errors()[:3]}"
            ) from exc

    @staticmethod
    def _build_spec(world_id: str, proposed: ProposedCounterexample) -> CounterexampleSpec:
        """Validate a proposed counterexample into the typed replay spec.

        Enum coercion happens here: an unknown operation or assertion kind
        fails validation rather than being mapped onto something plausible.
        """
        spec = CounterexampleSpec(
            counterexample_type=proposed.counterexample_type,
            target_world_id=world_id,
            operation=proposed.operation,
            assertion=CounterexampleAssertion(
                kind=proposed.assertion.kind,
                check_name=proposed.assertion.check_name,
                metric=proposed.assertion.metric,
                threshold=proposed.assertion.threshold,
            ),
            setup=OrderSelector(
                created_under_version=proposed.setup.created_under_version,
                min_schema_version=proposed.setup.min_schema_version,
                order_id=proposed.setup.order_id,
            ),
            expected=proposed.expected,
            rationale=proposed.rationale or proposed.expected,
        )
        # Validate eagerly so an unreplayable check name or metric is rejected
        # here — recorded as an ERROR attack — rather than surfacing later as an
        # exception from the replay engine. Both malformed-operation and
        # malformed-assertion therefore fail the same, visible way.
        validate_spec(spec)
        return spec

    def _sandbox_evidence(self, world: World, result: TurnResult) -> tuple[Evidence, ...]:
        """Record that sandbox exploration happened, as non-verifiable context.

        Sandbox artifacts are explicitly ``machine_verifiable=False``: they are
        useful provenance for a human, and they can never contribute to a veto.
        """
        if not result.sandbox_ids and not result.subagent_thread_ids:
            return ()
        return (
            Evidence(
                evidence_id=new_id("evidence"),
                kind=EvidenceKind.COUNTEREXAMPLE,
                source="trueforge-doppelganger",
                claim="adversarial exploration performed in a TrueForge sandbox",
                world_id=world.world_id,
                observed=(
                    f"subagents={len(result.subagent_thread_ids)} "
                    f"sandboxes={len(result.sandbox_ids)} "
                    f"tools={len(result.tools_called())}"
                ),
                expected="exploratory only; not authoritative",
                passed=None,
                severity=EvidenceSeverity.INFO,
                machine_verifiable=False,
                artifact=f"trueforge:session/{result.session_id}/turn/{result.turn_id}",
                recorded_at=utc_now(),
            ),
        )

    @staticmethod
    def _counterexample(
        world: World,
        *,
        title: str,
        hypothesis: str,
        status: CounterexampleStatus,
        evidence_ids: tuple[str, ...] = (),
        reproduction_steps: tuple[str, ...] = (),
    ) -> Counterexample:
        return Counterexample(
            attack_id=new_id("attack"),
            world_id=world.world_id,
            title=title,
            hypothesis=hypothesis,
            created_at=utc_now(),
            reproduction_steps=reproduction_steps,
            evidence_ids=evidence_ids,
            status=status,
        )

    @staticmethod
    def _title_for(spec: CounterexampleSpec, replay: ReproductionResult) -> str:
        prefix = "Reproduced" if replay.reproduced else "Not reproduced"
        return f"{prefix}: {spec.counterexample_type} via {spec.operation}"

    @staticmethod
    def _steps_for(spec: CounterexampleSpec) -> tuple[str, ...]:
        return (
            f"select order matching {spec.setup.model_dump(exclude_none=True)}",
            f"apply operation {spec.operation}",
            f"assert {spec.assertion.kind} {spec.assertion.check_name or spec.assertion.metric}",
        )

    @staticmethod
    def _assert_turn_usable(result: TurnResult) -> None:
        """Fail closed on an errored, cancelled, or approval-paused adversarial turn."""
        if result.status in (TurnStatus.ERROR, TurnStatus.CANCELLED):
            raise TurnFailedError(result.turn_id, result.status, result.error_detail)
        if result.is_paused_for_approval:
            raise TrueForgeError(
                "adversary attempted a tool call requiring approval; adversaries may not mutate"
            )
