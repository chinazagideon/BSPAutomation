# 8. Tenant and Resource Level PostgreSQL GiST Constraint

We decided to apply PostgreSQL `TSTZRANGE` GiST exclusion constraints on `(merchant_id WITH =, resource_id WITH =, time_range WITH &&)` for the reservations engine.

This provides mathematical zero double-booking guarantees partitioned cleanly across multiple merchants and multiple internal staff or assets (doctors, inspection officers, dispatch riders) within a single database table.
