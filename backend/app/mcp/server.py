"""BRANCHPOINT's MCP server: the demo reality surface exposed to MCP clients.

Every tool here is annotated explicitly — no tool ships without
``read_only_hint``/``destructive_hint`` set, because an ambiguous annotation is
itself a safety defect for any client (TrueForge, later) that classifies tools
by these hints. See :data:`READ_TOOL_ANNOTATIONS` and
:data:`DESTRUCTIVE_TOOL_ANNOTATIONS`.

BRANCHPOINT's own commit-capability gate (:mod:`app.infrastructure.demo.capability`)
is the actual authorization boundary for every destructive tool. MCP tool
annotations are hints for a client's UI, not an enforcement mechanism — the
capability check runs identically whether or not a client honors the hints,
and a destructive tool called with a missing, invalid, expired, replayed, or
mismatched capability is rejected the same way a direct Python call would be.
"""

from collections.abc import Callable
from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp_types import ToolAnnotations
from pydantic import BaseModel, Field

from app.domain.actions.models import ActionType
from app.domain.commits.models import CommitStatus
from app.domain.primitives import ScalarValue
from app.domain.runs.lifecycle import RunStatus
from app.domain.runs.models import BranchpointRun
from app.domain.worlds.models import World
from app.infrastructure.demo.actions import (
    FLAG_KEY_PARAM,
    TARGET_REPLICAS_PARAM,
    VERSION_PARAM,
)
from app.infrastructure.demo.capability import CapabilityError, CapabilityStore
from app.infrastructure.demo.counterexample import (
    CounterexampleSpec,
    SpecValidationError,
    reproduce,
)
from app.infrastructure.demo.dependencies import get_capability_store, get_demo_engine
from app.infrastructure.demo.engine import DemoProductionEngine
from app.infrastructure.demo.metrics import compute_metrics
from app.infrastructure.demo.state import DemoProductionState
from app.infrastructure.demo.workload import (
    DEPLOYMENT_SCHEMA_SUPPORT,
    PAYMENT_REVISION_INTRODUCED_IN_SCHEMA,
)

READ_TOOL_ANNOTATIONS = ToolAnnotations(
    read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)
DESTRUCTIVE_TOOL_ANNOTATIONS = ToolAnnotations(
    read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=False
)

#: Host/Origin values a local BRANCHPOINT deployment is ever legitimately
#: reached on. Bare and wildcard-port forms are both listed because different
#: clients omit the port for the default HTTP port and others always include it.
LOCAL_MCP_HOSTS = ["localhost", "localhost:*", "127.0.0.1", "127.0.0.1:*", "[::1]", "[::1]:*"]
LOCAL_MCP_ORIGINS = [f"http://{host}" for host in LOCAL_MCP_HOSTS]


def build_transport_security(*, insecure_localhost: bool = False) -> TransportSecuritySettings:
    """Build the MCP transport security policy.

    Defaults to DNS-rebinding Host/Origin validation restricted to localhost —
    the deployment-independent backstop for "only reachable from localhost":
    it rejects any request whose Host/Origin doesn't claim to be local,
    regardless of which interface the process happens to be bound to. It is
    not the authorization boundary for mutations (the one-time commit
    capability is — see :mod:`app.infrastructure.demo.capability`), but read
    tools have no capability gate, so this is what stands between them and
    the network.

    ``insecure_localhost=True`` disables validation entirely. Callers should
    only ever pass this from an explicit opt-in setting
    (``BRANCHPOINT_MCP_INSECURE_LOCALHOST``), never as a default, and even
    then this process should still only be bound to a loopback interface.
    """
    if insecure_localhost:
        return TransportSecuritySettings(enable_dns_rebinding_protection=False)
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=LOCAL_MCP_HOSTS,
        allowed_origins=LOCAL_MCP_ORIGINS,
    )


