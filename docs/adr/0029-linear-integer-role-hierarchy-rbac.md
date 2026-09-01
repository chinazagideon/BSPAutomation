# 29. Linear Integer Role Hierarchy for Role-Based Access Control (RBAC)

## Context

In an enterprise SME platform with diverse organizational roles (`OWNER`, `ADMIN`, `MANAGER`, `AGENT`, `READ_ONLY`), maintaining exhaustive lists of permitted roles for dozens of API endpoints creates code verbosity, authorization drift, and high regression risk whenever a new role is introduced.

## Decision

We decided to implement a **Linear Integer Role Hierarchy**:

1. **Explicit Integer Role Ranks**:
   - `OWNER = 100` (Business proprietor, full tenant administration, financial settlement configuration, billing).
   - `ADMIN = 80` (System administrator, user provisioning, operational configuration).
   - `MANAGER = 60` (Desk manager, queue reassignment, ticket resolution, catalog management).
   - `AGENT = 40` (Customer support agent, live chat responder, reservation booking).
   - `READ_ONLY = 20` (Auditor, read-only analytics, compliance reviewer).
2. **Declarative Minimum Role Guard**:
   - FastAPI dependencies enforce access via `require_min_role(Role.MANAGER)`. Any authenticated user whose role rank is greater than or equal to the required threshold is granted access automatically.
3. **High-Risk Financial & Compliance Action Overrides**:
   - Operations that permanently alter financial balances (manual journal entry posting), modify RLS tenant configurations, or export NDPA PII audit vaults bypass generic role hierarchy and require explicit `OWNER` or `ADMIN` verification.

## Consequences

- **Pros**:
  - Clean, readable route definitions (`Depends(require_min_role(Role.AGENT))`).
  - Zero permission drift when adding intermediate operational tiers.
  - Strict isolation of sensitive financial and compliance capabilities.
- **Cons**:
  - Requires all operational roles within a merchant to conform to a single linear hierarchy.
