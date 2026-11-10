"""Application Services for Anti-Ghosting Checkout Carts and 4-Leg Double Entry Ledger."""

from datetime import datetime, timedelta, timezone
from uuid import UUID
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.contexts.ledger.models import CheckoutCart, CartItem, VirtualNuban, JournalEntry, JournalPosting
from app.contexts.ledger.schemas import CartCreateRequest, CartResponse, VirtualNubanRead, LedgerValidationRequest, LedgerValidationResponse
from app.adapters.moniepoint import get_payment_gateway_adapter


class LedgerService:
    @staticmethod
    async def create_anti_ghosting_cart(
        session: AsyncSession,
        merchant_id: UUID,
        request: CartCreateRequest,
    ) -> CartResponse:
        """
        Creates an anti-ghosting checkout cart with an atomic 10-minute hold and
        generates a dedicated dynamic virtual NUBAN via Moniepoint MFB.
        """
        total_kobo = sum(item.unit_price_kobo * item.quantity for item in request.items)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=request.hold_minutes)

        cart = CheckoutCart(
            merchant_id=merchant_id,
            conversation_id=request.conversation_id,
            customer_phone=request.customer_phone,
            cart_status="HELD_PENDING_TRANSFER",
            total_amount_kobo=total_kobo,
            expires_at=expires_at,
        )
        session.add(cart)
        await session.flush()

        from app.contexts.knowledge.offering_schemas import compute_offering_id

        for item_data in request.items:
            resolved_offering_id = item_data.offering_id or UUID(compute_offering_id(merchant_id, item_data.item_sku))
            item = CartItem(
                cart_id=cart.id,
                offering_id=resolved_offering_id,
                item_sku=item_data.item_sku,
                item_title=item_data.item_title,
                unit_price_kobo=item_data.unit_price_kobo,
                quantity=item_data.quantity,
                subtotal_kobo=item_data.unit_price_kobo * item_data.quantity,
            )
            session.add(item)

        # Generate Dedicated Virtual NUBAN via Adapter
        payment_adapter = get_payment_gateway_adapter()
        nuban_data = await payment_adapter.generate_virtual_nuban(
            merchant_id=str(merchant_id),
            customer_phone=request.customer_phone,
            amount_kobo=total_kobo,
            order_reference=f"CART_{str(cart.id)[:8]}",
        )

        virtual_nuban = VirtualNuban(
            merchant_id=merchant_id,
            cart_id=cart.id,
            bank_name=nuban_data.get("bank_name", "Moniepoint MFB"),
            bank_code=nuban_data.get("bank_code", "50515"),
            account_number=nuban_data.get("account_number", "9031842901"),
            account_name=nuban_data.get("account_name", "Enterprise SME Store"),
            status="ASSIGNED",
            assigned_at=datetime.now(timezone.utc),
        )
        session.add(virtual_nuban)
        await session.flush()

        return CartResponse(
            id=cart.id,
            customer_phone=cart.customer_phone,
            total_amount_kobo=cart.total_amount_kobo,
            total_amount_naira=cart.total_amount_kobo / 100.0,
            cart_status=cart.cart_status,
            expires_at=cart.expires_at,
            virtual_nuban=VirtualNubanRead(
                bank_name=virtual_nuban.bank_name,
                bank_code=virtual_nuban.bank_code,
                account_number=virtual_nuban.account_number,
                account_name=virtual_nuban.account_name,
                amount_kobo=total_kobo,
                amount_naira=total_kobo / 100.0,
                expires_in_seconds=request.hold_minutes * 60,
            ),
        )

    @staticmethod
    def validate_ledger_equation(request: LedgerValidationRequest) -> LedgerValidationResponse:
        """
        Validates double-entry fundamental equation (Assets = Liabilities + Equity)
        and verifies bank transfer variance against expected invoice amount.
        """
        is_balanced = abs(request.assets - (request.liabilities + request.equity)) < 0.01
        is_amount_matched = request.received_amount == request.expected_amount
        variance = request.expected_amount - request.received_amount

        ai_explanation = None
        if not is_balanced:
            ai_explanation = (
                f"Ledger Imbalance Detected: Assets (₦{request.assets:,.2f}) does not equal "
                f"Liabilities (₦{request.liabilities:,.2f}) + Equity (₦{request.equity:,.2f}). "
                f"Verify debit/credit balancing legs."
            )
        elif not is_amount_matched:
            ai_explanation = (
                f"Payment Discrepancy: Received ₦{request.received_amount:,.2f} vs Expected ₦{request.expected_amount:,.2f} "
                f"(Variance: ₦{variance:,.2f}). Check for gateway fee deduction (₦100) or stamp duty (₦50)."
            )

        status_str = "SETTLED_BALANCED" if is_balanced and is_amount_matched else "MISMATCH_ALERT"
        eq_str = f"₦{request.assets:,.2f} (Assets) {'==' if is_balanced else '!='} ₦{request.liabilities:,.2f} (Liabilities) + ₦{request.equity:,.2f} (Equity)"

        return LedgerValidationResponse(
            transaction_ref=request.transaction_ref,
            assets=request.assets,
            liabilities=request.liabilities,
            equity=request.equity,
            is_balanced=is_balanced,
            is_amount_matched=is_amount_matched,
            variance_naira=variance,
            status=status_str,
            ai_explanation=ai_explanation,
            accounting_equation=eq_str,
        )
