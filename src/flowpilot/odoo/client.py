from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import httpx
import time

from flowpilot.config import Settings, get_settings

Domain = list[list[Any]]


class OdooError(RuntimeError):
    pass


class OdooClient(Protocol):
    def search_read(
        self,
        model: str,
        *,
        domain: Domain,
        fields: list[str],
        limit: int = 50,
        order: str | None = None,
    ) -> list[dict[str, Any]]: ...

    def call(self, model: str, method: str, payload: dict[str, Any]) -> Any: ...


@dataclass(slots=True)
class JSON2OdooClient:
    base_url: str
    database: str
    api_key: str
    timeout_seconds: float = 20.0
    retry_attempts: int = 3

    def call(self, model: str, method: str, payload: dict[str, Any]) -> Any:
        url = f"{self.base_url.rstrip('/')}/json/2/{model}/{method}"
        headers = {
            "Authorization": f"bearer {self.api_key}",
            "X-Odoo-Database": self.database,
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "FlowPilot/0.1.0",
        }
        last_error: Exception | None = None
        for attempt in range(1, self.retry_attempts + 1):
            try:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    response = client.post(url, headers=headers, json=payload)
                if response.is_error:
                    try:
                        detail = response.json()
                    except ValueError:
                        detail = {"message": response.text[:2_000]}
                    raise OdooError(
                        f"Odoo JSON-2 call failed ({response.status_code}) "
                        f"{model}.{method}: {detail}"
                    )
                return response.json()
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                last_error = exc
                if attempt < self.retry_attempts:
                    time.sleep(min(5.0, 0.5 * (2 ** (attempt - 1))))
        assert last_error is not None
        raise last_error

    def search_read(
        self,
        model: str,
        *,
        domain: Domain,
        fields: list[str],
        limit: int = 50,
        order: str | None = None,
    ) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {"domain": domain, "fields": fields, "limit": limit}
        if order:
            payload["order"] = order
        result = self.call(model, "search_read", payload)
        if not isinstance(result, list):
            raise OdooError(f"Expected list from {model}.search_read")
        return [dict(item) for item in result]


class FakeOdooClient:
    """In-memory Odoo boundary that records side effects for local verification."""

    def __init__(self) -> None:
        self.sales_orders = [
            {
                "id": 1042,
                "name": "S042",
                "partner_id": [31, "Northstar Retail"],
                "amount_total": 48_500.0,
                "currency_id": [1, "USD"],
                "commitment_date": "2026-08-03 00:00:00",
                "state": "sale",
                "warehouse_id": [1, "Main Warehouse"],
                "invoice_status": "to invoice",
                "delivery_status": "partial",
            },
            {
                "id": 1043,
                "name": "S043",
                "partner_id": [44, "Beacon Medical"],
                "amount_total": 12_900.0,
                "currency_id": [1, "USD"],
                "commitment_date": "2026-08-08 00:00:00",
                "state": "sale",
                "warehouse_id": [1, "Main Warehouse"],
                "invoice_status": "no",
                "delivery_status": "pending",
            },
        ]
        self.products = [
            {
                "id": 501,
                "display_name": "Industrial Sensor X9",
                "default_code": "SENSOR-X9",
                "qty_available": 12.0,
                "free_qty": 4.0,
                "virtual_available": -18.0,
                "uom_id": [1, "Units"],
            },
            {
                "id": 502,
                "display_name": "Control Relay R4",
                "default_code": "RELAY-R4",
                "qty_available": 120.0,
                "free_qty": 86.0,
                "virtual_available": 52.0,
                "uom_id": [1, "Units"],
            },
        ]
        self.purchase_orders = [
            {
                "id": 801,
                "name": "P00801",
                "partner_id": [77, "Acme Components"],
                "date_planned": "2026-07-27 00:00:00",
                "amount_total": 21_700.0,
                "state": "purchase",
                "receipt_status": "late",
            }
        ]
        self.created_actions: list[dict[str, Any]] = []

    def search_read(
        self,
        model: str,
        *,
        domain: Domain,
        fields: list[str],
        limit: int = 50,
        order: str | None = None,
    ) -> list[dict[str, Any]]:
        del order
        source = {
            "sale.order": self.sales_orders,
            "product.product": self.products,
            "purchase.order": self.purchase_orders,
            "crm.lead": [
                {
                    "id": 42,
                    "name": "Northstar renewal",
                    "partner_id": [31, "Northstar Retail"],
                    "expected_revenue": 75_000.0,
                    "probability": 60.0,
                    "stage_id": [3, "Proposal"],
                    "date_deadline": "2026-08-15",
                }
            ],
        }.get(model, [])
        if model == "product.product" and domain:
            needle = str(domain[0][-1]).lower()
            source = [item for item in source if needle in str(item.get("default_code", "")).lower()]
        result = []
        for item in source[:limit]:
            selected = {field: item.get(field) for field in fields}
            selected["id"] = item["id"]
            result.append(selected)
        return result

    def call(self, model: str, method: str, payload: dict[str, Any]) -> Any:
        if method in {"create", "write", "action_confirm", "action_schedule", "execute_approved_action"}:
            record = {
                "id": 90_000 + len(self.created_actions),
                "model": model,
                "method": method,
                **payload,
            }
            self.created_actions.append(record)
            return record["id"] if method == "create" else {"ok": True, "receipt": record["id"]}
        if method == "search_read":
            return self.search_read(
                model,
                domain=payload.get("domain", []),
                fields=payload.get("fields", []),
                limit=payload.get("limit", 50),
                order=payload.get("order"),
            )
        raise OdooError(f"Fake Odoo method is not implemented: {model}.{method}")


def build_odoo_client(settings: Settings | None = None) -> OdooClient:
    active = settings or get_settings()
    if active.odoo_mode == "fake":
        return FakeOdooClient()
    if not active.odoo_api_key or not active.odoo_database:
        raise OdooError("ODOO_API_KEY and ODOO_DATABASE are required for JSON-2 mode")
    return JSON2OdooClient(
        base_url=active.odoo_base_url,
        database=active.odoo_database,
        api_key=active.odoo_api_key,
        timeout_seconds=active.odoo_timeout_seconds,
        retry_attempts=active.odoo_retry_attempts,
    )
