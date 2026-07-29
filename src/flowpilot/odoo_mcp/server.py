from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from flowpilot.config import get_settings
from flowpilot.odoo.client import build_odoo_client
from flowpilot.odoo.operations import (
    get_inventory_position as read_inventory_position,
    list_at_risk_sales_orders as read_at_risk_sales_orders,
    list_late_purchase_orders as read_late_purchase_orders,
    search_crm_opportunities as read_crm_opportunities,
)

settings = get_settings()
mcp = FastMCP(
    "FlowPilot Odoo Read-Only Gateway",
    instructions=(
        "Expose read-only Odoo evidence. This server never publishes write tools; "
        "mutations must pass through FlowPilot's durable approval worker."
    ),
    host=settings.odoo_mcp_host,
    port=settings.odoo_mcp_port,
    json_response=True,
    stateless_http=True,
)


@mcp.tool()
def list_at_risk_sales_orders(limit: int = 20) -> list[dict[str, Any]]:
    """List committed sales orders whose delivery state requires investigation."""
    return read_at_risk_sales_orders(build_odoo_client(settings), limit=max(1, min(limit, 100)))


@mcp.tool()
def get_inventory_position(sku: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    """Read available, free, and forecast inventory for an optional SKU."""
    return read_inventory_position(
        build_odoo_client(settings), sku=sku, limit=max(1, min(limit, 100))
    )


@mcp.tool()
def list_late_purchase_orders(limit: int = 20) -> list[dict[str, Any]]:
    """List purchase orders whose planned receipt date is already in the past."""
    return read_late_purchase_orders(build_odoo_client(settings), limit=max(1, min(limit, 100)))


@mcp.tool()
def search_crm_opportunities(query: str, limit: int = 20) -> list[dict[str, Any]]:
    """Search current CRM opportunities by name."""
    return read_crm_opportunities(
        build_odoo_client(settings), query=query, limit=max(1, min(limit, 100))
    )


def run() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    run()
