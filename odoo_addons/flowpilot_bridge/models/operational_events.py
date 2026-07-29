from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
import uuid
from datetime import timedelta

import requests

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class FlowPilotWebhookEvent(models.Model):
    _name = "flowpilot.webhook.event"
    _description = "FlowPilot Webhook Outbox Event"
    _order = "create_date asc"

    event_id = fields.Char(required=True, index=True, readonly=True, default=lambda self: str(uuid.uuid4()))
    tenant_id = fields.Char(required=True, index=True, readonly=True)
    event_type = fields.Char(required=True, index=True, readonly=True)
    model_name = fields.Char(required=True, index=True, readonly=True)
    record_id = fields.Integer(required=True, index=True, readonly=True)
    company_id = fields.Many2one("res.company", readonly=True)
    payload_json = fields.Json(required=True, readonly=True)
    state = fields.Selection(
        [("pending", "Pending"), ("retry", "Retry"), ("sent", "Sent"), ("dead", "Dead")],
        default="pending",
        required=True,
        index=True,
        readonly=True,
    )
    attempts = fields.Integer(default=0, readonly=True)
    next_attempt_at = fields.Datetime(default=fields.Datetime.now, index=True, readonly=True)
    sent_at = fields.Datetime(readonly=True)
    last_error = fields.Text(readonly=True)

    _event_id_unique = models.Constraint("UNIQUE(event_id)", "Webhook event ID must be unique.")

    @api.model
    def enqueue(self, event_type, record, payload):
        params = self.env["ir.config_parameter"].sudo()
        tenant_id = params.get_param("flowpilot.tenant_id")
        if not tenant_id:
            _logger.info("FlowPilot tenant is not configured; event %s was not queued", event_type)
            return self.browse()
        return self.create(
            {
                "tenant_id": tenant_id,
                "event_type": event_type,
                "model_name": record._name,
                "record_id": record.id,
                "company_id": record.company_id.id if "company_id" in record._fields else False,
                "payload_json": payload,
            }
        )

    @api.model
    def _cron_dispatch(self, batch_size=100):
        now = fields.Datetime.now()
        events = self.search(
            [("state", "in", ["pending", "retry"]), ("next_attempt_at", "<=", now)],
            order="create_date asc",
            limit=batch_size,
        )
        for event in events:
            event._deliver()

    def _deliver(self):
        self.ensure_one()
        params = self.env["ir.config_parameter"].sudo()
        url = params.get_param("flowpilot.webhook_url")
        secret = params.get_param("flowpilot.webhook_secret")
        if not url or not secret:
            self.write({"state": "dead", "last_error": "Webhook URL or secret is not configured"})
            return

        envelope = {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "database": self.env.cr.dbname,
            "model": self.model_name,
            "record_id": self.record_id,
            "company_id": self.company_id.id or None,
            "occurred_at": fields.Datetime.to_datetime(self.create_date).isoformat() + "Z",
            "payload": self.payload_json,
        }
        raw = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode()
        timestamp = str(int(time.time()))
        digest = hmac.new(secret.encode(), timestamp.encode() + b"." + raw, hashlib.sha256).hexdigest()
        try:
            response = requests.post(
                url,
                data=raw,
                headers={
                    "Content-Type": "application/json",
                    "X-FlowPilot-Tenant": self.tenant_id,
                    "X-FlowPilot-Timestamp": timestamp,
                    "X-FlowPilot-Signature": f"sha256={digest}",
                    "Idempotency-Key": self.event_id,
                },
                timeout=10,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            attempts = self.attempts + 1
            terminal = attempts >= 8
            delay = min(900, 2 ** min(attempts, 9))
            self.write(
                {
                    "state": "dead" if terminal else "retry",
                    "attempts": attempts,
                    "next_attempt_at": fields.Datetime.now() + timedelta(seconds=delay),
                    "last_error": str(exc)[:4000],
                }
            )
            return
        self.write(
            {
                "state": "sent",
                "attempts": self.attempts + 1,
                "sent_at": fields.Datetime.now(),
                "last_error": False,
            }
        )


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def write(self, values):
        result = super().write(values)
        watched = {"state", "commitment_date", "warehouse_id"}
        if watched.intersection(values):
            for order in self:
                self.env["flowpilot.webhook.event"].enqueue(
                    "sale_order.changed",
                    order,
                    {
                        "name": order.name,
                        "state": order.state,
                        "amount_total": order.amount_total,
                        "currency": order.currency_id.name,
                        "commitment_date": order.commitment_date.isoformat() if order.commitment_date else None,
                        "summary": "A sales-order field relevant to fulfillment changed.",
                    },
                )
        return result


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    def write(self, values):
        result = super().write(values)
        watched = {"state", "date_planned", "partner_id"}
        if watched.intersection(values):
            for order in self:
                self.env["flowpilot.webhook.event"].enqueue(
                    "purchase_order.changed",
                    order,
                    {
                        "name": order.name,
                        "state": order.state,
                        "amount_total": order.amount_total,
                        "currency": order.currency_id.name,
                        "date_planned": order.date_planned.isoformat() if order.date_planned else None,
                        "summary": "A purchase-order field relevant to inbound supply changed.",
                    },
                )
        return result


class CrmLead(models.Model):
    _inherit = "crm.lead"

    def write(self, values):
        result = super().write(values)
        watched = {"stage_id", "user_id", "date_deadline", "priority", "probability"}
        if watched.intersection(values):
            for lead in self.filtered(lambda item: item.type == "opportunity"):
                self.env["flowpilot.webhook.event"].enqueue(
                    "crm_opportunity.changed",
                    lead,
                    {
                        "name": lead.name,
                        "expected_revenue": lead.expected_revenue,
                        "probability": lead.probability,
                        "stage": lead.stage_id.name,
                        "date_deadline": lead.date_deadline.isoformat() if lead.date_deadline else None,
                        "summary": "A CRM field relevant to opportunity progression changed.",
                    },
                )
        return result
