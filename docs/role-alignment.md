# Applied AI / FDE role alignment

The motivating job description asks for Python, AI applications, automation, intelligent business systems, Odoo/enterprise integration, LLMs, agents, RAG, workflow automation, and practical business outcomes. FlowPilot maps those requirements to inspectable evidence rather than keyword claims.

| Role signal | Repository evidence |
|---|---|
| Strong Python | typed service/domain code, Pydantic contracts, tests, async agent boundary |
| Enterprise system integration | Odoo 19 JSON-2 client and Odoo bridge addon |
| LLM/agent engineering | OpenAI Agents SDK, structured output, function tools, MCP, compaction |
| RAG | document ingestion, tenant-scoped chunks, pgvector/hybrid retrieval, provenance |
| Workflow automation | inbox → jobs → investigation → approval → execution → outbox |
| Backend engineering | HTTP, SSE, webhooks, transactions, RLS, queues, retries, idempotency |
| Customer-facing product | Next.js operations and approval console |
| Production delivery | Docker, Kubernetes, Terraform, CI, health/readiness, observability |
| FDE judgment | product wedge, design-partner workflow, configurable integrations, safety boundary |
| Quality and MLOps | deterministic/live evals, model routing, usage/cost ledger, regression workflow |

## What not to claim

Do not say the project has customer scale, uptime, revenue, or live Odoo correctness until those are measured. Say what has been verified locally and show the commands. Then use a paid design partner to turn engineering evidence into operational evidence.
