"""Shared MCP test fixtures.

MCP's SDK vendors its own ``httpx2``/``httpcore2`` stack internally, separate
from the ``httpx`` this repository uses elsewhere — a plain ``httpx.ASGITransport``
is not wire-compatible with the MCP client's ``httpx2.AsyncClient``, so tests
against the MCP server use ``httpx2.ASGITransport`` instead.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx2
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.routing import Mount

from app.infrastructure.demo.capability import CapabilityStore
from app.infrastructure.demo.engine import DemoProductionEngine
from app.infrastructure.persistence.memory import InMemoryRunRepository
from app.mcp.server import build_mcp_server


class MCPTestHarness:
    """A fully isolated MCP server plus the demo state it reads and mutates."""

    def __init__(
        self,
        mcp: MCPServer,
        engine: DemoProductionEngine,
        capability_store: CapabilityStore,
        run_repository: InMemoryRunRepository,
    ) -> None:
        self.mcp = mcp
        self.engine = engine
        self.capability_store = capability_store
        self.run_repository = run_repository


def _build_isolated_app(mcp: MCPServer) -> Starlette:
    mcp_app = mcp.streamable_http_app(
        streamable_http_path="/",
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )

    @asynccontextmanager
    async def lifespan(_app: Starlette) -> AsyncIterator[None]:
        async with mcp.session_manager.run():
            yield

    return Starlette(routes=[Mount("/mcp", app=mcp_app)], lifespan=lifespan)


@pytest.fixture
async def mcp_harness() -> AsyncIterator[MCPTestHarness]:
    """An MCP server wired to its own isolated demo engine/capability store/run repository."""
    engine = DemoProductionEngine()
    capability_store = CapabilityStore()
    run_repository = InMemoryRunRepository()
    mcp = build_mcp_server(
        engine=engine, capability_store=capability_store, run_repository=run_repository
    )
    yield MCPTestHarness(mcp, engine, capability_store, run_repository)


@asynccontextmanager
async def mcp_session(harness: MCPTestHarness) -> AsyncIterator[ClientSession]:
    """Open a real MCP client session against ``harness`` over an in-process ASGI transport."""
    test_app = _build_isolated_app(harness.mcp)
    transport = httpx2.ASGITransport(app=test_app)
    async with harness.mcp.session_manager.run():
        async with httpx2.AsyncClient(transport=transport, base_url="http://test") as http_client:
            async with streamable_http_client("http://test/mcp/", http_client=http_client) as (
                read,
                write,
            ):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    yield session
