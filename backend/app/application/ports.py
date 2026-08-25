"""Application contracts for capabilities BRANCHPOINT does not own yet.

Phase 1 ships no implementation of these beyond in-memory test doubles.
TrueForge backs the planner and the adversarial tester later; sandboxes back the
world executor; MCP tools back the reality reader, mutator, and verifier.
"""

from collections.abc import Sequence
from typing import Protocol

from app.domain.actions.models import CandidateAction
from app.domain.commits.models import CommitReceipt, OperationReceipt
from app.domain.events import RunEvent
from app.domain.incidents.models import Incident, ObservedState
from app.domain.runs.models import BranchpointRun
from app.domain.verification.models import VerificationCheck
from app.domain.worlds.models import AdversarialReport, World, WorldExecutionReport


class RealityReader(Protocol):
    """Reads structured observations from the real system."""

    async def observe(self, incident: Incident) -> ObservedState:
        """Return the observed state of reality for ``incident``."""
        ...


class CandidatePlanner(Protocol):
    """Proposes candidate actions. Proposals are inert; they never execute."""

    async def plan(
        self, incident: Incident, observed_state: ObservedState
    ) -> Sequence[CandidateAction]:
        """Return candidate actions worth testing counterfactually."""
        ...


class WorldExecutor(Protocol):
    """Executes one candidate action inside one isolated counterfactual world.

    Each call is independent and takes a single world, so worlds can be executed
    concurrently later without changing this contract.
    """

    async def execute(self, world: World) -> WorldExecutionReport:
        """Execute ``world``'s candidate action counterfactually and measure the result."""
        ...


class AdversarialTester(Protocol):
    """Attacks a world and tries to produce reproducible counterexamples."""

    async def attack(self, world: World) -> AdversarialReport:
        """Return counterexamples and evidence produced by attacking ``world``."""
        ...


class RealityMutator(Protocol):
    """Applies exactly one approved action to reality."""

    async def apply(self, run: BranchpointRun, world: World) -> Sequence[OperationReceipt]:
        """Perform the approved action and return one receipt per operation."""
        ...


class RealityVerifier(Protocol):
    """Independently checks reality after a commit."""

    async def verify(
        self, run: BranchpointRun, commit_receipt: CommitReceipt
    ) -> Sequence[VerificationCheck]:
        """Return post-commit checks against reality."""
        ...


class RunRepository(Protocol):
    """Stores runs."""

    async def save(self, run: BranchpointRun) -> None:
        """Persist ``run``, replacing any earlier version of it."""
        ...

    async def get(self, run_id: str) -> BranchpointRun | None:
        """Return the stored run, or ``None`` when it does not exist."""
        ...

    async def list_runs(self) -> Sequence[BranchpointRun]:
        """Return every stored run, newest first."""
        ...


class EventSink(Protocol):
    """Collects run timeline events."""

    async def emit(self, event: RunEvent) -> None:
        """Record one run event."""
        ...
