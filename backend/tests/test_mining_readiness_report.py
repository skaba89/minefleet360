"""Database constraints for historical reports, not operational approvals."""

from uuid import uuid4

from sqlalchemy import text

from app.core.db import new_session
from app.core.tenancy import set_tenant_context
from tests.conftest import Api
from tests.test_mining_route_graph import rejected


def test_readiness_report_storage(api: Api) -> None:
    first = api.tenant()
    second = api.tenant()
    params = {
        "t": first.tenant_id,
        "s": first.sites["S1"],
        "r": uuid4(),
        "actor": first.admin.user_id,
        "digest": "a" * 64,
        "tolerance": 2.0,
        "findings": "[]",
        "version": "mining-readiness-v1",
    }
    insert = text(
        "INSERT INTO mining_readiness_report "
        "(tenant_id, site_id, revision_id, actor_user_id, digest_version, "
        "evidence_digest, tolerance_m, findings) "
        "VALUES (:t, :s, :r, :actor, :version, :digest, :tolerance, CAST(:findings AS jsonb)) "
        "RETURNING report_id"
    )
    with new_session() as db:
        set_tenant_context(db, first.tenant_id)
        conn = db.connection()
        conn.execute(
            text(
                "INSERT INTO mining_route_revision (tenant_id, site_id, revision_id, version, provenance) "
                "VALUES (:t, :s, :r, 1, 'Synthetic')"
            ),
            params,
        )
        for changes in (
            {"digest": "bad"},
            {"version": "unknown"},
            {"tolerance": -1.0},
            {"tolerance": float("nan")},
            {"tolerance": float("inf")},
            {"findings": "{}"},
        ):
            with rejected(conn, "23514"):
                conn.execute(insert, {**params, **changes})
        with rejected(conn, "23503"):
            conn.execute(insert, {**params, "s": first.sites["S2"]})
        with rejected(conn, "23503"):
            conn.execute(insert, {**params, "actor": second.admin.user_id})
        report = conn.execute(insert, params).scalar_one()
        assert conn.execute(insert, params).scalar_one() != report
        assert conn.execute(text("SELECT count(*) FROM mining_readiness_report")).scalar_one() == 2
        with rejected(conn, "42501"):
            conn.execute(text("UPDATE mining_readiness_report SET tolerance_m = 1"))
        with rejected(conn, "42501"):
            conn.execute(text("DELETE FROM mining_readiness_report"))
        db.commit()
    with new_session() as db:
        set_tenant_context(db, second.tenant_id)
        conn = db.connection()
        assert conn.execute(text("SELECT count(*) FROM mining_readiness_report")).scalar_one() == 0
        with rejected(conn, "23503"):
            conn.execute(insert, {**params, "t": second.tenant_id, "actor": second.admin.user_id})