#: Literal names of every read-only tool, used to configure TrueForge agents by
#: explicit name rather than relying on the ``@read-only`` selector. See the
#: Code Mode note in the README: annotations are verified correct against
#: TrueForge 0.1.4, and naming tools literally is the belt-and-braces backup.
READ_ONLY_TOOL_NAMES: tuple[str, ...] = (
    "branchpoint_get_incident",
    "branchpoint_get_metrics",
    "branchpoint_get_deployment",
    "branchpoint_get_feature_flags",
    "branchpoint_get_schema",
    "branchpoint_get_orders_summary",
    "branchpoint_get_reality_state",
    "branchpoint_get_world",
    "branchpoint_get_world_action",
    "branchpoint_get_world_metrics",
    "branchpoint_get_world_orders_summary",
    "branchpoint_get_compatibility_context",
    "branchpoint_reproduce_counterexample",
)

#: Literal names of every destructive tool.
DESTRUCTIVE_TOOL_NAMES: tuple[str, ...] = (
    "branchpoint_disable_feature_flag",
    "branchpoint_set_deployment_version",
    "branchpoint_scale_service",
    "branchpoint_commit_recommended_world",
)

#: The single destructive tool the Phase 3 hero path uses.
COMMIT_TOOL_NAME = "branchpoint_commit_recommended_world"


#: Deployment versions this demo's mutation tools may set. Any other string is
#: rejected by the tool's own input schema before the handler ever runs.
DeploymentVersion = Literal["v2.40", "v2.41"]


# ----- response models -------------------------------------------------------


class IncidentSummary(BaseModel):
    """The current incident as derived from live reality, not a stored record."""

    breached: bool
    title: str
    checkout_error_rate: float
    checkout_error_rate_threshold: float
    affected_users: int
    affected_services: tuple[str, ...]


class MetricsSummary(BaseModel):
    """Every derived headline metric."""

    regression_active: bool
    checkout_error_rate: float
    checkout_p95_ms: float
    pricing_timeout_rate: float
    affected_users: int
    database_latency_ms: float
    checkout_cpu_utilization: float
    pricing_cpu_utilization: float
    daily_infra_cost_usd: float


class DeploymentSummary(BaseModel):
    """The deployed pricing-service version."""

    service: str
    version: str
    previous_version: str | None


class FeatureFlagSummary(BaseModel):
    """One demo feature flag."""

    key: str
    enabled: bool
    service: str


class FeatureFlagsSummary(BaseModel):
    """Every demo feature flag."""

    flags: tuple[FeatureFlagSummary, ...]


class SchemaSummary(BaseModel):
    """Orders schema version and deployment compatibility."""

    orders_schema_version: int
    payment_revision_introduced_in_schema: int
    deployment_schema_support: dict[str, int]


class OrdersSummary(BaseModel):
    """Aggregate order counts only — never raw order records or payment data."""

    total_orders: int
    orders_with_payment_revision: int
    orders_schema_version: int


class RealityStateSummary(BaseModel):
    """Every read-safe field of current reality, combined."""

    deployment: DeploymentSummary
    feature_flags: FeatureFlagsSummary
    capacity_replicas: int
    metrics: MetricsSummary
    orders: OrdersSummary


class MutationReceipt(BaseModel):
    """The result of a destructive tool call."""

    operation: str
    target: str
    succeeded: bool
    capability_id: str


class WorldSummary(BaseModel):
    """A counterfactual world as an agent sees it. Never reality."""

    world_id: str
    run_id: str
    status: str
    verdict: str | None
    action_name: str
    action_type: str
    evidence_count: int
    counterexample_count: int


class WorldActionSummary(BaseModel):
    """The exact action a world applied."""

    world_id: str
    action_id: str
    name: str
    action_type: str
    target_service: str
    parameters: dict[str, ScalarValue]
    reversible: bool
    risk_class: str


class WorldMetricsSummary(BaseModel):
    """Metrics measured inside one counterfactual world."""

    world_id: str
    metrics: MetricsSummary
    reality_metrics: MetricsSummary


class CompatibilityContext(BaseModel):
    """Version/schema facts an adversary needs to reason about compatibility.

    States what each deployment supports and what schema versions exist in the
    data. It deliberately does not draw the conclusion — connecting "this world
    runs an older deployment" to "these records need a newer schema" is the
    adversary's job.
    """

    world_id: str
    world_deployment_version: str
    reality_deployment_version: str
    deployment_schema_support: dict[str, int]
    orders_schema_version: int
    order_schema_versions_present: tuple[int, ...]
    fields_introduced_by_schema: dict[str, int]


