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


@pytest_asyncio.fixture
async def seeded_demo_tenants() -> dict:
    """Provisions the standard multi-tenant demo catalogs in database & Redis."""
    from app.core.database import async_session_factory
    from app.contexts.knowledge.seeder import CatalogSeeder
    from app.contexts.knowledge.seed_data import (
        ALABA_AGRO_MERCHANT_ID,
        LEKKI_GLOW_MERCHANT_ID,
        HORIZON_TECH_MERCHANT_ID,
    )

    async with async_session_factory() as session:
        await CatalogSeeder.seed_all(session=session, reset=False)

    return {
        "alaba_agro_id": str(ALABA_AGRO_MERCHANT_ID),
        "lekki_glow_id": str(LEKKI_GLOW_MERCHANT_ID),
        "horizon_tech_id": str(HORIZON_TECH_MERCHANT_ID),
    }

