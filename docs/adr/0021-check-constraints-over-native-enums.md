# 21. Check Constraints over Native PostgreSQL Enums for Zero-Downtime Migrations

We decided to model entity statuses and categories using `VARCHAR(32)` with database-level `CHECK` constraints rather than PostgreSQL native `ENUM` types.

Native PostgreSQL ENUMs introduce operational friction during zero-downtime continuous deployment, requiring transactional locks and complex migration workarounds to add or rename values. Check constraints provide equivalent integrity guarantees while allowing seamless schema alterations via `ADD CONSTRAINT ... NOT VALID` and `VALIDATE CONSTRAINT`.
