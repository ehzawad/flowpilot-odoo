from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from flowpilot.config import Settings
from flowpilot.db.base import create_schema
from flowpilot.scripts.seed_demo import seed_demo


@pytest.fixture
def settings(tmp_path: Path) -> Iterator[Settings]:
    database_url = f"sqlite:///{tmp_path / 'flowpilot.db'}"
    value = Settings(
        environment="test",
        database_url=database_url,
        worker_database_url=database_url,
        auto_create_schema=True,
        seed_demo_data=False,
        agent_runtime="fake",
        odoo_mode="fake",
        odoo_write_mode="fake",
        auth_mode="demo",
    )
    create_schema(database_url)
    seed_demo(value)
    yield value
