"""Lot 2c — relevés de compteur, documents réglementaires et documents exigés (docs/PLAN_LOT2.md §8)."""

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


def _day(offset: int) -> str:
    return (date.today() + timedelta(days=offset)).isoformat()


def _reading(  # type: ignore[no-untyped-def]
    client: TestClient,
    w: World,  # noqa: F811
    vehicle: str,
    kind: str,
    value: float,
    at: datetime | None = None,
    *,
    reset: str | None = None,
    headers: dict[str, str] | None = None,
):
    body: dict[str, object] = {"meter_kind": kind, "value": value}
    if at is not None:
        body["read_at"] = at.isoformat()
    if reset is not None:
        body["reset_reason"] = reset
    path = "meter-resets" if reset else "meter-readings"
    return client.post(f"{API}/vehicles/{vehicle}/{path}", headers=headers or w.ops.headers, json=body)


def _document(client: TestClient, w: World, vehicle: str, **body: object):  # type: ignore[no-untyped-def]  # noqa: F811
    return client.post(
        f"{API}/vehicles/{vehicle}/documents",
        headers=w.ops.headers,
        json={"doc_type": "INSURANCE", "reference": "POL-FICTIVE-001", "valid_until": _day(200), **body},
    )


def _all_documents(client: TestClient, w: World, vehicle: str) -> None:  # noqa: F811
    """Tous les documents exigés pour un tombereau (D-42), valides."""
    for doc_type in ("INSURANCE", "INTERNAL_INSPECTION", "SITE_ACCESS_PERMIT"):
        assert (
            _document(client, w, vehicle, doc_type=doc_type, reference=f"{doc_type[:3]}-1").status_code == 201
        )


@pytest.fixture
def block_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "required_documents_policy", "block")


# --- Compteurs ----------------------------------------------------------------------------------------


def test_meter_readings_are_ordered_and_plausible(client: TestClient, w: World) -> None:  # noqa: F811
    vehicle = _vehicle(client, w)  # tombereau rigide : 60 km/h au plus (D-43)
    start = _now() - timedelta(hours=2)
    assert _reading(client, w, vehicle, "ODOMETER_KM", 1000, start).status_code == 201
    assert _reading(client, w, vehicle, "ODOMETER_KM", 1100.5).status_code == 201  # 100 km en 2 h
    cases = {
        "below_last_reading": _reading(client, w, vehicle, "ODOMETER_KM", 1050),
        "implausible_increase": _reading(client, w, vehicle, "ODOMETER_KM", 1300),
        "before_last_reading": _reading(
            client, w, vehicle, "ODOMETER_KM", 1200, start + timedelta(minutes=30)
        ),
        "out_of_tolerance": _reading(client, w, vehicle, "ODOMETER_KM", 1200, _now() + timedelta(hours=1)),
    }
    for expected, resp in cases.items():
        assert resp.status_code == 422, (expected, resp.text)
        assert resp.json()["details"][0]["type"] == expected, resp.text
    listed = client.get(f"{API}/vehicles/{vehicle}/meter-readings", headers=w.ops.headers).json()
    assert [r["value"] for r in listed["items"]] == [1100.5, 1000.0]
    assert listed["items"][0]["recorded_by"] is None  # auteur masqué hors administration (L2C-R-08)
    as_admin = client.get(f"{API}/vehicles/{vehicle}/meter-readings", headers=w.t.admin.headers).json()
    assert as_admin["items"][0]["recorded_by"] is not None


def test_light_vehicle_has_a_higher_ceiling(client: TestClient, w: World) -> None:  # noqa: F811
    light = _vehicle(client, w, category="LIGHT_VEHICLE")
    assert _reading(client, w, light, "ODOMETER_KM", 10_000, _now() - timedelta(hours=2)).status_code == 201
    assert _reading(client, w, light, "ODOMETER_KM", 10_200).status_code == 201  # 100 km/h : véhicule léger
    absent = _reading(client, w, light, "HOUR_METER", 10)
    assert absent.status_code == 422 and absent.json()["details"][0]["type"] == "not_on_category"


def test_hour_meter_cannot_run_faster_than_time(client: TestClient, w: World) -> None:  # noqa: F811
    vehicle = _vehicle(client, w)
    assert _reading(client, w, vehicle, "HOUR_METER", 500, _now() - timedelta(hours=2)).status_code == 201
    too_fast = _reading(client, w, vehicle, "HOUR_METER", 503)
    assert too_fast.status_code == 422 and too_fast.json()["details"][0]["type"] == "implausible_increase"
    assert _reading(client, w, vehicle, "HOUR_METER", 501.9).status_code == 201


