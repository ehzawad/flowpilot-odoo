# ADR 0003: PostgreSQL jobs before Kafka or Redis

**Status:** accepted

Cases, approvals, and execution commands already require PostgreSQL transactions. A jobs table with
unique idempotency keys, leases, retries, and `SKIP LOCKED` gives coherent semantics for the pilot.
Adopt an external broker when measured backlog, fan-out, retention, or organizational boundaries
justify the extra consistency system.
