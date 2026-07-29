# Production deployment and scaling

## Deployment model

The repository provides Docker Compose for local integration, Kubernetes manifests for workload
shape, and an AWS Terraform foundation for stateful infrastructure. Kubernetes is optional; a small
pilot can run the same API/worker/web containers on Cloud Run, ECS, Azure Container Apps, or another
managed platform.

## Workload separation

- API replicas serve HTTP and SSE.
- Worker replicas consume PostgreSQL jobs.
- Odoo MCP replicas receive read-only Odoo credentials.
- Web replicas serve the standalone Next.js app.
- Alembic migrations run once before rollout.

Do not run the supplier simulator in a real customer environment; replace it with the customer's
integration.

## Database connection budget

A horizontally scaled application can exhaust PostgreSQL before CPU is saturated:

\[
C_{total}=R_{api}P_{api}+R_{worker}P_{worker}+C_{ops}
\]

Keep the total below the safe database limit with migration and incident headroom. Use small pools,
replica caps, and a provider pooler when deployment dynamics demand it.

## Autoscaling

The included API HPA uses CPU as a portable baseline. Worker CPU is often a poor signal because model
and network waits dominate; production worker scaling should use pending-job age/depth plus per-tenant
fairness. Add KEDA or a cloud queue scaler only after exporting that metric.

## Initial SLO hypotheses

| SLI | Pilot objective |
|---|---|
| API availability | 99.5% monthly |
| webhook acceptance p95 | < 500 ms |
| dashboard read p95 | < 750 ms |
| queued investigation start p95 | < 60 s |
| duplicate side effects | 0 |
| cross-tenant access | 0 tolerated |
| approval/hash bypass | 0 tolerated |

These are targets to validate, not claims about the repository.

## Rollout sequence

1. Run migrations and tenant-isolation tests.
2. Deploy API and read-only MCP services.
3. Verify Odoo/RAG evidence without write permissions.
4. Enable proposals while execution remains globally disabled.
5. Enable one low-risk action for one design partner.
6. Review every proposal, rejection, retry, and receipt.
7. Expand by action and tenant, never by a global autonomy switch.

## Backup and recovery

Use automated PostgreSQL backups and point-in-time recovery. Exercise restoration before a paid
pilot. Replaying inbox, jobs, outbox, or Odoo operations must preserve idempotency. Odoo backup remains
the customer's system-of-record responsibility.

## Observability

The current code exposes Prometheus HTTP metrics and structured application logs; the Agents SDK can
emit OpenAI traces. Add an OTLP SDK/exporter in the deployment environment when the customer's
observability platform is known. Correlate request, case, run, action, job, and Odoo receipt IDs.
Treat model inputs and tool outputs as potentially sensitive data with explicit retention controls.
