from __future__ import annotations

from prometheus_client import Counter, Histogram

HTTP_REQUESTS = Counter(
    "flowpilot_http_requests_total",
    "HTTP requests handled by FlowPilot",
    ["method", "route", "status"],
)
HTTP_LATENCY = Histogram(
    "flowpilot_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "route"],
)
JOBS = Counter(
    "flowpilot_jobs_total",
    "Durable jobs by type and terminal state",
    ["job_type", "state"],
)
AGENT_RUNS = Counter(
    "flowpilot_agent_runs_total",
    "Agent runs by runtime and result",
    ["runtime", "status"],
)
