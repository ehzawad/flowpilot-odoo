from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from flowpilot.odoo.client import OdooClient

READ_TOOL_NAMES = {
    "odoo.list_at_risk_sales_orders",
    "odoo.get_inventory_position",
    "odoo.list_late_purchase_orders",
    "odoo.search_crm_opportunities",
}

WRITE_TOOL_NAMES = {
    "odoo.create_followup_activity",
    "odoo.create_draft_rfq",
    "odoo.update_crm_opportunity",
}


def list_at_risk_sales_orders(client: OdooClient, limit: int = 20) -> list[dict[str, Any]]:
    return client.search_read(
        "sale.order",
        domain=[["state", "in", ["sale", "done"]]],
        fields=[
            "name",
            "partner_id",
            "amount_total",
            "currency_id",
            "commitment_date",
            "state",
            "warehouse_id",
            "invoice_status",
            "delivery_status",
        ],
        limit=limit,
        order="commitment_date asc",
    )


def get_inventory_position(
    client: OdooClient, *, sku: str | None = None, limit: int = 20
) -> list[dict[str, Any]]:
    domain: list[list[Any]] = []
    if sku:
        domain = [["default_code", "ilike", sku]]
    return client.search_read(
        "product.product",
        domain=domain,
        fields=[
            "display_name",
            "default_code",
            "qty_available",
            "free_qty",
            "virtual_available",
            "uom_id",
        ],
        limit=limit,
        order="virtual_available asc",
    )


def list_late_purchase_orders(client: OdooClient, limit: int = 20) -> list[dict[str, Any]]:
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    return client.search_read(
        "purchase.order",
        domain=[["state", "in", ["purchase", "done"]], ["date_planned", "<", now]],
        fields=["name", "partner_id", "date_planned", "amount_total", "state", "receipt_status"],
        limit=limit,
        order="date_planned asc",
    )


def search_crm_opportunities(client: OdooClient, query: str, limit: int = 20) -> list[dict[str, Any]]:
    return client.search_read(
        "crm.lead",
        domain=[["type", "=", "opportunity"], ["name", "ilike", query]],
        fields=["name", "partner_id", "expected_revenue", "probability", "stage_id", "date_deadline"],
        limit=limit,
        order="expected_revenue desc",
    )


def execute_write_action(
    client: OdooClient,
    *,
    tool_name: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    if tool_name not in WRITE_TOOL_NAMES:
        raise ValueError(f"Write tool is not allowlisted: {tool_name}")

    if tool_name == "odoo.create_followup_activity":
        required = {"res_model_id", "res_id", "activity_type_id", "summary"}
        _require_keys(payload, required)
        record_id = client.call("mail.activity", "create", {"vals_list": payload})
        return {"ok": True, "model": "mail.activity", "record_id": record_id}

    if tool_name == "odoo.create_draft_rfq":
        required = {"partner_id", "order_line"}
        _require_keys(payload, required)
        values = {**payload, "state": "draft"}
        record_id = client.call("purchase.order", "create", {"vals_list": values})
        return {"ok": True, "model": "purchase.order", "record_id": record_id, "state": "draft"}

    if tool_name == "odoo.update_crm_opportunity":
        required = {"ids", "values"}
        _require_keys(payload, required)
        result = client.call(
            "crm.lead", "write", {"ids": payload["ids"], "vals": payload["values"]}
        )
        return {"ok": bool(result), "model": "crm.lead", "ids": payload["ids"]}

    raise AssertionError("Unreachable write-tool branch")


def _require_keys(payload: dict[str, Any], required: set[str]) -> None:
    missing = sorted(required - payload.keys())
    if missing:
        raise ValueError(f"Action payload is missing required keys: {', '.join(missing)}")
