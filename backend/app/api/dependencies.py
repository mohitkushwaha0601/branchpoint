"""Composition root for the HTTP boundary.

The plain ``/api/v1/runs`` endpoints wire the orchestrator with in-memory
storage only. No planner, executor, adversarial tester, mutator, or verifier
is configured for it, so any step needing one fails loudly rather than
pretending it ran — that default is deliberate and unrelated to the demo
wiring below.

The demo endpoints wire a *second* orchestrator that shares the same run
repository and event sink but adds the Phase 2 demo adapters (deterministic
hero planner/executor/attacker, plus the demo reality reader/mutator/
verifier). Both orchestrators observe and mutate the same runs, because both
resolve ``get_run_repository``/``get_event_sink`` — process-wide singletons —
rather than constructing their own storage.
"""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from app.application.orchestration.approval import ApprovalCoordinator
from app.application.orchestration.orchestrator import BranchpointOrchestrator
from app.application.orchestration.task_runner import BackgroundTaskRunner
from app.infrastructure.demo.adapters import (
    DemoRealityMutator,
    DemoRealityReader,
    DemoRealityVerifier,
    DemoWorldExecutor,
)
from app.infrastructure.demo.dependencies import get_capability_store, get_demo_engine
from app.infrastructure.demo.hero import HeroAdversarialTester, HeroCandidatePlanner
from app.infrastructure.persistence.memory import InMemoryEventSink, InMemoryRunRepository
from app.infrastructure.trueforge.adversary import TrueForgeAdversarialTester
from app.infrastructure.trueforge.client import TrueForgeClient
from app.infrastructure.trueforge.commit_operator import TrueForgeCommitOperator
from app.infrastructure.trueforge.planner import PLANNER_TOOLS, TrueForgeCandidatePlanner
from app.infrastructure.trueforge.sessions import InMemorySessionBindingStore


@lru_cache
def get_run_repository() -> InMemoryRunRepository:
    """Return the process-wide in-memory run store."""
    return InMemoryRunRepository()


@lru_cache
def get_event_sink() -> InMemoryEventSink:
    """Return the process-wide in-memory event collector."""
    return InMemoryEventSink()


def get_orchestrator(
    repository: Annotated[InMemoryRunRepository, Depends(get_run_repository)],
    events: Annotated[InMemoryEventSink, Depends(get_event_sink)],
) -> BranchpointOrchestrator:
    """Build a bare orchestrator for the request: no adapters configured."""
    return BranchpointOrchestrator(repository=repository, events=events)


def get_demo_orchestrator(
    repository: Annotated[InMemoryRunRepository, Depends(get_run_repository)],
    events: Annotated[InMemoryEventSink, Depends(get_event_sink)],
) -> BranchpointOrchestrator:
    """Build an orchestrator wired with the deterministic Phase 2 demo adapters.

    ``HeroCandidatePlanner`` and ``HeroAdversarialTester`` are demo test
    adapters, not AI — see :mod:`app.infrastructure.demo.hero`.
    """
    engine = get_demo_engine()
    capability_store = get_capability_store()
    return BranchpointOrchestrator(
        repository=repository,
        events=events,
        reality_reader=DemoRealityReader(engine),
        planner=HeroCandidatePlanner(),
        world_executor=DemoWorldExecutor(engine),
        adversarial_tester=HeroAdversarialTester(engine),
        mutator=DemoRealityMutator(engine, capability_store),
        verifier=DemoRealityVerifier(engine),
    )


RunRepositoryDep = Annotated[InMemoryRunRepository, Depends(get_run_repository)]
EventSinkDep = Annotated[InMemoryEventSink, Depends(get_event_sink)]
OrchestratorDep = Annotated[BranchpointOrchestrator, Depends(get_orchestrator)]
DemoOrchestratorDep = Annotated[BranchpointOrchestrator, Depends(get_demo_orchestrator)]


@lru_cache
def get_background_runner() -> BackgroundTaskRunner:
    """Return the process-wide runner that owns in-flight agent-run drives.

    Process-wide because the run repository it writes through is too: a second
    backend process would have neither this runner's tasks nor those runs.
    **One process is the deployment requirement.**
    """
    return BackgroundTaskRunner()


@lru_cache
def get_session_binding_store() -> InMemorySessionBindingStore:
    """Return the process-wide TrueForge session binding store."""
    return InMemorySessionBindingStore()


@lru_cache
def get_trueforge_client() -> TrueForgeClient:
    """Return the process-wide TrueForge HTTP client."""
    from app.core.config import get_settings

    return TrueForgeClient(base_url=get_settings().trueforge_base_url)


def build_agent_orchestrator() -> BranchpointOrchestrator:
    """Build an orchestrator wired with the **real** TrueForge planner and adversary.

    This is the Phase 3 path. It shares the demo engine, capability store, run
    repository, and event sink with every other surface, and differs from the
    Phase 2 demo orchestrator only in that planning and adversarial testing are
    performed by TrueForge agents rather than deterministic demo fixtures.
    """
    from app.core.config import get_settings

    settings = get_settings()
    # Resolved once, here, and handed to both agents: the planner and every
    # DOPPELGÄNGER in a run always speak to the same model. Neither adapter
    # reads the environment itself.
    model = settings.resolve_model()
    engine = get_demo_engine()
    capability_store = get_capability_store()
    client = get_trueforge_client()
    bindings = get_session_binding_store()

    return BranchpointOrchestrator(
        repository=get_run_repository(),
        events=get_event_sink(),
        reality_reader=DemoRealityReader(engine),
        planner=TrueForgeCandidatePlanner(
            client,
            model=model,
            bindings=bindings,
            mcp_server_name=settings.trueforge_mcp_server_name,
            read_only_tools=PLANNER_TOOLS,
        ),
        world_executor=DemoWorldExecutor(engine),
        adversarial_tester=TrueForgeAdversarialTester(
            client,
            engine,
            model=model,
            bindings=bindings,
            mcp_server_name=settings.trueforge_mcp_server_name,
            sandbox_enabled=settings.trueforge_sandbox_enabled,
            skill_name=settings.trueforge_skill_name,
        ),
        mutator=DemoRealityMutator(engine, capability_store),
        verifier=DemoRealityVerifier(engine),
    )


def build_commit_operator() -> TrueForgeCommitOperator:
    """Build the TrueForge agent that carries out one approved commit."""
    from app.core.config import get_settings

    settings = get_settings()
    return TrueForgeCommitOperator(
        get_trueforge_client(),
        model=settings.resolve_model(),
        bindings=get_session_binding_store(),
        mcp_server_name=settings.trueforge_mcp_server_name,
    )


def build_approval_coordinator() -> ApprovalCoordinator:
    """Build the coordinator behind ``POST /api/v1/runs/{run_id}/approval``.

    Deliberately wired to the *demo* orchestrator, not the agent one: recording
    the human decision and running the Phase 1 mutate/verify steps needs the
    reality adapters, not a planner or an adversary. Both orchestrators share
    the process-wide run repository and event sink, so this observes and
    advances exactly the run ``POST /api/v1/agent-runs`` created.
    """
    repository = get_run_repository()
    events = get_event_sink()
    return ApprovalCoordinator(
        orchestrator=get_demo_orchestrator(repository, events),
        repository=repository,
        events=events,
        commit_operator=build_commit_operator(),
    )


SessionBindingStoreDep = Annotated[InMemorySessionBindingStore, Depends(get_session_binding_store)]
BackgroundRunnerDep = Annotated[BackgroundTaskRunner, Depends(get_background_runner)]
