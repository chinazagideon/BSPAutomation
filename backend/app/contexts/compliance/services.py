"""Application Services for NDPA Compliance, PII Sanitization, and Chained Consent Auditing."""

import re
from typing import List, Tuple, Optional
from uuid import UUID
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.contexts.compliance.models import ConsentEvent, PiiRedactionAudit
from app.contexts.compliance.schemas import (
    PiiSanitizeRequest,
    PiiSanitizeResponse,
    RedactedEntity,
    ConsentLogRequest,
    ConsentEventRead,
)
from app.core.security import compute_sha256_hash


def sanitize_nigerian_pii_detailed(text: str) -> Tuple[str, List[RedactedEntity]]:
    """
    Scans and sanitizes Nigerian financial and national identifiers:
    - 16-digit Debit Card PAN
    - 11-digit Bank Verification Number (BVN)
    - 11-digit National Identity Number (NIN)
    - 10-digit NUBAN Bank Account Number
    """
    redacted: List[RedactedEntity] = []
    sanitized = text

    # 1. Debit Card PAN (16 digits)
    card_pattern = r"\b(?:\d{4}[-\s]?){3}\d{4}\b"
    for match in re.finditer(card_pattern, text):
        raw = match.group(0)
        clean = re.sub(r"[-\s]", "", raw)
        if len(clean) == 16:
            token = f"[REDACTED_CARD_PAN_{clean[-4:]}]"
            redacted.append(RedactedEntity(type="CARD_PAN", value=raw, token=token))
            sanitized = sanitized.replace(raw, token)

    # 2. Explicit BVN (11 digits)
    bvn_pattern = r"\b((?:my\s+)?(?:bvn|bank\s*verification\s*(?:no|number|num)?|bank\s*id)\s*(?:is|be|dey|:=|:|=|-|#)?\s*)(\d{11})\b"
    for match in re.finditer(bvn_pattern, sanitized, flags=re.IGNORECASE):
        prefix = match.group(1)
        bvn = match.group(2)
        token = f"[REDACTED_BVN_{bvn[-4:]}]"
        redacted.append(RedactedEntity(type="BVN", value=bvn, token=token))
        sanitized = sanitized.replace(f"{prefix}{bvn}", f"{prefix}{token}")

    # 3. Explicit NIN (11 digits)
    nin_pattern = r"\b((?:my\s+)?(?:nin|nimc(?:\s*nin)?|national\s*(?:id(?:entity)?|identification))\s*(?:is|be|dey|:=|:|=|-|#)?\s*)(\d{11})\b"
    for match in re.finditer(nin_pattern, sanitized, flags=re.IGNORECASE):
        prefix = match.group(1)
        nin = match.group(2)
        token = f"[REDACTED_NIN_{nin[-4:]}]"
        redacted.append(RedactedEntity(type="NIN", value=nin, token=token))
        sanitized = sanitized.replace(f"{prefix}{nin}", f"{prefix}{token}")

    # 4. Explicit NUBAN Account (10 digits)
    nuban_pattern = r"\b((?:my\s+)?(?:account|acct|nuban|bank\s*account)\s*(?:is|be|dey|:=|:|=|-|#)?\s*)(\d{10})\b"
    for match in re.finditer(nuban_pattern, sanitized, flags=re.IGNORECASE):
        prefix = match.group(1)
        acct = match.group(2)
        token = f"[REDACTED_NUBAN_{acct[-4:]}]"
        redacted.append(RedactedEntity(type="NUBAN", value=acct, token=token))
        sanitized = sanitized.replace(f"{prefix}{acct}", f"{prefix}{token}")

    return sanitized, redacted


class ComplianceService:
    @staticmethod
    def sanitize_text(request: PiiSanitizeRequest) -> PiiSanitizeResponse:
        """Executes zero-retention PII sanitization returning masked text and token mapping."""
        sanitized_text, redacted_entities = sanitize_nigerian_pii_detailed(request.text)
        safety_score = 100 if len(redacted_entities) > 0 else 98

        return PiiSanitizeResponse(
            original_text=request.text,
            sanitized_text=sanitized_text,
            redacted_entities=redacted_entities,
            safety_score=safety_score,
        )

    @staticmethod
    async def log_chained_consent_event(
        session: AsyncSession,
        merchant_id: UUID,
        request: ConsentLogRequest,
    ) -> ConsentEventRead:
        """
        Records an NDPA 2023 consent action in the SHA-256 cryptographically chained audit ledger.
        """
        # Retrieve previous event hash for this merchant
        last_event_query = await session.execute(
            select(ConsentEvent)
            .where(ConsentEvent.merchant_id == merchant_id)
            .order_by(desc(ConsentEvent.created_at))
            .limit(1)
        )
        last_event = last_event_query.scalar_one_or_none()
        prev_hash = last_event.immutable_hash if last_event else "0" * 64

        now = datetime.now(timezone.utc)
        iso_time = now.isoformat()
        digest_input = f"{prev_hash}|{request.customer_phone}|{request.action}|{iso_time}"
        immutable_hash = compute_sha256_hash(digest_input)

        event = ConsentEvent(
            merchant_id=merchant_id,
            customer_phone=request.customer_phone,
            action=request.action,
            channel=request.channel,
            previous_event_hash=prev_hash,
            immutable_hash=immutable_hash,
            created_at=now,
        )
        session.add(event)
        await session.flush()

        return ConsentEventRead.model_validate(event)

    @staticmethod
    def check_opt_out_keyword(text: str) -> Optional[str]:
        """
        Intercepts explicit NDPA opt-out trigger keywords on fast-path:
        STOP, UNSUBSCRIBE, CANCEL, COMOT.
        """
        upper = text.strip().upper()
        if upper in ["STOP", "UNSUBSCRIBE", "CANCEL"]:
            return "OPT_OUT_STOP"
        if upper in ["COMOT", "NO SEND AGAIN", "COMOT ME"]:
            return "OPT_OUT_COMOT"
        return None
