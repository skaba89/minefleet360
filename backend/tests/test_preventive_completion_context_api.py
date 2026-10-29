"""Parcours PostgreSQL/API : sélection des preuves, isolation et finalisation."""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.core.config import get_settings
from tests.conftest import API, Api
from tests.test_assignment import World, _vehicle, w  # noqa: F401


def test_completion_context_and_finalization_are_tenant_site_scoped(
    client: TestClient,
    w: World,  # noqa: F811
    api: Api,
) -> None:
    vehicle = _vehicle(client, w)
    other_vehicle = _vehicle(client, w)
    created = client.post(
        f"{API}/preventive-plans",
        headers=w.ops.headers,
        json={"vehicle_id": vehicle, "code": "COMPLETE-UI", "km_interval": 1000, "hours_interval": 100},
    )
    assert created.status_code == 201, created.text
    plan_id = created.json()["maintenance_plan_id"]
    requested = client.post(
        f"{API}/work-orders",
        headers=w.ops.headers,
        json={"vehicle_id": vehicle, "symptom_code": "SERVICE"},
    )
    assert requested.status_code == 201, requested.text
    order_id = requested.json()["work_order_id"]
    due_id = uuid.uuid4()
    closed = datetime.now(UTC) - timedelta(minutes=5)
    good_km, good_hours = uuid.uuid4(), uuid.uuid4()
    excluded = [uuid.uuid4() for _ in range(4)]
    engine = create_engine(get_settings().database_url())
    try:
        with engine.begin() as conn:
            conn.execute(
                text("SELECT set_config('app.tenant_id', :tenant, true)"),
                {"tenant": str(w.t.tenant_id)},
            )
            # État de stockage préparé pour exercer la lecture et la commande,
            # sans répéter ici les tests du cycle qualité déjà couverts.
            conn.execute(
                text(
                    "UPDATE work_order SET kind = 'PREVENTIVE', status = 'CLOSED', "
                    "closed_at = :closed, closed_by = :actor, assigned_to = :actor "
                    "WHERE work_order_id = :order"
                ),
                {"closed": closed, "actor": w.ops.user_id, "order": order_id},
            )
            conn.execute(
                text(
                    "INSERT INTO maintenance_due "
                    "(maintenance_due_id, tenant_id, maintenance_plan_id, vehicle_id, "
                    "trigger_kind, trigger_key, due_meter, status, work_order_id) "
                    "VALUES (:due, :tenant, :plan, :vehicle, 'KM', 'KM:1000', 1000, 'SCHEDULED', :order)"
                ),
                {
                    "due": due_id,
                    "tenant": w.t.tenant_id,
                    "plan": plan_id,
                    "vehicle": vehicle,
                    "order": order_id,
                },
            )
            rows = [
                (good_km, vehicle, w.t.sites["S1"], "ODOMETER_KM", closed - timedelta(minutes=1)),
                (good_hours, vehicle, w.t.sites["S1"], "HOUR_METER", closed - timedelta(minutes=4)),
                (excluded[0], vehicle, w.t.sites["S1"], "ODOMETER_KM", closed - timedelta(minutes=3)),
                (excluded[1], vehicle, w.t.sites["S1"], "ODOMETER_KM", closed + timedelta(minutes=1)),
                (excluded[2], other_vehicle, w.t.sites["S1"], "ODOMETER_KM", closed - timedelta(minutes=1)),
                (excluded[3], vehicle, w.t.sites["S2"], "ODOMETER_KM", closed - timedelta(minutes=1)),
            ]
            for approval, target, site, kind, approved in rows:
                conn.execute(
                    text(
                        "INSERT INTO maintenance_meter_reconciliation_approval "
                        "(approval_id, tenant_id, vehicle_id, site_id, meter_kind, baseline_total, "
                        "current_total, reconciliation_reference, approved_by, approved_at) "
                        "VALUES (:id, :tenant, :vehicle, :site, :kind, 0, 1200, 'FICTIF-UI', :actor, :at)"
                    ),
                    {
                        "id": approval,
                        "tenant": w.t.tenant_id,
                        "vehicle": target,
                        "site": site,
                        "kind": kind,
                        "actor": w.ops.user_id,
                        "at": approved,
                    },
                )
            for read_at in (closed - timedelta(minutes=2), closed + timedelta(minutes=2)):
                conn.execute(
                    text(
                        "INSERT INTO vehicle_meter_reading "
                        "(tenant_id, vehicle_id, site_id, meter_kind, value, read_at, recorded_by) "
                        "VALUES (:tenant, :vehicle, :site, 'ODOMETER_KM', 1199, :at, :actor)"
                    ),
                    {
                        "tenant": w.t.tenant_id,
                        "vehicle": vehicle,
                        "site": w.t.sites["S1"],
                        "at": read_at,
                        "actor": w.ops.user_id,
                    },
                )
        url = f"{API}/work-orders/{order_id}/preventive-completion"
        assert client.get(url).status_code == 401
        assert client.get(url, headers=w.dispatcher.headers).status_code == 403
        other_site = api.user(w.t, "WORKSHOP_CHIEF", "SITE", "S2")
        assert client.get(url, headers=other_site.headers).status_code == 404
        outsider = api.tenant(sites=())
        other_ops = api.user(outsider, "OPS_MANAGER")
        assert client.get(url, headers=other_ops.headers).status_code == 404
        assert (
            client.get(url, headers=w.ops.headers, params={"tenant_id": str(w.t.tenant_id)}).status_code
            == 422
        )

        response = client.get(url, headers=w.ops.headers)
        assert response.status_code == 200, response.text
        context = response.json()
        assert context["maintenance_due_id"] == str(due_id)
        assert context["status"] == "SCHEDULED"
        meters = {meter["meter_kind"]: meter for meter in context["meters"]}
        assert [item["approval_id"] for item in meters["ODOMETER_KM"]["approvals"]] == [str(good_km)]
        assert [item["approval_id"] for item in meters["HOUR_METER"]["approvals"]] == [str(good_hours)]
        assert meters["ODOMETER_KM"]["frozen_total"] is None
        finish_url = f"{API}/work-orders/{order_id}/complete-preventive"
        refused = client.post(finish_url, headers=w.ops.headers, json={})
        assert refused.status_code == 409, refused.text
        done = client.post(
            finish_url,
            headers=w.ops.headers,
            json={"odometer_approval_id": str(good_km), "hour_meter_approval_id": str(good_hours)},
        )
        assert done.status_code == 200, done.text
        assert done.json()["changed"] is True
        replay = client.post(finish_url, headers=w.ops.headers, json={})
        assert replay.status_code == 200, replay.text
        assert replay.json()["changed"] is False
        final = client.get(url, headers=w.ops.headers)
        assert final.status_code == 200, final.text
        assert final.json()["status"] == "COMPLETED"
        assert all(meter["frozen_total"] == "1200.0" for meter in final.json()["meters"])
        assert all(not meter["approvals"] for meter in final.json()["meters"])
    finally:
        engine.dispose()
