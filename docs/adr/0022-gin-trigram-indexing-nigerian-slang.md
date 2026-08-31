# 22. PostgreSQL GIN Trigram Indexing for Nigerian Slang and Catalog Matching

We decided to use the PostgreSQL `pg_trgm` extension with GIN trigram indexes on catalog item names, descriptions, and Nigerian Pidgin / Slang phrase dictionaries.

GIN trigram indexes enable sub-millisecond typo-tolerant fuzzy matching (`word_similarity() > 0.6`) directly in the transactional database. This allows fast-path intent matching and inventory lookups without the infrastructure complexity, operational overhead, and network latency of an external search engine cluster.
