# Troubleshooting

## The UI loads but investigations stay queued

Run the worker separately (`uv run flowpilot-worker`) or use Compose. Inspect `/v1/jobs/{id}` for
attempts and `last_error`.

## PostgreSQL rejects every tenant query

The RLS policy is fail-closed. Confirm the API transaction called `set_config` and the application role
does not have `BYPASSRLS`. Run `tests/integration/test_postgres_rls.py` against the migrated database.

## Odoo MCP is unreachable

Check `ODOO_MCP_URL`, DNS inside the deployment network, and the MCP process. The OpenAI runtime can
continue with case/RAG tools but must lower confidence when live Odoo evidence is unavailable.

## Odoo write returns 403 or access error

This is usually correct least-privilege behavior. Review the dedicated bot user's ACLs, record rules,
company, and field access. Do not “fix” it with `sudo()`.

## An approval returns 409

The proposal was already decided, expired, or the browser submitted a stale hash. Reload the action.
Never accept a changed payload under an earlier approval.

## SQLite date/time errors

SQLite does not preserve timezone metadata. The security hash normalizes naive values to UTC, but
production should use PostgreSQL with timezone-aware columns.
