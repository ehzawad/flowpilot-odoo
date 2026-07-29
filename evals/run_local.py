from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

from sqlalchemy import select

from flowpilot.agent.context import AgentContext
from flowpilot.agent.fake_runtime import FakeAgentRuntime
from flowpilot.config import Settings
from flowpilot.db.base import create_schema, session_scope
from flowpilot.db.models import Case
from flowpilot.scripts.seed_demo import seed_demo


async def main() -> None:
    cases_path = Path(__file__).with_name("cases.jsonl")
    cases = [json.loads(line) for line in cases_path.read_text().splitlines() if line.strip()]
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="flowpilot-eval-") as directory:
        database_url = f"sqlite:///{Path(directory) / 'eval.db'}"
        settings = Settings(
            environment="test",
            database_url=database_url,
            worker_database_url=database_url,
            auto_create_schema=True,
            seed_demo_data=False,
            agent_runtime="fake",
            odoo_mode="fake",
        )
        create_schema(database_url)
        seed_demo(settings)
        runtime = FakeAgentRuntime()
        with session_scope(database_url, organization_id=settings.demo_tenant_id) as session:
            available = {
                item.category: item
                for item in session.scalars(
                    select(Case).where(Case.organization_id == settings.demo_tenant_id)
                )
            }
        for item in cases:
            selected = available.get(item["category"])
            if selected is None:
                # Create a stable unknown-category probe by reusing a case and changing only
                # its category inside the isolated eval database.
                selected = next(iter(available.values()))
                with session_scope(database_url, organization_id=settings.demo_tenant_id) as session:
                    db_case = session.get(Case, selected.id)
                    assert db_case
                    db_case.category = item["category"]
            result = await runtime.run(
                AgentContext(
                    organization_id=settings.demo_tenant_id,
                    case_id=selected.id,
                    user_id=settings.demo_user_id,
                    database_url=database_url,
                    settings=settings,
                ),
                item["message"],
            )
            tools = {draft.tool_name for draft in result.actions}
            if item.get("forbid_actions") and tools:
                failures.append(f"{item['id']}: expected no actions, got {sorted(tools)}")
            if required := item.get("must_propose"):
                if required not in tools:
                    failures.append(f"{item['id']}: missing required action {required}")
            if forbidden := item.get("forbidden_tool"):
                if forbidden in tools:
                    failures.append(f"{item['id']}: emitted forbidden action {forbidden}")
            if len(result.answer.evidence) < item["min_evidence"]:
                failures.append(f"{item['id']}: insufficient evidence")
            with session_scope(database_url, organization_id=settings.demo_tenant_id) as session:
                db_case = session.get(Case, selected.id)
                assert db_case
                # Restore original demo category for subsequent cases.
                if selected.external_ref.startswith("sale.order"):
                    db_case.category = "inventory_shortage"
        report = {"cases": len(cases), "passed": len(cases) - len(failures), "failures": failures}
        results_dir = Path(__file__).with_name("results")
        results_dir.mkdir(exist_ok=True)
        (results_dir / "latest.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
        if failures:
            raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
