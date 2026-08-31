# 18. Pre-Provisioned Virtual NUBAN Pool with Cooldown Quarantine

We decided to manage dynamic virtual NUBAN accounts via a pre-provisioned pool per merchant with a 30-minute post-expiration cooldown quarantine before recycling accounts.

Pre-provisioned local pooling eliminates external bank API latency on checkout initiation (<10ms local checkout assignment) and guarantees availability during partner bank API downtimes. The 30-minute quarantine period prevents transaction collision from delayed interbank NIBSS Instant Payment (NIP) settlements.
