# 16. PostgreSQL Logical Schemas, Multi-Tenant Row-Level Security, and UUIDv7 Identifiers

We decided to organize the database into five PostgreSQL logical schemas (`ingress`, `ledger`, `reservations`, `desk`, `compliance`), enforce tenant isolation via mandatory `merchant_id` with PostgreSQL Row-Level Security (RLS), and utilize time-ordered `UUIDv7` primary keys across all tables.

Logical schemas provide strict bounded context isolation and modularity while retaining single-database ACID transaction guarantees for cross-context workflows (e.g., atomic appointment slot holds coupled with virtual NUBAN cart generation). Database-level RLS policies mathematically prevent tenant data leakage, and UUIDv7 guarantees collision-free distributed generation while preserving B-Tree sequential indexing locality.
