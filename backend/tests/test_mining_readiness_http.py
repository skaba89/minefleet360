"""HTTP contracts for readiness reports and review decisions (Phase 6).

The services carry the authorization depth (four eyes, current qualification,
evidence integrity, transactional pinning); these checks pin the HTTP surface:
routes declared in the matrix, status codes, payloads and audit staging.
"""

from datetime import date, timedelta
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.authz.dependencies import Authorized
from app.authz.principal import Grant, Principal, evaluate
from app.core.clock import SystemClock
from app.core.db import new_session
from app.core.tenancy import set_tenant_context
from app.dispatch.mining_tolerance_service import (
    approve_tolerance_qualification,
    propose_tolerance_qualification,
    retire_tolerance_qualification,
)
from tests.conftest import API, Api


def _base(api: Api):
    tenant = api.tenant()
    site = tenant.sites["S1"]
    ops = api.user(tenant, "OPS_MANAGER", "SITE", site="S1")
    hse = api.user(tenant, "HSE", "SITE", site="S1")
    dispatcher = api.user(tenant, "DISPATCHER", "SITE", site="S1")
    auditor = api.user(tenant, "AUDITOR", "TENANT")
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
        # Clean graph (zero findings) — recipe proven by the readiness snapshot tests.
        for key, longitude in (("a", -13.5), ("b", -13.499)):
            params[key] = uuid4()
            db.execute(
                text(
                    "INSERT INTO mining_route_node (tenant_id, site_id, revision_id, node_id, "
                    "position, provenance) "
                    "VALUES (:t, :s, :r, :node, ST_SetSRID(ST_Point(:lon, 9.5), 4326), 'Synthetic survey')"
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
                "INSERT INTO mining_road_restriction (tenant_id, site_id, revision_id, segment_id, "
                "max_gross_mass_kg, max_speed_kmh, max_height_mm, max_width_mm, max_length_mm, "
                "uphill_permille, downhill_permille, provenance) "
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
                "INSERT INTO mining_road_allowed_category (tenant_id, site_id, revision_id, segment_id, "
                "vehicle_category_id) VALUES (:t, :s, :r, :segment, :category)"
            ),
            {**params, "category": category},
        )

        def principal(user_id: UUID, role: str) -> Authorized:
            built = Principal(user_id, tenant.tenant_id, "CUSTOMER", uuid4(), (Grant(role, "SITE", site),))
            return Authorized(built, evaluate(built, "dispatch.readiness.record"), db, SystemClock())

        qualification = propose_tolerance_qualification(
            principal(ops.user_id, "OPS_MANAGER"),
            site_id=site,
            tolerance_m=2.0,
            survey_source="Topographic campaign 2026-11",
            measurement_method="GNSS RTK",
            instrument_precision_m=0.05,
            surveyed_on=date.today() - timedelta(days=1),
            referential_version="topo-ref-v3",
            justification="Perimeter survey of the haul road network",
            responsible_user_id=ops.user_id,
        )
        approve_tolerance_qualification(
            principal(hse.user_id, "HSE"), site_id=site, qualification_id=qualification
        )
        db.commit()
    return tenant, site, revision, ops, hse, dispatcher, auditor, qualification


def _base_url(site: UUID, revision: UUID) -> str:
    return f"{API}/sites/{site}/mining/revisions/{revision}/readiness-reports"


