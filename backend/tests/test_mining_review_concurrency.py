"""Real concurrent PostgreSQL checks for review decisions (transactional coherence).

Three proofs, on separate connections: a source writer blocks until the decision
transaction releases its locks; a writer that committed before the decision is
detected by digest mismatch (EVIDENCE_STALE); two concurrent decisions produce
exactly one winner through the unique index wait.
"""

import threading
import time
from datetime import date, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.authz.dependencies import Authorized
from app.authz.principal import Grant, Principal, evaluate
from app.core.clock import SystemClock
from app.core.db import new_session
from app.core.errors import AppError
from app.core.tenancy import set_tenant_context
from app.dispatch.mining_report_service import record_draft_readiness
from app.dispatch.mining_review_locks import lock_review_sources
from app.dispatch.mining_review_service import reject_readiness_report
from app.dispatch.mining_tolerance_service import (
    approve_tolerance_qualification,
    propose_tolerance_qualification,
)
from tests.conftest import Api


def _auth(tenant, site, db, user_id) -> Authorized:
    principal = Principal(
        user_id, tenant.tenant_id, "CUSTOMER", uuid4(), (Grant("OPS_MANAGER", "SITE", site),)
    )
    scope = evaluate(principal, "dispatch.location.manage")
    assert scope is not None
    return Authorized(principal, scope, db, SystemClock())


def _prepare_review(api: Api):
    tenant = api.tenant()
    site = tenant.sites["S1"]
    reviewer = api.user(tenant, "OPS_MANAGER", "SITE", "S1")
    revision = uuid4()
    with new_session() as db:
        set_tenant_context(db, tenant.tenant_id)
        author = _auth(tenant, site, db, tenant.admin.user_id)
        reviewer_auth = _auth(tenant, site, db, reviewer.user_id)
        db.execute(
            text(
                "INSERT INTO mining_route_revision (tenant_id, site_id, revision_id, version, provenance) "
                "VALUES (:t, :s, :r, 1, 'Synthetic')"
            ),
            {"t": tenant.tenant_id, "s": site, "r": revision},
        )
        qualification = propose_tolerance_qualification(
            author,
            site_id=site,
            tolerance_m=2.0,
            survey_source="Topographic campaign 2026-11",
            measurement_method="GNSS RTK",
            instrument_precision_m=0.05,
            surveyed_on=date.today() - timedelta(days=1),
            referential_version="topo-ref-v3",
            justification="Perimeter survey of the haul road network",
            responsible_user_id=author.user_id,
        )
        approve_tolerance_qualification(reviewer_auth, site_id=site, qualification_id=qualification)
        report = record_draft_readiness(
            author,
            site_id=site,
            revision_id=revision,
            tolerance_m=2.0,
            tolerance_qualification_id=qualification,
        ).report_id
        db.commit()
    return tenant, site, revision, reviewer.user_id, report


# The writer-side contract pin: same advisory-key derivation as the decision path.
_ADVISORY_LOCK = text(
    """
    SELECT pg_advisory_xact_lock(
             ('x' || substr(CAST(:revision AS text), 1, 8))::bit(32)::int,
             ('x' || substr(CAST(:revision AS text), 25, 8))::bit(32)::int
           )
    """
)


def test_source_writers_block_until_decision_releases(api: Api) -> None:
    tenant, site, revision, _, _ = _prepare_review(api)
    with new_session() as db:
        set_tenant_context(db, tenant.tenant_id)
        lock_review_sources(_auth(tenant, site, db, tenant.admin.user_id), site_id=site, revision_id=revision)
        with new_session() as writer:
            set_tenant_context(writer, tenant.tenant_id)
            writer.execute(text("SET LOCAL lock_timeout = '400ms'"))
            with pytest.raises(DBAPIError) as error:
                writer.execute(_ADVISORY_LOCK, {"revision": revision})
            assert "lock timeout" in str(error.value)
            writer.rollback()
            set_tenant_context(writer, tenant.tenant_id)
            writer.execute(text("SET LOCAL lock_timeout = '400ms'"))
            with pytest.raises(DBAPIError) as error:
                writer.execute(
                    text("UPDATE site SET code = code WHERE tenant_id = :t AND site_id = :s"),
                    {"t": tenant.tenant_id, "s": site},
                )
            assert "lock timeout" in str(error.value)
        db.commit()
        set_tenant_context(db, tenant.tenant_id)
    with new_session() as writer:
        set_tenant_context(writer, tenant.tenant_id)
        lock_review_sources(
            _auth(tenant, site, writer, tenant.admin.user_id), site_id=site, revision_id=revision
        )
        writer.commit()


