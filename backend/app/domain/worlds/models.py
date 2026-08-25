"""Counterfactual worlds, adversarial counterexamples, and execution results."""

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from app.domain.actions.models import CandidateAction
from app.domain.errors import InvariantViolationError
from app.domain.evidence.models import Evidence
from app.domain.primitives import DomainModel, evolve, utc_now
from app.domain.worlds.lifecycle import (
    TERMINAL_WORLD_STATUSES,
    WorldStatus,
    assert_world_transition,
)


class WorldVerdict(StrEnum):
    """The evidence-backed conclusion about a world."""

    SURVIVED = "SURVIVED"
    VETOED = "VETOED"
    INCONCLUSIVE = "INCONCLUSIVE"
    EXECUTION_FAILED = "EXECUTION_FAILED"


class CounterexampleStatus(StrEnum):
    """How far a DOPPELGÄNGER attack got."""

    PROPOSED = "PROPOSED"
    EXECUTED = "EXECUTED"
    REPRODUCED = "REPRODUCED"
    NOT_REPRODUCED = "NOT_REPRODUCED"
    ERROR = "ERROR"


class Counterexample(DomainModel):
    """A DOPPELGÄNGER attack against one world.

    A counterexample claiming ``REPRODUCED`` is not automatically believed: it
    only vetoes a world when it references machine-verifiable failing evidence.
    Unsupported claims are recorded and ignored rather than rejected, so an
    untrusted adversary can never halt a run by asserting a reproduction.
    """

    attack_id: str
    world_id: str
    title: str
    hypothesis: str
    created_at: datetime = Field(default_factory=utc_now)
    reproduction_steps: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    status: CounterexampleStatus = CounterexampleStatus.PROPOSED


class ExecutionOutcome(DomainModel):
    """Deterministic, measured result of executing one candidate action in one world."""

    succeeded: bool
    goal_achieved: bool
    invariants_preserved: bool
    reversible: bool
    goal_attainment: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    regressions_detected: int = Field(default=0, ge=0)
    blast_radius: int = Field(default=0, ge=0)
    cost_delta: float = Field(default=0.0, allow_inf_nan=False)
    summary: str = ""


class WorldExecutionReport(DomainModel):
    """What a :class:`~app.application.ports.WorldExecutor` returns."""

    outcome: ExecutionOutcome
    evidence: tuple[Evidence, ...] = ()


class AdversarialReport(DomainModel):
    """What an :class:`~app.application.ports.AdversarialTester` returns."""

    counterexamples: tuple[Counterexample, ...] = ()
    evidence: tuple[Evidence, ...] = ()


class World(DomainModel):
    """One counterfactual branch testing exactly one candidate action."""

    world_id: str
    run_id: str
    candidate_action: CandidateAction
    created_at: datetime
    updated_at: datetime
    status: WorldStatus = WorldStatus.CREATED
    outcome: ExecutionOutcome | None = None
    evidence: tuple[Evidence, ...] = ()
    counterexamples: tuple[Counterexample, ...] = ()
    verdict: WorldVerdict | None = None
    verdict_reason: str = ""

    @classmethod
    def create(
        cls,
        *,
        world_id: str,
        run_id: str,
        candidate_action: CandidateAction,
        at: datetime | None = None,
    ) -> "World":
        """Create a world in ``CREATED`` state for one candidate action."""
        now = at or utc_now()
        return cls(
            world_id=world_id,
            run_id=run_id,
            candidate_action=candidate_action,
            created_at=now,
            updated_at=now,
        )

    @property
    def evidence_by_id(self) -> dict[str, Evidence]:
        """Index of this world's evidence, keyed by evidence id."""
        return {item.evidence_id: item for item in self.evidence}

    @property
    def is_terminal(self) -> bool:
        """Whether the world has reached a terminal status."""
        return self.status in TERMINAL_WORLD_STATUSES

    def transition_to(self, status: WorldStatus, *, at: datetime | None = None) -> "World":
        """Return a copy of this world moved to ``status``, enforcing the state machine."""
        assert_world_transition(self.status, status)
        return evolve(self, status=status, updated_at=at or utc_now())

    def record_execution(
        self, report: WorldExecutionReport, *, at: datetime | None = None
    ) -> "World":
        """Attach execution results and evidence to a world that is executing."""
        if self.status is not WorldStatus.EXECUTING:
            raise InvariantViolationError(
                "world execution recording",
                f"world {self.world_id} must be EXECUTING to record execution, is {self.status}",
            )
        return evolve(
            self,
            outcome=report.outcome,
            evidence=self.evidence + report.evidence,
            updated_at=at or utc_now(),
        )

    def record_attacks(self, report: AdversarialReport, *, at: datetime | None = None) -> "World":
        """Attach DOPPELGÄNGER counterexamples and their evidence to an attacked world."""
        if self.status is not WorldStatus.ATTACKING:
            raise InvariantViolationError(
                "adversarial recording",
                f"world {self.world_id} must be ATTACKING to record attacks, is {self.status}",
            )
        return evolve(
            self,
            counterexamples=self.counterexamples + report.counterexamples,
            evidence=self.evidence + report.evidence,
            updated_at=at or utc_now(),
        )

    def settle(self, verdict: WorldVerdict, reason: str, *, at: datetime | None = None) -> "World":
        """Record a verdict and move the world to its matching terminal status."""
        terminal = {
            WorldVerdict.SURVIVED: WorldStatus.SURVIVED,
            WorldVerdict.VETOED: WorldStatus.VETOED,
            WorldVerdict.EXECUTION_FAILED: WorldStatus.FAILED,
            WorldVerdict.INCONCLUSIVE: WorldStatus.FAILED,
        }[verdict]
        assert_world_transition(self.status, terminal)
        return evolve(
            self,
            status=terminal,
            verdict=verdict,
            verdict_reason=reason,
            updated_at=at or utc_now(),
        )
