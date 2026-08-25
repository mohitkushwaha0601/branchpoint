"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import APP_NAME, APP_VERSION, get_settings
from app.core.logging import configure_logging
from app.mcp.server import build_mcp_server, build_transport_security

settings = get_settings()
configure_logging(settings.log_level)

mcp_server = build_mcp_server()
# streamable_http_path left at its default ("/mcp") and mounted at the FastAPI
# root: the sub-app's own route already resolves exactly to "/mcp" with no
# Mount-prefix indirection, so there is no bare-path -> trailing-slash
# redirect for a client to (possibly incorrectly) follow.
mcp_app = mcp_server.streamable_http_app(
    transport_security=build_transport_security(insecure_localhost=settings.mcp_insecure_localhost)
)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Run the MCP session manager for the lifetime of the FastAPI process."""
    async with mcp_server.session_manager.run():
        yield


app = FastAPI(title=APP_NAME, version=APP_VERSION, lifespan=lifespan)
app.include_router(api_router)
# Mounted last and at root: FastAPI/Starlette match the explicit routes above
# first, so this only ever handles "/mcp" (and anything else the MCP sub-app
# itself defines), never shadowing /health or /api/v1/*.
app.mount("/", mcp_app)
