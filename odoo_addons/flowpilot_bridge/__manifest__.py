{
    "name": "FlowPilot Bridge",
    "summary": "Atomic approved-action execution and durable operational webhooks",
    "version": "19.0.1.0.0",
    "category": "Operations",
    "license": "LGPL-3",
    "author": "ehza",
    "depends": ["base", "mail", "sale_management", "purchase", "crm"],
    "data": [
        "security/ir.model.access.csv",
        "data/cron.xml",
    ],
    "installable": True,
    "application": False,
}
