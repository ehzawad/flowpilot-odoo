from __future__ import annotations

import hashlib
import json

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


ALLOWED_ACTIONS = {
    "odoo.create_followup_activity",
    "odoo.create_draft_rfq",
    "odoo.update_crm_opportunity",
}
CRM_ALLOWED_FIELDS = {"stage_id", "user_id", "date_deadline", "priority", "probability"}


class FlowPilotExecutionReceipt(models.Model):
    _name = "flowpilot.execution.receipt"
    _description = "FlowPilot Approved Action Receipt"
    _order = "create_date desc"

    idempotency_key = fields.Char(required=True, index=True, readonly=True)
    tool_name = fields.Char(required=True, index=True, readonly=True)
    payload_digest = fields.Char(required=True, index=True, readonly=True)
    payload_json = fields.Json(required=True, readonly=True)
    result_json = fields.Json(required=True, readonly=True)

    _idempotency_unique = models.Constraint(
        "UNIQUE(idempotency_key)",
        "A FlowPilot action may execute only once.",
    )


class FlowPilotBridge(models.AbstractModel):
    _name = "flowpilot.bridge"
    _description = "FlowPilot Atomic Business Action Bridge"

    @api.model
    def execute_approved_action(self, tool_name, payload, idempotency_key):
        """Execute one allowlisted action inside one Odoo transaction.

        FlowPilot binds human approval to the exact payload before calling this method. Odoo still
        validates the bot user's ACLs and record rules; this bridge deliberately does not use sudo.
        PostgreSQL advisory locking serializes concurrent retries for the same idempotency key.
        """
        if tool_name not in ALLOWED_ACTIONS:
            raise AccessError(_("The requested FlowPilot action is not allowlisted."))
        if not isinstance(payload, dict):
            raise ValidationError(_("Action payload must be an object."))
        if not isinstance(idempotency_key, str) or not 8 <= len(idempotency_key) <= 255:
            raise ValidationError(_("A valid idempotency key is required."))

        self.env.cr.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            [idempotency_key],
        )
        receipt_model = self.env["flowpilot.execution.receipt"]
        existing = receipt_model.search([("idempotency_key", "=", idempotency_key)], limit=1)
        if existing:
            return {
                "ok": True,
                "idempotent_replay": True,
                "result": existing.result_json,
            }

        normalized = self._validate_action_payload(tool_name, payload)
        result = self._execute_action(tool_name, normalized)
        payload_digest = hashlib.sha256(
            json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        receipt_model.create(
            {
                "idempotency_key": idempotency_key,
                "tool_name": tool_name,
                "payload_digest": payload_digest,
                "payload_json": normalized,
                "result_json": result,
            }
        )
        return {"ok": True, "idempotent_replay": False, "result": result}

    @api.model
    def _validate_action_payload(self, tool_name, payload):
        if tool_name == "odoo.create_followup_activity":
            required = {"res_model_id", "res_id", "activity_type_id", "summary"}
            allowed = required | {"note", "user_id", "date_deadline"}
            self._check_keys(payload, required, allowed)
            return dict(payload)
        if tool_name == "odoo.create_draft_rfq":
            required = {"partner_id", "order_line"}
            allowed = required | {"origin", "notes"}
            self._check_keys(payload, required, allowed)
            if not isinstance(payload["order_line"], list) or not payload["order_line"]:
                raise ValidationError(_("Draft RFQ requires at least one order line."))
            return dict(payload)
        if tool_name == "odoo.update_crm_opportunity":
            self._check_keys(payload, {"ids", "values"}, {"ids", "values"})
            if not isinstance(payload["ids"], list) or not payload["ids"]:
                raise ValidationError(_("CRM update requires record IDs."))
            if not isinstance(payload["values"], dict):
                raise ValidationError(_("CRM update values must be an object."))
            forbidden = set(payload["values"]) - CRM_ALLOWED_FIELDS
            if forbidden:
                raise ValidationError(_("CRM fields are not allowlisted: %s") % ", ".join(sorted(forbidden)))
            return dict(payload)
        raise AccessError(_("Unsupported FlowPilot action."))

    @api.model
    def _check_keys(self, payload, required, allowed):
        missing = required - set(payload)
        extra = set(payload) - allowed
        if missing:
            raise ValidationError(_("Missing fields: %s") % ", ".join(sorted(missing)))
        if extra:
            raise ValidationError(_("Unexpected fields: %s") % ", ".join(sorted(extra)))

    @api.model
    def _execute_action(self, tool_name, payload):
        if tool_name == "odoo.create_followup_activity":
            record = self.env["mail.activity"].create(payload)
            return {"model": record._name, "record_id": record.id}
        if tool_name == "odoo.create_draft_rfq":
            values = dict(payload)
            if "notes" in values:
                values["notes"] = values.pop("notes")
            record = self.env["purchase.order"].create(values)
            return {"model": record._name, "record_id": record.id, "state": record.state}
        leads = self.env["crm.lead"].browse(payload["ids"]).exists()
        if len(leads) != len(set(payload["ids"])):
            raise ValidationError(_("One or more CRM opportunities do not exist."))
        leads.write(payload["values"])
        return {"model": "crm.lead", "record_ids": leads.ids}
