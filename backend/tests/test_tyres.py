"""Pneumatiques : cycle de vie, coûts au km/heure, alertes, concurrence (docs/LIVRAISON_PNEUS.md)."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from threading import Barrier
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from app.core.config import get_settings
from app.maintenance.tyre_service import alerts_for, usage_from_events
from tests.conftest import API, Api
from tests.test_assignment import World, _vehicle, w  # noqa: F401  (fixture w)


def _tyre(client: TestClient, headers: dict[str, str], site: uuid.UUID, **extra: object):  # type: ignore[no-untyped-def]
    body: dict[str, object] = {
        "site_id": str(site),
        "serial_number": f"SN-{uuid.uuid4().hex[:8]}",
        "brand": "MarqueFictive",
        "model": "Minier X",
        "size": "27.00R49",
        "category": "DRIVE",
        "purchase_cost": "40000000.00",
        "currency": "GNF",
        "initial_tread_mm": "80.0",
        "scrap_tread_mm": "10.0",
        "nominal_pressure_kpa": 700,
        **extra,
    }
    return client.post(f"{API}/tyres", headers=headers, json=body)


def _act(client: TestClient, tyre: dict, path: str, headers: dict[str, str], **body: object):  # type: ignore[no-untyped-def,type-arg]
    return client.post(
        f"{API}/tyres/{tyre['tyre_id']}/{path}",
        headers={**headers, "If-Match": f'"{tyre["row_version"]}"'},
        json=body,
    )


def test_lifecycle_cost_per_km_and_history(client: TestClient, w: World, api: Api) -> None:  # noqa: F811
    chief = api.user(w.t, "WORKSHOP_CHIEF")
    mechanic = api.user(w.t, "MECHANIC", "SITE", "S1")
    vehicle = _vehicle(client, w)
    created = _tyre(client, chief.headers, w.t.sites["S1"])
    assert created.status_code == 201, created.text
    tyre = created.json()
    assert tyre["status"] == "IN_STOCK" and tyre["last_tread_mm"] == "80.0" and tyre["alerts"] == []

    no_meter = _act(client, tyre, "mount", mechanic.headers, vehicle_id=vehicle, position_code="AR-G-EXT")
    assert no_meter.status_code == 422
    tyre = _act(
        client,
        tyre,
        "mount",
        mechanic.headers,
        vehicle_id=vehicle,
        position_code="AR-G-EXT",
        odometer_km="1000",
    ).json()
    assert tyre["status"] == "MOUNTED" and tyre["position_code"] == "AR-G-EXT"
    backwards = _act(client, tyre, "inspections", mechanic.headers, tread_mm="70.0", odometer_km="900")
    assert backwards.status_code == 422 and backwards.json()["code"] == "TYRE_METER_DECREASED"
    tyre = _act(
        client, tyre, "inspections", mechanic.headers, tread_mm="70.0", pressure_kpa=690, odometer_km="1500"
    ).json()
    assert tyre["km_run"] == "500.0" and tyre["last_pressure_kpa"] == 690
    tyre = _act(
        client, tyre, "dismount", mechanic.headers, reason_code="WEAR", odometer_km="2000", tread_mm="60.0"
    ).json()
    assert tyre["status"] == "IN_STOCK" and tyre["vehicle_id"] is None and tyre["km_run"] == "1000.0"

    # Atelier externe : rechapage payé dans la devise du pneu.
    stale = tyre
    tyre = _act(client, tyre, "repair", chief.headers, action="SEND").json()
    assert tyre["status"] == "IN_REPAIR"
    assert _act(client, stale, "repair", chief.headers, action="SEND").json()["code"] == "VERSION_CONFLICT"
    usd = _act(
        client,
        tyre,
        "repair",
        chief.headers,
        action="RETREADED",
        cost="100",
        currency="USD",
        new_tread_mm="70.0",
    )
    assert usd.status_code == 422 and usd.json()["code"] == "TYRE_CURRENCY_MISMATCH"
    tyre = _act(
        client,
        tyre,
        "repair",
        chief.headers,
        action="RETREADED",
        cost="10000000.00",
        currency="GNF",
        new_tread_mm="70.0",
    ).json()
    assert tyre["retread_count"] == 1 and tyre["last_tread_mm"] == "70.0"

    tyre = _act(
        client,
        tyre,
        "mount",
        mechanic.headers,
        vehicle_id=vehicle,
        position_code="AR-G-EXT",
        odometer_km="5000",
    ).json()
    tyre = _act(client, tyre, "dismount", mechanic.headers, reason_code="ROTATION", odometer_km="5500").json()
    assert tyre["km_run"] == "1500.0"
    assert tyre["total_cost"] == "50000000.00" and tyre["cost_complete"] is True
    assert Decimal(tyre["cost_per_km"]) == (Decimal("50000000") / Decimal("1500")).quantize(Decimal("0.0001"))
    assert tyre["cost_per_hour"] is None  # aucun relevé d'heures : pas de coût horaire inventé

    mounted = _act(
        client, tyre, "mount", mechanic.headers, vehicle_id=vehicle, position_code="AV-G", hour_meter="100"
    ).json()
    assert (
        _act(client, mounted, "scrap", chief.headers, reason_code="WORN_OUT").json()["code"]
        == "TYRE_STATE_INVALID"
    )
    tyre = _act(client, mounted, "dismount", mechanic.headers, reason_code="DAMAGE", hour_meter="160").json()
    assert tyre["hours_run"] == "60.0"
    tyre = _act(client, tyre, "scrap", chief.headers, reason_code="IRREPARABLE_DAMAGE").json()
    assert tyre["status"] == "SCRAPPED" and tyre["alerts"] == []

    detail = client.get(f"{API}/tyres/{tyre['tyre_id']}", headers=chief.headers).json()
    assert [e["event_type"] for e in detail["events"]] == [
        "REGISTERED",
        "MOUNTED",
        "INSPECTED",
        "DISMOUNTED",
        "SENT_TO_REPAIR",
        "RETREADED",
        "MOUNTED",
        "DISMOUNTED",
        "MOUNTED",
        "DISMOUNTED",
        "SCRAPPED",
    ]
    by_vehicle = client.get(f"{API}/tyres", headers=chief.headers, params={"vehicle_id": vehicle}).json()
    assert by_vehicle["total"] == 0  # plus rien de monté
    audit = client.get(
        f"{API}/audit-events", headers=w.t.admin.headers, params={"action": "maintenance.tyre.scrap"}
    )
    assert any(e["entity_id"] == tyre["tyre_id"] for e in audit.json()["items"])


def test_rules_and_validation(client: TestClient, w: World, api: Api) -> None:  # noqa: F811
    chief = api.user(w.t, "WORKSHOP_CHIEF")
    vehicle = _vehicle(client, w)
    other_site_vehicle = _vehicle(client, w, "S2")
    serial = f"SN-{uuid.uuid4().hex[:8]}"
    assert _tyre(client, chief.headers, w.t.sites["S1"], serial_number=serial).status_code == 201
    duplicate = _tyre(
        client, chief.headers, w.t.sites["S1"], serial_number=serial.lower(), brand="marquefictive"
    )
    assert duplicate.status_code == 409 and duplicate.json()["code"] == "DUPLICATE_TYRE_SERIAL"
    assert _tyre(client, chief.headers, w.t.sites["S1"], currency=None).status_code == 422
    assert _tyre(client, chief.headers, w.t.sites["S1"], scrap_tread_mm="90.0").status_code == 422
    assert _tyre(client, chief.headers, w.t.sites["S1"], spare_part_id=str(uuid.uuid4())).status_code == 422

    first = _tyre(client, chief.headers, w.t.sites["S1"]).json()
    second = _tyre(client, chief.headers, w.t.sites["S1"]).json()
    assert (
        _act(
            client, first, "mount", chief.headers, vehicle_id=vehicle, position_code="AV-D", odometer_km="10"
        ).status_code
        == 200
    )
    taken = _act(
        client, second, "mount", chief.headers, vehicle_id=vehicle, position_code="AV-D", odometer_km="10"
    )
    assert taken.status_code == 409 and taken.json()["code"] == "TYRE_POSITION_OCCUPIED"
    elsewhere = _act(
        client,
        second,
        "mount",
        chief.headers,
        vehicle_id=other_site_vehicle,
        position_code="AV-D",
        odometer_km="10",
    )
    assert elsewhere.status_code == 422 and elsewhere.json()["code"] == "REFERENCE_NOT_FOUND"
    bad_position = _act(
        client, second, "mount", chief.headers, vehicle_id=vehicle, position_code="av d", odometer_km="10"
    )
    assert bad_position.status_code == 422
    foreign_order = _act(
        client,
        second,
        "mount",
        chief.headers,
        vehicle_id=vehicle,
        position_code="AV-G",
        odometer_km="1",
        work_order_id=str(uuid.uuid4()),
    )
    assert foreign_order.status_code == 422


def test_concurrent_mounts_on_one_position(client: TestClient, w: World, api: Api) -> None:  # noqa: F811
    chief = api.user(w.t, "WORKSHOP_CHIEF")
    vehicle = _vehicle(client, w)
    tyres = [_tyre(client, chief.headers, w.t.sites["S1"]).json() for _ in range(2)]
    barrier = Barrier(2)

    def mount(index: int) -> int:
        barrier.wait()
        return _act(
            client,
            tyres[index],
            "mount",
            chief.headers,
            vehicle_id=vehicle,
            position_code="AR-D-INT",
            odometer_km="5",
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = sorted(pool.map(mount, range(2)))
    assert codes == [200, 409]
    mounted = client.get(f"{API}/tyres", headers=chief.headers, params={"vehicle_id": vehicle}).json()
    assert mounted["total"] == 1


def test_scope_isolation_and_permissions(client: TestClient, w: World, api: Api) -> None:  # noqa: F811
    chief = api.user(w.t, "WORKSHOP_CHIEF")
    s2_mechanic = api.user(w.t, "MECHANIC", "SITE", "S2")
    tyre = _tyre(client, chief.headers, w.t.sites["S1"]).json()
    other = api.tenant()
    other_chief = api.user(other, "WORKSHOP_CHIEF")
    for headers in (s2_mechanic.headers, other_chief.headers):
        assert client.get(f"{API}/tyres/{tyre['tyre_id']}", headers=headers).status_code == 404
        listed = client.get(f"{API}/tyres", headers=headers).json()
        assert tyre["tyre_id"] not in {t["tyre_id"] for t in listed["items"]}
        assert _act(client, tyre, "inspections", headers, tread_mm="50.0").status_code == 404
    assert _tyre(client, other_chief.headers, w.t.sites["S1"]).status_code == 422
    mechanic = api.user(w.t, "MECHANIC", "SITE", "S1")
    assert _tyre(client, mechanic.headers, w.t.sites["S1"]).status_code == 403
    assert _act(client, tyre, "scrap", mechanic.headers, reason_code="AGE").status_code == 403
    assert client.get(f"{API}/tyres", headers=w.dispatcher.headers).status_code == 403


def test_alerts_and_alert_filter(client: TestClient, w: World, api: Api) -> None:  # noqa: F811
    chief = api.user(w.t, "WORKSHOP_CHIEF")
    vehicle = _vehicle(client, w)
    worn = _tyre(client, chief.headers, w.t.sites["S1"]).json()
    worn = _act(client, worn, "inspections", chief.headers, tread_mm="12.0", pressure_kpa=560).json()
    assert set(worn["alerts"]) == {"TREAD_LOW", "PRESSURE_DEVIATION"}
    limit = _act(client, worn, "inspections", chief.headers, tread_mm="9.5", pressure_kpa=700).json()
    assert limit["alerts"] == ["TREAD_AT_LIMIT"]
    healthy = _tyre(client, chief.headers, w.t.sites["S1"]).json()
    mounted = _act(
        client, healthy, "mount", chief.headers, vehicle_id=vehicle, position_code="AV-G", odometer_km="1"
    ).json()
    engine = create_engine(get_settings().database_url(), pool_size=1, max_overflow=0)
    try:
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(w.t.tenant_id)})
            conn.execute(
                text("UPDATE tyre SET mounted_at = now() - interval '45 days' WHERE tyre_id = :i"),
                {"i": mounted["tyre_id"]},
            )
            with pytest.raises(DBAPIError):
                with conn.begin_nested():
                    conn.execute(
                        text("UPDATE tyre_event SET note = 'x' WHERE tyre_id = :i"), {"i": mounted["tyre_id"]}
                    )
    finally:
        engine.dispose()
    flagged = client.get(
        f"{API}/tyres", headers=chief.headers, params={"alert_only": True, "page_size": 200}
    ).json()
    ids = {t["tyre_id"]: t["alerts"] for t in flagged["items"]}
    assert ids[mounted["tyre_id"]] == ["INSPECTION_OVERDUE"] and ids[worn["tyre_id"]] == ["TREAD_AT_LIMIT"]
    assert flagged["total"] == len(flagged["items"])


def _e(event_type: str, km: str | None = None, hours: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        event_type=event_type,
        odometer_km=Decimal(km) if km else None,
        hour_meter=Decimal(hours) if hours else None,
    )


def test_usage_ignores_unmeasured_periods() -> None:
    events = [_e("MOUNTED", "100"), _e("INSPECTED", "150"), _e("DISMOUNTED", "300"), _e("INSPECTED", "999")]
    events += [_e("MOUNTED", hours="10"), _e("INSPECTED", hours="25")]
    usage = usage_from_events(events)  # type: ignore[arg-type]
    assert usage.km == Decimal("200") and usage.hours == Decimal("15")
    # Compteur remplacé entre montage et démontage (relevé inférieur) : la période n'est pas comptée.
    assert usage_from_events([_e("MOUNTED", "500"), _e("DISMOUNTED", "20")]).km == 0  # type: ignore[list-item]


def test_alerts_pure_rules() -> None:
    now = datetime(2026, 11, 2, tzinfo=UTC)
    tyre = SimpleNamespace(
        status="MOUNTED",
        last_tread_mm=Decimal("20"),
        scrap_tread_mm=Decimal("10"),
        nominal_pressure_kpa=None,
        last_pressure_kpa=None,
        mounted_at=now - timedelta(days=40),
        last_inspected_at=now - timedelta(days=5),
    )
    assert alerts_for(tyre, now) == []  # type: ignore[arg-type]
    tyre.last_inspected_at = now - timedelta(days=31)
    assert alerts_for(tyre, now) == ["INSPECTION_OVERDUE"]  # type: ignore[arg-type]


def test_catalogue_link_and_stock_summary(client: TestClient, w: World, api: Api) -> None:  # noqa: F811
    chief = api.user(w.t, "WORKSHOP_CHIEF")
    keeper = api.user(w.t, "STOREKEEPER")
    each = client.post(
        f"{API}/parts",
        headers=keeper.headers,
        json={"code": f"PN-{uuid.uuid4().hex[:6]}", "name": "Pneu 27.00R49"},
    ).json()
    liquid = client.post(
        f"{API}/parts",
        headers=keeper.headers,
        json={"code": f"HUI-{uuid.uuid4().hex[:6]}", "name": "Huile", "unit": "LITER"},
    ).json()
    refused = _tyre(client, chief.headers, w.t.sites["S1"], spare_part_id=liquid["spare_part_id"])
    assert refused.status_code == 422 and refused.json()["details"][0]["type"] == "unit_not_each"
    size = f"T-{uuid.uuid4().hex[:4]}"
    linked = _tyre(
        client, chief.headers, w.t.sites["S1"], spare_part_id=each["spare_part_id"], size=size
    ).json()
    assert linked["spare_part_code"] == each["code"]
    second = _tyre(
        client, chief.headers, w.t.sites["S1"], spare_part_id=each["spare_part_id"], size=size
    ).json()
    worn = _tyre(
        client, chief.headers, w.t.sites["S1"], spare_part_id=each["spare_part_id"], size=size
    ).json()
    vehicle = _vehicle(client, w)
    assert (
        _act(
            client, second, "mount", chief.headers, vehicle_id=vehicle, position_code="AV-G", odometer_km="1"
        ).status_code
        == 200
    )
    assert _act(client, worn, "inspections", chief.headers, tread_mm="9.0").status_code == 200
    scrapped = _tyre(
        client, chief.headers, w.t.sites["S1"], spare_part_id=each["spare_part_id"], size=size
    ).json()
    assert _act(client, scrapped, "scrap", chief.headers, reason_code="AGE").status_code == 200

    stock = client.get(f"{API}/tyres/stock", headers=chief.headers).json()
    row = next(r for r in stock if r["size"] == size)
    assert row == {
        "site_id": str(w.t.sites["S1"]),
        "size": size,
        "brand": "MarqueFictive",
        "model": "Minier X",
        "spare_part_code": each["code"],
        "in_stock": 2,
        "mounted": 1,
        "in_repair": 0,
        "alerts_in_stock": 1,
    }
    s2 = api.user(w.t, "MECHANIC", "SITE", "S2")
    assert all(r["size"] != size for r in client.get(f"{API}/tyres/stock", headers=s2.headers).json())
    assert (
        client.get(
            f"{API}/tyres/stock", headers=s2.headers, params={"site_id": str(w.t.sites["S1"])}
        ).status_code
        == 404
    )
    other = api.user(api.tenant(), "WORKSHOP_CHIEF")
    assert all(r["size"] != size for r in client.get(f"{API}/tyres/stock", headers=other.headers).json())
