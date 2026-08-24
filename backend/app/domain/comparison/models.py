"""Value objects describing the deterministic comparison of completed worlds."""

from enum import StrEnum

from app.domain.primitives import DomainModel


class RejectionReason(StrEnum):
    """Why a world was disqualified from selection."""

    NOT_EVALUATED = "NOT_EVALUATED"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    ADVERSARIAL_VETO = "ADVERSARIAL_VETO"
    INVARIANT_VIOLATION = "INVARIANT_VIOLATION"
    CRITICAL_DATA_INTEGRITY_FAILURE = "CRITICAL_DATA_INTEGRITY_FAILURE"
    INCONCLUSIVE_VERDICT = "INCONCLUSIVE_VERDICT"


class RejectedWorld(DomainModel):
    """A disqualified world together with the evidence that disqualified it."""

    world_id: str
    reasons: tuple[RejectionReason, ...]
    detail: str = ""
    evidence_ids: tuple[str, ...] = ()


class WorldRanking(DomainModel):
    """One eligible world's position in the deterministic ordering.

    Worlds with identical deterministic evidence share a rank.
    """

    world_id: str
    rank: int
    goal_achieved: bool
    goal_attainment: float
    invariants_preserved: bool
    regressions_detected: int
    blast_radius: int
    reversible: bool
    cost_delta: float
    evidence_ids: tuple[str, ...] = ()


class ComparisonResult(DomainModel):
    """The outcome of comparing every world in a run.

    ``recommended_world_id`` is ``None`` when no world is eligible *or* when the
    best worlds are deterministically tied — BRANCHPOINT never invents a winner
    and never breaks a tie at random.
    """

    eligible_world_ids: tuple[str, ...] = ()
    tied_world_ids: tuple[str, ...] = ()
    rejected_worlds: tuple[RejectedWorld, ...] = ()
    rankings: tuple[WorldRanking, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    recommended_world_id: str | None = None
    summary: str = ""

    @property
    def has_recommendation(self) -> bool:
        """Whether comparison produced a single recommended world."""
        return self.recommended_world_id is not None

    @property
    def is_tied(self) -> bool:
        """Whether the top of the ranking is a deterministic tie."""
        return len(self.tied_world_ids) > 1
