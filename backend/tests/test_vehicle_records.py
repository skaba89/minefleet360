"""Lot 2c — relevés de compteur et documents réglementaires des véhicules (docs/PLAN_LOT2.md §8)."""

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from app.core.config import get_settings
from tests.conftest import API, Api
from tests.test_assignment import World, _create, _driver, _vehicle, w  # noqa: F401  (fixture w)
from tests.test_dispatch import _assignment, _event, _mission, _refs


def _now() -> datetime:
    return datetime.now(UTC)


def _reading(  # type: ignore[no-untyped-def]
    client: TestClient,
    w: World,  # noqa: F811
    vehicle: str,
    kind: str,
    value: float,
    at: datetime | None = None,
    **extra,
):
    body: dict[str, object] = {"meter_kind": kind, "value": value, **extra}
    if at is not None:
        body["read_at"] = at.isoformat()
    return client.post(f"{API}/vehicles/{vehicle}/meter-readings", headers=w.ops.headers, json=body)


def _document(client: TestClient, w: World, vehicle: str, **body: object):  # type: ignore[no-untyped-def]  # noqa: F811
    return client.post(
        f"{API}/vehicles/{vehicle}/documents",
        headers=w.ops.headers,
        json={"doc_type": "INSURANCE", "reference": "POL-FICTIVE-001", **body},
    )


# --- Compteurs ----------------------------------------------------------------------------------------


def test_meter_readings_are_ordered_and_plausible(client: TestClient, w: World) -> None:  # noqa: F811
    vehicle = _vehicle(client, w)
    start = _now() - timedelta(hours=2)
    assert _reading(client, w, vehicle, "ODOMETER_KM", 1000, start).status_code == 201
    assert _reading(client, w, vehicle, "ODOMETER_KM", 1100.5).status_code == 201  # 100 km en 2 h
    cases = {
        "below_last_reading": _reading(client, w, vehicle, "ODOMETER_KM", 1050),
        "implausible_increase": _reading(client, w, vehicle, "ODOMETER_KM", 5000),
        "before_last_reading": _reading(
            client, w, vehicle, "ODOMETER_KM", 1200, start + timedelta(minutes=30)
        ),
        "out_of_tolerance": _reading(client, w, vehicle, "ODOMETER_KM", 1200, _now() + timedelta(hours=1)),
    }
    for expected, resp in cases.items():
        assert resp.status_code == 422, (expected, resp.text)
        assert resp.json()["details"][0]["type"] == expected, resp.text
    # Remise à zéro motivée (compteur remplacé) : seule exception à la progression, tracée.
    reset = _reading(client, w, vehicle, "ODOMETER_KM", 12, reset_reason="METER_REPLACED")
    assert reset.status_code == 201 and reset.json()["reset_reason"] == "METER_REPLACED"
    listed = client.get(f"{API}/vehicles/{vehicle}/meter-readings", headers=w.ops.headers).json()
    assert [r["value"] for r in listed["items"]] == [12.0, 1100.5, 1000.0]
    audit = client.get(
        f"{API}/audit-events",
        headers=w.t.admin.headers,
        params={"entity_id": vehicle, "action": "vehicle_meter.record"},
    ).json()
    assert audit["total"] == 3


def test_hour_meter_cannot_run_faster_than_time(client: TestClient, w: World) -> None:  # noqa: F811
    vehicle = _vehicle(client, w)
    assert _reading(client, w, vehicle, "HOUR_METER", 500, _now() - timedelta(hours=2)).status_code == 201
    too_fast = _reading(client, w, vehicle, "HOUR_METER", 503)
    assert too_fast.status_code == 422 and too_fast.json()["details"][0]["type"] == "implausible_increase"
    assert _reading(client, w, vehicle, "HOUR_METER", 501.9).status_code == 201
    light = _vehicle(client, w, category="LIGHT_VEHICLE")
    absent = _reading(client, w, light, "HOUR_METER", 10)
    assert absent.status_code == 422 and absent.json()["details"][0]["type"] == "not_on_category"


def test_meter_permissions_scope_and_append_only(client: TestClient, w: World, api: Api) -> None:  # noqa: F811
    s2 = _vehicle(client, w, "S2")
    hidden = client.post(
        f"{API}/vehicles/{s2}/meter-readings",
        headers=w.dispatcher.headers,  # dispatcher du site S1
        json={"meter_kind": "ODOMETER_KM", "value": 10},
    )
    assert hidden.status_code == 404
    hse = api.user(w.t, "HSE")
    assert (
        client.post(
            f"{API}/vehicles/{s2}/meter-readings",
            headers=hse.headers,
            json={"meter_kind": "ODOMETER_KM", "value": 1},
        ).status_code
        == 403
    )
    assert _reading(client, w, s2, "ODOMETER_KM", 42).status_code == 201
    engine = create_engine(get_settings().database_url(), pool_size=1, max_overflow=0)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(w.t.tenant_id)})
            with pytest.raises(DBAPIError) as refused:
                conn.execute(
                    text("UPDATE vehicle_meter_reading SET value = 1 WHERE vehicle_id = :v"), {"v": s2}
                )
            assert getattr(refused.value.orig, "sqlstate", None) in ("MF001", "42501")
            conn.rollback()
    finally:
        engine.dispose()


# --- Documents ----------------------------------------------------------------------------------------


