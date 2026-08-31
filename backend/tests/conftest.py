"""Pytest Fixtures and Async Test Client Configuration."""

import pytest
import pytest_asyncio
from typing import AsyncGenerator
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.config import settings
from app.core.tenant import DEFAULT_DEV_MERCHANT_ID


@pytest_asyncio.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Provides an asynchronous HTTP test client against the FastAPI application."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def default_merchant_headers() -> dict:
    """Standard headers injecting the default development merchant tenant ID."""
    return {
        "X-Merchant-ID": DEFAULT_DEV_MERCHANT_ID,
        "Content-Type": "application/json",
    }
