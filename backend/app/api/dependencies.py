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
