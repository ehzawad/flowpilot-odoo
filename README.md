# FlowPilot for Odoo

**A production-oriented agentic operations copilot for order-to-cash and inventory exceptions.**

FlowPilot connects Odoo 19, tenant operating procedures, and selected third-party systems to
investigate business exceptions, assemble evidence, propose a precise remediation, obtain durable
human approval, and execute only the approved payload.

This repository is source code, not a prompt demo. It is designed as an inspectable portfolio project
for Applied AI, Agentic AI, and Forward-Deployed Engineering work: product scoping, typed tool calls,
MCP, RAG, context compaction, durable workflows, multi-tenancy, idempotency, evaluation,
observability, containers, Kubernetes, Terraform, and a customer-facing interface.

## Current verification status

The deterministic no-key path is implemented and locally exercised through:

```zsh
PYTHONPATH=src pytest -q tests/unit
PYTHONPATH=src python -m flowpilot.scripts.smoke
PYTHONPATH=src python evals/run_local.py
python -m compileall -q src tests migrations evals odoo_addons
```

The live OpenAI, real Odoo, OIDC, Docker, Kubernetes, and AWS paths require operator-owned
credentials or infrastructure and must be verified in the target environment. The repository does
not claim customer traffic, revenue, uptime, or production scale.

## Product boundary

The model receives read-only case, RAG, Odoo MCP, and optional third-party MCP tools. It does **not**
receive an Odoo write tool. A proposed mutation becomes a database record containing the exact tool,
target, payload, expiration, and hash. A human approves that exact hash. A worker later recomputes the
binding, verifies an HMAC authorization, and executes an allowlisted operation.

```mermaid
flowchart LR
  C[Odoo event or operator] --> API[FastAPI]
  API --> DB[(PostgreSQL)]
  API --> J[Durable job]
  J --> W[Worker]
  W --> A[Agent runtime]
  A -->|read-only| M[Odoo MCP]
  A -->|tenant scoped| R[RAG]
  A -->|draft only| P[Action proposal]
  P --> H[Human approval]
  H --> W
  W -->|exact approved payload| O[Odoo bridge]
```

## What is in the repository

```text
apps/
  api/Dockerfile                 FastAPI image
  worker/Dockerfile              background-worker image
  web/                           Next.js customer console and BFF
src/flowpilot/
  agent/                         fake/live runtimes, policy, memory, compaction
  api/                           HTTP, SSE, auth, webhooks, metrics
  db/                            SQLAlchemy model and tenant session boundary
  odoo/                          Odoo 19 JSON-2 client and action allowlist
  odoo_mcp/                      read-only Odoo MCP server
  supplier_mcp/                  third-party MCP simulator
  services/                      cases, RAG, approvals, jobs, outbox, agent runs
  worker/                        leasing, retries, execution handlers
odoo_addons/flowpilot_bridge/    atomic approved writes and webhook outbox
migrations/                      Alembic schema and forced PostgreSQL RLS
apps/web/                        customer-facing operations and approval UI
evals/                           deterministic behavioral regression suite
loadtests/                       Locust workload
infra/k8s/                       deployments, HPA, PDB, NetworkPolicy
infra/terraform/aws/             RDS/ECR/S3/SQS/secrets/logging/budget foundation
docs/                            architecture, security, API, setup, production, ADRs
tests/                           unit tests and PostgreSQL RLS integration test
```

## Quickstart: no API keys

### Docker Compose

```zsh
cp .env.example .env
docker compose up --build
```

Then open:

- Web console: `http://localhost:3000`
- API documentation: `http://localhost:8000/docs`
- Prometheus metrics: `http://localhost:8000/metrics`
- Odoo MCP: `http://localhost:8010/mcp`
- Supplier MCP simulator: `http://localhost:8020/mcp`

### Native development

```zsh
cp .env.example .env
# Change DATABASE_URL and WORKER_DATABASE_URL to sqlite:///./.data/flowpilot.db
uv sync --all-groups
uv run alembic upgrade head
uv run flowpilot-seed
```

