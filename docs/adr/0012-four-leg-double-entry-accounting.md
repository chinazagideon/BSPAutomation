# 12. Four-Leg Multi-Tier Double-Entry Settlement Ledger

We decided to structure all completed WhatsApp transactions as 4-leg double-entry transactions debiting Clearing Asset (Moniepoint MFB), Gateway Processing Fee Expense, and Statutory Stamp Duty Expense, and crediting Merchant Payable / Revenue Equity.

Nigerian payment rails deduct gateway fees (e.g. 1.5%) and statutory electronic money transfer levies (₦50 stamp duty) at source. A 4-leg entry guarantees that $Assets = Liabilities + Equity$ always balances deterministically while making fee discrepancies instantly explainable to merchants.
