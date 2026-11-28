"""Integration checks for positive approval: four eyes, current qualification, concurrency."""

import threading
import time
from dataclasses import replace
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
from app.dispatch.mining_review_read import load_review_history
from app.dispatch.mining_review_service import approve_readiness_report
from app.dispatch.mining_tolerance_service import (
    approve_tolerance_qualification,
    propose_tolerance_qualification,
    retire_tolerance_qualification,
)
from tests.conftest import Api


def _auth(tenant, site, db, user_id, role="OPS_MANAGER") -> Authorized:
    principal = Principal(user_id, tenant.tenant_id, "CUSTOMER", uuid4(), (Grant(role, "SITE", site),))
    scope = evaluate(principal, "dispatch.readiness.approve")
    assert scope is not None
    return Authorized(principal, scope, db, SystemClock())


def _prepare_approval(api: Api):
    tenant = api.tenant()
    site = tenant.sites["S1"]
    reviewer = api.user(tenant, "OPS_MANAGER", "SITE", "S1")
    hse = api.user(tenant, "HSE", "SITE", "S1")
    revision = uuid4()
    with new_session() as db:
        set_tenant_context(db, tenant.tenant_id)
        params = {"t": tenant.tenant_id, "s": site, "r": revision}
        db.execute(
            text(
                "INSERT INTO mining_route_revision (tenant_id, site_id, revision_id, version, provenance) "
                "VALUES (:t, :s, :r, 1, 'Synthetic survey')"
            ),
            params,
        )
        # Clean graph (zero findings): two nodes, one 110 m segment, a complete
        # restriction with an active category — the recipe proven by the
        # readiness snapshot tests.
        for key, longitude in (("a", -13.5), ("b", -13.499)):
            params[key] = uuid4()
            db.execute(
                text(
                    "INSERT INTO mining_route_node (tenant_id, site_id, revision_id, node_id, "
                    "position, provenance) VALUES (:t, :s, :r, :node, "
                    "ST_SetSRID(ST_Point(:lon, 9.5), 4326), 'Synthetic survey')"
                ),
                {**params, "node": params[key], "lon": longitude},
            )
        params["segment"] = uuid4()
        db.execute(
            text(
                "INSERT INTO mining_route_segment (tenant_id, site_id, revision_id, segment_id, "
                "origin_id, destination_id, path, distance_m, duration_seconds, provenance) "
                "SELECT :t, :s, :r, :segment, a.node_id, b.node_id, ST_MakeLine(a.position,b.position), "
                "110, 20, 'Synthetic survey' FROM mining_route_node a, mining_route_node b "
                "WHERE a.node_id = :a AND b.node_id = :b"
            ),
            params,
        )
        db.execute(
            text(
                "INSERT INTO mining_road_restriction "
                "(tenant_id, site_id, revision_id, segment_id, max_gross_mass_kg, max_speed_kmh, "
                "max_height_mm, max_width_mm, max_length_mm, uphill_permille, downhill_permille, provenance) "
                "VALUES (:t, :s, :r, :segment, 40000, 30, 4500, 3500, 13000, 80, 60, 'Synthetic survey')"
            ),
            params,
        )
        category = db.execute(
            text(
                "SELECT vehicle_category_id FROM vehicle_category WHERE tenant_id = :t AND is_active "
                "ORDER BY vehicle_category_id LIMIT 1"
            ),
            params,
        ).scalar_one()
        db.execute(
            text(
                "INSERT INTO mining_road_allowed_category "
                "(tenant_id, site_id, revision_id, segment_id, vehicle_category_id) "
                "VALUES (:t, :s, :r, :segment, :category)"
            ),
            {**params, "category": category},
        )
        author_auth = _auth(tenant, site, db, tenant.admin.user_id)
        reviewer_auth = _auth(tenant, site, db, reviewer.user_id)
        qualification = propose_tolerance_qualification(
            author_auth,
            site_id=site,
            tolerance_m=2.0,
            survey_source="Topographic campaign 2026-11",
            measurement_method="GNSS RTK",
            instrument_precision_m=0.05,
            surveyed_on=date.today() - timedelta(days=1),
            referential_version="topo-ref-v3",
            justification="Perimeter survey of the haul road network",
            responsible_user_id=author_auth.user_id,
        )
        approve_tolerance_qualification(reviewer_auth, site_id=site, qualification_id=qualification)
        report = record_draft_readiness(
            author_auth,
            site_id=site,
            revision_id=revision,
            tolerance_m=2.0,
            tolerance_qualification_id=qualification,
        ).report_id
        db.commit()
    return tenant, site, revision, reviewer.user_id, hse.user_id, report, qualification


