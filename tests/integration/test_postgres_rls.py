from __future__ import annotations

import os
import secrets
import uuid

import pytest

try:
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import conninfo_to_dict, make_conninfo
    from psycopg.types.json import Json
except ModuleNotFoundError:
    pytest.skip("psycopg is not installed", allow_module_level=True)

pytestmark = pytest.mark.integration


def _role_dsn(admin_dsn: str, *, user: str, password: str) -> str:
    values = conninfo_to_dict(admin_dsn)
    values.update(user=user, password=password)
    return make_conninfo(**values)


def test_forced_rls_isolates_case_and_agent_memory_rows() -> None:
    admin_dsn = os.getenv("POSTGRES_TEST_DATABASE_URL")
    if not admin_dsn:
        pytest.skip("POSTGRES_TEST_DATABASE_URL is not configured")

    suffix = uuid.uuid4().hex[:10]
    role = f"flowpilot_api_{suffix}"
    password = secrets.token_urlsafe(32)
    org_a = f"org-a-{suffix}"
    org_b = f"org-b-{suffix}"
    case_a = f"case-a-{suffix}"
    case_b = f"case-b-{suffix}"
    session_a = f"{org_a}:{case_a}:user-a"
    session_b = f"{org_b}:{case_b}:user-b"

    with psycopg.connect(admin_dsn, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD %s").format(sql.Identifier(role)), (password,))
        admin.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
            sql.Identifier(conninfo_to_dict(admin_dsn).get("dbname", "flowpilot")),
            sql.Identifier(role),
        ))
        admin.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role)))
        admin.execute(
            sql.SQL(
                "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {}"
            ).format(sql.Identifier(role))
        )
        admin.execute(
            sql.SQL("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {}").format(
                sql.Identifier(role)
            )
        )

        for organization_id, slug in ((org_a, f"a-{suffix}"), (org_b, f"b-{suffix}")):
            admin.execute(
                """
                INSERT INTO organizations
                    (id, slug, name, status, plan, settings_json, created_at, updated_at)
                VALUES (%s, %s, %s, 'active', 'pilot', %s, now(), now())
                """,
                (organization_id, slug, organization_id, Json({})),
            )
        for case_id, organization_id in ((case_a, org_a), (case_b, org_b)):
            admin.execute(
                """
                INSERT INTO cases
                    (id, organization_id, title, summary, category, severity, status,
                     source, external_ref, at_risk_value, currency, context_json,
                     created_at, updated_at)
                VALUES
                    (%s, %s, %s, '', 'operations_exception', 'medium', 'open',
                     'test', %s, 0, 'USD', %s, now(), now())
                """,
                (case_id, organization_id, case_id, case_id, Json({})),
            )
        for session_id, organization_id, case_id in (
            (session_a, org_a, case_a),
            (session_b, org_b, case_b),
        ):
            admin.execute(
                """
                INSERT INTO agent_memory_sessions
                    (session_id, organization_id, case_id, user_id, created_at, updated_at)
                VALUES (%s, %s, %s, 'test-user', now(), now())
                """,
                (session_id, organization_id, case_id),
            )

    api_dsn = _role_dsn(admin_dsn, user=role, password=password)
    with psycopg.connect(api_dsn) as connection:
        assert connection.execute("SELECT count(*) FROM cases").fetchone() == (0,)
        assert connection.execute("SELECT count(*) FROM agent_memory_sessions").fetchone() == (0,)

        connection.execute(
            "SELECT set_config('app.current_organization_id', %s, true)", (org_a,)
        )
        assert connection.execute("SELECT id FROM cases ORDER BY id").fetchall() == [(case_a,)]
        assert connection.execute(
            "SELECT session_id FROM agent_memory_sessions ORDER BY session_id"
        ).fetchall() == [(session_a,)]

        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            connection.execute(
                """
                INSERT INTO agent_memory_sessions
                    (session_id, organization_id, case_id, user_id, created_at, updated_at)
                VALUES (%s, %s, %s, 'attacker', now(), now())
                """,
                (f"forged-{suffix}", org_b, case_b),
            )
        connection.rollback()

        connection.execute(
            "SELECT set_config('app.current_organization_id', %s, true)", (org_b,)
        )
        assert connection.execute("SELECT id FROM cases ORDER BY id").fetchall() == [(case_b,)]
        assert connection.execute(
            "SELECT session_id FROM agent_memory_sessions ORDER BY session_id"
        ).fetchall() == [(session_b,)]

    with psycopg.connect(admin_dsn, autocommit=True) as admin:
        admin.execute(sql.SQL("DROP OWNED BY {} CASCADE").format(sql.Identifier(role)))
        admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))
