# ADR 0002: durable exact-payload approval outside the agent loop

**Status:** accepted

Agent SDK approval callbacks are useful for interactive tool calls but are not the source of truth for
a business workflow that must survive process restarts and browser disconnects. FlowPilot persists the
proposal, expected hash, approver, expiration, HMAC, and execution job in PostgreSQL. The model never
receives a direct Odoo write tool.
