"""Composition root for the HTTP boundary.

Phase 1 wires the orchestrator with in-memory storage only. No planner,
executor, adversarial tester, mutator, or verifier is configured, so any step
needing one fails loudly rather than pretending it ran.
"""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from app.application.orchestration.orchestrator import BranchpointOrchestrator
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
    """Build an orchestrator for the request."""
    return BranchpointOrchestrator(repository=repository, events=events)


RunRepositoryDep = Annotated[InMemoryRunRepository, Depends(get_run_repository)]
EventSinkDep = Annotated[InMemoryEventSink, Depends(get_event_sink)]
OrchestratorDep = Annotated[BranchpointOrchestrator, Depends(get_orchestrator)]