def test_technical_approval_transactional_audit(api: Api) -> None:
    tenant, site, revision, reviewer_id, _, report, _ = _prepare_approval(api)
    with new_session() as db:
        set_tenant_context(db, tenant.tenant_id)
        auth = _auth(tenant, site, db, reviewer_id)
        audit = text(
            "SELECT count(*) FROM audit_event WHERE action = 'mining_review_decision.approve' "
            "AND entity_id = :id"
        )
        decision = approve_readiness_report(
            auth,
            site_id=site,
            revision_id=revision,
            report_id=report,
            stage="TECHNICAL",
            reason="Réseau conforme",
        )
        history = load_review_history(auth, site_id=site, revision_id=revision, report_id=report)
        assert history.decisions[0].decision == "APPROVED"
        assert history.decisions[0].stage == "TECHNICAL"
        assert history.decisions[0].reason == "Réseau conforme"
        assert db.execute(audit, {"id": decision}).scalar_one() == 1
        with pytest.raises(AppError) as error:
            approve_readiness_report(
                auth, site_id=site, revision_id=revision, report_id=report, stage="TECHNICAL", reason="Encore"
            )
        assert error.value.code == "CONFLICT"
        db.rollback()
        set_tenant_context(db, tenant.tenant_id)
        assert load_review_history(auth, site_id=site, revision_id=revision, report_id=report).decisions == ()
        assert db.execute(audit, {"id": decision}).scalar_one() == 0
        committed = approve_readiness_report(
            auth,
            site_id=site,
            revision_id=revision,
            report_id=report,
            stage="TECHNICAL",
            reason="Réseau conforme",
        )
        db.commit()
        set_tenant_context(db, tenant.tenant_id)
        assert db.execute(audit, {"id": committed}).scalar_one() == 1


def test_approval_guards(api: Api) -> None:
    tenant, site, revision, reviewer_id, hse_id, report, _ = _prepare_approval(api)
    with new_session() as db:
        set_tenant_context(db, tenant.tenant_id)
        auth = _auth(tenant, site, db, reviewer_id)

        def approve(subject=auth, stage="TECHNICAL", reason="Validation technique"):
            return approve_readiness_report(
                subject, site_id=site, revision_id=revision, report_id=report, stage=stage, reason=reason
            )

        with pytest.raises(AppError) as error:
            approve(subject=_auth(tenant, site, db, tenant.admin.user_id))
        assert error.value.code == "SELF_APPROVAL_FORBIDDEN"
        with pytest.raises(AppError) as error:
            approve(subject=_auth(tenant, site, db, hse_id, role="HSE"))
        assert error.value.code == "PERMISSION_DENIED"
        dispatcher = Principal(
            uuid4(), tenant.tenant_id, "CUSTOMER", uuid4(), (Grant("DISPATCHER", "SITE", site),)
        )
        with pytest.raises(AppError) as error:
            approve(
                Authorized(dispatcher, evaluate(dispatcher, "dispatch.readiness.read"), db, SystemClock())
            )
        assert error.value.code == "PERMISSION_DENIED"
        platform = Principal(
            uuid4(), uuid4(), "PLATFORM", uuid4(), (Grant("PLATFORM_ADMIN", "PLATFORM", None),)
        )
        with pytest.raises(AppError) as error:
            approve(Authorized(platform, evaluate(platform, "dispatch.readiness.approve"), db, SystemClock()))
        assert error.value.code == "PERMISSION_DENIED"
        with pytest.raises(AppError) as error:
            approve(replace(auth, principal=replace(auth.principal, mfa_enrollment_pending=True)))
        assert error.value.code == "MFA_ENROLLMENT_REQUIRED"
        with pytest.raises(AppError) as error:
            approve(reason=" ")
        assert error.value.code == "VALIDATION_ERROR"
        with pytest.raises(AppError) as error:
            approve(reason="x" * 501)
        assert error.value.code == "VALIDATION_ERROR"
        with pytest.raises(AppError) as error:
            approve(stage="QUALITY")
        assert error.value.code == "VALIDATION_ERROR"
        db.rollback()