class ReproductionOutcome(BaseModel):
    """The result of BRANCHPOINT replaying a counterexample spec."""

    world_id: str
    reproduced: bool
    detail: str
    evidence_id: str
    evidence_passed: bool
    machine_verifiable: bool


class CommitOutcome(BaseModel):
    """The result of committing the recommended world to reality."""

    run_id: str
    world_id: str
    action_id: str
    commit_status: str
    verification_status: str
    run_status: str
    detail: str


def _reality_state_summary(state: DemoProductionState) -> RealityStateSummary:
    metrics = compute_metrics(state)
    return RealityStateSummary(
        deployment=DeploymentSummary(
            service=state.pricing_deployment.service,
            version=state.pricing_deployment.version,
            previous_version=state.pricing_deployment.previous_version,
        ),
        feature_flags=FeatureFlagsSummary(
            flags=(
                FeatureFlagSummary(
                    key=state.pricing_flag.key,
                    enabled=state.pricing_flag.enabled,
                    service=state.pricing_flag.service,
                ),
            )
        ),
        capacity_replicas=state.pricing_capacity.replicas,
        metrics=MetricsSummary(**metrics.model_dump()),
        orders=OrdersSummary(
            total_orders=len(state.orders),
            orders_with_payment_revision=sum(
                1 for order in state.orders if order.payment_revision is not None
            ),
            orders_schema_version=state.orders_schema_version,
        ),
    )


async def _resolve_capability_run_and_world(
    capability_store: CapabilityStore, run_repository, capability_token: str
) -> tuple[BranchpointRun, World]:
    """Resolve which run/world a capability token names, without spending it."""
    try:
        capability = await capability_store.peek(capability_token)
    except CapabilityError as exc:
        raise ToolError(str(exc)) from exc

    run = await run_repository.get(capability.run_id)
    if run is None:
        raise ToolError(f"capability names run {capability.run_id}, which no longer exists")
    world = run.world(capability.world_id)
    if world is None:
        raise ToolError(
            f"capability names world {capability.world_id}, which does not exist on this run"
        )
    return run, world


