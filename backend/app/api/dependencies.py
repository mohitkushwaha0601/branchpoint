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

from app.application.orchestration.orchestrator import BranchpointOrchestrator
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
from app.infrastructure.trueforge.planner import TrueForgeCandidatePlanner
from app.infrastructure.trueforge.sessions import InMemorySessionBindingStore
from app.mcp.server import READ_ONLY_TOOL_NAMES


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
            model=settings.trueforge_model,
            bindings=bindings,
            mcp_server_name=settings.trueforge_mcp_server_name,
            read_only_tools=READ_ONLY_TOOL_NAMES,
        ),
        world_executor=DemoWorldExecutor(engine),
        adversarial_tester=TrueForgeAdversarialTester(
            client,
            engine,
            model=settings.trueforge_model,
            bindings=bindings,
            mcp_server_name=settings.trueforge_mcp_server_name,
            sandbox_enabled=settings.trueforge_sandbox_enabled,
        ),
        mutator=DemoRealityMutator(engine, capability_store),
        verifier=DemoRealityVerifier(engine),
    )


SessionBindingStoreDep = Annotated[InMemorySessionBindingStore, Depends(get_session_binding_store)]
