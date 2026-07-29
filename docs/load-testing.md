# Load and resilience testing

The goal is reproducible evidence, not a claim of internet scale.

## HTTP workload

Start the API and worker, then run:

```zsh
uv run locust -f loadtests/locustfile.py --host http://localhost:8000
```

Measure p50/p95/p99 latency, error rate, job creation rate, database connections, queue age, and worker
throughput. Use the deterministic runtime so load tests do not spend model tokens.

## Failure experiments

- deliver 5% of webhooks twice and verify one inbox/job;
- kill a worker after claim and verify lease recovery;
- force Odoo timeouts and observe bounded retries/dead jobs;
- mutate an action payload after approval and verify worker rejection;
- remove the current tenant setting and verify RLS returns no tenant rows;
- create a noisy tenant and verify quotas/fair scheduling before production;
- disconnect an SSE client and resume with `Last-Event-ID`.

## Capacity model

For each workload, record request rate, concurrent investigations, average model latency, worker
service time, database pool size, and maximum replicas. A useful report identifies the first saturated
resource and the mitigation rather than saying the system is “infinitely scalable.”
