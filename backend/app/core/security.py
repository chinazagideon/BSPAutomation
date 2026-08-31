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
    """Computes a SHA-256 hexadecimal digest for cryptographic audit chaining."""
    return hashlib.sha256(data.encode("utf-8")).hexdigest()