def build_mcp_server(
    *,
    engine: DemoProductionEngine | None = None,
    capability_store: CapabilityStore | None = None,
    run_repository=None,
    orchestrator_factory: Callable[[], Any] | None = None,
    approval_actor: str = "human-via-trueforge",
) -> MCPServer:
    """Build the BRANCHPOINT MCP server bound to the process-wide demo singletons.

    Test callers may inject their own ``engine``/``capability_store``/
    ``run_repository`` for isolation; production code always resolves the
    shared process-wide instances so FastAPI, MCP, and the orchestrator's
    Phase 1 port adapters all observe and mutate the same state.
    """
    from app.api.dependencies import get_run_repository

    demo_engine = engine or get_demo_engine()
    demo_capability_store = capability_store or get_capability_store()
    demo_run_repository = run_repository or get_run_repository()
    orchestrator_factory = orchestrator_factory or _default_orchestrator_factory

    mcp = MCPServer(
        "branchpoint",
        title="BRANCHPOINT",
        version="0.1.0",
        instructions=(
            "Read and (with a valid one-time commit capability) mutate the BRANCHPOINT "
            "checkout demo production environment. Destructive tools require a capability "
            "token issued by a granted BRANCHPOINT approval; they reject any token that does "
            "not authorize exactly the run, world, action, and action content requested."
        ),
    )

    # ----- read tools ---------------------------------------------------------

    @mcp.tool(
        title="Get current incident",
        description="Describe the current checkout incident, derived live from reality.",
        annotations=READ_TOOL_ANNOTATIONS,
    )
    async def branchpoint_get_incident() -> IncidentSummary:
        state = await demo_engine.reality()
        metrics = compute_metrics(state)
        from app.infrastructure.demo.metrics import RECOVERY_SLO_ERROR_RATE_THRESHOLD

        breached = metrics.checkout_error_rate > RECOVERY_SLO_ERROR_RATE_THRESHOLD
        return IncidentSummary(
            breached=breached,
            title=(
                f"Checkout error rate at {metrics.checkout_error_rate:.1%}"
                if breached
                else "Checkout is within its recovery SLO"
            ),
            checkout_error_rate=metrics.checkout_error_rate,
            checkout_error_rate_threshold=RECOVERY_SLO_ERROR_RATE_THRESHOLD,
            affected_users=metrics.affected_users,
            affected_services=("checkout", state.pricing_deployment.service),
        )

    @mcp.tool(
        title="Get metrics",
        description="Return every derived headline metric for current reality.",
        annotations=READ_TOOL_ANNOTATIONS,
    )
    async def branchpoint_get_metrics() -> MetricsSummary:
        state = await demo_engine.reality()
        return MetricsSummary(**compute_metrics(state).model_dump())

    @mcp.tool(
        title="Get deployment",
        description="Return the current pricing-service deployment version.",
        annotations=READ_TOOL_ANNOTATIONS,
    )
    async def branchpoint_get_deployment() -> DeploymentSummary:
        state = await demo_engine.reality()
        return DeploymentSummary(
            service=state.pricing_deployment.service,
            version=state.pricing_deployment.version,
            previous_version=state.pricing_deployment.previous_version,
        )

    @mcp.tool(
        title="Get feature flags",
        description="Return every demo feature flag and its current state.",
        annotations=READ_TOOL_ANNOTATIONS,
    )
    async def branchpoint_get_feature_flags() -> FeatureFlagsSummary:
        state = await demo_engine.reality()
        return FeatureFlagsSummary(
            flags=(
                FeatureFlagSummary(
                    key=state.pricing_flag.key,
                    enabled=state.pricing_flag.enabled,
                    service=state.pricing_flag.service,
                ),
            )
        )

    @mcp.tool(
        title="Get orders schema",
        description="Return the orders schema version and deployment compatibility rules.",
        annotations=READ_TOOL_ANNOTATIONS,
    )
    async def branchpoint_get_schema() -> SchemaSummary:
        state = await demo_engine.reality()
        return SchemaSummary(
            orders_schema_version=state.orders_schema_version,
            payment_revision_introduced_in_schema=PAYMENT_REVISION_INTRODUCED_IN_SCHEMA,
            deployment_schema_support=dict(DEPLOYMENT_SCHEMA_SUPPORT),
        )

    @mcp.tool(
        title="Get orders summary",
        description="Return aggregate order counts. Never returns raw order records.",
        annotations=READ_TOOL_ANNOTATIONS,
    )
    async def branchpoint_get_orders_summary() -> OrdersSummary:
        state = await demo_engine.reality()
        return OrdersSummary(
            total_orders=len(state.orders),
            orders_with_payment_revision=sum(
                1 for order in state.orders if order.payment_revision is not None
            ),
            orders_schema_version=state.orders_schema_version,
        )

    @mcp.tool(
        title="Get reality state",
        description="Return every read-safe field of current reality, combined.",
        annotations=READ_TOOL_ANNOTATIONS,
    )
    async def branchpoint_get_reality_state() -> RealityStateSummary:
        state = await demo_engine.reality()
        return _reality_state_summary(state)

    # ----- counterfactual world inspection (read-only) --------------------------
    #
    # COUNTERFACTUAL WORLD != REALITY. These tools read world snapshots only.
    # None of them can mutate anything, and none names the defect an adversary
    # is meant to discover.

    async def _require_world(run_id: str, world_id: str):
        run = await demo_run_repository.get(run_id)
        if run is None:
            raise ToolError(f"run {run_id} does not exist")
        world = run.world(world_id)
        if world is None:
            raise ToolError(f"run {run_id} has no world {world_id}")
        return run, world

    @mcp.tool(
        title="Get counterfactual world",
        description=(
            "Inspect one counterfactual world: its status, verdict, and the action it "
            "applied. This is a simulated branch, never production reality."
        ),
        annotations=READ_TOOL_ANNOTATIONS,
    )
    async def branchpoint_get_world(run_id: str, world_id: str) -> WorldSummary:
        _, world = await _require_world(run_id, world_id)
        return WorldSummary(
            world_id=world.world_id,
            run_id=world.run_id,
            status=str(world.status),
            verdict=str(world.verdict) if world.verdict else None,
            action_name=world.candidate_action.name,
            action_type=str(world.candidate_action.action_type),
            evidence_count=len(world.evidence),
            counterexample_count=len(world.counterexamples),
        )

    @mcp.tool(
        title="Get counterfactual world action",
        description="Return the exact candidate action a counterfactual world applied.",
        annotations=READ_TOOL_ANNOTATIONS,
    )
    async def branchpoint_get_world_action(run_id: str, world_id: str) -> WorldActionSummary:
        _, world = await _require_world(run_id, world_id)
        action = world.candidate_action
        return WorldActionSummary(
            world_id=world.world_id,
            action_id=action.action_id,
            name=action.name,
            action_type=str(action.action_type),
            target_service=action.target.service,
            parameters=dict(action.parameters),
            reversible=action.reversible,
            risk_class=str(action.risk_class),
        )

    @mcp.tool(
        title="Get counterfactual world metrics",
        description=(
            "Return metrics measured inside a counterfactual world, alongside current "
            "reality metrics for comparison."
        ),
        annotations=READ_TOOL_ANNOTATIONS,
    )
    async def branchpoint_get_world_metrics(run_id: str, world_id: str) -> WorldMetricsSummary:
        await _require_world(run_id, world_id)
        world_state = await demo_engine.world_state(world_id)
        reality = await demo_engine.reality()
        return WorldMetricsSummary(
            world_id=world_id,
            metrics=MetricsSummary(**compute_metrics(world_state).model_dump()),
            reality_metrics=MetricsSummary(**compute_metrics(reality).model_dump()),
        )

    @mcp.tool(
        title="Get counterfactual world orders summary",
        description=(
            "Aggregate order counts inside a counterfactual world, grouped by the version "
            "that created them. Never returns raw order records or payment data."
        ),
        annotations=READ_TOOL_ANNOTATIONS,
    )
    async def branchpoint_get_world_orders_summary(run_id: str, world_id: str) -> OrdersSummary:
        await _require_world(run_id, world_id)
        state = await demo_engine.world_state(world_id)
        return OrdersSummary(
            total_orders=len(state.orders),
            orders_with_payment_revision=sum(
                1 for order in state.orders if order.payment_revision is not None
            ),
            orders_schema_version=state.orders_schema_version,
        )

    @mcp.tool(
        title="Get compatibility context",
        description=(
            "Return version and schema facts for a counterfactual world: which orders "
            "schema each deployment supports, which schema versions exist in the data, "
            "and which schema introduced which field. Draws no conclusions."
        ),
        annotations=READ_TOOL_ANNOTATIONS,
    )
    async def branchpoint_get_compatibility_context(
        run_id: str, world_id: str
    ) -> CompatibilityContext:
        await _require_world(run_id, world_id)
        state = await demo_engine.world_state(world_id)
        reality = await demo_engine.reality()
        return CompatibilityContext(
            world_id=world_id,
            world_deployment_version=state.pricing_deployment.version,
            reality_deployment_version=reality.pricing_deployment.version,
            deployment_schema_support=dict(DEPLOYMENT_SCHEMA_SUPPORT),
            orders_schema_version=state.orders_schema_version,
            order_schema_versions_present=tuple(
                sorted({order.schema_version for order in state.orders})
            ),
            fields_introduced_by_schema={"payment_revision": PAYMENT_REVISION_INTRODUCED_IN_SCHEMA},
        )

    @mcp.tool(
        title="Reproduce counterexample",
        description=(
            "Replay a structured counterexample against a counterfactual world's isolated "
            "snapshot and report whether BRANCHPOINT reproduces it. Operates only on the "
            "world, never on reality, and executes no caller-supplied code."
        ),
        annotations=READ_TOOL_ANNOTATIONS,
    )
    async def branchpoint_reproduce_counterexample(
        run_id: str, world_id: str, spec: CounterexampleSpec
    ) -> ReproductionOutcome:
        await _require_world(run_id, world_id)
        if spec.target_world_id != world_id:
            raise ToolError(
                f"spec targets world {spec.target_world_id!r} but was submitted for {world_id!r}"
            )
        state = await demo_engine.world_state(world_id)
        try:
            result = reproduce(spec, state)
        except SpecValidationError as exc:
            raise ToolError(str(exc)) from exc

        evidence = result.evidence[0]
        return ReproductionOutcome(
            world_id=world_id,
            reproduced=result.reproduced,
            detail=result.detail,
            evidence_id=evidence.evidence_id,
            evidence_passed=bool(evidence.passed),
            machine_verifiable=evidence.machine_verifiable,
        )

    # ----- destructive reality tools -------------------------------------------
    #
    # COUNTERFACTUAL WORLD != REALITY: these tools mutate reality only, and only
    # with a valid one-time capability. They never accept a world id — a world
    # is inspected and mutated exclusively through BRANCHPOINT's own isolated
    # WorldExecutor adapter, never through MCP.

    @mcp.tool(
        title="Disable feature flag",
        description=(
            "Disable a demo feature flag in reality. Requires a commit capability token "
            "issued for a FEATURE_FLAG_DISABLE action matching this exact flag."
        ),
        annotations=DESTRUCTIVE_TOOL_ANNOTATIONS,
    )
    async def branchpoint_disable_feature_flag(
        capability_token: str, flag_key: Literal["PRICING_V2"]
    ) -> MutationReceipt:
        run, world = await _resolve_capability_run_and_world(
            demo_capability_store, demo_run_repository, capability_token
        )
        action = world.candidate_action
        if action.action_type is not ActionType.FEATURE_FLAG_DISABLE:
            raise ToolError("this capability does not authorize a FEATURE_FLAG_DISABLE action")
        if action.parameters.get(FLAG_KEY_PARAM) != flag_key:
            raise ToolError(
                f"this capability authorizes flag_key={action.parameters.get(FLAG_KEY_PARAM)!r}"
            )

        receipts = await demo_engine.apply_to_reality(
            run=run,
            world=world,
            capability_store=demo_capability_store,
            capability_token=capability_token,
        )
        return _first_receipt(receipts)

    @mcp.tool(
        title="Set deployment version",
        description=(
            "Set the pricing-service deployment version in reality. Requires a commit "
            "capability token issued for a ROLLBACK action matching this exact version."
        ),
        annotations=DESTRUCTIVE_TOOL_ANNOTATIONS,
    )
    async def branchpoint_set_deployment_version(
        capability_token: str,
        service: Literal["pricing-service"],
        version: DeploymentVersion,
    ) -> MutationReceipt:
        run, world = await _resolve_capability_run_and_world(
            demo_capability_store, demo_run_repository, capability_token
        )
        action = world.candidate_action
        if action.action_type is not ActionType.ROLLBACK:
            raise ToolError("this capability does not authorize a ROLLBACK action")
        if action.target.service != service:
            raise ToolError(f"this capability authorizes service={action.target.service!r}")
        if action.parameters.get(VERSION_PARAM) != version:
            raise ToolError(
                f"this capability authorizes version={action.parameters.get(VERSION_PARAM)!r}"
            )

        receipts = await demo_engine.apply_to_reality(
            run=run,
            world=world,
            capability_store=demo_capability_store,
            capability_token=capability_token,
        )
        return _first_receipt(receipts)

    @mcp.tool(
        title="Scale service",
        description=(
            "Set pricing-service replica count in reality. Requires a commit capability "
            "token issued for a SCALE action matching this exact replica count."
        ),
        annotations=DESTRUCTIVE_TOOL_ANNOTATIONS,
    )
    async def branchpoint_scale_service(
        capability_token: str,
        service: Literal["pricing-service"],
        target_replicas: Annotated[int, Field(ge=1, le=50)],
    ) -> MutationReceipt:
        run, world = await _resolve_capability_run_and_world(
            demo_capability_store, demo_run_repository, capability_token
        )
        action = world.candidate_action
        if action.action_type is not ActionType.SCALE:
            raise ToolError("this capability does not authorize a SCALE action")
        if action.target.service != service:
            raise ToolError(f"this capability authorizes service={action.target.service!r}")
        if action.parameters.get(TARGET_REPLICAS_PARAM) != target_replicas:
            raise ToolError(
                f"this capability authorizes target_replicas={action.parameters.get(TARGET_REPLICAS_PARAM)!r}"
            )

        receipts = await demo_engine.apply_to_reality(
            run=run,
            world=world,
            capability_store=demo_capability_store,
            capability_token=capability_token,
        )
        return _first_receipt(receipts)

    @mcp.tool(
        title="Commit recommended world",
        description=(
            "Apply the deterministically recommended world's action to production reality, "
            "then independently verify the result. Requires the run to be awaiting approval "
            "with this exact world recommended. This is the only tool an agent should use to "
            "change reality; it never exposes a capability token."
        ),
        annotations=DESTRUCTIVE_TOOL_ANNOTATIONS,
    )
    async def branchpoint_commit_recommended_world(
        run_id: str, world_id: str, expected_action_id: str | None = None
    ) -> CommitOutcome:
        run = await demo_run_repository.get(run_id)
        if run is None:
            raise ToolError(f"run {run_id} does not exist")
        if run.status is not RunStatus.AWAITING_APPROVAL:
            raise ToolError(
                f"run {run_id} is {run.status}; only a run awaiting approval may be committed"
            )
        if run.comparison is None or run.comparison.recommended_world_id != world_id:
            recommended = run.comparison.recommended_world_id if run.comparison else None
            raise ToolError(
                f"world {world_id} is not the recommended world for run {run_id} "
                f"(recommended: {recommended})"
            )

        world = run.require_world(world_id)
        if (
            expected_action_id is not None
            and world.candidate_action.action_id != expected_action_id
        ):
            raise ToolError(
                f"world {world_id} carries action {world.candidate_action.action_id}, "
                f"not the expected {expected_action_id}"
            )

        orchestrator = orchestrator_factory()
        # Reaching this line means TrueForge already paused this destructive
        # tool call and a human explicitly allowed it. That human decision is
        # what we record here, bound by Phase 1 to this exact world and to a
        # content fingerprint of this exact action.
        run = await orchestrator.decide_approval(
            run_id,
            approved=True,
            actor=approval_actor,
            reason="approved by human via TrueForge tool approval",
        )
        run = await orchestrator.commit(run.run_id)
        commit_status = run.commit_receipt.status if run.commit_receipt else CommitStatus.FAILED

        verification_status = "NOT_RUN"
        if commit_status is CommitStatus.SUCCEEDED:
            run = await orchestrator.verify(run.run_id)
            verification_status = str(run.verification.status) if run.verification else "NOT_RUN"

        return CommitOutcome(
            run_id=run.run_id,
            world_id=world_id,
            action_id=world.candidate_action.action_id,
            commit_status=str(commit_status),
            verification_status=verification_status,
            run_status=str(run.status),
            detail=(
                "committed and independently verified"
                if str(run.status) == "SUCCEEDED"
                else f"run ended {run.status}: {run.failure_reason or 'see verification'}"
            ),
        )

    return mcp


def _default_orchestrator_factory() -> Any:
    """Build the process-wide demo orchestrator used by the commit tool."""
    from app.api.dependencies import get_demo_orchestrator, get_event_sink, get_run_repository

    return get_demo_orchestrator(get_run_repository(), get_event_sink())


def _first_receipt(receipts: tuple) -> MutationReceipt:
    receipt = receipts[0]
    return MutationReceipt(
        operation=receipt.operation,
        target=receipt.target,
        succeeded=receipt.succeeded,
        capability_id=receipt.reference or "",
    )


__all__ = [
    "COMMIT_TOOL_NAME",
    "DESTRUCTIVE_TOOL_ANNOTATIONS",
    "DESTRUCTIVE_TOOL_NAMES",
    "READ_ONLY_TOOL_NAMES",
    "READ_TOOL_ANNOTATIONS",
    "build_mcp_server",
    "build_transport_security",
]
