"""Historical technical report service integration checks."""

from dataclasses import replace
from datetime import date, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from app.authz.dependencies import Authorized
from app.authz.principal import Grant, Principal, evaluate
from app.core.clock import SystemClock
from app.core.db import new_session
from app.core.errors import AppError
from app.core.tenancy import set_tenant_context
from app.dispatch.mining_readiness import ReadinessFinding
from app.dispatch.mining_report_read import get_readiness_report, list_readiness_reports
from app.dispatch.mining_report_service import record_draft_readiness
from app.dispatch.mining_tolerance_service import (
    approve_tolerance_qualification,
    propose_tolerance_qualification,
)
from tests.conftest import Api


def _approved_qualification(auth, approver_auth, site) -> UUID:
    qualification = propose_tolerance_qualification(
        auth,
        site_id=site,
        tolerance_m=2.0,
        survey_source="Topographic campaign 2026-11",
        measurement_method="GNSS RTK",
        instrument_precision_m=0.05,
        surveyed_on=date.today() - timedelta(days=1),
        referential_version="topo-ref-v3",
        justification="Perimeter survey of the haul road network",
        responsible_user_id=auth.user_id,
    )
    approve_tolerance_qualification(approver_auth, site_id=site, qualification_id=qualification)
    return qualification


def test_record_draft_report(api: Api) -> None:
    tenant = api.tenant()
    site = tenant.sites["S1"]
    revision = uuid4()
    with new_session() as db:
        set_tenant_context(db, tenant.tenant_id)
        db.execute(
            text(
                "INSERT INTO mining_route_revision (tenant_id, site_id, revision_id, version, provenance) "
                "VALUES (:t, :s, :r, 1, 'Synthetic')"
            ),
            {"t": tenant.tenant_id, "s": site, "r": revision},
        )
        principal = Principal(
            tenant.admin.user_id,
            tenant.tenant_id,
            "CUSTOMER",
            uuid4(),
            (Grant("OPS_MANAGER", "SITE", site),),
        )
        scope = evaluate(principal, "dispatch.location.manage")
        assert scope is not None
        auth = Authorized(principal, scope, db, SystemClock())
        approver = api.user(tenant, "OPS_MANAGER", "SITE", "S1")
        approver_auth = Authorized(replace(principal, user_id=approver.user_id), scope, db, SystemClock())
        qualification = _approved_qualification(auth, approver_auth, site)
        unapproved = propose_tolerance_qualification(
            auth,
            site_id=site,
            tolerance_m=4.0,
            survey_source="Draft campaign",
            measurement_method="GNSS RTK",
            instrument_precision_m=0.05,
            surveyed_on=date.today() - timedelta(days=1),
            referential_version="topo-ref-v3",
            justification="Draft survey awaiting approval",
            responsible_user_id=auth.user_id,
        )

        def save(
            subject=auth,
            requested_site=site,
            tolerance=2,
            qualification_id=qualification,
        ):
            return record_draft_readiness(
                subject,
                site_id=requested_site,
                revision_id=revision,
                tolerance_m=tolerance,
                tolerance_qualification_id=qualification_id,
            )

        dispatcher = replace(principal, grants=(Grant("DISPATCHER", "SITE", site),))
        with pytest.raises(AppError) as error:
            save(replace(auth, principal=dispatcher))
        assert error.value.code == "PERMISSION_DENIED"
        with pytest.raises(AppError) as error:
            save(requested_site=tenant.sites["S2"])
        assert error.value.code == "PERMISSION_DENIED"
        with pytest.raises(AppError) as error:
            save(replace(auth, principal=replace(principal, mfa_enrollment_pending=True)))
        assert error.value.code == "MFA_ENROLLMENT_REQUIRED"
        with pytest.raises(AppError) as error:
            save(tolerance=3)
        assert error.value.code == "VALIDATION_ERROR"
        with pytest.raises(AppError) as error:
            save(qualification_id=unapproved)
        assert error.value.code == "CONFLICT"
        assert db.execute(text("SELECT count(*) FROM mining_readiness_report")).scalar_one() == 0
        db.commit()
        set_tenant_context(db, tenant.tenant_id)
        result = save()
        assert result.evidence.findings == (ReadinessFinding("EMPTY_GRAPH"),)
        report = db.execute(
            text(
                "SELECT evidence_digest, findings, actor_user_id, tolerance_qualification_id "
                "FROM mining_readiness_report WHERE report_id = :report"
            ),
            {"report": result.report_id},
        ).one()
        assert report.evidence_digest == result.evidence.digest
        assert report.findings == [{"code": "EMPTY_GRAPH", "segment_id": None}]
        assert report.actor_user_id == tenant.admin.user_id
        assert report.tolerance_qualification_id == qualification
        audit = text(
            "SELECT count(*) FROM audit_event WHERE action = 'mining_readiness_report.create' "
            "AND entity_id = :report AND after_data->>'tolerance_qualification_id' = :qualification"
        )
        assert (
            db.execute(audit, {"report": result.report_id, "qualification": str(qualification)}).scalar_one()
            == 1
        )
        db.rollback()
        set_tenant_context(db, tenant.tenant_id)
        assert db.execute(text("SELECT count(*) FROM mining_readiness_report")).scalar_one() == 0
        assert (
            db.execute(audit, {"report": result.report_id, "qualification": str(qualification)}).scalar_one()
            == 0
        )
        committed = save()
        db.commit()
        set_tenant_context(db, tenant.tenant_id)
        assert db.execute(text("SELECT count(*) FROM mining_readiness_report")).scalar_one() == 1
        assert (
            db.execute(
                audit, {"report": committed.report_id, "qualification": str(qualification)}
            ).scalar_one()
            == 1
        )


