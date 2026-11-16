"""Fiabilité et coûts de maintenance par engin (docs/LIVRAISON_FIABILITE.md)."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.core.config import get_settings
from app.maintenance.reliability import _union
from tests.conftest import API, Account, Api
from tests.test_assignment import World, _vehicle, w  # noqa: F401  (fixture w)

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _h(hours: float) -> datetime:
    return T0 + timedelta(hours=hours)


def _act(client: TestClient, kind: str, order_id: str, headers: dict[str, str], **body: object) -> None:
    url = f"{API}/work-orders/{order_id}"
    version = client.get(url, headers=headers).headers["ETag"]
    resp = client.post(f"{url}/{kind}", headers={**headers, "If-Match": version}, json=body)
    assert resp.status_code == 200, resp.text


def _closed_order(
    client: TestClient,
    w: World,  # noqa: F811
    vehicle: str,
    chief: Account,
    mechanic: Account,
    *,
    immobilize: bool,
    labour_minutes: int = 0,
) -> str:
    resp = client.post(
        f"{API}/work-orders",
        headers=w.dispatcher.headers,
        json={"vehicle_id": vehicle, "symptom_code": "ENGINE", "priority": "HIGH", "immobilize": immobilize},
    )
    assert resp.status_code == 201, resp.text
    oid = str(resp.json()["work_order_id"])
    _act(client, "decision", oid, chief.headers, action="APPROVE")
    _act(client, "decision", oid, chief.headers, action="ASSIGN", assigned_to=str(mechanic.user_id))
    _act(client, "progress", oid, mechanic.headers, action="START")
    if labour_minutes:
        labour = client.post(
            f"{API}/work-orders/{oid}/labour",
            headers=mechanic.headers,
            json={"minutes": labour_minutes, "performed_on": date.today().isoformat()},
        )
        assert labour.status_code == 201, labour.text
    _act(client, "progress", oid, mechanic.headers, action="SUBMIT", work_done="Remplacement fictif")
    _act(client, "decision", oid, chief.headers, action="QC_PASS")
    return oid


def _backdate(w: World, oid: str, reported: float, started: float, closed: float) -> None:  # noqa: F811
    engine = create_engine(get_settings().database_url(), pool_size=1, max_overflow=0)
    try:
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(w.t.tenant_id)})
            conn.execute(
                text(
                    "UPDATE work_order SET reported_at = :r, started_at = :s, closed_at = :c "
                    "WHERE work_order_id = :o"
                ),
                {"r": _h(reported), "s": _h(started), "c": _h(closed), "o": oid},
            )
    finally:
        engine.dispose()


def test_union_counts_overlaps_once() -> None:
    assert _union([]) == timedelta()
    assert _union([(_h(10), _h(20)), (_h(15), _h(30)), (_h(40), _h(41))]) == timedelta(hours=21)


def test_reliability_indicators_per_vehicle(client: TestClient, w: World, api: Api) -> None:  # noqa: F811
    chief = api.user(w.t, "WORKSHOP_CHIEF")
    mechanic = api.user(w.t, "MECHANIC", "SITE", "S1")
    worn, healthy, overlapped = _vehicle(client, w), _vehicle(client, w), _vehicle(client, w)

    blocking = _closed_order(client, w, worn, chief, mechanic, immobilize=True)
    _backdate(w, blocking, reported=10, started=12, closed=20)  # 10 h immobilisé, remis en 10 h
    workshop = _closed_order(client, w, worn, chief, mechanic, immobilize=False, labour_minutes=90)
    _backdate(w, workshop, reported=30, started=40, closed=45)  # 5 h à l'atelier, remis en 15 h
    first = _closed_order(client, w, overlapped, chief, mechanic, immobilize=True)
    _backdate(w, first, reported=10, started=10, closed=20)
    second = _closed_order(client, w, overlapped, chief, mechanic, immobilize=True)
    _backdate(w, second, reported=15, started=16, closed=30)
    outside = _closed_order(client, w, healthy, chief, mechanic, immobilize=True)
    _backdate(w, outside, reported=200, started=201, closed=210)  # hors période

    resp = client.get(
        f"{API}/maintenance/reliability",
        headers=chief.headers,
        params={"from": T0.isoformat(), "to": _h(100).isoformat()},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["period_hours"] == "100.00"
    rows = {r["vehicle_id"]: r for r in body["vehicles"]}
    assert rows[worn]["failures"] == 2 and rows[worn]["closed_corrective"] == 2
    assert rows[worn]["downtime_hours"] == "15.00" and rows[worn]["availability_percent"] == "85.00"
    assert rows[worn]["mttr_hours"] == "12.50" and rows[worn]["mtbf_hours"] == "42.50"
    assert rows[worn]["labour_hours"] == "1.50"
    assert rows[worn]["parts_cost_known"] == "0" and rows[worn]["parts_cost_complete"] is True
    assert rows[overlapped]["downtime_hours"] == "20.00"
    assert rows[healthy]["failures"] == 0 and rows[healthy]["mtbf_hours"] is None
    assert rows[healthy]["availability_percent"] == "100.00"
    assert body["vehicles"][0]["vehicle_id"] == overlapped  # moins disponible en premier
    assert body["totals"]["failures"] == 4 and body["totals"]["downtime_hours"] == "35.00"


def test_reliability_scope_and_validation(client: TestClient, w: World, api: Api) -> None:  # noqa: F811
    s2_chief = api.user(w.t, "WORKSHOP_CHIEF", "SITE", "S2")
    vehicle = _vehicle(client, w)
    listed = client.get(f"{API}/maintenance/reliability", headers=s2_chief.headers).json()
    assert vehicle not in {r["vehicle_id"] for r in listed["vehicles"]}
    forbidden_site = client.get(
        f"{API}/maintenance/reliability", headers=s2_chief.headers, params={"site_id": str(w.t.sites["S1"])}
    )
    assert forbidden_site.status_code == 404
    other = api.tenant()
    foreign = client.get(f"{API}/maintenance/reliability", headers=other.admin.headers)
    assert foreign.status_code == 403
    ops = client.get(f"{API}/maintenance/reliability", headers=w.ops.headers).json()
    assert vehicle in {r["vehicle_id"] for r in ops["vehicles"]}
    inverted = client.get(
        f"{API}/maintenance/reliability",
        headers=w.ops.headers,
        params={"from": _h(10).isoformat(), "to": _h(5).isoformat()},
    )
    assert inverted.status_code == 422
    too_long = client.get(
        f"{API}/maintenance/reliability",
        headers=w.ops.headers,
        params={"from": (T0 - timedelta(days=400)).isoformat(), "to": T0.isoformat()},
    )
    assert too_long.status_code == 422
    dispatcher = client.get(f"{API}/maintenance/reliability", headers=w.dispatcher.headers)
    assert dispatcher.status_code == 403


def _service_dates(w: World, vehicle: str, commissioned: date | None, decommissioned: date | None) -> None:  # noqa: F811
    engine = create_engine(get_settings().database_url(), pool_size=1, max_overflow=0)
    try:
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(w.t.tenant_id)})
            # Invariant ck_vehicle_retired : date de réforme ⇔ statut RETIRED.
            if decommissioned is None:
                conn.execute(
                    text("UPDATE vehicle SET commissioned_on = :c WHERE vehicle_id = :v"),
                    {"c": commissioned, "v": vehicle},
                )
            else:
                conn.execute(
                    text(
                        "UPDATE vehicle SET commissioned_on = :c, decommissioned_on = :d, status = 'RETIRED' "
                        "WHERE vehicle_id = :v"
                    ),
                    {"c": commissioned, "d": decommissioned, "v": vehicle},
                )
    finally:
        engine.dispose()


def _site_zone(w: World) -> ZoneInfo:  # noqa: F811
    engine = create_engine(get_settings().database_url(), pool_size=1, max_overflow=0)
    try:
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(w.t.tenant_id)})
            name = conn.execute(
                text(
                    "SELECT coalesce(s.timezone, t.default_timezone) FROM site s "
                    "JOIN tenant t ON t.tenant_id = s.tenant_id WHERE s.site_id = :s"
                ),
                {"s": str(w.t.sites["S1"])},
            ).scalar_one()
    finally:
        engine.dispose()
    return ZoneInfo(name)


def test_reliability_uses_each_vehicle_service_window(client: TestClient, w: World, api: Api) -> None:  # noqa: F811
    """Limite levée (LIVRAISON_FIABILITE.md) : la durée de référence est celle où l'engin était en service."""
    chief = api.user(w.t, "WORKSHOP_CHIEF")
    mechanic = api.user(w.t, "MECHANIC", "SITE", "S1")
    zone = _site_zone(w)
    late, retired, future, conflicting = (_vehicle(client, w) for _ in range(4))
    # Période P : 2026-01-01 00:00 → 2026-01-05 00:00 (heure du site), soit 96 h.
    start = datetime(2026, 1, 1, tzinfo=zone)
    end = datetime(2026, 1, 5, tzinfo=zone)

    # Mis en service le 2 janvier : 72 h de service ; une panne bloquante de 12 h dans la fenêtre.
    _service_dates(w, late, date(2026, 1, 2), None)
    failure = _closed_order(client, w, late, chief, mechanic, immobilize=True)
    _backdate_at(
        w, failure, reported=datetime(2026, 1, 3, tzinfo=zone), closed=datetime(2026, 1, 3, 12, tzinfo=zone)
    )
    # Réformé le 3 janvier (fin de journée) : 72 h de service ; immobilisation débordant la réforme.
    _service_dates(w, retired, None, date(2026, 1, 3))
    overflow = _closed_order(client, w, retired, chief, mechanic, immobilize=True)
    _backdate_at(
        w,
        overflow,
        reported=datetime(2026, 1, 3, 18, tzinfo=zone),
        closed=datetime(2026, 1, 4, 6, tzinfo=zone),
    )
    # Mis en service après P, sans OT : omis (ni disponible ni indisponible).
    _service_dates(w, future, date(2026, 2, 1), None)
    # Mis en service après P mais avec une panne dans P : dates incohérentes → durée de P, signalé.
    _service_dates(w, conflicting, date(2026, 2, 1), None)
    odd = _closed_order(client, w, conflicting, chief, mechanic, immobilize=True)
    _backdate_at(
        w, odd, reported=datetime(2026, 1, 2, tzinfo=zone), closed=datetime(2026, 1, 2, 6, tzinfo=zone)
    )

    body = client.get(
        f"{API}/maintenance/reliability",
        headers=chief.headers,
        params={"from": start.isoformat(), "to": end.isoformat()},
    ).json()
    rows = {r["vehicle_id"]: r for r in body["vehicles"]}
    assert body["period_hours"] == "96.00"
    assert rows[late]["service_hours"] == "72.00" and rows[late]["service_dates_conflict"] is False
    assert rows[late]["downtime_hours"] == "12.00"
    assert rows[late]["availability_percent"] == "83.33"  # (72 − 12) / 72, et non (96 − 12) / 96
    assert rows[late]["mtbf_hours"] == "60.00"
    assert rows[retired]["service_hours"] == "72.00"
    assert rows[retired]["downtime_hours"] == "6.00"  # immobilisation bornée à la réforme (18 h → 24 h)
    assert rows[retired]["availability_percent"] == "91.67"
    assert future not in rows
    assert rows[conflicting]["service_dates_conflict"] is True
    assert rows[conflicting]["service_hours"] == "96.00" and rows[conflicting]["downtime_hours"] == "6.00"
    # Totaux : heures de service réellement sommées, pas « durée de P × nombre d'engins ».
    service_total = sum(Decimal(r["service_hours"]) for r in body["vehicles"])
    assert Decimal(body["totals"]["service_hours"]) == service_total
    downtime_total = Decimal(body["totals"]["downtime_hours"])
    expected = ((service_total - downtime_total) * 100 / service_total).quantize(Decimal("0.01"))
    assert Decimal(body["totals"]["availability_percent"]) == expected


def _backdate_at(w: World, oid: str, *, reported: datetime, closed: datetime) -> None:  # noqa: F811
    engine = create_engine(get_settings().database_url(), pool_size=1, max_overflow=0)
    try:
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(w.t.tenant_id)})
            conn.execute(
                text(
                    "UPDATE work_order SET reported_at = :r, started_at = :r, closed_at = :c "
                    "WHERE work_order_id = :o"
                ),
                {"r": reported, "c": closed, "o": oid},
            )
    finally:
        engine.dispose()
