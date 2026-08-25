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

from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations
from pydantic import BaseModel, Field

from app.domain.actions.models import ActionType
from app.domain.runs.models import BranchpointRun
from app.domain.worlds.models import World
from app.infrastructure.demo.actions import (
    FLAG_KEY_PARAM,
    TARGET_REPLICAS_PARAM,
    VERSION_PARAM,
)
from app.infrastructure.demo.capability import CapabilityError, CapabilityStore
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

    return mcp


def _first_receipt(receipts: tuple) -> MutationReceipt:
    receipt = receipts[0]
    return MutationReceipt(
        operation=receipt.operation,
        target=receipt.target,
        succeeded=receipt.succeeded,
        capability_id=receipt.reference or "",
    )


__all__ = ["build_mcp_server", "READ_TOOL_ANNOTATIONS", "DESTRUCTIVE_TOOL_ANNOTATIONS"]
