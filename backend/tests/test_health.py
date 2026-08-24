"""Health endpoint contract tests."""

from importlib.metadata import version

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import APP_VERSION, SERVICE_NAME
from app.main import app


@pytest.mark.asyncio
async def test_health() -> None:
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "branchpoint-backend",
        "version": APP_VERSION,
    }


def test_app_version_is_read_from_installed_package_metadata() -> None:
    assert APP_VERSION == version(SERVICE_NAME)
