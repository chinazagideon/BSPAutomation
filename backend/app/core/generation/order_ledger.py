"""Persistent Customer Order Repository for PostgreSQL (ledger.customer_orders).

Decoupled from transient LIFO ContextStack so logistics, status, and delivery inquiries
can resolve against a customer's real purchase history.
"""

import time
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

import structlog
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.ledger.models import CustomerOrder
from app.core.database import async_session_factory

logger = structlog.get_logger(__name__)

ORDER_LEDGER_MAX_ENTRIES = 10
_IN_MEMORY_ORDER_FALLBACK: Dict[str, List[Dict[str, Any]]] = {}


class OrderReference(BaseModel):
    """Pydantic representation of a persistent customer order."""
    id: Optional[str] = None
    order_summary: str
    delivery_zone: Optional[str] = None
    fulfillment_type: Optional[str] = None
    total_kobo: int = 0
    created_at: float = Field(default_factory=time.time)
    metadata_json: Dict[str, Any] = Field(default_factory=dict)


class OrderInquiryResult(BaseModel):
    """Structured result of customer order status inquiry (ADR-0048)."""
    cardinality: Literal["ZERO", "SINGLE", "MULTIPLE"]
    order: Optional[OrderReference] = None
    orders: List[OrderReference] = Field(default_factory=list)


class CustomerOrderLedger:
    """PostgreSQL persistent repository for customer orders with in-memory fallback."""

    @classmethod
    async def list_recent(
        cls,
        merchant_id: str,
        customer_phone: str,
        session: Optional[AsyncSession] = None,
        limit: int = ORDER_LEDGER_MAX_ENTRIES,
    ) -> List[OrderReference]:
        """Queries recent customer orders from PostgreSQL, newest first."""
        try:
            m_uuid = UUID(merchant_id)
        except (ValueError, TypeError):
            m_uuid = None

        if m_uuid:
            if session:
                return await cls._query_db(session, m_uuid, customer_phone, limit)
            try:
                async with async_session_factory() as ephemeral_session:
                    return await cls._query_db(ephemeral_session, m_uuid, customer_phone, limit)
            except Exception as err:
                logger.warning("customer_orders_db_query_fallback", error=str(err))

        # In-memory fallback
        key = f"{merchant_id}:{customer_phone}"
        raw = _IN_MEMORY_ORDER_FALLBACK.get(key, [])
        return [OrderReference.model_validate(item) for item in raw[:limit]]

    @staticmethod
    async def _query_db(
        session: AsyncSession,
        merchant_uuid: UUID,
        customer_phone: str,
        limit: int,
    ) -> List[OrderReference]:
        stmt = (
            select(CustomerOrder)
            .where(
                CustomerOrder.merchant_id == merchant_uuid,
                CustomerOrder.customer_phone == customer_phone,
            )
            .order_by(desc(CustomerOrder.created_at))
            .limit(limit)
        )
        res = await session.execute(stmt)
        rows = res.scalars().all()
        return [
            OrderReference(
                id=str(row.id),
                order_summary=row.order_summary,
                delivery_zone=row.delivery_zone,
                fulfillment_type=row.fulfillment_type,
                total_kobo=row.total_kobo,
                created_at=row.created_at.timestamp() if row.created_at else time.time(),
                metadata_json=row.metadata_json or {},
            )
            for row in rows
        ]

    @classmethod
    async def lookup_order_for_inquiry(
        cls,
        merchant_id: str,
        customer_phone: str,
        order_ref: Optional[str] = None,
        session: Optional[AsyncSession] = None,
    ) -> OrderInquiryResult:
        """
        Looks up customer orders for post-purchase order tracking (ADR-0048).
        Strictly NDPA-compliant: searches by (merchant_id, customer_phone) or explicit order_ref.
        """
        recent = await cls.list_recent(merchant_id, customer_phone, session=session, limit=5)

        if order_ref:
            ref_clean = order_ref.lstrip("#").strip().lower()
            matching = [o for o in recent if o.id and o.id.lower().startswith(ref_clean)]
            if matching:
                return OrderInquiryResult(cardinality="SINGLE", order=matching[0], orders=[matching[0]])

        if not recent:
            return OrderInquiryResult(cardinality="ZERO", order=None, orders=[])
        if len(recent) == 1:
            return OrderInquiryResult(cardinality="SINGLE", order=recent[0], orders=recent)
        return OrderInquiryResult(cardinality="MULTIPLE", order=recent[0], orders=recent)

    @classmethod
    async def record_order(
        cls,
        merchant_id: str,
        customer_phone: str,
        bound_slots: Dict[str, Any],
        total_kobo: int,
        cart_id: Optional[str] = None,
        session: Optional[AsyncSession] = None,
    ) -> OrderReference:
        """Persists a new order into ledger.customer_orders in PostgreSQL."""
        line_items = bound_slots.get("line_items")
        if isinstance(line_items, list) and len(line_items) > 1:
            summary = bound_slots.get("product_name") or "bulk items"
        else:
            summary = f"{bound_slots.get('quantity', 1)}x {bound_slots.get('product_name', 'item')}"

        delivery_zone = bound_slots.get("delivery_zone") or bound_slots.get("location")
        fulfillment_type = bound_slots.get("fulfillment_type") or "EXPRESS_DELIVERY"
        total = int(total_kobo or 0)

        try:
            m_uuid = UUID(merchant_id)
        except (ValueError, TypeError):
            m_uuid = None

        try:
            c_uuid = UUID(cart_id) if cart_id else None
        except (ValueError, TypeError):
            c_uuid = None

        persisted_id = None
        if m_uuid:
            if session:
                order_row = CustomerOrder(
                    merchant_id=m_uuid,
                    cart_id=c_uuid,
                    customer_phone=customer_phone,
                    order_summary=summary,
                    delivery_zone=delivery_zone,
                    fulfillment_type=fulfillment_type,
                    total_kobo=total,
                    metadata_json=dict(bound_slots),
                )
                session.add(order_row)
                await session.flush()
                persisted_id = str(order_row.id)
            else:
                try:
                    async with async_session_factory() as ephemeral_session:
                        order_row = CustomerOrder(
                            merchant_id=m_uuid,
                            cart_id=c_uuid,
                            customer_phone=customer_phone,
                            order_summary=summary,
                            delivery_zone=delivery_zone,
                            fulfillment_type=fulfillment_type,
                            total_kobo=total,
                            metadata_json=dict(bound_slots),
                        )
                        ephemeral_session.add(order_row)
                        await ephemeral_session.commit()
                        persisted_id = str(order_row.id)
                except Exception as err:
                    logger.warning("customer_orders_db_insert_fallback", error=str(err))

        ref = OrderReference(
            id=persisted_id,
            order_summary=summary,
            delivery_zone=delivery_zone,
            fulfillment_type=fulfillment_type,
            total_kobo=total,
            created_at=time.time(),
            metadata_json=dict(bound_slots),
        )

        # Update in-memory fallback
        key = f"{merchant_id}:{customer_phone}"
        existing = _IN_MEMORY_ORDER_FALLBACK.get(key, [])
        _IN_MEMORY_ORDER_FALLBACK[key] = [ref.model_dump()] + existing[:ORDER_LEDGER_MAX_ENTRIES - 1]

        return ref
