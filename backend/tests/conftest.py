"""Pytest Fixtures and Async Test Client Configuration."""

import pytest
import pytest_asyncio
from typing import AsyncGenerator, Callable
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.config import settings
from app.core.security import create_access_token


@pytest_asyncio.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Provides an asynchronous HTTP test client against the FastAPI application."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def auth_headers_factory() -> Callable[..., dict]:
    """Factory fixture to generate cryptographically signed JWT Bearer authorization headers."""
    def _create_headers(
        merchant_id: str = "018f6c5a-8b1e-7230-a890-123456789abc",
        role: str = "OWNER",
        user_id: str = "018f6c5a-8b1e-7230-a890-987654321def",
    ) -> dict:
        token = create_access_token({
            "sub": user_id,
            "merchant_id": merchant_id,
            "merchant_slug": "demo-enterprise-sme",
            "role": role,
            "email": f"{role.lower()}@demo-sme.ng",
        })
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
    return _create_headers


@pytest.fixture
def default_merchant_headers(auth_headers_factory) -> dict:
    """Standard authenticated headers with OWNER role."""
    return auth_headers_factory()
