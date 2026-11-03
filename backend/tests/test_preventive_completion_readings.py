"""Finalisation sans approbation : cumul de clôture calculé depuis le jalon validé et les relevés (0059).

Parcours : dernier entretien déclaré et approuvé par un tiers -> OT préventif clôturé -> finalisation
sans approbation (cumul figé `READINGS`) -> le cycle suivant repart de ce jalon. Entretien initial :
sans cumul de départ, le dernier relevé brut avant la clôture devient la référence.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection

from app.core.config import get_settings
from tests.conftest import API, Api
from tests.test_assignment import World, _vehicle, w  # noqa: F401

D = Decimal


def _approved_declaration(
    client: TestClient,
    api: Api,
    w: World,  # noqa: F811
    body: dict[str, object],
    decided_at: datetime,
) -> None:
    """Déclaration approuvée par un tiers, datée comme dans le vrai flux (avant la clôture de l'OT)."""
    made = client.post(f"{API}/preventive-declarations", headers=w.ops.headers, json=body)
    assert made.status_code == 201, made.text
    chief = api.user(w.t, "WORKSHOP_CHIEF", "SITE", "S1")
    decided = client.post(
        f"{API}/preventive-declarations/{made.json()['service_declaration_id']}/decide",
        headers=chief.headers,
        json={"decision": "APPROVE"},
    )
    assert decided.status_code == 200, decided.text
    engine = create_engine(get_settings().database_url())
    try:
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(w.t.tenant_id)})
            conn.execute(
                text(
                    "UPDATE maintenance_service_declaration SET decided_at = :at "
                    "WHERE service_declaration_id = :d"
                ),
                {"at": decided_at, "d": made.json()["service_declaration_id"]},
            )
    finally:
        engine.dispose()


def _reading(conn: Connection, w: World, vehicle: str, kind: str, value: str, at: datetime) -> None:  # noqa: F811
    conn.execute(
        text(
            "INSERT INTO vehicle_meter_reading (tenant_id, vehicle_id, site_id, meter_kind, value, read_at, "
            "recorded_by) VALUES (:t, :v, :s, :k, :value, :at, :by)"
        ),
        {
            "t": w.t.tenant_id,
            "v": vehicle,
            "s": w.t.sites["S1"],
            "k": kind,
            "value": value,
            "at": at,
            "by": w.ops.user_id,
        },
    )


def _closed_preventive_order(
    client: TestClient,
    w: World,  # noqa: F811
    conn: Connection,
    vehicle: str,
    plan_id: str,
    *,
    trigger: str,
    closed: datetime,
) -> str:
    requested = client.post(
        f"{API}/work-orders", headers=w.ops.headers, json={"vehicle_id": vehicle, "symptom_code": "SERVICE"}
    )
    assert requested.status_code == 201, requested.text
    order_id = requested.json()["work_order_id"]
    # État de stockage préparé (le cycle qualité de l'OT est couvert ailleurs).
    conn.execute(
        text(
            "UPDATE work_order SET kind = 'PREVENTIVE', status = 'CLOSED', closed_at = :closed, "
            "closed_by = :actor, assigned_to = :actor WHERE work_order_id = :order"
        ),
        {"closed": closed, "actor": w.ops.user_id, "order": order_id},
    )
    due_meter, due_on = (D("1000"), None) if trigger == "KM" else (None, closed.date())
    conn.execute(
        text(
            "INSERT INTO maintenance_due (tenant_id, maintenance_plan_id, vehicle_id, trigger_kind, "
            "trigger_key, due_meter, due_on, status, work_order_id) "
            "VALUES (:t, :p, :v, :kind, :key, :meter, :on, 'SCHEDULED', :order)"
        ),
        {
            "t": w.t.tenant_id,
            "p": plan_id,
            "v": vehicle,
            "kind": trigger,
            "key": f"{trigger}:T",
            "meter": due_meter,
            "on": due_on,
            "order": order_id,
        },
    )
    return order_id


def _status(client: TestClient, w: World, vehicle: str) -> dict:  # type: ignore[type-arg]  # noqa: F811
    resp = client.get(f"{API}/vehicles/{vehicle}/preventive-status", headers=w.ops.headers)
    assert resp.status_code == 200, resp.text
    return resp.json()[0]  # type: ignore[no-any-return]


