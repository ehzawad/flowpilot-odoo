# Product scope

FlowPilot is an order-to-cash and inventory-exception copilot for Odoo operators. It is not a general
ERP chatbot and not an autonomous business manager.

## Customer job

An operations or support team receives an exception such as a stockout, delayed supplier receipt, or
high-value CRM risk. Evidence is distributed across Odoo, SOPs, and external portals. The team needs a
fast diagnosis, a traceable recommendation, and a safe way to execute a narrowly scoped remediation.

## Initial workflow

1. Receive or create an operational case.
2. Gather current Odoo facts and tenant procedures.
3. Explain the diagnosis and uncertainty.
4. Stage a complete, exact action payload when justified.
5. Obtain human approval bound to that payload.
6. Execute through a durable worker and idempotent Odoo bridge.
7. Persist the result as an audit event and future regression case.

## Included action types

- create a follow-up activity;
- create a draft RFQ;
- update a small allowlist of CRM fields.

Draft RFQs and follow-up activities are intentionally reversible. Automatic payment, invoice, order
confirmation, deletion, refund, or inventory adjustment is outside the initial boundary.

## Commercial pilot hypothesis

Sell the first deployment as a productized FDE engagement: workflow mapping, one Odoo connection, one
external evidence source, one or two approved actions, a historical evaluation set, and a measurable
triage-time objective. Productize only repeated customizations.
