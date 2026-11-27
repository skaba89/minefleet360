"""Integration checks for immutable historical review decisions."""

from dataclasses import replace
from uuid import uuid4

import pytest

from sqlalchemy import text

from app.authz.dependencies import Authorized
from app.authz.principal import Grant, Principal, evaluate
from app.core.clock import SystemClock
from app.core.db import new_session
from app.core.errors import AppError
from app.core.tenancy import set_tenant_context
from app.dispatch.mining_review_read import load_review_history
from tests.conftest import Api
from tests.test_mining_route_graph import rejected


def test_mining_review_decision_storage(api: Api) -> None:
    tenant = api.tenant()
    other = api.tenant()
    technical = api.user(tenant, "OPS_MANAGER", "SITE", "S1")
    hse = api.user(tenant, "HSE", "SITE", "S1")
    params = {"t": tenant.tenant_id, "s": tenant.sites["S1"], "r": uuid4()}
    insert_report = text(
        "INSERT INTO mining_readiness_report "
        "(tenant_id, site_id, revision_id, actor_user_id, digest_version, "
        "evidence_digest, tolerance_m, findings) "
        "VALUES (:t, :s, :r, :author, 'mining-readiness-v1', :digest, 2, CAST(:findings AS jsonb)) "
        "RETURNING report_id"
    )
    insert_review = text(
        "INSERT INTO mining_review_decision "
        "(tenant_id, site_id, revision_id, report_id, stage, decision, actor_user_id, reason) "
        "VALUES (:t, :s, :r, :report, :stage, :decision, :actor, 'Synthetic review')"
    )
    with new_session() as db:
        set_tenant_context(db, tenant.tenant_id)
        conn = db.connection()
        conn.execute(
            text(
                "INSERT INTO mining_route_revision (tenant_id, site_id, revision_id, version, provenance) "
                "VALUES (:t, :s, :r, 1, 'Synthetic')"
            ),
            params,
        )
        report_params = {**params, "author": tenant.admin.user_id, "digest": "a" * 64}
        report = conn.execute(insert_report, {**report_params, "findings": "[]"}).scalar_one()
        failed = conn.execute(
            insert_report, {**report_params, "findings": '[{"code":"EMPTY_GRAPH","segment_id":null}]'}
        ).scalar_one()
        principal = Principal(
            tenant.admin.user_id,
            tenant.tenant_id,
            "CUSTOMER",
            uuid4(),
            (Grant("DISPATCHER", "SITE", tenant.sites["S1"]),),
        )
        scope = evaluate(principal, "dispatch.location.read")
        assert scope is not None
        auth = Authorized(principal, scope, db, SystemClock())

        def history(subject=auth, report_id=report, site=tenant.sites["S1"]):
            return load_review_history(subject, site_id=site, revision_id=params["r"], report_id=report_id)

        assert history().decisions == ()
        assert history().technical_review() is None
        with pytest.raises(AppError) as error:
            history(report_id=uuid4())
        assert error.value.code == "NOT_FOUND"
        with pytest.raises(AppError) as error:
            history(site=tenant.sites["S2"])
        assert error.value.code == "PERMISSION_DENIED"
        with pytest.raises(AppError) as error:
            history(replace(auth, principal=replace(principal, mfa_enrollment_pending=True)))
        assert error.value.code == "MFA_ENROLLMENT_REQUIRED"
        review = {
            **params,
            "report": report,
            "stage": "TECHNICAL",
            "decision": "APPROVED",
            "actor": technical.user_id,
        }
        with rejected(conn, "23514"):
            conn.execute(insert_review, {**review, "report": failed})
        with rejected(conn, "23514"):
            conn.execute(insert_review, {**review, "actor": tenant.admin.user_id})
        with rejected(conn, "23503"):
            conn.execute(insert_review, {**review, "actor": other.admin.user_id})
        with rejected(conn, "23503"):
            conn.execute(insert_review, {**review, "s": tenant.sites["S2"]})
        with rejected(conn, "23514"):
            conn.execute(insert_review, {**review, "stage": "HSE", "actor": hse.user_id})
        conn.execute(insert_review, {**review, "report": failed, "decision": "REJECTED"})
        with rejected(conn, "23514"):
            conn.execute(insert_review, {**review, "report": failed, "stage": "HSE", "actor": hse.user_id})
        conn.execute(insert_review, review)
        technical_history = history()
        assert len(technical_history.decisions) == 1
        prior = technical_history.technical_review()
        assert prior is not None
        assert prior.actor_user_id == technical.user_id
        assert prior.evidence_digest == "a" * 64
        assert prior.decision == "APPROVED"
        rejected_prior = history(report_id=failed).technical_review()
        assert rejected_prior is not None
        assert rejected_prior.decision == "REJECTED"
        with rejected(conn, "23505"):
            conn.execute(insert_review, review)
        with rejected(conn, "23514"):
            conn.execute(insert_review, {**review, "stage": "HSE"})
        conn.execute(insert_review, {**review, "stage": "HSE", "actor": hse.user_id})
        complete = history()
        assert [item.stage for item in complete.decisions] == ["TECHNICAL", "HSE"]
        assert complete.decisions[1].actor_user_id == hse.user_id
        assert complete.technical_review() == prior
        assert conn.execute(text("SELECT count(*) FROM mining_review_decision")).scalar_one() == 3
        with rejected(conn, "42501"):
            conn.execute(text("UPDATE mining_review_decision SET decision = 'REJECTED'"))
        with rejected(conn, "42501"):
            conn.execute(text("DELETE FROM mining_review_decision"))
        db.commit()
    with new_session() as db:
        set_tenant_context(db, other.tenant_id)
        conn = db.connection()
        assert conn.execute(text("SELECT count(*) FROM mining_review_decision")).scalar_one() == 0
        foreign = replace(
            principal,
            tenant_id=other.tenant_id,
            user_id=other.admin.user_id,
            grants=(Grant("DISPATCHER", "SITE", other.sites["S1"]),),
        )
        with pytest.raises(AppError) as error:
            load_review_history(
                replace(auth, db=db, principal=foreign),
                site_id=other.sites["S1"],
                revision_id=params["r"],
                report_id=report,
            )
        assert error.value.code == "NOT_FOUND"
        with rejected(conn, "23503"):
            conn.execute(insert_review, {**review, "t": other.tenant_id, "actor": other.admin.user_id})
