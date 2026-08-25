"""Fixtures for Phase 3 approval/commit tests."""

from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest

from app.application.orchestration.orchestrator import BranchpointOrchestrator
from app.domain.incidents.models import Incident
from app.domain.runs.models import BranchpointRun
from app.infrastructure.demo.adapters import (
    DemoRealityMutator,
    DemoRealityReader,
    DemoRealityVerifier,
    DemoWorldExecutor,
)
from app.infrastructure.demo.capability import CapabilityStore
from app.infrastructure.demo.engine import DemoProductionEngine
from app.infrastructure.demo.hero import HeroAdversarialTester, HeroCandidatePlanner
from app.infrastructure.persistence.memory import InMemoryEventSink, InMemoryRunRepository
from app.mcp.server import build_mcp_server
from tests.mcp.conftest import MCPTestHarness


@dataclass
class CommitHarness:
    """An isolated stack for exercising the commit path over MCP.

    Planning and adversarial testing use the deterministic Phase 2 demo
    adapters here on purpose: these tests are about the *approval and commit
    gates*, which are model-independent. TrueForge planner/adversary behaviour
    is covered separately against the fake transport.
    """

    engine: DemoProductionEngine
    orchestrator: BranchpointOrchestrator
    mcp: MCPTestHarness
    events: InMemoryEventSink

    async def drive_to_approval(self, incident: Incident) -> BranchpointRun:
        return await self.orchestrator.drive_to_approval(incident)


@pytest.fixture
async def commit_harness() -> AsyncIterator[CommitHarness]:
    """Build an isolated engine, orchestrator, and MCP server that share state."""
    engine = DemoProductionEngine()
    capability_store = CapabilityStore()
    repository = InMemoryRunRepository()
    events = InMemoryEventSink()

    orchestrator = BranchpointOrchestrator(
        repository=repository,
        events=events,
        reality_reader=DemoRealityReader(engine),
        planner=HeroCandidatePlanner(),
        world_executor=DemoWorldExecutor(engine),
        adversarial_tester=HeroAdversarialTester(engine),
        mutator=DemoRealityMutator(engine, capability_store),
        verifier=DemoRealityVerifier(engine),
    )

    mcp = build_mcp_server(
        engine=engine,
        capability_store=capability_store,
        run_repository=repository,
        orchestrator_factory=lambda: orchestrator,
        approval_actor="human-via-trueforge",
    )
    harness = MCPTestHarness(mcp, engine, capability_store, repository)
    yield CommitHarness(engine=engine, orchestrator=orchestrator, mcp=harness, events=events)
