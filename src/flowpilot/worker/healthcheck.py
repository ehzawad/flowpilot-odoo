from __future__ import annotations

from sqlalchemy import text

from flowpilot.config import get_settings
from flowpilot.db.base import session_scope


def main() -> None:
    settings = get_settings()
    with session_scope(settings.effective_worker_database_url) as session:
        session.execute(text("SELECT 1"))


if __name__ == "__main__":
    main()
