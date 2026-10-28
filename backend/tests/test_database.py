"""Tests de base de données (MODELE_PHYSIQUE_LOT1 §12) exécutés sous le rôle applicatif mf_app."""

import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError

from app.core.config import get_settings
from tests.conftest import Api

TENANT_TABLES = (
    "site",
    "user_account",
    "user_role_assignment",
    "account_token",
    "auth_session",
    "audit_event",
    "vehicle",
    "driver",
    "vehicle_assignment",
    "mission",
    "mission_event",
    "rotation",
    "weighing_ticket",
    "weighing_ticket_decision",
    "vehicle_meter_reading",
    "vehicle_document",
)
GLOBAL_TABLES = {
    "role",
    "role_allowed_scope",
    "license_category_ref",
    "vehicle_category_template",
    "vehicle_category_template_license",
    "alembic_version",
    "spatial_ref_sys",
}


@pytest.fixture(scope="module")
def app_engine() -> Engine:
    return create_engine(get_settings().database_url(), pool_size=1, max_overflow=0)


@pytest.fixture(scope="module")
def owner_engine() -> Engine:
    return create_engine(get_settings().database_url(owner=True))


def _ctx(conn: Connection, tenant_id: uuid.UUID) -> None:
    conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)})


def test_dbt08_app_role_cannot_bypass_rls(app_engine: Engine) -> None:
    with app_engine.connect() as conn:
        row = conn.execute(
            text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
        ).one()
        owned = conn.execute(
            text("SELECT count(*) FROM pg_tables WHERE tableowner = current_user")
        ).scalar_one()
    assert (row.rolsuper, row.rolbypassrls, owned) == (False, False, 0)


