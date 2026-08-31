# 3. Dual-Layer PostgreSQL GiST and Redis Reservation Holds

We decided to combine PostgreSQL `TSTZRANGE` with GiST exclusion constraints at the persistence layer and Redis TTL keyspace notifications at the memory caching layer for appointment slot holds.

PostgreSQL GiST constraints mathematically eliminate double-booking race conditions across concurrent booking requests. Redis provides lightweight, sub-millisecond 10-minute hold countdowns and reactive UI timer notifications without polling the database.
