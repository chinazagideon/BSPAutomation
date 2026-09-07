"""Desk State Context Provider (ADR-0041)."""

from typing import Dict, Any, Optional
from uuid import UUID

from app.core.generation.context import ContextProvider, ContextSlice


class DeskStateSliceProvider(ContextProvider):
    """Provides human agent queue status and desk operating rules for context aggregation."""

    @property
    def slice_name(self) -> str:
        return "desk_state"

    async def resolve(
        self,
        merchant_id: Optional[UUID],
        customer_phone: Optional[str],
        options: Optional[Dict[str, Any]] = None,
    ) -> ContextSlice:
        content = (
            "Support Desk Status: Active\n"
            "Operating Model: 6-Field Context Synthesis Active\n"
            "Escalation Policy: Warm lead and custom consultation handoff supported."
        )
        return ContextSlice(
            slice_name=self.slice_name,
            content=content,
            token_estimate=25,
            is_cached=True,
        )
