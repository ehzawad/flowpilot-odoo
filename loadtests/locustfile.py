from __future__ import annotations

import uuid

from locust import HttpUser, between, task


class FlowPilotUser(HttpUser):
    wait_time = between(0.2, 1.2)

    def on_start(self) -> None:
        self.headers = {
            "X-Tenant-ID": "tenant-demo",
            "X-User-ID": f"load-user-{uuid.uuid4().hex[:8]}",
            "X-User-Role": "operator",
        }
        response = self.client.get("/v1/cases", headers=self.headers)
        response.raise_for_status()
        self.case_id = response.json()[0]["id"]

    @task(5)
    def read_dashboard(self) -> None:
        self.client.get("/v1/dashboard", headers=self.headers, name="GET /v1/dashboard")

    @task(4)
    def read_cases(self) -> None:
        self.client.get("/v1/cases", headers=self.headers, name="GET /v1/cases")

    @task(2)
    def read_timeline(self) -> None:
        self.client.get(
            f"/v1/cases/{self.case_id}/events",
            headers=self.headers,
            name="GET /v1/cases/:id/events",
        )

    @task(1)
    def enqueue_idempotent_investigation(self) -> None:
        request_id = uuid.uuid4().hex
        self.client.post(
            f"/v1/cases/{self.case_id}/investigations",
            headers=self.headers,
            json={
                "message": "Investigate this exception and identify the safest next step.",
                "client_request_id": request_id,
            },
            name="POST /v1/cases/:id/investigations",
        )
