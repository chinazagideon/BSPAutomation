# Checkout & Ledger Context

Maintains active cart states during asynchronous bank transfers, issues dedicated dynamic virtual NUBANs (Moniepoint MFB primary), and enforces 4-leg double-entry balance verification on all settlements.

## Language

**Anti-Ghosting Cart**:
An active customer order preserved in persistent storage while the buyer switches out of WhatsApp to complete a bank transfer or USSD transaction.
_Avoid_: Pending order, draft checkout

**Dynamic Virtual NUBAN**:
A dedicated temporary 10-digit Nigerian bank account number generated dynamically per active checkout hold for unambiguous, 100% correlated settlement matching.
_Avoid_: Static account, merchant account

**4-Leg Double-Entry Settlement**:
A balanced ledger entry recording Clearing Asset debit, Gateway Processing Fee debit, Statutory Stamp Duty debit, and Merchant Payable/Revenue credit.
_Avoid_: Payment log, transaction record

**Variance Tolerance Policy**:
A merchant-configurable numerical threshold defining the acceptable discrepancy between an invoice and received bank settlement before flagging for manual review.
_Avoid_: Error margin, payment slack

**Double-Entry Reconciler**:
The deterministic validator ensuring that every transaction satisfies Assets = Liabilities + Equity before writing ledger entries.
_Avoid_: Payment checker, balance validator

**Mismatch Explainer**:
An AI-driven diagnostic tool that analyzes discrepancy between received bank transfer payloads and expected amounts, explaining gateway deductions or shortfalls to merchants.
_Avoid_: Error logger, payment debugger

**Virtual NUBAN Cooldown Quarantine**:
A 30-minute buffer window where an expired virtual account is quarantined before returning to the available pool to prevent late-arriving transfer collisions.
_Avoid_: Account timeout, hold delay

**Kobo Minor Currency Precision**:
The integer representation of monetary amounts where ₦1.00 equals 100 kobo to prevent floating-point rounding discrepancies in double-entry reconciliation.
_Avoid_: Fractional Naira, decimal amount

