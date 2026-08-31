# 13. Dynamic Dedicated Virtual NUBAN Session Correlation

We decided to generate dynamic, dedicated virtual NUBAN accounts per active checkout hold (10-minute validity) rather than relying on static accounts with manual transfer narration references.

Nigerian bank apps frequently truncate, delay, or strip narration remarks during interbank NIBSS Instant Payment (NIP) transfers. Dedicated virtual accounts guarantee 100% deterministic, automated correlation between the bank webhook and the customer's WhatsApp shopping cart.
