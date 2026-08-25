"""Phase 3 agent-run service.

Drives a BRANCHPOINT run using TrueForge-backed adapters. This is a thin
coordinator: every safety decision still belongs to the Phase 1 orchestrator
and the deterministic domain beneath it. The service exists to (a) wire the
TrueForge adapters in, and (b) emit the richer Phase 3 event timeline around
the unchanged Phase 1 steps.

World execution and adversarial testing stay **sequential**, exactly as Phase 1
runs them. Making them concurrent would mean changing orchestration that 180
tests currently pin down, and the brief is explicit that correctness beats
cosmetic concurrency. The ``WorldExecutor``/``AdversarialTester`` ports already
take a single world each, so this can be parallelised later without touching
any contract.
"""

from app.application.orchestration.orchestrator import BranchpointOrchestrator
from app.domain.events import RunEvent, RunEventType
from app.domain.incidents.models import Incident
from app.domain.primitives import ScalarValue, new_id, utc_now
from app.domain.runs.models import BranchpointRun
from app.infrastructure.trueforge.sessions import InMemorySessionBindingStore


class AgentRunService:
    """Runs the deterministic BRANCHPOINT pipeline with TrueForge agents attached."""

    def __init__(
        self,
        *,
        orchestrator: BranchpointOrchestrator,
        events,
        bindings: InMemorySessionBindingStore,
    ) -> None:
        self._orchestrator = orchestrator
        self._events = events
        self._bindings = bindings

    async def drive_to_approval(self, incident: Incident) -> BranchpointRun:
        """Create a run and drive it to the human approval gate.

        Stops at ``AWAITING_APPROVAL`` (or a terminal rejection). Nothing in
        reality has changed when this returns: committing requires a separate,
        human-approved destructive tool call.
        """
        run = await self._orchestrator.create_run(incident)
        await self._emit(run.run_id, RunEventType.PLANNER_STARTED, "TrueForge planner starting")

        run = await self._orchestrator.observe(run.run_id)
        run = await self._orchestrator.plan(run.run_id)
        await self._emit_session_bindings(run.run_id)

        if run.is_terminal:
            await self._emit(
                run.run_id, RunEventType.PLANNER_COMPLETED, "planner produced no usable plan"
            )
            return run

        await self._emit(
            run.run_id,
            RunEventType.PLANNER_COMPLETED,
            f"planner proposed {len(run.candidate_actions)} candidate action(s)",
            payload={"candidate_count": float(len(run.candidate_actions))},
        )

        run = await self._orchestrator.fork(run.run_id)
        run = await self._orchestrator.execute_worlds(run.run_id)

        for world in run.worlds:
            await self._emit(
                run.run_id,
                RunEventType.WORLD_AGENT_STARTED,
                f"world agent starting for {world.candidate_action.name}",
                world_id=world.world_id,
            )

        run = await self._orchestrator.run_adversarial_tests(run.run_id)
        await self._emit_session_bindings(run.run_id)

        run = await self._orchestrator.compare(run.run_id)
        return await self._orchestrator.request_approval(run.run_id)

    async def _emit_session_bindings(self, run_id: str) -> None:
        """Publish which TrueForge sessions this run is bound to."""
        for binding in await self._bindings.list_for_run(run_id):
            await self._emit(
                run_id,
                RunEventType.TRUEFORGE_SESSION_CREATED,
                f"{binding.purpose} session {binding.trueforge_session_id}",
                world_id=binding.world_id,
                payload={
                    "purpose": str(binding.purpose),
                    "trueforge_session_id": binding.trueforge_session_id,
                    "status": str(binding.status),
                },
            )

    async def _emit(
        self,
        run_id: str,
        event_type: RunEventType,
        summary: str,
        *,
        world_id: str | None = None,
        payload: dict[str, ScalarValue] | None = None,
    ) -> None:
        await self._events.emit(
            RunEvent(
                event_id=new_id("evt"),
                run_id=run_id,
                world_id=world_id,
                event_type=event_type,
                summary=summary,
                occurred_at=utc_now(),
                payload=payload or {},
            )
        )
