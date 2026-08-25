"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from mcp.server.transport_security import TransportSecuritySettings

from app.api.router import api_router
from app.core.config import APP_NAME, APP_VERSION, get_settings
from app.core.logging import configure_logging
from app.mcp.server import build_mcp_server

settings = get_settings()
configure_logging(settings.log_level)

mcp_server = build_mcp_server()
mcp_app = mcp_server.streamable_http_app(
    streamable_http_path="/",
    # DNS-rebinding Host/Origin checks protect a server reachable from a
    # browser on an untrusted network; this demo binds to localhost only, and
    # the real authorization boundary for every mutation is the one-time
    # commit capability (app.infrastructure.demo.capability), not the Host
    # header. Revisit before ever exposing this beyond localhost.
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Run the MCP session manager for the lifetime of the FastAPI process."""
    async with mcp_server.session_manager.run():
        yield


app = FastAPI(title=APP_NAME, version=APP_VERSION, lifespan=lifespan)
app.include_router(api_router)
app.mount("/mcp", mcp_app)