In separate terminals:

```zsh
uv run flowpilot-api
uv run flowpilot-worker
cd apps/web && npm install && npm run dev
```

See [docs/setup.md](docs/setup.md) for the complete setup and verification loop.

## End-to-end case flow

1. An Odoo event or operator creates a tenant-owned case.
2. The API acknowledges quickly and inserts an idempotent job.
3. A worker claims the job with a lease.
4. The runtime gathers current case facts, tenant SOPs, read-only Odoo evidence, and optional external
   MCP evidence.
5. A Pydantic `AgentAnswer` and zero or more validated `ActionDraft` objects are persisted.
6. The UI displays evidence, uncertainty, the complete payload, risk level, expiration, and hash.
7. An approver accepts or rejects the exact payload.
8. A separate execution job verifies state, expiry, recomputed hash, approver, and HMAC.
9. The worker calls the fake Odoo boundary, direct JSON-2 action, or custom bridge.
10. The result and an idempotent outbox event become part of the durable case timeline.

## Agent engineering surface

The OpenAI runtime uses:

- OpenAI Agents SDK;
- Pydantic structured output;
- local function tools;
- Streamable HTTP MCP clients with static tool filtering;
- application-owned tenant memory;
- OpenAI Responses compaction;
- tracing metadata;
- severity-based model routing;
- bounded turns, output tokens, wall-clock time, and soft cost budget.

The deterministic runtime follows the same proposal and approval boundary and is used for CI,
load-testing, local demos, and failure injection.

## Data and scaling semantics

- PostgreSQL is the source of truth for cases, agent runs, approvals, jobs, inbox/outbox, usage, and
  memory.
- Production migrations force RLS on tenant-owned tables.
- Job claiming uses `FOR UPDATE SKIP LOCKED` on PostgreSQL.
- Webhooks, investigations, execution jobs, Odoo receipts, and outbox events have idempotency keys.
- API and worker replicas scale independently.
- SSE is a reconnectable projection over durable case events.
- SQLite and deterministic embeddings keep the local path cheap; PostgreSQL/pgvector is the target
  production database.

## Tests and evaluations

```zsh
uv run pytest -m 'not integration'
uv run flowpilot-smoke
uv run python evals/run_local.py
uv run python scripts/validate_repo.py
```

For PostgreSQL RLS:

```zsh
export DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/flowpilot
export POSTGRES_TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/flowpilot
uv run alembic upgrade head
uv run pytest tests/integration/test_postgres_rls.py
```

## Production activation checklist

Before a real pilot:

1. Replace all development secrets and switch to OIDC.
2. Create a least-privilege Odoo bot user and short-lived/rotated key.
3. Put database and MCP endpoints on private networks.
4. Add server-side MCP OAuth, workload identity, or mTLS.
5. Run migrations with a separate owner role and prove RLS with the application role.
6. Start read-only, then enable one low-risk action for one tenant.
7. Build an evaluation set from sanitized historical cases.
8. Establish SLOs, budget alerts, backup restoration, retention, and a kill switch.

## Documentation

- [Product scope](docs/product.md)
- [System architecture](docs/architecture.md)
- [Local setup](docs/setup.md)
- [API contracts](docs/api.md)
- [Security model](docs/security.md)
- [Credentials](docs/credentials.md)
- [Evaluation strategy](docs/evaluations.md)
- [Load and resilience testing](docs/load-testing.md)
- [Production deployment](docs/production.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Role alignment](docs/role-alignment.md)
- [Portfolio evidence](docs/portfolio-evidence.md)
- [Architecture decisions](docs/adr/)

## Deliberate omissions

The first version does not use Kafka, Redis, a service mesh, arbitrary Odoo RPC, a multi-agent
hierarchy, or autonomous high-risk writes. Those additions are justified only by measured throughput,
fan-out, ownership, or reliability constraints.

## License

Apache-2.0 for the FlowPilot application. The optional Odoo addon declares LGPL-3 to match Odoo
module conventions.
