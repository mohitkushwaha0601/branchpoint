"""In-memory test doubles for every application port."""

from collections.abc import Sequence

from app.domain.actions.models import CandidateAction
from app.domain.commits.models import CommitReceipt, OperationReceipt
from app.domain.incidents.models import Incident, ObservedState
from app.domain.runs.models import BranchpointRun
from app.domain.verification.models import VerificationCheck
from app.domain.worlds.models import AdversarialReport, World, WorldExecutionReport
from tests.factories import FIXED_TIME


class SequentialIds:
    """Deterministic id factory so tests can assert on identifiers."""

    def __init__(self) -> None:
        self._counts: dict[str, int] = {}

    def __call__(self, prefix: str) -> str:
        self._counts[prefix] = self._counts.get(prefix, 0) + 1
        return f"{prefix}_{self._counts[prefix]}"


class StubRealityReader:
    """Returns a fixed observation."""

    def __init__(self, observed_state: ObservedState) -> None:
        self._observed_state = observed_state

    async def observe(self, incident: Incident) -> ObservedState:
        return self._observed_state


class StubPlanner:
    """Returns fixed candidate actions."""

    def __init__(self, candidates: Sequence[CandidateAction]) -> None:
        self._candidates = tuple(candidates)

    async def plan(
        self, incident: Incident, observed_state: ObservedState
    ) -> Sequence[CandidateAction]:
        return self._candidates


class ScriptedWorldExecutor:
    """Returns a scripted execution report per action id."""

    def __init__(self, reports: dict[str, WorldExecutionReport]) -> None:
        self._reports = reports
        self.executed: list[str] = []

    async def execute(self, world: World) -> WorldExecutionReport:
        self.executed.append(world.world_id)
        return self._reports[world.candidate_action.action_id]


class ScriptedAdversarialTester:
    """Returns a scripted adversarial report per action id."""

    def __init__(self, reports: dict[str, AdversarialReport]) -> None:
        self._reports = reports
        self.attacked: list[str] = []

    async def attack(self, world: World) -> AdversarialReport:
        self.attacked.append(world.world_id)
        return self._reports.get(world.candidate_action.action_id, AdversarialReport())


class RecordingMutator:
    """Records what was committed and reports success."""

    def __init__(self, *, succeeds: bool = True) -> None:
        self._succeeds = succeeds
        self.applied: list[tuple[str, str]] = []

    async def apply(self, run: BranchpointRun, world: World) -> Sequence[OperationReceipt]:
        self.applied.append((world.world_id, world.candidate_action.action_id))
        return (
            OperationReceipt(
                operation=str(world.candidate_action.action_type),
                target=world.candidate_action.target.service,
                succeeded=self._succeeds,
                completed_at=FIXED_TIME,
                reference="test://operation/1",
            ),
        )


class StubVerifier:
    """Returns fixed post-commit checks."""

    def __init__(self, checks: Sequence[VerificationCheck]) -> None:
        self._checks = tuple(checks)
        self.verified: list[str] = []

    async def verify(
        self, run: BranchpointRun, commit_receipt: CommitReceipt
    ) -> Sequence[VerificationCheck]:
        self.verified.append(commit_receipt.commit_id)
        return self._checks


class ExplodingWorldExecutor:
    """Raises for a specific action id, to prove one broken world cannot abort a run."""

    def __init__(self, failing_action_id: str, reports: dict[str, WorldExecutionReport]) -> None:
        self._failing_action_id = failing_action_id
        self._reports = reports

    async def execute(self, world: World) -> WorldExecutionReport:
        if world.candidate_action.action_id == self._failing_action_id:
            raise RuntimeError("sandbox unavailable")
        return self._reports[world.candidate_action.action_id]