def _record(
    client: TestClient, headers: dict[str, str], site: UUID, revision: UUID, qualification: UUID
) -> dict:
    resp = client.post(
        _base_url(site, revision),
        headers=headers,
        json={"tolerance_m": 2.0, "tolerance_qualification_id": str(qualification)},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_record_list_detail_review_flow(api: Api) -> None:
    _, site, revision, _ops, _, dispatcher, auditor, qualification = _base(api)
    payload = _record(api.client, dispatcher.headers, site, revision, qualification)
    assert payload["summary"]["evidence_kind"] == "HISTORICAL_TECHNICAL_INSPECTION"
    assert payload["findings"] == []
    assert payload["summary"]["tolerance_qualification_id"] == str(qualification)
    report_id = payload["summary"]["report_id"]

    listing = api.client.get(_base_url(site, revision), headers=auditor.headers)
    assert listing.status_code == 200, listing.text
    body = listing.json()
    assert [item["report_id"] for item in body["items"]] == [report_id]
    assert body["next_cursor"] is None

    detail = api.client.get(f"{_base_url(site, revision)}/{report_id}", headers=auditor.headers)
    assert detail.status_code == 200, detail.text
    assert detail.json() == payload

    review = api.client.get(f"{_base_url(site, revision)}/{report_id}/review", headers=auditor.headers)
    assert review.status_code == 200, review.text
    assert review.json()["evidence_kind"] == "MINING_REVIEW_HISTORY"
    assert review.json()["decisions"] == []


def test_decision_endpoints_guardrails(api: Api) -> None:
    _, site, revision, ops, hse, dispatcher, auditor, qualification = _base(api)
    _record(api.client, dispatcher.headers, site, revision, qualification)
    report_id = api.client.get(_base_url(site, revision), headers=ops.headers).json()["items"][0]["report_id"]

    def decide(headers: dict[str, str], stage: str, reason: str, action: str = "reject"):
        return api.client.post(
            f"{_base_url(site, revision)}/{report_id}/{action}",
            headers=headers,
            json={"stage": stage, "reason": reason},
        )

    dispatcher_reject = decide(dispatcher.headers, "TECHNICAL", "Sans permission")
    assert (dispatcher_reject.status_code, dispatcher_reject.json()["code"]) == (403, "PERMISSION_DENIED")

    auditor_reject = decide(auditor.headers, "TECHNICAL", "Sans permission")
    assert auditor_reject.status_code == 403

    hse_technical = decide(hse.headers, "TECHNICAL", "Mauvais rôle pour l'étape")
    assert (hse_technical.status_code, hse_technical.json()["code"]) == (403, "PERMISSION_DENIED")

    ops_hse = decide(ops.headers, "HSE", "Mauvais rôle pour l'étape", action="approve")
    assert (ops_hse.status_code, ops_hse.json()["code"]) == (403, "PERMISSION_DENIED")

    unknown = api.client.get(f"{_base_url(site, revision)}/{uuid4()}", headers=ops.headers)
    assert (unknown.status_code, unknown.json()["code"]) == (404, "NOT_FOUND")

    bad_stage = decide(ops.headers, "QUALITY", "Étape inconnue", action="approve")
    assert bad_stage.status_code == 422

    long_reason = decide(ops.headers, "TECHNICAL", "x" * 501, action="approve")
    assert long_reason.status_code == 422

    extra_field = api.client.post(
        f"{_base_url(site, revision)}/{report_id}/approve",
        headers=ops.headers,
        json={"stage": "TECHNICAL", "reason": "Champ interdit", "decision": "APPROVED"},
    )
    assert extra_field.status_code == 422


def test_rejection_and_audit(api: Api) -> None:
    tenant, site, revision, ops, _, dispatcher, _, qualification = _base(api)
    _record(api.client, dispatcher.headers, site, revision, qualification)
    report_id = api.client.get(_base_url(site, revision), headers=ops.headers).json()["items"][0]["report_id"]

    rejected = api.client.post(
        f"{_base_url(site, revision)}/{report_id}/reject",
        headers=ops.headers,
        json={"stage": "TECHNICAL", "reason": "Relevé incomplet"},
    )
    assert rejected.status_code == 201, rejected.text
    body = rejected.json()
    assert body["decision"] == "REJECTED"
    assert body["stage"] == "TECHNICAL"
    assert body["reason"] == "Relevé incomplet"
    assert body["evidence_kind"] == "MINING_REVIEW_DECISION"

    with new_session() as db:
        set_tenant_context(db, tenant.tenant_id)
        assert (
            db.execute(
                text(
                    "SELECT count(*) FROM audit_event WHERE action = 'mining_review_decision.reject' "
                    "AND entity_id = :id"
                ),
                {"id": UUID(body["decision_id"])},
            ).scalar_one()
            == 1
        )

    again = api.client.post(
        f"{_base_url(site, revision)}/{report_id}/reject",
        headers=ops.headers,
        json={"stage": "TECHNICAL", "reason": "Doublon"},
    )
    assert (again.status_code, again.json()["code"]) == (409, "CONFLICT")


def test_double_approval_four_eyes(api: Api) -> None:
    tenant, site, revision, ops, hse, _, _, qualification = _base(api)
    author = api.user(tenant, "OPS_MANAGER", "SITE", site="S1")
    _record(api.client, author.headers, site, revision, qualification)
    report_id = api.client.get(_base_url(site, revision), headers=ops.headers).json()["items"][0]["report_id"]

    self_approval = api.client.post(
        f"{_base_url(site, revision)}/{report_id}/approve",
        headers=author.headers,
        json={"stage": "TECHNICAL", "reason": "L'auteur ne s'approuve pas"},
    )
    assert (self_approval.status_code, self_approval.json()["code"]) == (422, "SELF_APPROVAL_FORBIDDEN")

    technical = api.client.post(
        f"{_base_url(site, revision)}/{report_id}/approve",
        headers=ops.headers,
        json={"stage": "TECHNICAL", "reason": "Réseau conforme au relevé"},
    )
    assert technical.status_code == 201, technical.text
    assert technical.json()["decision"] == "APPROVED"

    wrong_stage = api.client.post(
        f"{_base_url(site, revision)}/{report_id}/approve",
        headers=ops.headers,
        json={"stage": "HSE", "reason": "OPS n'approuve pas l'étape HSE"},
    )
    assert (wrong_stage.status_code, wrong_stage.json()["code"]) == (403, "PERMISSION_DENIED")

    hse_approval = api.client.post(
        f"{_base_url(site, revision)}/{report_id}/approve",
        headers=hse.headers,
        json={"stage": "HSE", "reason": "Validation HSE indépendante"},
    )
    assert hse_approval.status_code == 201, hse_approval.text
    assert hse_approval.json()["decision"] == "APPROVED"

    review = api.client.get(f"{_base_url(site, revision)}/{report_id}/review", headers=hse.headers).json()
    assert [item["stage"] for item in review["decisions"]] == ["TECHNICAL", "HSE"]

    duplicate = api.client.post(
        f"{_base_url(site, revision)}/{report_id}/approve",
        headers=ops.headers,
        json={"stage": "TECHNICAL", "reason": "Doublon"},
    )
    assert (duplicate.status_code, duplicate.json()["code"]) == (409, "CONFLICT")


def test_stale_evidence_and_retired_qualification(api: Api) -> None:
    tenant, site, revision, ops, _, dispatcher, _, qualification = _base(api)
    _record(api.client, dispatcher.headers, site, revision, qualification)
    report_id = api.client.get(_base_url(site, revision), headers=ops.headers).json()["items"][0]["report_id"]

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

    stale = api.client.post(
        f"{_base_url(site, revision)}/{report_id}/approve",
        headers=ops.headers,
        json={"stage": "TECHNICAL", "reason": "Le graphe a changé"},
    )
    assert (stale.status_code, stale.json()["code"]) == (409, "EVIDENCE_STALE")

    with new_session() as db:
        set_tenant_context(db, tenant.tenant_id)
        built = Principal(
            ops.user_id, tenant.tenant_id, "CUSTOMER", uuid4(), (Grant("OPS_MANAGER", "SITE", site),)
        )
        retire_tolerance_qualification(
            Authorized(built, evaluate(built, "dispatch.readiness.record"), db, SystemClock()),
            site_id=site,
            qualification_id=qualification,
        )
        db.commit()

    retired = api.client.post(
        f"{_base_url(site, revision)}/{report_id}/approve",
        headers=ops.headers,
        json={"stage": "TECHNICAL", "reason": "Qualification retirée"},
    )
    assert (retired.status_code, retired.json()["code"]) == (409, "CONFLICT")
