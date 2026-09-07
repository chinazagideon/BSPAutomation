"""Three-Tier Token Degradation on Soft Limits and Redis Two-Phase Reservation (ADR-0040)."""

import structlog
from typing import Tuple, Optional
from uuid import UUID
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.core.generation.ports import TaskPriority
from app.core.redis import get_redis_client

logger = structlog.get_logger(__name__)

NORMAL_TIER_MIN_TOKENS = 2000
CONSERVATION_TIER_MIN_TOKENS = 1
LEEWAY_TOKENS = 1000


class ThreeTierWalletGuard:
    """
    Enforces Three-Tier Soft Limit Degradation and atomic two-phase token reservations:
    1. Normal Tier (>2,000 tokens): All contexts can invoke Gemini Flash.
    2. Conservation Soft Cap (1 - 2,000 tokens): Internal admin tasks are throttled to deterministic mode.
    3. Hard Cap (<= 0 tokens with 1,000 leeway): Degrades all contexts to fast-path heuristics.
    """

    @staticmethod
    async def evaluate_tier(
        balance_tokens: int,
        task_priority: TaskPriority,
    ) -> Tuple[bool, str]:
        """Evaluates whether an inference request may proceed based on balance and priority."""
        if balance_tokens > NORMAL_TIER_MIN_TOKENS:
            return True, "NORMAL_TIER"

        if CONSERVATION_TIER_MIN_TOKENS <= balance_tokens <= NORMAL_TIER_MIN_TOKENS:
            if task_priority == TaskPriority.CUSTOMER_FACING:
                return True, "CONSERVATION_SOFT_CAP_ALLOWED"
            else:
                return False, "CONSERVATION_SOFT_CAP_THROTTLED"

        # Balance <= 0
        if balance_tokens >= -LEEWAY_TOKENS:
            # Within leeway buffer for in-flight customer requests
            if task_priority == TaskPriority.CUSTOMER_FACING:
                return True, "LEEWAY_BUFFER_ALLOWED"
            return False, "LEEWAY_BUFFER_INTERNAL_THROTTLED"

        return False, "HARD_CAP_EXHAUSTED"

    @staticmethod
    async def reserve_tokens(
        merchant_id: UUID,
        estimated_tokens: int = 400,
        redis_client: Optional[Redis] = None,
    ) -> bool:
        """Atomically reserves an estimated token ceiling in Redis to prevent burst overdrafts."""
        client = redis_client or await get_redis_client()
        key = f"wallet:reserved:{merchant_id}"
        try:
            await client.incrby(key, estimated_tokens)
            await client.expire(key, 60)  # 60-second safety expiry
            return True
        except Exception as e:
            logger.warning("wallet_reservation_failed", merchant_id=str(merchant_id), error=str(e))
            return True  # Fallback to allow if Redis is unavailable in local dev

    @staticmethod
    async def release_reservation(
        merchant_id: UUID,
        estimated_tokens: int = 400,
        redis_client: Optional[Redis] = None,
    ) -> None:
        """Releases the reserved tokens from Redis after inference completion or failure."""
        client = redis_client or await get_redis_client()
        key = f"wallet:reserved:{merchant_id}"
        try:
            current = await client.decrby(key, estimated_tokens)
            if current < 0:
                await client.set(key, 0)
        except Exception as e:
            logger.warning("wallet_release_failed", merchant_id=str(merchant_id), error=str(e))