def test_document_defaults_validation_and_withdrawal(client: TestClient, w: World, api: Api) -> None:  # noqa: F811
    vehicle = _vehicle(client, w)
    no_date = _document(client, w, vehicle)
    assert no_date.status_code == 422  # assurance bloquante par défaut : échéance obligatoire
    permit = _document(client, w, vehicle, doc_type="SITE_ACCESS_PERMIT", reference="ACCES-12")
    assert permit.status_code == 201 and permit.json()["blocks_assignment"] is False
    insurance = _document(client, w, vehicle, valid_until=(date.today() + timedelta(days=10)).isoformat())
    assert insurance.status_code == 201, insurance.text
    doc = insurance.json()
    assert doc["blocks_assignment"] is True and doc["validity"] == "EXPIRING"
    assert _document(client, w, vehicle, reference="Nom <script>").status_code == 422  # référence codée
    url = f"{API}/vehicle-documents/{doc['vehicle_document_id']}"
    assert (
        client.post(f"{url}/withdraw", headers=w.dispatcher.headers, json={"reason_code": "LOST"}).status_code
        == 403
    )
    withdrawn = client.post(
        f"{url}/withdraw",
        headers={**w.ops.headers, "If-Match": f'"{doc["row_version"]}"'},
        json={"reason_code": "LOST"},
    )
    assert withdrawn.status_code == 200 and withdrawn.json()["validity"] == "WITHDRAWN"
    again = client.patch(
        url,
        headers={**w.ops.headers, "If-Match": f'"{withdrawn.json()["row_version"]}"'},
        json={"issuer": "Assureur"},
    )
    assert again.status_code == 409  # un document retiré ne se modifie plus
    hse = api.user(w.t, "HSE")
    by_hse = client.post(
        f"{API}/vehicles/{vehicle}/documents",
        headers=hse.headers,
        json={"doc_type": "TECHNICAL_INSPECTION", "reference": "VT-2026-1", "valid_until": "2030-01-01"},
    )
    assert by_hse.status_code == 201
    audit = client.get(
        f"{API}/audit-events",
        headers=w.t.admin.headers,
        params={"entity_id": doc["vehicle_document_id"], "action": "vehicle_document.withdraw"},
    ).json()
    assert audit["total"] == 1


def _expire(client: TestClient, w: World, document: dict) -> None:  # type: ignore[type-arg]  # noqa: F811
    """Échéance passée (hier) : la validité est dérivée des dates, rien d'autre n'est stocké."""
    resp = client.patch(
        f"{API}/vehicle-documents/{document['vehicle_document_id']}",
        headers={**w.ops.headers, "If-Match": f'"{document["row_version"]}"'},
        json={"valid_until": (date.today() - timedelta(days=2)).isoformat()},
    )
    assert resp.status_code == 200, resp.text


def test_expired_blocking_document_blocks_assignment_and_departure(client: TestClient, w: World) -> None:  # noqa: F811
    """RM-104 : affectation refusée, affectation en cours non conforme, départ refusé ; renouvellement."""
    assignment = _assignment(client, w)
    vehicle = assignment["vehicle_id"]
    mid = _mission(client, w, assignment, _refs(client, w)).json()["mission_id"]
    insurance = _document(
        client, w, vehicle, valid_until=(date.today() + timedelta(days=200)).isoformat()
    ).json()
    _expire(client, w, insurance)
    refused = _event(client, w, mid, "DEPARTED")
    assert (refused.status_code, refused.json()["code"]) == (422, "MISSION_NOT_ELIGIBLE")
    assert "VEHICLE_DOCUMENT_EXPIRED" in [r["code"] for r in refused.json()["details"]["reasons"]]
    current = client.get(
        f"{API}/vehicle-assignments/{assignment['vehicle_assignment_id']}", headers=w.ops.headers
    ).json()
    assert "VEHICLE_DOCUMENT_EXPIRED" in str(current["compliance"])
    other_vehicle = _vehicle(client, w)
    expired_new = _document(
        client, w, other_vehicle, valid_until=(date.today() + timedelta(days=200)).isoformat()
    )
    _expire(client, w, expired_new.json())
    blocked = _create(client, w, other_vehicle, _driver(client, w))
    assert blocked.status_code == 422
    assert "VEHICLE_DOCUMENT_EXPIRED" in str(blocked.json()["details"])
    due = client.get(f"{API}/vehicle-documents", headers=w.ops.headers).json()
    assert insurance["vehicle_document_id"] in {d["vehicle_document_id"] for d in due}
    # Renouvellement : nouvel exemplaire valide → de nouveau éligible, plus d'alerte pour l'ancien.
    renewed = _document(client, w, vehicle, reference="POL-FICTIVE-002", valid_until="2030-12-31")
    assert renewed.status_code == 201
    assert _event(client, w, mid, "DEPARTED").status_code == 200
    due = client.get(f"{API}/vehicle-documents", headers=w.ops.headers).json()
    assert insurance["vehicle_document_id"] not in {d["vehicle_document_id"] for d in due}


def test_non_blocking_and_entry_error_documents_do_not_block(client: TestClient, w: World) -> None:  # noqa: F811
    vehicle = _vehicle(client, w)
    permit = _document(
        client,
        w,
        vehicle,
        doc_type="ROAD_PERMIT",
        reference="RP-1",
        valid_until=(date.today() + timedelta(days=90)).isoformat(),
    ).json()
    _expire(client, w, permit)
    wrong = _document(client, w, vehicle, valid_until=(date.today() - timedelta(days=1)).isoformat()).json()
    client.post(
        f"{API}/vehicle-documents/{wrong['vehicle_document_id']}/withdraw",
        headers={**w.ops.headers, "If-Match": f'"{wrong["row_version"]}"'},
        json={"reason_code": "ENTRY_ERROR"},
    )
    created = _create(client, w, vehicle, _driver(client, w))
    assert created.status_code == 201, created.text
