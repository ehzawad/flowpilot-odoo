# Security model and threat analysis

## Trust boundaries

Model output, user input, retrieved documents, Odoo records, MCP results, webhook bodies, and
third-party responses are untrusted. Policy and authorization live in application code, database
constraints, deployment identity, and Odoo ACLs.

## Principal threats and controls

| Threat | Control |
|---|---|
| Cross-tenant access | tenant predicates, OIDC tenant claim, forced PostgreSQL RLS, isolation test |
| Prompt injection | evidence wrappers, bounded tools, no policy from retrieved text |
| Excessive agency | no agent-visible write tool, exact proposal payload, human approval |
| Approval bait-and-switch | canonical JSON, payload hash, HMAC, worker recomputation |
| Duplicate side effects | inbox uniqueness, job keys, Odoo receipt, outbox key |
| Webhook forgery/replay | timestamped HMAC over raw body, bounded age, event uniqueness |
| MCP expansion | business-level tools, static client allowlist, private network, production auth requirement |
| Confused deputy | dedicated service identities and least-privilege Odoo bot user |
| Secret leakage | ignored env files, BFF, secret manager, no secret logging |
| RAG exfiltration | tenant filter before ranking, RLS, bounded excerpts |
| Cost denial of service | turn/token/time/cost budgets and usage ledger |
| Supply-chain compromise | pinned direct runtime versions, automated dependency review, container scanning |

## Approval state machine

```text
pending ──approve──> approved ──worker claim──> running ──success──> succeeded
   │                    │                           └─failure──> retry/dead
   ├─reject──────────> rejected
   └─expiry──────────> expired
```

Only `approver` and `admin` can approve. The worker verifies state, expiry, exact payload hash,
approver, and HMAC authorization before calling Odoo.

## Row-level security

The migration enables and forces RLS on tenant-owned tables. An application transaction sets:

```sql
SELECT set_config('app.current_organization_id', :tenant_id, true);
```

Use separate migration and application roles, and never grant `BYPASSRLS` to the API. A starter role
script is in `infra/postgres/production_roles.sql`.

## Odoo permissions

The bridge does not use `sudo()`. Odoo ACLs, record rules, company rules, and field access still apply.
Each new write action needs a specific permission story, payload validator, negative test, and kill
switch.

## Known boundary

The local MCP examples are intentionally development services. They bind to the Compose/Kubernetes
network and demonstrate tool schemas and transports. Before exposing them outside a trusted network,
add server-side OAuth/workload authentication; an Authorization header that no server validates is not
a control.

## Production checklist

Replace development secrets, enable OIDC, restrict CORS, isolate MCP/database endpoints, encrypt data
and backups, define retention, run tenant/prompt/approval tests, review traces for customer data, test
backup restoration and key rotation, and assign an incident-response owner.