def test_dbt40_every_table_is_global_or_tenant_scoped_with_forced_rls(owner_engine: Engine) -> None:
    with owner_engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
                       EXISTS (SELECT 1 FROM information_schema.columns col
                               WHERE col.table_name = c.relname AND col.column_name = 'tenant_id'
                                 AND col.is_nullable = 'NO') AS has_tenant,
                       EXISTS (SELECT 1 FROM pg_policies p WHERE p.tablename = c.relname) AS has_policy,
                       c.relispartition
                FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
                """
            )
        ).all()
    problems = []
    for r in rows:
        if r.relname in GLOBAL_TABLES:
            continue
        if not (r.relrowsecurity and r.relforcerowsecurity and r.has_tenant):
            problems.append(r.relname)
        elif not r.relispartition and not r.has_policy:
            problems.append(r.relname)
    assert problems == []


def test_dbt44_audit_partitions_have_no_grant_for_app(app_engine: Engine) -> None:
    with app_engine.connect() as conn:
        partitions = (
            conn.execute(
                text(
                    "SELECT inhrelid::regclass::text FROM pg_inherits"
                    " WHERE inhparent = 'audit_event'::regclass"
                )
            )
            .scalars()
            .all()
        )
        assert len(partitions) >= 13
        for part in partitions:
            assert not conn.execute(
                text("SELECT has_table_privilege(current_user, :p, 'SELECT')"), {"p": part}
            ).scalar_one()


def test_dbt01_no_context_returns_zero_rows_without_error(api: Api, app_engine: Engine) -> None:
    api.tenant()
    with app_engine.connect() as conn:
        for table in (*TENANT_TABLES, "tenant"):
            assert conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0  # noqa: S608


def test_dbt02_reused_pooled_connection_after_commit_sees_nothing(api: Api, app_engine: Engine) -> None:
    tenant = api.tenant()
    with app_engine.connect() as conn:
        _ctx(conn, tenant.tenant_id)
        assert conn.execute(text("SELECT count(*) FROM site")).scalar_one() == 2
        conn.commit()
        assert conn.execute(text("SELECT count(*) FROM site")).scalar_one() == 0


def test_dbt03_dbt04_context_a_cannot_read_or_write_b(api: Api, app_engine: Engine) -> None:
    a, b = api.tenant(), api.tenant()
    with app_engine.connect() as conn:
        _ctx(conn, a.tenant_id)
        assert (
            conn.execute(
                text("SELECT count(*) FROM site WHERE tenant_id = :b"), {"b": str(b.tenant_id)}
            ).scalar_one()
            == 0
        )
        updated = conn.execute(
            text("UPDATE site SET name = 'piraté' WHERE site_id = :s"), {"s": str(b.sites["S1"])}
        )
        assert updated.rowcount == 0
        with pytest.raises(ProgrammingError) as exc:
            conn.execute(
                text(
                    "INSERT INTO site (tenant_id, code, name, site_type) VALUES (:b, 'X1', 'Intrus', 'MINE')"
                ),
                {"b": str(b.tenant_id)},
            )
        assert exc.value.orig is not None and exc.value.orig.sqlstate == "42501"


def test_dbt10_composite_fk_rejects_cross_tenant_reference(api: Api, owner_engine: Engine) -> None:
    """Même en contournant l'application, une attribution ne peut viser un site d'un autre tenant."""
    a, b = api.tenant(), api.tenant()
    app_engine = create_engine(get_settings().database_url())
    with app_engine.connect() as conn:
        _ctx(conn, a.tenant_id)
        with pytest.raises(IntegrityError) as exc:
            conn.execute(
                text(
                    "INSERT INTO user_role_assignment (tenant_id, tenant_kind, user_account_id, role_code,"
                    " scope_type, site_id, granted_by)"
                    " VALUES (:a, 'CUSTOMER', :u, 'DISPATCHER', 'SITE', :s, :u)"
                ),
                {"a": str(a.tenant_id), "u": str(a.admin.user_id), "s": str(b.sites["S1"])},
            )
        assert exc.value.orig is not None and exc.value.orig.sqlstate == "23503"
    app_engine.dispose()


def test_dbt11_platform_scope_refused_in_customer_tenant(api: Api, app_engine: Engine) -> None:
    a = api.tenant()
    with app_engine.connect() as conn:
        _ctx(conn, a.tenant_id)
        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    "INSERT INTO user_role_assignment (tenant_id, tenant_kind, user_account_id, role_code,"
                    " scope_type, granted_by) VALUES (:a, 'CUSTOMER', :u, 'PLATFORM_ADMIN', 'PLATFORM', :u)"
                ),
                {"a": str(a.tenant_id), "u": str(a.admin.user_id)},
            )


def test_dbt30_audit_is_append_only_for_app_role(api: Api, app_engine: Engine) -> None:
    a = api.tenant()
    for statement in (
        "UPDATE audit_event SET reason = 'x'",
        "DELETE FROM audit_event",
        "TRUNCATE audit_event",
    ):
        with app_engine.connect() as conn:
            _ctx(conn, a.tenant_id)
            with pytest.raises(DBAPIError) as exc:
                conn.execute(text(statement))
            assert exc.value.orig is not None and exc.value.orig.sqlstate == "42501"


def test_dbt30_audit_trigger_blocks_owner_updates(owner_engine: Engine) -> None:
    with owner_engine.connect() as conn:
        conn.execute(text("SELECT set_config('row_security', 'off', true)"))
        with pytest.raises(DBAPIError) as exc:
            conn.execute(text("UPDATE audit_event SET reason = 'x'"))
        assert exc.value.orig is not None and exc.value.orig.sqlstate in ("MF001", "42501")


def test_dbt06_tenant_id_is_immutable(api: Api, app_engine: Engine) -> None:
    a, b = api.tenant(), api.tenant()
    with app_engine.connect() as conn:
        _ctx(conn, a.tenant_id)
        with pytest.raises(DBAPIError):
            conn.execute(
                text("UPDATE site SET tenant_id = :b WHERE site_id = :s"),
                {"b": str(b.tenant_id), "s": str(a.sites["S1"])},
            )


def test_dbt07_tenant_readable_only_by_exact_login_code(api: Api, app_engine: Engine) -> None:
    a = api.tenant()
    with app_engine.connect() as conn:
        conn.execute(text("SELECT set_config('app.login_tenant_code', :c, true)"), {"c": a.code})
        rows = conn.execute(text("SELECT code FROM tenant")).scalars().all()
    assert rows == [a.code]


def test_dbt36_row_version_incremented_by_trigger(api: Api, app_engine: Engine) -> None:
    a = api.tenant()
    with app_engine.connect() as conn:
        _ctx(conn, a.tenant_id)
        before = conn.execute(
            text("SELECT row_version FROM site WHERE site_id = :s"), {"s": str(a.sites["S1"])}
        ).scalar_one()
        conn.execute(text("UPDATE site SET name = 'Renommé' WHERE site_id = :s"), {"s": str(a.sites["S1"])})
        after = conn.execute(
            text("SELECT row_version FROM site WHERE site_id = :s"), {"s": str(a.sites["S1"])}
        ).scalar_one()
        conn.rollback()
    assert after == before + 1
