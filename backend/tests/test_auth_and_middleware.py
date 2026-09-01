"""Comprehensive Automated Tests for Authentication, RBAC, and Middleware Pipeline."""

import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from httpx import AsyncClient

from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.core.database import async_session_factory
from app.contexts.core.models import Merchant, User, RefreshToken


@pytest.mark.asyncio
async def test_register_merchant_and_owner(async_client: AsyncClient):
    """Verifies atomic merchant registration, initial OWNER user creation, and token issuance."""
    unique_suffix = str(uuid4())[:8]
    payload = {
        "business_name": f"Lagos Electronics Ltd {unique_suffix}",
        "slug": f"lagos-electronics-{unique_suffix}",
        "bsp_provider": "META_CLOUD",
        "whatsapp_business_phone": f"+234803{unique_suffix[:7]}",
        "default_currency": "NGN",
        "variance_tolerance_kobo": 5000,
        "anti_ghosting_hold_seconds": 600,
        "owner_email": f"owner_{unique_suffix}@lagos-electronics.ng",
        "owner_password": "StrongPassword123!",
        "owner_full_name": "Babajide Sanwo",
    }

    response = await async_client.post("/api/v1/core/auth/register", json=payload)
    assert response.status_code == 201, response.text
    data = response.json()

    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["role"] == "OWNER"
    assert data["full_name"] == "Babajide Sanwo"
    assert data["expires_in"] == 900

    # Verify HttpOnly cookies are set
    cookies = response.cookies
    assert "access_token" in cookies
    assert "refresh_token" in cookies


@pytest.mark.asyncio
async def test_login_and_get_user_profile(async_client: AsyncClient):
    """Verifies user login and profile retrieval using JWT claims."""
    unique_suffix = str(uuid4())[:8]
    email = f"ceo_{unique_suffix}@alaba-market.ng"
    password = "SuperSecretPassword123"

    # 1. Register merchant
    reg_payload = {
        "business_name": f"Alaba Spares {unique_suffix}",
        "slug": f"alaba-spares-{unique_suffix}",
        "bsp_provider": "META_CLOUD",
        "whatsapp_business_phone": f"+234802{unique_suffix[:7]}",
        "default_currency": "NGN",
        "variance_tolerance_kobo": 0,
        "anti_ghosting_hold_seconds": 600,
        "owner_email": email,
        "owner_password": password,
        "owner_full_name": "Chukwudi Okafor",
    }
    reg_res = await async_client.post("/api/v1/core/auth/register", json=reg_payload)
    assert reg_res.status_code == 201

    # 2. Login
    login_payload = {"email": email, "password": password}
    login_res = await async_client.post("/api/v1/core/auth/login", json=login_payload)
    assert login_res.status_code == 200
    token_data = login_res.json()
    access_token = token_data["access_token"]

    # 3. Call GET /api/v1/core/auth/me
    headers = {"Authorization": f"Bearer {access_token}"}
    me_res = await async_client.get("/api/v1/core/auth/me", headers=headers)
    assert me_res.status_code == 200
    me_data = me_res.json()

    assert me_data["user"]["email"] == email
    assert me_data["user"]["role"] == "OWNER"
    assert me_data["role_rank"] == 100
    assert me_data["active_channel"] == "JWT"
    assert me_data["merchant"]["slug"] == f"alaba-spares-{unique_suffix}"


