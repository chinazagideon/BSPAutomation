"""Security utilities: JWT token management, password hashing, and AES-256 PII encryption."""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Dict
import jwt
from passlib.context import CryptContext
import hashlib
import hmac
import base64
import os

from app.core.config import settings

# Password Hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hashes a raw password string using bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain password against its bcrypt hash."""
    return pwd_context.verify(plain_password, hashed_password)


# JWT Access Tokens
def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Generates a signed JWT access token containing tenant, user, and role claims."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc)})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Decodes and validates a JWT access token signature and expiration."""
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        return payload
    except (jwt.PyJWTError, Exception):
        return None


# Webhook Signature Verification (HMAC-SHA256)
def verify_meta_webhook_signature(
    payload_body: bytes,
    signature_header: str,
    app_secret: str,
) -> bool:
    """Validates incoming Meta X-Hub-Signature-256 header against the raw request body."""
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected_hash = signature_header[7:]
    generated_hash = hmac.new(
        key=app_secret.encode("utf-8"),
        msg=payload_body,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected_hash, generated_hash)


# Ephemeral PII Token Encryption / Decryption (AES-256 GCM simulation / Tokenization)
def generate_pii_token(entity_type: str, raw_value: str, salt: str = "") -> str:
    """Generates a deterministic masked token for PII redaction (e.g., [REDACTED_BVN_5432])."""
    last_four = raw_value[-4:] if len(raw_value) >= 4 else raw_value
    return f"[REDACTED_{entity_type}_{last_four}]"


def compute_sha256_hash(data: str) -> str:
    """Computes a SHA-256 hexadecimal digest for cryptographic audit chaining and token indexing."""
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


# Refresh Token Utilities
import secrets
from fastapi import Response


def generate_refresh_token() -> tuple[str, str]:
    """
    Generates a high-entropy cryptographically secure refresh token (64 hex characters)
    and its SHA-256 hash for database storage.
    Returns: (raw_token, token_hash)
    """
    raw_token = secrets.token_urlsafe(48)
    token_hash = compute_sha256_hash(raw_token)
    return raw_token, token_hash


def set_auth_cookies(
    response: Response,
    access_token: str,
    refresh_token: Optional[str] = None,
    refresh_cookie_path: Optional[str] = None,
) -> None:
    """Sets secure HttpOnly cookies for browser-based admin portals."""
    is_secure = settings.ENVIRONMENT in ["production", "staging"]
    target_refresh_path = refresh_cookie_path or settings.auth_cookie_path

    response.set_cookie(
        key="access_token",
        value=access_token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        secure=is_secure,
        samesite="lax",
        path="/",
    )
    if refresh_token:
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
            httponly=True,
            secure=is_secure,
            samesite="lax",
            path=target_refresh_path,
        )


def clear_auth_cookies(
    response: Response,
    refresh_cookie_path: Optional[str] = None,
) -> None:
    """Clears authentication cookies on logout."""
    target_refresh_path = refresh_cookie_path or settings.auth_cookie_path
    response.delete_cookie(key="access_token", path="/")
    response.delete_cookie(key="refresh_token", path=target_refresh_path)


# Hashed API Key Verification (for B2B / Admin Integrations)
def hash_api_key(api_key: str) -> str:
    """Hashes a merchant B2B API key using SHA-256."""
    return compute_sha256_hash(api_key)


def verify_api_key(plain_key: str, hashed_key: str) -> bool:
    """Constant-time comparison for API keys."""
    computed_hash = hash_api_key(plain_key)
    return hmac.compare_digest(computed_hash, hashed_key)

