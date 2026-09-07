"""Asynchronous Redis Client Manager."""

import structlog
from typing import Optional
from redis.asyncio import Redis, from_url
from app.core.config import settings

logger = structlog.get_logger(__name__)

_redis_client: Optional[Redis] = None


async def get_redis_client() -> Redis:
    """Returns singleton asynchronous Redis client."""
    global _redis_client
    if _redis_client is None:
        _redis_client = from_url(settings.REDIS_URL, decode_responses=True)
    return _redis_client


async def close_redis_client() -> None:
    """Closes the singleton Redis connection pool."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
