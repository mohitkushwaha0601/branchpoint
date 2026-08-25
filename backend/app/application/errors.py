"""Application-level error types."""


class ApplicationError(Exception):
    """Base class for orchestration errors."""


class RunNotFoundError(ApplicationError):
    """Raised when a run id does not exist."""

    def __init__(self, run_id: str) -> None:
        super().__init__(f"run {run_id} does not exist")
        self.run_id = run_id


class PortNotConfiguredError(ApplicationError):
    """Raised when a step needs a capability that has not been wired up.

    Phase 1 ships no production adapters, so an orchestrator built without a
    port fails loudly instead of pretending the step happened.
    """

    def __init__(self, port: str) -> None:
        super().__init__(f"{port} is not configured for this orchestrator")
        self.port = port
