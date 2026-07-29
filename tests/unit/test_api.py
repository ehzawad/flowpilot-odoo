from __future__ import annotations

from fastapi.testclient import TestClient

from flowpilot.api.main import app
from flowpilot.config import reset_settings_cache


def test_demo_api_lists_seeded_cases(monkeypatch, tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'api.db'}"
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("WORKER_DATABASE_URL", database_url)
    monkeypatch.setenv("AUTO_CREATE_SCHEMA", "true")
    monkeypatch.setenv("SEED_DEMO_DATA", "true")
    monkeypatch.setenv("AUTH_MODE", "demo")
    reset_settings_cache()
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        cases = client.get("/v1/cases")
        assert cases.status_code == 200
        assert len(cases.json()) == 3
        dashboard = client.get("/v1/dashboard").json()
        assert dashboard["open_cases"] == 3
        assert dashboard["at_risk_value"] == "145200.00"
    reset_settings_cache()
