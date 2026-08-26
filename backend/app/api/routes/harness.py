"""The TrueForge harness trace: read-only proof that the harness did the work.

This is the one place a browser can see TrueForge activity, and it sees only
what BRANCHPOINT has redacted and normalized. TrueForge itself is never exposed:
its address is not in any response, and no request from a browser reaches it.

Nothing here is authoritative. A harness trace says *the runtime ran a subagent
and a sandbox command*; it never says a world is safe or broken. Evidence
authority, counterexample reproduction, and vetoes are untouched by this module.
"""

from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.api.dependencies import (
    RunRepositoryDep,
    SessionBindingStoreDep,
    get_trueforge_client,
)
from app.application.orchestration.harness_trace import HarnessTraceService
from app.infrastructure.trueforge.harness import HarnessCategory, HarnessStatus

router = APIRouter(prefix="/api/v1/runs", tags=["harness"])


class HarnessSessionResponse(BaseModel):
    """One TrueForge session this run is bound to.

    Returned even when TrueForge cannot be read, because the binding is
    BRANCHPOINT's own record. It is what makes session continuity checkable: the
    same run re-read later reports the same session ids.
    """

    purpose: str
    trueforge_session_id: str
    world_id: str | None
    status: str
    last_turn_id: str | None
    created_at: datetime
    updated_at: datetime


class HarnessTraceEntryResponse(BaseModel):
    """One redacted row of TrueForge harness activity."""

    trace_id: str
    timestamp: str
    session_id: str
    purpose: str
    world_id: str | None
    category: HarnessCategory
    status: HarnessStatus
    summary: str
    tool_name: str
    mcp_server: str
    thread_id: str
    sandbox_id: str
    exit_code: int | None


class HarnessTraceResponse(BaseModel):
    """Everything the harness view renders for one run."""

    run_id: str
    #: ``available`` or ``unavailable`` — never a guess dressed as a fact.
    trueforge_status: str
    detail: str
    sessions: tuple[HarnessSessionResponse, ...]
    entries: tuple[HarnessTraceEntryResponse, ...]


@router.get("/{run_id}/harness-trace", response_model=HarnessTraceResponse)
async def get_harness_trace(
    run_id: str,
    repository: RunRepositoryDep,
    bindings: SessionBindingStoreDep,
) -> HarnessTraceResponse:
    """Return the TrueForge harness activity for one run.

    404 for a run BRANCHPOINT does not know. A run it does know but TrueForge
    cannot answer for returns 200 with ``trueforge_status="unavailable"`` — the
    run page keeps working and the timeline says why it is empty.
    """
    if await repository.get(run_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"run {run_id} not found")

    service = HarnessTraceService(client=get_trueforge_client(), bindings=bindings)
    trace = await service.trace(run_id)

    return HarnessTraceResponse(
        run_id=trace.run_id,
        trueforge_status=trace.trueforge_status,
        detail=trace.detail,
        sessions=tuple(
            HarnessSessionResponse(
                purpose=str(binding.purpose),
                trueforge_session_id=binding.trueforge_session_id,
                world_id=binding.world_id,
                status=str(binding.status),
                last_turn_id=binding.last_turn_id,
                created_at=binding.created_at,
                updated_at=binding.updated_at,
            )
            for binding in trace.bindings
        ),
        entries=tuple(HarnessTraceEntryResponse(**entry.model_dump()) for entry in trace.entries),
    )
