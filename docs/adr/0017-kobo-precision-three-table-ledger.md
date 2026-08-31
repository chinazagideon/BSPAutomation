# 17. Integer Kobo Precision and Three-Table Immutable Double-Entry Ledger Engine

We decided to record all monetary values as integer Kobo (`BIGINT`) with ISO-4217 currency identifiers, and implement the double-entry accounting engine using a three-table immutable structure (`ledger_accounts`, `journal_entries`, `journal_postings`) with balanced debit/credit validation.

Integer Kobo eliminates all floating-point rounding errors and fractional discrepancies when reconciling Nigerian payment settlements against statutory deductions (gateway processing fees and stamp duty). The three-table model supports arbitrary multi-leg splits (e.g. 4-leg settlements) while maintaining an auditable, append-only financial journal.
