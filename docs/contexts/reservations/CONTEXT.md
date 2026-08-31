# Reservations Context

Manages time-based appointment and resource bookings, preventing race conditions and double-bookings using PostgreSQL GiST constraints and provisional holds.

## Language

**Atomic Slot**:
A discrete time range for a merchant service protected by a PostgreSQL `TSTZRANGE` GiST exclusion constraint to mathematically prevent overlapping bookings.
_Avoid_: Calendar event, appointment slot

**Resource Range Lock**:
A composite exclusion rule indexed across merchant ID, resource/staff ID, and timestamp range enforcing zero-overlap invariants in the database.
_Avoid_: Booking lock, row lock

**Anti-No-Show Hold**:
A 10-minute provisional reservation placed on an Atomic Slot while waiting for a commitment deposit webhook.
_Avoid_: Temporary booking, soft reservation

**Slot Releaser**:
An automated background worker that releases expired provisional holds back into the available pool when the hold TTL expires without payment.
_Avoid_: Booking canceller, timeout cron

**Partial GiST Temporal Lock**:
A PostgreSQL GiST exclusion constraint applied exclusively to active and confirmed slot records, permitting expired holds and cancellations to remain in historical logs without blocking new bookings.
_Avoid_: Conditional lock, active index