def test_meter_reset_is_a_separate_lowering_action(client: TestClient, w: World, api: Api) -> None:  # noqa: F811
    """L2C-R-04 : la remise à zéro ne sert qu'à baisser, et seuls l'atelier et l'exploitation la font."""
    vehicle = _vehicle(client, w)
    assert _reading(client, w, vehicle, "ODOMETER_KM", 5000, _now() - timedelta(hours=1)).status_code == 201
    jump = _reading(client, w, vehicle, "ODOMETER_KM", 9_999_999, reset="ROLLOVER")
    assert jump.status_code == 422 and jump.json()["details"][0]["type"] == "reset_not_lower"
    mechanic = api.user(w.t, "MECHANIC", "SITE", "S1")
    assert (
        _reading(
            client, w, vehicle, "ODOMETER_KM", 3, reset="METER_REPLACED", headers=mechanic.headers
        ).status_code
        == 403
    )
    assert _reading(client, w, vehicle, "ODOMETER_KM", 5010, headers=mechanic.headers).status_code == 201
    reset = _reading(client, w, vehicle, "ODOMETER_KM", 3, reset="METER_REPLACED")
    assert reset.status_code == 201 and reset.json()["reset_reason"] == "METER_REPLACED"
    audit = client.get(
        f"{API}/audit-events",
        headers=w.t.admin.headers,
        params={"entity_id": vehicle, "action": "vehicle_meter.reset"},
    ).json()["items"][0]
    assert audit["before_data"]["value"] == 5010.0 and audit["reason"] == "METER_REPLACED"


def test_meter_scope_and_append_only(client: TestClient, w: World, api: Api) -> None:  # noqa: F811
    s2 = _vehicle(client, w, "S2")
    hidden = _reading(client, w, s2, "ODOMETER_KM", 10, headers=w.dispatcher.headers)  # dispatcher du site S1
    assert hidden.status_code == 404
    assert _reading(client, w, s2, "ODOMETER_KM", 1, headers=api.user(w.t, "HSE").headers).status_code == 403
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


def test_documents_are_immutable_and_withdrawn_with_a_reason(client: TestClient, w: World, api: Api) -> None:  # noqa: F811
    vehicle = _vehicle(client, w)
    undated = _document(client, w, vehicle, valid_until=None)
    assert undated.status_code == 422  # seule la carte grise est sans échéance (L2C-R-03)
    assert (
        _document(client, w, vehicle, doc_type="REGISTRATION", reference="CG-1", valid_until=None).status_code
        == 201
    )
    assert _document(client, w, vehicle, reference="Nom <script>").status_code == 422  # référence codée
    insurance = _document(client, w, vehicle, valid_until=_day(10))
    doc = insurance.json()
    assert doc["required"] is True and doc["validity"] == "EXPIRING"  # alerte à 45 jours (D-42)
    url = f"{API}/vehicle-documents/{doc['vehicle_document_id']}"
    assert client.patch(url, headers=w.ops.headers, json={"valid_until": _day(400)}).status_code in (404, 405)
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
    by_hse = client.post(
        f"{API}/vehicles/{vehicle}/documents",
        headers=api.user(w.t, "HSE").headers,
        json={"doc_type": "INTERNAL_INSPECTION", "reference": "INSP-2026-1", "valid_until": "2030-01-01"},
    )
    assert by_hse.status_code == 201
    engine = create_engine(get_settings().database_url(), pool_size=1, max_overflow=0)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(w.t.tenant_id)})
            for statement in (
                "UPDATE vehicle_document SET valid_until = '2099-01-01' WHERE vehicle_document_id = :d",
                "UPDATE vehicle_document SET status = 'VALID', status_reason = NULL"
                " WHERE vehicle_document_id = :d",
            ):
                with pytest.raises(DBAPIError) as refused:
                    conn.execute(text(statement), {"d": doc["vehicle_document_id"]})
                assert getattr(refused.value.orig, "sqlstate", None) == "MF001"  # L2C-R-09
                conn.rollback()
                conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(w.t.tenant_id)})
    finally:
        engine.dispose()