def test_findings_block_approval(api: Api) -> None:
    tenant, site, revision, reviewer_id, _, _report, qualification = _prepare_approval(api)
    with new_session() as db:
        set_tenant_context(db, tenant.tenant_id)
        db.execute(
            text(
                "INSERT INTO mining_readiness_report (tenant_id, site_id, revision_id, digest_version, "
                "evidence_digest, tolerance_m, findings, actor_user_id, tolerance_qualification_id) "
                "VALUES (:t, :s, :r, 'mining-readiness-v1', :d, 2.0, CAST(:findings AS jsonb), :a, :q)"
            ),
            {
                "t": tenant.tenant_id,
                "s": site,
                "r": revision,
                "d": "b" * 64,
                "findings": '[{"code":"EMPTY_GRAPH","segment_id":null}]',
                "a": tenant.admin.user_id,
                "q": qualification,
            },
        )
        failed = db.execute(
            text("SELECT report_id FROM mining_readiness_report WHERE evidence_digest = :d"), {"d": "b" * 64}
        ).scalar_one()
        auth = _auth(tenant, site, db, reviewer_id)
        with pytest.raises(AppError) as error:
            approve_readiness_report(
                auth,
                site_id=site,
                revision_id=revision,
                report_id=failed,
                stage="TECHNICAL",
                reason="Contient une anomalie",
            )
        assert error.value.code == "CONFLICT"
        assert db.execute(text("SELECT count(*) FROM mining_review_decision")).scalar_one() == 0
        db.commit()


def test_hse_approval_requires_independent_technical(api: Api) -> None:
    tenant, site, revision, reviewer_id, hse_id, report, _ = _prepare_approval(api)
    with new_session() as db:
        set_tenant_context(db, tenant.tenant_id)
        hse_auth = _auth(tenant, site, db, hse_id, role="HSE")
        reviewer_auth = _auth(tenant, site, db, reviewer_id)
        with pytest.raises(AppError) as error:
            approve_readiness_report(
                hse_auth,
                site_id=site,
                revision_id=revision,
                report_id=report,
                stage="HSE",
                reason="Validation HSE",
            )
        assert error.value.code == "CONFLICT"
        approve_readiness_report(
            reviewer_auth,
            site_id=site,
            revision_id=revision,
            report_id=report,
            stage="TECHNICAL",
            reason="Technique OK",
        )
        with pytest.raises(AppError) as error:
            approve_readiness_report(
                _auth(tenant, site, db, reviewer_id, role="HSE"),
                site_id=site,
                revision_id=revision,
                report_id=report,
                stage="HSE",
                reason="Le réviseur technique ne réapprouve pas en HSE",
            )
        assert error.value.code == "CONFLICT"
        approve_readiness_report(
            hse_auth,
            site_id=site,
            revision_id=revision,
            report_id=report,
            stage="HSE",
            reason="Validation HSE",
        )
        history = load_review_history(hse_auth, site_id=site, revision_id=revision, report_id=report)
        assert [item.decision for item in history.decisions] == ["APPROVED", "APPROVED"]
        with pytest.raises(AppError) as error:
            approve_readiness_report(
                hse_auth, site_id=site, revision_id=revision, report_id=report, stage="HSE", reason="Bis"
            )
        assert error.value.code == "CONFLICT"
        db.commit()
        set_tenant_context(db, tenant.tenant_id)
        assert (
            db.execute(
                text("SELECT count(*) FROM mining_review_decision WHERE report_id = :p"), {"p": report}
            ).scalar_one()
            == 2
        )


