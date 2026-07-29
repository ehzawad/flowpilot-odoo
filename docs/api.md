# API and event contracts

FastAPI exposes `/openapi.json` and `/docs` by default.

## Authentication

Development accepts `X-Tenant-ID`, `X-User-ID`, `X-User-Email`, and `X-User-Role`. Production rejects
demo authentication and validates an OIDC bearer token. The Next.js backend-for-frontend attaches
these headers server-side in demo mode.

## Principal routes

| Method | Route | Purpose |
|---|---|---|
| `GET` | `/health` | process liveness |
| `GET` | `/ready` | database readiness |
| `GET` | `/metrics` | Prometheus exposition |
| `GET` | `/v1/dashboard` | tenant summary |
| `GET/POST` | `/v1/cases` | list/create cases |
| `GET` | `/v1/cases/{id}` | case detail |
| `GET` | `/v1/cases/{id}/events` | durable timeline |
| `GET` | `/v1/cases/{id}/events/stream` | reconnectable SSE projection |
| `POST` | `/v1/cases/{id}/investigations` | enqueue an investigation |
| `GET` | `/v1/jobs/{id}` | durable job state |
| `GET` | `/v1/cases/{case_id}/agent-runs/{run_id}` | persisted agent result |
| `GET` | `/v1/approvals` | pending proposals |
| `POST` | `/v1/actions/{id}/decision` | approve/reject exact payload |
| `GET` | `/v1/integrations` | connector status |
| `GET` | `/v1/usage` | tenant usage/cost summary |
| `POST` | `/v1/knowledge/documents` | ingest a tenant document |
| `GET` | `/v1/knowledge/search?q=...` | inspect retrieval |
| `POST` | `/v1/webhooks/odoo` | signed Odoo event ingress |

## Investigation idempotency

```json
{
  "message": "Investigate the order and propose the safest next action.",
  "client_request_id": "client-generated UUID"
}
```

The unique key combines organization, case, and client request ID. A retry returns the existing job
rather than starting a second run.

## Approval decision

```json
{
  "decision": "approve",
  "reason": "Vendor and quantity were reviewed.",
  "expected_payload_hash": "64-character digest shown to the approver"
}
```

A stale or changed hash returns `409 Conflict`. The approval decision and execution job are written in
the same database transaction.

## Signed Odoo webhook

Required headers:

```http
X-FlowPilot-Tenant: tenant-demo
X-FlowPilot-Timestamp: 1785312000
X-FlowPilot-Signature: sha256=<hex HMAC>
```

The HMAC covers `timestamp + "." + raw_body`. `event_id` is unique per tenant/provider. Duplicate
delivery returns `duplicate: true` without creating a second case or job.

## SSE replay

Clients can send `Last-Event-ID`. The server resumes after the corresponding durable case event and
emits keepalive comments. SSE is a projection; the database remains the source of truth.