def _expired(client: TestClient, w: World, vehicle: str, doc_type: str = "INSURANCE") -> dict:  # type: ignore[type-arg]  # noqa: F811
    """Exemplaire échu avant-hier (la validité est dérivée des dates, rien d'autre n'est stocké)."""
    resp = _document(
        client, w, vehicle, doc_type=doc_type, reference="ECHU-1", valid_from=_day(-400), valid_until=_day(-2)
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_expired_required_document_blocks_assignment_and_departure(client: TestClient, w: World) -> None:  # noqa: F811
    """RM-104 : affectation refusée, affectation en cours non conforme, départ refusé ; renouvellement."""
    assignment = _assignment(client, w)
    vehicle = assignment["vehicle_id"]
    mid = _mission(client, w, assignment, _refs(client, w)).json()["mission_id"]
    insurance = _expired(client, w, vehicle)
    refused = _event(client, w, mid, "DEPARTED")
    assert (refused.status_code, refused.json()["code"]) == (422, "MISSION_NOT_ELIGIBLE")
    assert "VEHICLE_DOCUMENT_EXPIRED" in [r["code"] for r in refused.json()["details"]["reasons"]]
    current = client.get(
        f"{API}/vehicle-assignments/{assignment['vehicle_assignment_id']}", headers=w.ops.headers
    ).json()
    assert "VEHICLE_DOCUMENT_EXPIRED" in str(current["compliance"])
    other_vehicle = _vehicle(client, w)
    _expired(client, w, other_vehicle)
    blocked = _create(client, w, other_vehicle, _driver(client, w))
    assert blocked.status_code == 422 and "VEHICLE_DOCUMENT_EXPIRED" in str(blocked.json()["details"])
    due = client.get(f"{API}/vehicle-documents", headers=w.ops.headers).json()
    assert insurance["vehicle_document_id"] in {d["vehicle_document_id"] for d in due}
    # Renouvellement : nouvel exemplaire valide → de nouveau éligible, plus d'alerte pour l'ancien.
    assert (
        _document(client, w, vehicle, reference="POL-FICTIVE-002", valid_until="2030-12-31").status_code
        == 201
    )
    assert _event(client, w, mid, "DEPARTED").status_code == 200
    due = client.get(f"{API}/vehicle-documents", headers=w.ops.headers).json()
    assert insurance["vehicle_document_id"] not in {d["vehicle_document_id"] for d in due}


def test_blocking_cannot_be_bypassed(client: TestClient, w: World, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    """L2C-R-01 : « erreur de saisie » tardive refusée ; un document non exigé ne couvre pas un exigé."""
    vehicle = _vehicle(client, w)
    insurance = _expired(client, w, vehicle)
    monkeypatch.setattr(get_settings(), "document_entry_error_window", timedelta(0))
    late = client.post(
        f"{API}/vehicle-documents/{insurance['vehicle_document_id']}/withdraw",
        headers={**w.ops.headers, "If-Match": f'"{insurance["row_version"]}"'},
        json={"reason_code": "ENTRY_ERROR"},
    )
    assert late.status_code == 422 and late.json()["details"][0]["type"] == "entry_error_too_late"
    assert _document(client, w, vehicle, doc_type="OTHER", reference="AUTRE-1").status_code == 201
    still = _create(client, w, vehicle, _driver(client, w))
    assert still.status_code == 422 and "VEHICLE_DOCUMENT_EXPIRED" in str(still.json()["details"])


def test_entry_error_is_ignored_and_missing_documents_follow_the_policy(
    client: TestClient,
    w: World,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D-42 : document exigé jamais saisi → avertissement (« warn ») ou refus (« block »)."""
    vehicle = _vehicle(client, w)
    wrong = _expired(client, w, vehicle)
    client.post(
        f"{API}/vehicle-documents/{wrong['vehicle_document_id']}/withdraw",
        headers={**w.ops.headers, "If-Match": f'"{wrong["row_version"]}"'},
        json={"reason_code": "ENTRY_ERROR"},
    )
    listing = client.get(f"{API}/vehicles/{vehicle}/documents", headers=w.ops.headers).json()
    assert set(listing["missing_types"]) == {"INSURANCE", "INTERNAL_INSPECTION", "SITE_ACCESS_PERMIT"}
    created = _create(client, w, vehicle, _driver(client, w))
    assert created.status_code == 201, created.text
    monkeypatch.setattr(get_settings(), "required_documents_policy", "block")
    other = _vehicle(client, w)
    refused = _create(client, w, other, _driver(client, w))
    assert refused.status_code == 422 and "VEHICLE_DOCUMENT_MISSING" in str(refused.json()["details"])
    _all_documents(client, w, other)
    assert _create(client, w, other, _driver(client, w)).status_code == 201


def test_required_documents_per_category(client: TestClient, w: World, api: Api) -> None:  # noqa: F811
    """D-42 : catalogue par catégorie, modifiable par l'administrateur du tenant seulement."""
    category = w.categories["RIGID_DUMP_TRUCK"]
    url = f"{API}/vehicle-categories/{category}/required-documents"
    current = client.get(url, headers=w.ops.headers).json()
    assert set(current["doc_types"]) == {"INSURANCE", "INTERNAL_INSPECTION", "SITE_ACCESS_PERMIT"}
    assert client.put(url, headers=w.ops.headers, json={"doc_types": ["INSURANCE"]}).status_code == 403
    changed = client.put(url, headers=w.t.admin.headers, json={"doc_types": ["INSURANCE", "REGISTRATION"]})
    assert changed.status_code == 200 and changed.json()["doc_types"] == ["INSURANCE", "REGISTRATION"]
    vehicle = _vehicle(client, w)
    listing = client.get(f"{API}/vehicles/{vehicle}/documents", headers=w.ops.headers).json()
    assert listing["required_types"] == ["INSURANCE", "REGISTRATION"]
    other_tenant = api.tenant()
    foreign = client.get(url, headers=other_tenant.admin.headers)
    assert foreign.status_code == 404
