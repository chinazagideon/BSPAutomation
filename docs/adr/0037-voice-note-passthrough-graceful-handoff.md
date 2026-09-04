# 37. Voice Note Passthrough and Graceful Handoff

## Context
In Nigerian commercial WhatsApp messaging, customers frequently communicate using voice notes in varying dialects (Nigerian Pidgin, Yoruba, Igbo, Hausa) with heavy street background noise. Integrating third-party speech-to-text models (e.g. Whisper) adds 1–3 seconds of latency, high token/compute cost, and frequent transcription hallucinations on localized trade vernacular.

## Decision
We decided to adopt a Voice Note Passthrough policy: the system preserves incoming audio messages by recording their immutable Meta `media_id` in `ingress.messages` (`raw_text_redacted = "[VOICE_NOTE_MEDIA_ID: {media_id}]"`, `direction = "INBOUND"`), dispatches an automated tone-matched Pidgin/English acknowledgment offering the customer the option to type if urgent, and gracefully triggers a human desk handoff (`DISPATCH_AGENT_HANDOFF`) so human agents can play the original audio directly in the desk interface.

## Consequences
- **Pros**: Zero transcription latency and API costs; avoids embarrassing dialect translation errors; delivers superior customer experience by letting human agents hear nuances, intonations, and emotion directly.
- **Cons**: Escalates all voice notes to human agents rather than resolving them automatically via self-service bots.