def test_readiness_report_history(api: Api) -> None:
    tenant = api.tenant()
    other = api.tenant()
    site = tenant.sites["S1"]
    revision = uuid4()
    empty_revision = uuid4()
    with new_session() as db:
        set_tenant_context(db, tenant.tenant_id)
        for rev, version in ((revision, 1), (empty_revision, 2)):
            db.execute(
                text(
                    "INSERT INTO mining_route_revision "
                    "(tenant_id, site_id, revision_id, version, provenance) "
                    "VALUES (:t, :s, :r, :v, 'Synthetic')"
                ),
                {"t": tenant.tenant_id, "s": site, "r": rev, "v": version},
            )
        principal = Principal(
            tenant.admin.user_id,
            tenant.tenant_id,
            "CUSTOMER",
            uuid4(),
            (Grant("OPS_MANAGER", "SITE", site),),
        )
        scope = evaluate(principal, "dispatch.location.read")
        assert scope is not None
        auth = Authorized(principal, scope, db, SystemClock())
        approver = api.user(tenant, "OPS_MANAGER", "SITE", "S1")
        approver_scope = evaluate(replace(principal, user_id=approver.user_id), "dispatch.location.manage")
        assert approver_scope is not None
        approver_auth = Authorized(
            replace(principal, user_id=approver.user_id), approver_scope, db, SystemClock()
        )
        qualification = _approved_qualification(auth, approver_auth, site)
        assert list_readiness_reports(auth, site_id=site, revision_id=empty_revision) == ([], None)
        results = [
            record_draft_readiness(
                auth,
                site_id=site,
                revision_id=revision,
                tolerance_m=2.0,
                tolerance_qualification_id=qualification,
            )
            for _ in range(3)
        ]
        reader_principal = replace(principal, grants=(Grant("DISPATCHER", "SITE", site),))
        reader = replace(auth, principal=reader_principal)
        first, cursor = list_readiness_reports(reader, site_id=site, revision_id=revision, limit=2)
        assert len(first) == 2
        assert cursor == first[-1].report_id
        second, end = list_readiness_reports(reader, site_id=site, revision_id=revision, before=cursor)
        assert len(second) == 1
        assert end is None
        assert [row.report_id for row in first + second] == sorted(
            (item.report_id for item in results), reverse=True
        )
        detail = get_readiness_report(
            reader, site_id=site, revision_id=revision, report_id=first[0].report_id
        )
        assert detail.summary == first[0]
        assert detail.findings == (ReadinessFinding("EMPTY_GRAPH"),)
        with pytest.raises(AppError) as error:
            list_readiness_reports(reader, site_id=site, revision_id=empty_revision, before=cursor)
        assert error.value.code == "NOT_FOUND"
        with pytest.raises(AppError) as error:
            list_readiness_reports(reader, site_id=site, revision_id=revision, limit=101)
        assert error.value.code == "VALIDATION_ERROR"
        with pytest.raises(AppError) as error:
            list_readiness_reports(reader, site_id=tenant.sites["S2"], revision_id=revision)
        assert error.value.code == "PERMISSION_DENIED"
        with pytest.raises(AppError) as error:
            list_readiness_reports(
                replace(reader, principal=replace(reader.principal, mfa_enrollment_pending=True)),
                site_id=site,
                revision_id=revision,
            )
        assert error.value.code == "MFA_ENROLLMENT_REQUIRED"
        db.commit()
        set_tenant_context(db, other.tenant_id)
        foreign = replace(
            principal,
            tenant_id=other.tenant_id,
            user_id=other.admin.user_id,
            grants=(Grant("DISPATCHER", "SITE", other.sites["S1"]),),
        )
        with pytest.raises(AppError) as error:
            get_readiness_report(
                replace(auth, principal=foreign),
                site_id=other.sites["S1"],
                revision_id=revision,
                report_id=results[0].report_id,
            )
        assert error.value.code == "NOT_FOUND"
