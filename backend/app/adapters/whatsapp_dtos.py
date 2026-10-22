"""Anti-Corruption Layer (ACL) DTO Contracts and Canonical Payload Normalizers for WhatsApp BSPs."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.adapters.base import NormalizedInboundEnvelope


class MetaTextMessageDTO(BaseModel):
    preview_url: bool = False
    body: str


class MetaSendTextMessageRequestDTO(BaseModel):
    messaging_product: str = "whatsapp"
    recipient_type: str = "individual"
    to: str
    type: str = "text"
    text: MetaTextMessageDTO


class MetaMessageCreatedDTO(BaseModel):
    id: str


class MetaSendMessageResponseDTO(BaseModel):
    messaging_product: str = "whatsapp"
    contacts: List[Dict[str, Any]] = Field(default_factory=list)
    messages: List[MetaMessageCreatedDTO]


def extract_cloud_api_phone_number_id(payload: Dict[str, Any]) -> Optional[str]:
    """Extracts external WhatsApp phone_number_id from Cloud API-compatible webhook payloads."""
    if "entry" in payload and isinstance(payload["entry"], list) and len(payload["entry"]) > 0:
        entry = payload["entry"][0]
        changes = entry.get("changes", [])
        if changes and isinstance(changes, list) and len(changes) > 0:
            value = changes[0].get("value", {})
            metadata = value.get("metadata", {})
            if "phone_number_id" in metadata:
                return str(metadata["phone_number_id"])
    return payload.get("phone_number_id")


def normalize_cloud_api_webhook_payload(
    payload: Dict[str, Any],
    provider_name: str = "META_CLOUD",
) -> NormalizedInboundEnvelope:
    """Normalizes Cloud API-shaped JSON structures into a canonical NormalizedInboundEnvelope."""
    phone_number_id = extract_cloud_api_phone_number_id(payload)
    env = NormalizedInboundEnvelope(
        provider=provider_name,
        phone_number_id=phone_number_id,
    )

    if not payload.get("entry") or not isinstance(payload["entry"], list):
        return env

    entry = payload["entry"][0]
    changes = entry.get("changes", [])
    if not changes or not isinstance(changes, list):
        return env

    value = changes[0].get("value", {})
    contacts = value.get("contacts", [])
    if contacts and isinstance(contacts, list) and len(contacts) > 0:
        profile = contacts[0].get("profile", {})
        env.customer_name = profile.get("name", "Valued Customer")

    statuses = value.get("statuses", [])
    if statuses and isinstance(statuses, list) and len(statuses) > 0:
        st = statuses[0]
        env.is_status_update = True
        env.status_value = str(st.get("status", "delivered"))
        env.status_message_id = str(st.get("id", ""))
        env.sender_phone = str(st.get("recipient_id", ""))
        return env

    messages = value.get("messages", [])
    if not messages or not isinstance(messages, list):
        return env

    msg = messages[0]
    env.has_message = True
    env.sender_phone = str(msg.get("from", ""))
    env.message_id = str(msg.get("id", ""))
    msg_type = msg.get("type", "text")
    env.message_type = msg_type

    if msg_type == "text":
        env.text = msg.get("text", {}).get("body", "").strip()
    elif msg_type == "interactive":
        env.is_interactive = True
        interactive = msg.get("interactive", {})
        itype = interactive.get("type")
        if itype == "button_reply":
            reply = interactive.get("button_reply", {})
            env.text = reply.get("title", "")
            env.interactive_id = reply.get("id")
        elif itype == "list_reply":
            reply = interactive.get("list_reply", {})
            env.text = reply.get("title", "")
            env.interactive_id = reply.get("id")
    elif msg_type == "button":
        env.is_interactive = True
        btn = msg.get("button", {})
        env.text = btn.get("text", "")
        env.interactive_id = btn.get("payload")
    elif msg_type in ["audio", "voice"]:
        env.is_audio = True
        audio = msg.get("audio", {}) or msg.get("voice", {})
        media_id = audio.get("id")
        env.media_id = media_id
        env.text = f"[VOICE_NOTE_MEDIA_ID: {media_id}]"
    elif msg_type == "reaction":
        reaction = msg.get("reaction", {})
        emoji = reaction.get("emoji", "👍")
        env.reaction_emoji = emoji
        env.text = f"[REACTION: {emoji}]"
    elif msg_type == "location":
        loc = msg.get("location", {})
        env.location_coords = {
            "latitude": loc.get("latitude"),
            "longitude": loc.get("longitude"),
            "name": loc.get("name"),
            "address": loc.get("address"),
        }
        addr = loc.get("name") or loc.get("address") or f"{loc.get('latitude')},{loc.get('longitude')}"
        env.text = f"Deliver to {addr}"
    else:
        env.text = f"[UNSUPPORTED_MESSAGE_TYPE: {msg_type}]"

    return env