def test_writer_committed_before_decision_refuses(api: Api) -> None:
    tenant, site, revision, reviewer_id, report = _prepare_review(api)
    with new_session() as db:
        set_tenant_context(db, tenant.tenant_id)
        db.execute(
            text(
                "INSERT INTO mining_route_node (tenant_id, site_id, revision_id, position, provenance) "
                "VALUES (:t, :s, :r, ST_SetSRID(ST_MakePoint(-10.15, 9.72), 4326), 'Nœud concurrent')"
            ),
            {"t": tenant.tenant_id, "s": site, "r": revision},
        )
        db.commit()
        set_tenant_context(db, tenant.tenant_id)
        auth = _auth(tenant, site, db, reviewer_id)
        with pytest.raises(AppError) as error:
            reject_readiness_report(
                auth,
                site_id=site,
                revision_id=revision,
                report_id=report,
                stage="TECHNICAL",
                reason="Un tronçon a été ajouté après le relevé",
            )
        assert error.value.code == "EVIDENCE_STALE"
        assert db.execute(text("SELECT count(*) FROM mining_review_decision")).scalar_one() == 0
        assert (
            db.execute(
                text("SELECT count(*) FROM audit_event WHERE action = 'mining_review_decision.reject'")
            ).scalar_one()
            == 0
        )
        db.commit()


def test_concurrent_rejection_single_winner(api: Api) -> None:
    tenant, site, revision, reviewer_id, report = _prepare_review(api)
    started = threading.Event()
    outcome: dict[str, object] = {}

    def winner() -> None:
        try:
            with new_session() as db:
                set_tenant_context(db, tenant.tenant_id)
                db.execute(text("SET lock_timeout = '10s'"))
                db.execute(
                    text(
                        "INSERT INTO mining_review_decision "
                        "(tenant_id, site_id, revision_id, report_id, stage, decision, "
                        "actor_user_id, reason) VALUES (:t, :s, :r, :p, 'TECHNICAL', 'REJECTED', "
                        ":a, 'Décision concurrente gagnante')"
                    ),
                    {
                        "t": tenant.tenant_id,
                        "s": site,
                        "r": revision,
                        "p": report,
                        "a": reviewer_id,
                    },
                )
                started.set()
                time.sleep(1.5)
                db.commit()
            outcome["winner"] = True
        except DBAPIError as exc:  # pragma: no cover - diagnostic only
            outcome["winner"] = False
            outcome["error"] = repr(exc)

    thread = threading.Thread(target=winner)
    thread.start()
    assert started.wait(5)
    with new_session() as db:
        set_tenant_context(db, tenant.tenant_id)
        db.execute(text("SET lock_timeout = '10s'"))
        auth = _auth(tenant, site, db, reviewer_id)
        before = time.monotonic()
        with pytest.raises(AppError) as error:
            reject_readiness_report(
                auth,
                site_id=site,
                revision_id=revision,
                report_id=report,
                stage="TECHNICAL",
                reason="Rejet concurrent perdant",
            )
        elapsed = time.monotonic() - before
        assert error.value.code == "CONFLICT"
        assert elapsed >= 1.0, "the loser must really wait on the unique index"
    thread.join(10)
    assert outcome.get("winner") is True
    with new_session() as db:
        set_tenant_context(db, tenant.tenant_id)
        assert (
            db.execute(
                text(
                    "SELECT count(*) FROM mining_review_decision WHERE report_id = :p AND stage = 'TECHNICAL'"
                ),
                {"p": report},
            ).scalar_one()
            == 1
        )
