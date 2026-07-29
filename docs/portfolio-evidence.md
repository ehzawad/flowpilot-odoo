# Portfolio and interview evidence

## Five-minute demo narrative

1. Show an Odoo-originated fulfillment-risk case and commercial exposure.
2. Run the agent and expand the evidence packet.
3. Point out that Odoo and supplier data arrive through separate MCP servers.
4. Show the exact action proposal, payload hash, risk level, and expiry.
5. Approve it and show the durable job and case timeline.
6. Run the worker and show the idempotent Odoo receipt.
7. Open the trace/evaluation/cost views.
8. Explain one deliberate omission: no arbitrary model-driven writes.

## Artifacts to publish after a real pilot

- customer workflow map;
- architecture and ADRs;
- threat model;
- evaluation report;
- load/recovery report;
- monthly cost model;
- one incident postmortem about FlowPilot itself;
- before/after operational metric;
- sanitized customer testimonial or design-partner statement;
- revenue or paid-pilot evidence.

## Resume bullet template

> Built and operated a multi-tenant agentic operations copilot integrating Odoo, tenant SOP retrieval, and authenticated MCP tools. Designed durable human approval, immutable action binding, idempotent event/job processing, PostgreSQL RLS, model routing, evaluation, observability, and container/Kubernetes delivery. Investigated **[N]** monthly exceptions for **[M]** teams, reducing median triage time by **[X]%** at **[$Y]** per case.

Use only measured numbers.

## Interview deep dives

Be ready to defend:

- why the product is narrower than “agentic ERP”;
- why one agent is enough initially;
- why writes bypass the agent tool loop and go through durable approvals;
- why PostgreSQL is used for jobs before Kafka/Redis;
- how RLS and application filters complement each other;
- how duplicate webhooks and worker crashes are handled;
- how compaction differs from retrieval and durable case state;
- how MCP changes the integration contract but does not remove authorization concerns;
- how to determine the next service boundary from measured failure/scaling pressure.