def test_retired_qualification_blocks_approval(api: Api) -> None:
    tenant, site, revision, reviewer_id, _, report, qualification = _prepare_approval(api)
    with new_session() as db:
        set_tenant_context(db, tenant.tenant_id)
        auth = _auth(tenant, site, db, reviewer_id)
        retire_tolerance_qualification(auth, site_id=site, qualification_id=qualification)
        db.commit()
        set_tenant_context(db, tenant.tenant_id)
        with pytest.raises(AppError) as error:
            approve_readiness_report(
                auth,
                site_id=site,
                revision_id=revision,
                report_id=report,
                stage="TECHNICAL",
                reason="Qualification retirée",
            )
        assert error.value.code == "CONFLICT"
        assert db.execute(text("SELECT count(*) FROM mining_review_decision")).scalar_one() == 0
        db.commit()


def test_grandfathered_report_without_qualification(api: Api) -> None:
    tenant, site, revision, reviewer_id, _, _, _ = _prepare_approval(api)
    with new_session() as db:
        set_tenant_context(db, tenant.tenant_id)
        db.execute(
            text(
                "INSERT INTO mining_readiness_report (tenant_id, site_id, revision_id, digest_version, "
                "evidence_digest, tolerance_m, findings, actor_user_id) "
                "VALUES (:t, :s, :r, 'mining-readiness-v1', :d, 2.0, '[]'::jsonb, :a)"
            ),
            {"t": tenant.tenant_id, "s": site, "r": revision, "d": "c" * 64, "a": tenant.admin.user_id},
        )
        legacy = db.execute(
            text("SELECT report_id FROM mining_readiness_report WHERE evidence_digest = :d"), {"d": "c" * 64}
        ).scalar_one()
        auth = _auth(tenant, site, db, reviewer_id)
        with pytest.raises(AppError) as error:
            approve_readiness_report(
                auth,
                site_id=site,
                revision_id=revision,
                report_id=legacy,
                stage="TECHNICAL",
                reason="Sans qualification",
            )
        assert error.value.code == "CONFLICT"
        db.commit()


def test_evidence_stale_blocks_approval(api: Api) -> None:
    tenant, site, revision, reviewer_id, _, report, _ = _prepare_approval(api)
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
            approve_readiness_report(
                auth,
                site_id=site,
                revision_id=revision,
                report_id=report,
                stage="TECHNICAL",
                reason="Graphe modifié",
            )
        assert error.value.code == "EVIDENCE_STALE"
        assert db.execute(text("SELECT count(*) FROM mining_review_decision")).scalar_one() == 0
        assert (
            db.execute(
                text("SELECT count(*) FROM audit_event WHERE action = 'mining_review_decision.approve'")
            ).scalar_one()
            == 0
        )
        db.commit()


def test_concurrent_approval_single_winner(api: Api) -> None:
    tenant, site, revision, reviewer_id, _, report, _ = _prepare_approval(api)
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
                        "actor_user_id, reason) VALUES (:t, :s, :r, :p, 'TECHNICAL', 'APPROVED', "
                        ":a, 'Approbation concurrente gagnante')"
                    ),
                    {"t": tenant.tenant_id, "s": site, "r": revision, "p": report, "a": reviewer_id},
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
            approve_readiness_report(
                auth,
                site_id=site,
                revision_id=revision,
                report_id=report,
                stage="TECHNICAL",
                reason="Perdant concurrent",
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
