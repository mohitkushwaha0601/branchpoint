"""FastAPI application entry point."""

from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import APP_NAME, APP_VERSION, get_settings
from app.core.logging import configure_logging

settings = get_settings()
configure_logging(settings.log_level)

app = FastAPI(title=APP_NAME, version=APP_VERSION)
app.include_router(api_router)
