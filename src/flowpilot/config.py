from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables or ``.env``."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    environment: Literal["development", "test", "production"] = "development"
    app_name: str = "FlowPilot"
    log_level: str = "INFO"
    public_app_url: str = "http://localhost:3000"
    api_base_url: str = "http://localhost:8000"
    database_url: str = "sqlite:///./.data/flowpilot.db"
    worker_database_url: str | None = None
    database_pool_size: int = 5
    database_max_overflow: int = 5
    database_pool_timeout_seconds: int = 15
    auto_create_schema: bool = True
    seed_demo_data: bool = True

    agent_runtime: Literal["fake", "openai"] = "fake"
    openai_api_key: str | None = None
    openai_model: str = "gpt-5.6-terra"
    openai_fast_model: str = "gpt-5.6-luna"
    openai_frontier_model: str = "gpt-5.6-sol"
    openai_compaction_model: str = "gpt-5.6-luna"
    openai_embedding_model: str = "text-embedding-3-large"
    use_frontier_for_critical: bool = False
    agent_max_turns: int = 8
    agent_timeout_seconds: int = 90
    agent_max_input_tokens: int = 90_000
    agent_max_output_tokens: int = 5_000
    agent_compaction_trigger_items: int = 24
    agent_soft_cost_limit_usd: float = 1.0
    openai_tracing_enabled: bool = False

    openai_luna_input_usd_per_million: float = 1.0
    openai_luna_output_usd_per_million: float = 6.0
    openai_terra_input_usd_per_million: float = 2.5
    openai_terra_output_usd_per_million: float = 15.0
    openai_sol_input_usd_per_million: float = 5.0
    openai_sol_output_usd_per_million: float = 30.0

    odoo_mode: Literal["fake", "json2"] = "fake"
    odoo_write_mode: Literal["fake", "direct", "bridge"] = "fake"
    odoo_base_url: str = "http://localhost:8069"
    odoo_database: str | None = None
    odoo_api_key: str | None = None
    odoo_timeout_seconds: float = 20
    odoo_retry_attempts: int = 3
    odoo_mcp_url: str = "http://localhost:8010/mcp"
    odoo_mcp_host: str = "0.0.0.0"
    odoo_mcp_port: int = 8010
    odoo_mcp_service_token: str = "development-only-token"
    odoo_bridge_webhook_secret: str = "development-webhook-secret"
    odoo_action_signing_secret: str = "development-action-secret"
    webhook_max_age_seconds: int = 300
    auto_investigate_odoo_events: bool = True

    supplier_mcp_enabled: bool = True
    supplier_mcp_host: str = "0.0.0.0"
    supplier_mcp_port: int = 8020
    supplier_mcp_service_token: str = "development-supplier-token"

    third_party_mcp_enabled: bool = False
    third_party_mcp_name: str = "supplier-portal"
    third_party_mcp_url: str = "http://localhost:8020/mcp"
    third_party_mcp_bearer_token: str | None = None
    third_party_mcp_allowed_tools: str = "get_supplier_order_status,get_carrier_eta"

    auth_mode: Literal["demo", "oidc"] = "demo"
    oidc_issuer: str | None = None
    oidc_audience: str | None = None
    oidc_jwks_url: str | None = None
    demo_tenant_id: str = "tenant-demo"
    demo_user_id: str = "user-demo"
    demo_user_email: str = "operator@northstar.example"

    event_sink_url: str | None = None
    event_sink_bearer_token: str | None = None
    otel_exporter_otlp_endpoint: str | None = None
    otel_service_name: str = "flowpilot-api"
    prometheus_enabled: bool = True

    worker_poll_seconds: float = 0.5
    worker_lease_seconds: int = 120
    worker_max_attempts: int = 6
    worker_concurrency: int = 1
    inline_worker: bool = False

    @field_validator("database_url", "worker_database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str | None) -> str | None:
        if not value:
            return value
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+psycopg://", 1)
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value

    @model_validator(mode="after")
    def validate_production_safety(self) -> Settings:
        if self.environment == "production":
            if self.auth_mode == "demo":
                raise ValueError("AUTH_MODE=demo is forbidden in production")
            if self.agent_runtime == "openai" and not self.openai_api_key:
                raise ValueError("OPENAI_API_KEY is required for the OpenAI runtime")
            if self.odoo_mode == "json2" and not self.odoo_api_key:
                raise ValueError("ODOO_API_KEY is required for Odoo JSON-2")
            weak = {
                "development-only-token",
                "development-webhook-secret",
                "development-action-secret",
            }
            values = {
                self.odoo_mcp_service_token,
                self.odoo_bridge_webhook_secret,
                self.odoo_action_signing_secret,
            }
            if weak & values:
                raise ValueError("Development secrets are forbidden in production")
        return self

    @property
    def effective_worker_database_url(self) -> str:
        return self.worker_database_url or self.database_url

    @property
    def allowed_third_party_tools(self) -> set[str]:
        return {item.strip() for item in self.third_party_mcp_allowed_tools.split(",") if item.strip()}

    def ensure_local_directories(self) -> None:
        if self.database_url.startswith("sqlite:///"):
            path = self.database_url.removeprefix("sqlite:///")
            Path(path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_local_directories()
    return settings


def reset_settings_cache() -> None:
    get_settings.cache_clear()