@pytest.mark.asyncio
async def test_account_lockout_governor(async_client: AsyncClient):
    """Verifies that 5 consecutive failed login attempts trigger temporary account lockout (ADR-0032)."""
    unique_suffix = str(uuid4())[:8]
    email = f"lockout_{unique_suffix}@sme.ng"
    password = "CorrectPassword123"

    # Register user
    await async_client.post("/api/v1/core/auth/register", json={
        "business_name": f"Lockout SME {unique_suffix}",
        "slug": f"lockout-sme-{unique_suffix}",
        "bsp_provider": "META_CLOUD",
        "whatsapp_business_phone": f"+234809{unique_suffix[:7]}",
        "owner_email": email,
        "owner_password": password,
        "owner_full_name": "Lockout Tester",
    })

    # Fail login 4 times (401 Unauthorized)
    for _ in range(4):
        res = await async_client.post("/api/v1/core/auth/login", json={"email": email, "password": "WrongPassword"})
        assert res.status_code == 401

    # 5th failure triggers lockout
    res_5 = await async_client.post("/api/v1/core/auth/login", json={"email": email, "password": "WrongPassword"})
    assert res_5.status_code == 401

    # 6th attempt (even with correct password) is blocked by lockout governor with HTTP 429
    res_locked = await async_client.post("/api/v1/core/auth/login", json={"email": email, "password": password})
    assert res_locked.status_code == 429
    assert "temporarily locked" in res_locked.json()["detail"]


@pytest.mark.asyncio
async def test_refresh_token_rotation_and_concurrency_leeway(async_client: AsyncClient):
    """Verifies single-use token rotation and the 5-second concurrency grace window (ADR-0027, ADR-0032)."""
    unique_suffix = str(uuid4())[:8]
    email = f"refresh_{unique_suffix}@sme.ng"

    # Register
    reg_res = await async_client.post("/api/v1/core/auth/register", json={
        "business_name": f"Refresh SME {unique_suffix}",
        "slug": f"refresh-sme-{unique_suffix}",
        "bsp_provider": "META_CLOUD",
        "whatsapp_business_phone": f"+234808{unique_suffix[:7]}",
        "owner_email": email,
        "owner_password": "Password123!",
        "owner_full_name": "Refresh Tester",
    })
    initial_refresh_token = reg_res.json()["refresh_token"]

    # 1. Rotate token
    rotate_res = await async_client.post(
        "/api/v1/core/auth/refresh",
        json={"refresh_token": initial_refresh_token},
    )
    assert rotate_res.status_code == 200
    rotated_data = rotate_res.json()
    new_refresh_token = rotated_data["refresh_token"]
    assert new_refresh_token != initial_refresh_token

    # 2. Concurrency Leeway: Call immediately with the original token (within 5 seconds) -> succeeds!
    leeway_res = await async_client.post(
        "/api/v1/core/auth/refresh",
        json={"refresh_token": initial_refresh_token},
    )
    assert leeway_res.status_code == 200
    assert "access_token" in leeway_res.json()


@pytest.mark.asyncio
async def test_token_theft_replay_detection_revocation(async_client: AsyncClient):
    """Verifies that presenting a consumed token after the leeway period triggers whole-family revocation."""
    unique_suffix = str(uuid4())[:8]
    email = f"theft_{unique_suffix}@sme.ng"

    # Register
    reg_res = await async_client.post("/api/v1/core/auth/register", json={
        "business_name": f"Theft SME {unique_suffix}",
        "slug": f"theft-sme-{unique_suffix}",
        "bsp_provider": "META_CLOUD",
        "whatsapp_business_phone": f"+234807{unique_suffix[:7]}",
        "owner_email": email,
        "owner_password": "Password123!",
        "owner_full_name": "Theft Tester",
    })
    token_1 = reg_res.json()["refresh_token"]

    # Rotate token once
    rot_res = await async_client.post("/api/v1/core/auth/refresh", json={"refresh_token": token_1})
    assert rot_res.status_code == 200
    token_2 = rot_res.json()["refresh_token"]

    # Manually backdate consumed_at on token_1 in the DB by 10 seconds to simulate replay after leeway
    from app.core.security import compute_sha256_hash
    token_1_hash = compute_sha256_hash(token_1)

    async with async_session_factory() as session:
        from sqlalchemy import update
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.token_hash == token_1_hash)
            .values(consumed_at=datetime.now(timezone.utc) - timedelta(seconds=15))
        )
        await session.commit()

    # Now attempt replay attack using token_1
    replay_res = await async_client.post("/api/v1/core/auth/refresh", json={"refresh_token": token_1})
    assert replay_res.status_code == 401
    assert "Refresh token reuse detected" in replay_res.json()["detail"]

    # Verify that token_2 in the same family has also been revoked
    token_2_res = await async_client.post("/api/v1/core/auth/refresh", json={"refresh_token": token_2})
    assert token_2_res.status_code == 401
    assert "revoked" in token_2_res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_strict_multi_tenant_isolation(async_client: AsyncClient):
    """Verifies that unverified X-Merchant-ID headers cannot spoof tenant context (ADR-0026)."""
    # 1. Calling protected endpoint without token -> 401 Unauthorized
    res_no_auth = await async_client.get(
        "/api/v1/core/auth/me",
        headers={"X-Merchant-ID": "018f6c5a-8b1e-7230-a890-123456789abc"},
    )
    assert res_no_auth.status_code == 401

    # 2. Calling with bogus JWT -> 401 Unauthorized
    res_bad_jwt = await async_client.get(
        "/api/v1/core/auth/me",
        headers={"Authorization": "Bearer invalid.jwt.token"},
    )
    assert res_bad_jwt.status_code == 401


