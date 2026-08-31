"""Moniepoint MFB Payment Gateway Adapter with Audited Egress & Typed ACL DTOs."""

from typing import Dict, Any, Optional
import random
from pydantic import BaseModel, Field

from app.adapters.base import PaymentGatewayPort
from app.core.config import settings
from app.core.egress import AuditedHttpClient, audited_http_client


# =============================================================================
# MONIEPOINT ANTI-CORRUPTION LAYER (ACL) DTO CONTRACTS
# =============================================================================

class MoniepointCreateAccountRequestDTO(BaseModel):
    """Outbound DTO for requesting dedicated dynamic virtual account creation."""
    amount: float
    customerPhone: str
    reference: str
    bankCode: str = "50515"  # Moniepoint MFB


class MoniepointCreateAccountResponseDTO(BaseModel):
    """Inbound DTO strictly validating Moniepoint MFB account creation response."""
    accountNumber: str = Field(..., min_length=10, max_length=10)
    accountName: str
    bankName: str = "Moniepoint MFB"
    bankCode: str = "50515"
    reference: str
    expiresInSeconds: int = 600


class MoniepointSettlementResponseDTO(BaseModel):
    """Inbound DTO strictly validating Moniepoint settlement payload."""
    reference: str
    status: str
    settledAmount: float
    gatewayFee: float = 100.0  # ₦100.00
    stampDuty: float = 50.0    # ₦50.00


# =============================================================================
# ADAPTER IMPLEMENTATION
# =============================================================================

class MoniepointAdapter(PaymentGatewayPort):
    """Production Moniepoint MFB Adapter using AuditedHttpClient Anti-Corruption Layer."""

    def __init__(self, api_key: str, base_url: str, http_client: Optional[AuditedHttpClient] = None):
        self.api_key = api_key
        self.base_url = base_url
        self.http_client = http_client or audited_http_client

    async def generate_virtual_nuban(
        self,
        merchant_id: str,
        customer_phone: str,
        amount_kobo: int,
        order_reference: str,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}/virtual-accounts"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        request_dto = MoniepointCreateAccountRequestDTO(
            amount=amount_kobo / 100.0,
            customerPhone=customer_phone,
            reference=order_reference,
        )

        # Execute through Audited Egress Gateway with Typed DTO validation
        response_dto: MoniepointCreateAccountResponseDTO = await self.http_client.request(
            method="POST",
            url=url,
            json_body=request_dto,
            headers=headers,
            response_dto=MoniepointCreateAccountResponseDTO,
            target_service="MONIEPOINT_MFB",
            merchant_id=merchant_id,
        )

        return {
            "bank_name": response_dto.bankName,
            "bank_code": response_dto.bankCode,
            "account_number": response_dto.accountNumber,
            "account_name": response_dto.accountName,
            "expires_in_seconds": response_dto.expiresInSeconds,
        }

    async def verify_settlement(self, payment_reference: str) -> Dict[str, Any]:
        url = f"{self.base_url}/transactions/{payment_reference}"
        headers = {"Authorization": f"Bearer {self.api_key}"}

        response_dto: MoniepointSettlementResponseDTO = await self.http_client.request(
            method="GET",
            url=url,
            headers=headers,
            response_dto=MoniepointSettlementResponseDTO,
            target_service="MONIEPOINT_MFB",
        )

        return {
            "reference": response_dto.reference,
            "status": response_dto.status,
            "gateway_fee_kobo": int(response_dto.gatewayFee * 100),
            "stamp_duty_kobo": int(response_dto.stampDuty * 100),
        }


class MockMoniepointAdapter(PaymentGatewayPort):
    """Local Dev & CI Mock Simulator for Moniepoint MFB Virtual NUBANs."""

    async def generate_virtual_nuban(
        self,
        merchant_id: str,
        customer_phone: str,
        amount_kobo: int,
        order_reference: str,
    ) -> Dict[str, Any]:
        random_suffix = random.randint(100000, 999999)
        nuban = f"903{random_suffix:06d}"[:10]
        return {
            "bank_name": "Moniepoint MFB",
            "bank_code": "50515",
            "account_number": nuban,
            "account_name": "Enterprise SME Store",
            "amount_kobo": amount_kobo,
            "amount_naira": amount_kobo / 100.0,
            "order_reference": order_reference,
            "expires_in_seconds": 600,
            "is_mock": True,
        }

    async def verify_settlement(self, payment_reference: str) -> Dict[str, Any]:
        return {
            "reference": payment_reference,
            "status": "SUCCESS",
            "gateway_fee_kobo": 10000,  # ₦100.00
            "stamp_duty_kobo": 5000,    # ₦50.00
            "is_mock": True,
        }


def get_payment_gateway_adapter(http_client: Optional[AuditedHttpClient] = None) -> PaymentGatewayPort:
    """Factory creating payment gateway adapter based on configuration."""
    if settings.USE_MOCK_PAYMENT_GATEWAY or not settings.MONIEPOINT_API_KEY:
        return MockMoniepointAdapter()
    return MoniepointAdapter(settings.MONIEPOINT_API_KEY, settings.MONIEPOINT_BASE_URL, http_client=http_client)
