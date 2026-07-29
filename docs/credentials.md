# Credentials and external integrations

The repository contains variable names and setup procedures, never usable secret values. Copy
`.env.example` to an ignored `.env` only for local development. Production values belong in the
platform secret manager.

## OpenAI

Required only for `AGENT_RUNTIME=openai`:

```dotenv
OPENAI_API_KEY=
```

Use a project-scoped key, server-side only, with a spending limit and alerts. The deterministic
runtime requires no key and is the default for tests and local product exploration.

## Odoo 19 JSON-2

Required only for `ODOO_MODE=json2`:

```dotenv
ODOO_BASE_URL=https://customer.example.com
ODOO_DATABASE=customer_database
ODOO_API_KEY=
```

Create a dedicated bot user. Grant only the models, companies, fields, and records needed by enabled
read tools and approved actions. The bridge addon deliberately avoids `sudo()`.

The reference implementation has one Odoo connection per deployment. A multi-customer SaaS version
should store encrypted per-tenant credential references and resolve them from Vault, AWS Secrets
Manager, Google Secret Manager, or an equivalent system; do not put all customer keys in one JSON
environment variable.

## MCP

The local Compose network is the boundary for the included MCP servers. The client sends service
credentials, but a production deployment must also make the server or gateway validate them. Use
OAuth 2.1, workload identity, mTLS, private networking, and an explicit tool allowlist. Never expose a
customer-data MCP endpoint publicly without real authorization.

## Approval and webhooks

```dotenv
ODOO_BRIDGE_WEBHOOK_SECRET=
ODOO_ACTION_SIGNING_SECRET=
```

Use independent random values. The webhook secret authenticates raw event delivery. The action secret
binds a human decision to the action ID, exact payload hash, and approver. Rotate them independently
with an overlap/replay plan.

## OIDC

Production rejects demo-header authentication:

```dotenv
AUTH_MODE=oidc
OIDC_ISSUER=
OIDC_AUDIENCE=
OIDC_JWKS_URL=
```

Map identity-provider claims to `viewer`, `operator`, `approver`, and `admin`. Role or tenant values
sent by browser JavaScript are not authorization evidence.

## Ownership

| Secret | Runtime consumer | Recommended owner |
|---|---|---|
| OpenAI key | worker | AI/platform team |
| Odoo API key | Odoo MCP and action worker | customer Odoo admin |
| approval signing key | API and worker | security/platform team |
| webhook HMAC key | Odoo addon and API | integration owner |
| OIDC configuration | API and web BFF | identity team |
| external MCP credential | agent worker | connector owner |
