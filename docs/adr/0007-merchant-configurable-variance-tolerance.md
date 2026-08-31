# 7. Merchant-Configurable Variance Tolerance Policy

We decided to keep double-entry ledger reconciliation strictly deterministic while allowing the variance tolerance threshold (e.g. for USSD transfer fees or stamp duties) to be configured per merchant via their dashboard.

Different business verticals (high-volume FMCG vs high-ticket real estate) require different tolerance policies for minor bank transfer deductions. Storing the threshold in merchant settings preserves database consistency without hardcoding business rules.
