"""Typed Domain Gateway Exceptions for Anti-Corruption Layer Error Handling."""

from typing import Optional, Any, Dict


class DomainGatewayException(Exception):
    """Base exception for all third-party external gateway failures."""

    def __init__(
        self,
        message: str,
        provider: str,
        status_code: Optional[int] = None,
        error_code: Optional[str] = None,
        raw_error: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.provider = provider
        self.status_code = status_code
        self.error_code = error_code
        self.raw_error = raw_error or {}


# Payment Gateway Domain Exceptions
class PaymentGatewayException(DomainGatewayException):
    """Base exception for payment gateway clearing errors (Moniepoint MFB, Paystack)."""
    pass


class PaymentGatewayDeclinedException(PaymentGatewayException):
    """Raised when an account creation or transfer request is explicitly declined by the bank rail."""
    pass


class PaymentGatewayTimeoutException(PaymentGatewayException):
    """Raised when the payment provider clearing network times out."""
    pass


# WhatsApp BSP Domain Exceptions
class WhatsAppBSPException(DomainGatewayException):
    """Base exception for WhatsApp Business Solution Provider failures."""
    pass


class WhatsAppRateLimitedException(WhatsAppBSPException):
    """Raised when Meta or Termii throttles outbound conversational messaging."""
    pass


class WhatsAppDeliveryFailedException(WhatsAppBSPException):
    """Raised when an outbound WhatsApp message cannot be delivered to the recipient."""
    pass


# Schema & Anti-Corruption Invariant Exceptions
class ProviderSchemaMismatchException(DomainGatewayException):
    """Raised when an external API response fails strict DTO hydration validation."""
    pass


# Multi-Channel Security & Anti-Spoofing Exceptions (ADR-0048)
class TenantChannelSecurityError(Exception):
    """Raised when an outbound egress attempt requests an unauthorized or inactive phone_number_id."""
    def __init__(self, merchant_id: str, phone_number_id: str, reason: str = "Unauthorized"):
        super().__init__(f"Security violation for tenant {merchant_id}: phone_number_id '{phone_number_id}' is {reason}")
        self.merchant_id = merchant_id
        self.phone_number_id = phone_number_id
        self.reason = reason