def test_km_cycle_closes_on_computed_total_and_restarts_from_it(
    client: TestClient,
    api: Api,
    w: World,  # noqa: F811
) -> None:
    vehicle = _vehicle(client, w)
    plan = client.post(
        f"{API}/preventive-plans",
        headers=w.ops.headers,
        json={"vehicle_id": vehicle, "code": "KM-CYCLE", "km_interval": 1000},
    ).json()
    now = datetime.now(UTC).replace(microsecond=0)
    serviced = now - timedelta(days=10)
    closed = now - timedelta(hours=2)
    _approved_declaration(
        client,
        api,
        w,
        {
            "vehicle_id": vehicle,
            "plan_code": "KM-CYCLE",
            "knowledge": "KNOWN",
            "serviced_at": serviced.isoformat(),
            "odometer_km": "5000",
        },
        decided_at=serviced + timedelta(days=1),
    )
    engine = create_engine(get_settings().database_url())
    try:
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(w.t.tenant_id)})
            # Compteur brut à une autre échelle que le cumul déclaré : seules les hausses comptent.
            _reading(conn, w, vehicle, "ODOMETER_KM", "4000", serviced - timedelta(hours=1))
            _reading(conn, w, vehicle, "ODOMETER_KM", "4400", serviced + timedelta(days=3))
            _reading(conn, w, vehicle, "ODOMETER_KM", "4700", closed - timedelta(hours=1))
            order_id = _closed_preventive_order(
                client, w, conn, vehicle, plan["maintenance_plan_id"], trigger="KM", closed=closed
            )
            _reading(conn, w, vehicle, "ODOMETER_KM", "4900", closed + timedelta(minutes=30))

        context = client.get(f"{API}/work-orders/{order_id}/preventive-completion", headers=w.ops.headers)
        assert context.status_code == 200, context.text
        (meter,) = context.json()["meters"]
        assert meter["approvals"] == [] and D(meter["computed_total"]) == D("5700")

        done = client.post(
            f"{API}/work-orders/{order_id}/complete-preventive", headers=w.ops.headers, json={}
        )
        assert done.status_code == 200, done.text
        assert done.json()["changed"] is True
        replay = client.post(
            f"{API}/work-orders/{order_id}/complete-preventive", headers=w.ops.headers, json={}
        )
        assert replay.status_code == 200 and replay.json()["changed"] is False

        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(w.t.tenant_id)})
            frozen = conn.execute(
                text(
                    "SELECT cumulative_total, source, reconciliation_approval_id FROM "
                    "maintenance_service_meter_baseline WHERE work_order_id = :o"
                ),
                {"o": order_id},
            ).one()
            audited = conn.execute(
                text(
                    "SELECT count(*) FROM audit_event WHERE tenant_id = :t "
                    "AND action = 'maintenance.service_meter_baseline.create'"
                ),
                {"t": str(w.t.tenant_id)},
            ).scalar_one()
        assert (frozen.cumulative_total, frozen.source, frozen.reconciliation_approval_id) == (
            D("5700.0"),
            "READINGS",
            None,
        )
        assert audited == 1

        # Le cycle suivant part de la clôture : 5 700 + 200 km relevés depuis, reste 800.
        state = _status(client, w, vehicle)
        assert state["baseline_source"] == "WORK_ORDER"
        assert D(state["current_km"]) == D("5900") and D(state["remaining_km"]) == D("800")
        assert state["status"] == "UPCOMING"
    finally:
        engine.dispose()


def test_initial_service_freezes_last_raw_reading_and_refuses_without_any(
    client: TestClient,
    api: Api,
    w: World,  # noqa: F811
) -> None:
    vehicle = _vehicle(client, w)
    plan = client.post(
        f"{API}/preventive-plans",
        headers=w.ops.headers,
        json={"vehicle_id": vehicle, "code": "H-INIT", "hours_interval": 250},
    ).json()
    closed = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=1)
    _approved_declaration(
        client,
        api,
        w,
        {"vehicle_id": vehicle, "plan_code": "H-INIT", "knowledge": "UNKNOWN"},
        decided_at=closed - timedelta(days=1),
    )
    engine = create_engine(get_settings().database_url())
    try:
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(w.t.tenant_id)})
            order_id = _closed_preventive_order(
                client, w, conn, vehicle, plan["maintenance_plan_id"], trigger="INITIAL", closed=closed
            )
        finish = f"{API}/work-orders/{order_id}/complete-preventive"
        # Aucun relevé avant la clôture : refus explicite, rien n'est figé.
        refused = client.post(finish, headers=w.ops.headers, json={})
        assert refused.status_code == 409, refused.text
        assert refused.json()["details"] == {"missing_meter_kinds": ["HOUR_METER"]}

        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(w.t.tenant_id)})
            _reading(conn, w, vehicle, "HOUR_METER", "300", closed - timedelta(minutes=20))
        done = client.post(finish, headers=w.ops.headers, json={})
        assert done.status_code == 200, done.text
        state = _status(client, w, vehicle)
        assert state["baseline_source"] == "WORK_ORDER" and D(state["current_hours"]) == D("300")
        assert D(state["remaining_hours"]) == D("250")
    finally:
        engine.dispose()
