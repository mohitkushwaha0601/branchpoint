"""Explicit domain error types."""


class DomainError(Exception):
    """Base class for every BRANCHPOINT domain error."""


class IllegalTransitionError(DomainError):
    """Raised when a lifecycle transition is not permitted."""

    def __init__(self, entity: str, current: str, requested: str) -> None:
        super().__init__(f"{entity} cannot transition from {current} to {requested}")
        self.entity = entity
        self.current = current
        self.requested = requested


class InvariantViolationError(DomainError):
    """Raised when an operation would violate a domain invariant."""

    def __init__(self, invariant: str, detail: str) -> None:
        super().__init__(f"{invariant}: {detail}")
        self.invariant = invariant
        self.detail = detail
