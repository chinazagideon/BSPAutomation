# 19. Partial GiST Temporal Exclusion Constraint on Active Reservation Slots

We decided to apply PostgreSQL `TSTZRANGE` GiST exclusion constraints with a partial filter: `WHERE (status IN ('HELD_PENDING_PAYMENT', 'CONFIRMED'))`.

Restricting the exclusion constraint to active holds and confirmed appointments mathematically eliminates double-booking race conditions while permitting expired holds, cancellations, and released slots to remain in the same table for reporting, auditing, and analytics without table archiving overhead.