@pytest.mark.asyncio
async def test_linear_rbac_hierarchy(async_client: AsyncClient, auth_headers_factory):
    """Verifies that require_min_role allows authorized ranks and forbids subordinate roles (ADR-0029)."""
    merchant_id = str(uuid4())

    # 1. AGENT (rank 40) tries to provision a user (requires ADMIN rank 80) -> 403 Forbidden
    agent_headers = auth_headers_factory(merchant_id=merchant_id, role="AGENT")
    res_agent = await async_client.post(
        "/api/v1/core/auth/users",
        json={"email": "new_agent@sme.ng", "password": "Password123!", "full_name": "New Staff", "role": "AGENT"},
        headers=agent_headers,
    )
    assert res_agent.status_code == 403
    assert "requires at least 'ADMIN'" in res_agent.json()["detail"]

    # 2. OWNER (rank 100) provisions a user -> 201 Created (or succeeds with DB session)
    # Register actual merchant & owner first to have matching DB foreign keys
    reg_payload = {
        "business_name": "RBAC Test Mart",
        "slug": f"rbac-mart-{str(uuid4())[:6]}",
        "bsp_provider": "META_CLOUD",
        "whatsapp_business_phone": "+2348051234567",
        "owner_email": f"owner_{str(uuid4())[:6]}@rbac.ng",
        "owner_password": "Password123!",
        "owner_full_name": "RBAC Owner",
    }
    reg_res = await async_client.post("/api/v1/core/auth/register", json=reg_payload)
    owner_token = reg_res.json()["access_token"]
    owner_headers = {"Authorization": f"Bearer {owner_token}"}

    create_user_res = await async_client.post(
        "/api/v1/core/auth/users",
        json={"email": f"agent_{str(uuid4())[:6]}@rbac.ng", "password": "Password123!", "full_name": "Staff Agent", "role": "AGENT"},
        headers=owner_headers,
    )
    assert create_user_res.status_code == 201
    assert create_user_res.json()["role"] == "AGENT"


@pytest.mark.asyncio
async def test_middleware_pipeline_and_rfc7807_error(async_client: AsyncClient):
    """Verifies X-Trace-ID, X-Process-Time-Ms headers, and RFC 7807 error envelopes (ADR-0028)."""
    # 1. Health check headers
    health_res = await async_client.get("/api/health")
    assert health_res.status_code == 200
    assert "X-Trace-ID" in health_res.headers
    assert "X-Process-Time-Ms" in health_res.headers

    # 2. 404 Error formatted as RFC 7807 Problem Details
    not_found_res = await async_client.get("/api/v1/unknown-route-for-testing")
    assert not_found_res.status_code == 404
    data = not_found_res.json()
    assert "type" in data
    assert "title" in data
    assert data["status"] == 404
    assert "trace_id" in data
    assert data["trace_id"] == not_found_res.headers.get("X-Trace-ID")
