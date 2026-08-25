"""The deterministic demo production engine: reality plus isolated worlds.

Every :class:`~app.infrastructure.demo.state.DemoProductionState` snapshot is
frozen, so isolation between worlds is structural rather than a deep-copy
convention: applying an action to one snapshot always returns a *new*
snapshot, and nothing in this engine ever assigns into an existing one.
Mutating a world can therefore never be observed by another world or by
reality, because there is no shared mutable state to leak through.

FastAPI, the MCP server, and every Phase 1 port adapter (:mod:`adapters`) all
resolve the same process-wide engine instance through
:func:`app.infrastructure.demo.dependencies.get_demo_engine`, so this is the
single source of truth for demo production state in the process.
"""

import asyncio

from app.domain.actions.models import CandidateAction
from app.domain.commits.models import OperationReceipt
from app.domain.runs.models import BranchpointRun
from app.domain.worlds.models import World
from app.infrastructure.demo.actions import apply_action
from app.infrastructure.demo.capability import CapabilityStore
from app.infrastructure.demo.scenario import DEFAULT_SCENARIO_PATH, load_initial_state
from app.infrastructure.demo.state import DemoProductionState


class UnknownWorldError(Exception):
    """Raised when a world id has no snapshot in this engine."""

    def __init__(self, world_id: str) -> None:
        super().__init__(f"no demo snapshot exists for world {world_id}")
        self.world_id = world_id


class DemoProductionEngine:
    """Owns the current reality snapshot and one snapshot per counterfactual world."""

    def __init__(self, *, scenario_path=DEFAULT_SCENARIO_PATH) -> None:
        self._scenario_path = scenario_path
        self._reality = load_initial_state(scenario_path)
        self._worlds: dict[str, DemoProductionState] = {}
        self._lock = asyncio.Lock()

    async def reset(self) -> DemoProductionState:
        """Restore reality to the exact initial incident and discard every world snapshot."""
        async with self._lock:
            self._reality = load_initial_state(self._scenario_path)
            self._worlds = {}
            return self._reality

    async def reality(self) -> DemoProductionState:
        """Return the current reality snapshot."""
        async with self._lock:
            return self._reality

    async def snapshot_world(self, world_id: str) -> DemoProductionState:
        """Fork an isolated snapshot of current reality for ``world_id``, or return the
        existing one if this world has already been forked."""
        async with self._lock:
            existing = self._worlds.get(world_id)
            if existing is not None:
                return existing
            snapshot = self._reality
            self._worlds[world_id] = snapshot
            return snapshot

    async def world_state(self, world_id: str) -> DemoProductionState:
        """Return the current snapshot for ``world_id``."""
        async with self._lock:
            state = self._worlds.get(world_id)
        if state is None:
            raise UnknownWorldError(world_id)
        return state

    async def apply_to_world(self, world_id: str, action: CandidateAction) -> DemoProductionState:
        """Apply ``action`` to ``world_id``'s isolated snapshot and store the result.

        Never touches reality or any other world's snapshot: the new state
        replaces only this world's entry.
        """
        async with self._lock:
            before = self._worlds.get(world_id, self._reality)
            after = apply_action(before, action)
            self._worlds[world_id] = after
            return after

    async def apply_to_reality(
        self,
        *,
        run: BranchpointRun,
        world: World,
        capability_store: CapabilityStore,
        capability_token: str,
    ) -> tuple[OperationReceipt, ...]:
        """Mutate reality with ``world``'s action, gated by a valid one-time capability.

        This is the single mutation path for reality: every caller — the
        orchestrator's ``RealityMutator`` and every destructive MCP tool —
        goes through this method, so the capability check can never be
        bypassed by calling a different entry point.
        """
        action = world.candidate_action
        spent = await capability_store.consume(
            capability_token,
            run_id=run.run_id,
            world_id=world.world_id,
            action_id=action.action_id,
            action_fingerprint=action.fingerprint(),
        )

        async with self._lock:
            before = self._reality
            after = apply_action(before, action)
            self._reality = after

        return (
            OperationReceipt(
                operation=str(action.action_type),
                target=action.target.service,
                succeeded=True,
                completed_at=spent.used_at or spent.issued_at,
                detail=f"applied {action.name} to reality",
                reference=spent.capability_id,
            ),
        )
