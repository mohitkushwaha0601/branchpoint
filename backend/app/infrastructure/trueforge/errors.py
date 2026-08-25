"""Errors raised at the TrueForge infrastructure boundary.

None of these ever escape into the domain: the planner and adversary adapters
translate them into domain outcomes (a rejected plan, an inconclusive world)
before returning. Fail closed — a TrueForge failure must never be reported as
"this world is safe".
"""


class TrueForgeError(Exception):
    """Base class for every TrueForge integration error."""


class TrueForgeUnavailableError(TrueForgeError):
    """Raised when TrueForge cannot be reached or returns a transport error."""


class TrueForgeAPIError(TrueForgeError):
    """Raised when TrueForge returns an unexpected HTTP status."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(f"TrueForge returned HTTP {status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail


class TurnFailedError(TrueForgeError):
    """Raised when a turn ends in an error or cancelled state."""

    def __init__(self, turn_id: str, status: str, detail: str = "") -> None:
        super().__init__(f"turn {turn_id} ended {status}: {detail}".rstrip(": "))
        self.turn_id = turn_id
        self.status = status


class StructuredOutputError(TrueForgeError):
    """Raised when a turn's final message is not the bounded JSON we required.

    Carries ``feedback`` suitable for handing straight back to the agent on a
    bounded retry — the agent is told what was wrong, never silently corrected.
    """

    def __init__(self, detail: str, feedback: str = "") -> None:
        super().__init__(detail)
        self.detail = detail
        self.feedback = feedback or detail


class PlanValidationError(TrueForgeError):
    """Raised when a proposed plan cannot be validated into CandidateActions."""

    def __init__(self, detail: str, feedback: str = "") -> None:
        super().__init__(detail)
        self.detail = detail
        self.feedback = feedback or detail
