"""Sorties de carburant rejouables depuis l'outbox terrain (Idempotency-Key, hors ligne).

Même contrat que les relevés de compteur (test_meter_reading_offline) : la clé est liée au tenant
ET au compte authentifié, le corps est empreinté, un rejet métier ne consomme pas la clé et un
rejeu réussi renvoie la sortie d'origine sans nouvel événement d'audit.
"""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from tests.conftest import API, Api
from tests.test_fuel_pumps import _assigned_vehicle_and_driver, _tank


def _offline(client: TestClient, headers: dict[str, str], key: str, body: dict[str, object]):  # type: ignore[no-untyped-def]
    return client.post(f"{API}/fuel/issues", headers={**headers, "Idempotency-Key": key}, json=body)


def _issue_body(
    tank: dict[str, object], vehicle_id: str, driver_id: str, meter_kind: str | None, liters: str = "50.000"
) -> dict[str, object]:
    body: dict[str, object] = {
        "fuel_tank_id": tank["fuel_tank_id"],
        "vehicle_id": vehicle_id,
        "driver_id": driver_id,
        "liters": liters,
        "requested_at": datetime.now(UTC).isoformat(),
    }
    if meter_kind is not None:
        body.update({"meter_kind": meter_kind, "meter_value": "100.0"})
    return body


def _stocked_scenario(
    client: TestClient, api: Api
) -> tuple[object, dict[str, object], dict[str, str], str, str, str | None]:
    tenant = api.tenant(sites=("MINE",))
    tank = _tank(client, tenant.admin.headers, tenant.sites["MINE"])
    received = client.post(
        f"{API}/fuel/tanks/{tank['fuel_tank_id']}/receipts",
        headers=tenant.admin.headers,
        json={
            "liters": "500.000",
            "reference": "BL-OFFLINE-01",
            "occurred_at": (datetime.now(UTC) - timedelta(minutes=20)).isoformat(),
        },
    )
    assert received.status_code == 201, received.text
    ops_headers, vehicle_id, driver_id, meter_kind = _assigned_vehicle_and_driver(client, api, tenant)
    return tenant, tank, ops_headers, vehicle_id, driver_id, meter_kind


def test_offline_fuel_issue_replay_creates_it_once(client: TestClient, api: Api) -> None:
    tenant, tank, ops_headers, vehicle_id, driver_id, meter_kind = _stocked_scenario(client, api)
    key = str(uuid.uuid4())
    body = _issue_body(tank, vehicle_id, driver_id, meter_kind)
    first = _offline(client, ops_headers, key, body)
    assert first.status_code == 201, first.text
    assert "Idempotency-Replayed" not in first.headers
    again = _offline(client, ops_headers, key, body)
    assert again.status_code == 201 and again.headers["Idempotency-Replayed"] == "true"
    issue_id = first.json()["fuel_issue_id"]
    assert again.json()["fuel_issue_id"] == issue_id
    listed = client.get(f"{API}/fuel/issues", headers=tenant.admin.headers).json()
    assert sum(1 for i in listed["items"] if i["fuel_issue_id"] == issue_id) == 1
    audit = client.get(
        f"{API}/audit-events",
        headers=tenant.admin.headers,
        params={"action": "fuel.issue.request", "entity_id": issue_id},
    ).json()["items"]
    assert len(audit) == 1  # la sortie initiale seulement, le rejeu n'ajoute rien
    # Même clé, contenu altéré : refusé, jamais une seconde sortie.
    altered = _offline(client, ops_headers, key, {**body, "liters": "60.000"})
    assert (altered.status_code, altered.json()["code"]) == (422, "IDEMPOTENCY_KEY_REUSED")


def test_rejected_issue_does_not_consume_the_key_and_key_is_per_account(client: TestClient, api: Api) -> None:
    tenant, tank, ops_headers, vehicle_id, driver_id, meter_kind = _stocked_scenario(client, api)
    key = str(uuid.uuid4())
    too_much = _offline(
        client, ops_headers, key, _issue_body(tank, vehicle_id, driver_id, meter_kind, liters="99999.000")
    )
    assert too_much.status_code == 409, too_much.text  # stock insuffisant : rejet métier
    # Le rejet a annulé la réservation de la clé : la demande corrigée passe avec la même clé.
    ok = _offline(client, ops_headers, key, _issue_body(tank, vehicle_id, driver_id, meter_kind))
    assert ok.status_code == 201 and "Idempotency-Replayed" not in ok.headers
    # La clé est liée au compte : un autre OPS rejoue pour son propre compte, sans reprendre la sortie.
    second = api.user(tenant, "OPS_MANAGER")
    theirs = _offline(client, second.headers, key, _issue_body(tank, vehicle_id, driver_id, meter_kind))
    assert theirs.status_code == 201 and "Idempotency-Replayed" not in theirs.headers
    assert theirs.json()["fuel_issue_id"] != ok.json()["fuel_issue_id"]
    # Sans le droit de demander une sortie : refusé avant toute réservation.
    hr = api.user(tenant, "HR")
    forbidden = _offline(
        client, hr.headers, str(uuid.uuid4()), _issue_body(tank, vehicle_id, driver_id, meter_kind)
    )
    assert forbidden.status_code == 403, forbidden.text
