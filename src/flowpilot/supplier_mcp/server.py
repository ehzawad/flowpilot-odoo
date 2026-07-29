from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from mcp.server.fastmcp import FastMCP

from flowpilot.config import get_settings

settings = get_settings()
mcp = FastMCP(
    "FlowPilot Supplier Portal Simulator",
    instructions=(
        "A local, read-only third-party MCP simulator. Replace this service with a real "
        "supplier or logistics MCP endpoint during a customer deployment."
    ),
    host=settings.supplier_mcp_host,
    port=settings.supplier_mcp_port,
    json_response=True,
    stateless_http=True,
)


@mcp.tool()
def get_supplier_order_status(purchase_order: str) -> dict[str, Any]:
    """Return a deterministic supplier status for a purchase order."""
    return {
        "purchase_order": purchase_order,
        "supplier": "Acme Components",
        "status": "delayed_at_origin",
        "committed_ship_date": (datetime.now(UTC) + timedelta(days=1)).date().isoformat(),
        "confidence": 0.82,
        "source": "supplier-portal-simulator",
    }


@mcp.tool()
def get_carrier_eta(tracking_number: str) -> dict[str, Any]:
    """Return a deterministic carrier ETA for a tracking number."""
    return {
        "tracking_number": tracking_number,
        "carrier": "Northline Freight",
        "status": "in_transit",
        "eta": (datetime.now(UTC) + timedelta(days=3)).isoformat(),
        "last_scan": "Regional hub",
        "source": "supplier-portal-simulator",
    }


def run() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    run()
