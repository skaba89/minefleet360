"""Bouton « Évaluer les échéances » et liste des échéances d'un site (tranche B2).

L'évaluation enregistre les échéances dues sous le nom du responsable atelier, dans sa portée, sans
doublon au rejeu et sans créer d'OT ; la liste est limitée au site et à la société.
"""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.core.config import get_settings
from tests.conftest import API, Account, Api
from tests.test_assignment import World, _vehicle, w  # noqa: F401


def _plan_with_declaration(
    client: TestClient,
    w: World,  # noqa: F811
    approver: Account,
    *,
    site: str,
    code: str,
    declaration: dict[str, object] | None,
) -> str:
    vehicle = _vehicle(client, w, site=site)
    made = client.post(
        f"{API}/preventive-plans",
        headers=w.ops.headers,
        json={"vehicle_id": vehicle, "code": code, "days_interval": 30},
    )
    assert made.status_code == 201, made.text
    if declaration is not None:
        declared = client.post(
            f"{API}/preventive-declarations",
            headers=w.ops.headers,
            json={"vehicle_id": vehicle, "plan_code": code, **declaration},
        )
        assert declared.status_code == 201, declared.text
        decided = client.post(
            f"{API}/preventive-declarations/{declared.json()['service_declaration_id']}/decide",
            headers=approver.headers,
            json={"decision": "APPROVE"},
        )
        assert decided.status_code == 200, decided.text
    return vehicle


def test_evaluate_records_site_dues_once_and_lists_them(
    client: TestClient,
    api: Api,
    w: World,  # noqa: F811
) -> None:
    chief_s1 = api.user(w.t, "WORKSHOP_CHIEF", "SITE", "S1")
    chief_s2 = api.user(w.t, "WORKSHOP_CHIEF", "SITE", "S2")
    old_service = (datetime.now(UTC) - timedelta(days=40)).replace(microsecond=0).isoformat()
    overdue = _plan_with_declaration(
        client,
        w,
        chief_s1,
        site="S1",
        code="CAL-30",
        declaration={"knowledge": "KNOWN", "serviced_at": old_service},
    )
    initial = _plan_with_declaration(
        client, w, chief_s1, site="S1", code="INIT-30", declaration={"knowledge": "UNKNOWN"}
    )
    _plan_with_declaration(client, w, chief_s1, site="S1", code="NO-BASE", declaration=None)
    other_site = _plan_with_declaration(
        client, w, chief_s2, site="S2", code="S2-INIT", declaration={"knowledge": "UNKNOWN"}
    )
    site_s1 = str(w.t.sites["S1"])

    evaluate = f"{API}/preventive-dues/evaluate"
    first = client.post(evaluate, headers=chief_s1.headers, json={"site_id": site_s1})
    assert first.status_code == 200, first.text
    assert first.json() == {
        "plans_evaluated": 3,
        "due_now": 2,
        "created": 2,
        "already_recorded": 0,
        "upcoming": 0,
        "insufficient_data": 1,
    }
    replay = client.post(evaluate, headers=chief_s1.headers, json={"site_id": site_s1})
    assert replay.status_code == 200, replay.text
    assert (replay.json()["created"], replay.json()["already_recorded"]) == (0, 2)

    listed = client.get(f"{API}/preventive-dues", headers=chief_s1.headers, params={"status": "DUE"})
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["total"] == 2
    by_vehicle = {item["vehicle_id"]: item for item in body["items"]}
    assert set(by_vehicle) == {overdue, initial}
    assert by_vehicle[overdue]["trigger_kind"] == "DAYS" and by_vehicle[overdue]["plan_code"] == "CAL-30"
    assert by_vehicle[initial]["trigger_kind"] == "INITIAL" and by_vehicle[initial]["work_order_id"] is None

    # Planifier depuis la liste : l'échéance passe en SCHEDULED avec son OT.
    scheduled = client.post(
        f"{API}/preventive-dues/{by_vehicle[overdue]['maintenance_due_id']}/schedule",
        headers=chief_s1.headers,
    )
    assert scheduled.status_code == 200, scheduled.text
    after = client.get(
        f"{API}/preventive-dues", headers=chief_s1.headers, params={"status": "SCHEDULED"}
    ).json()
    assert [item["vehicle_id"] for item in after["items"]] == [overdue]

    # Portée société : l'autre site n'avait rien enregistré ; une évaluation société le couvre.
    tenant_wide = client.post(evaluate, headers=w.ops.headers, json={})
    assert tenant_wide.status_code == 200, tenant_wide.text
    assert tenant_wide.json()["created"] == 1
    everything = client.get(
        f"{API}/preventive-dues", headers=w.ops.headers, params={"page_size": 50, "open_only": True}
    ).json()
    assert {item["vehicle_id"] for item in everything["items"]} == {overdue, initial, other_site}

    engine = create_engine(get_settings().database_url())
    try:
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(w.t.tenant_id)})
            evaluations = conn.execute(
                text(
                    "SELECT count(*) FROM audit_event WHERE tenant_id = :t "
                    "AND action = 'maintenance.due.evaluate'"
                ),
                {"t": str(w.t.tenant_id)},
            ).scalar_one()
            orders = conn.execute(
                text("SELECT count(*) FROM work_order WHERE tenant_id = :t AND kind = 'PREVENTIVE'"),
                {"t": str(w.t.tenant_id)},
            ).scalar_one()
        assert evaluations == 3
        assert orders == 1  # seule la planification explicite a créé un OT
    finally:
        engine.dispose()


def test_evaluate_and_list_respect_permission_site_and_tenant(
    client: TestClient,
    api: Api,
    w: World,  # noqa: F811
) -> None:
    chief_s1 = api.user(w.t, "WORKSHOP_CHIEF", "SITE", "S1")
    chief_s2 = api.user(w.t, "WORKSHOP_CHIEF", "SITE", "S2")
    vehicle_s2 = _plan_with_declaration(
        client, w, chief_s2, site="S2", code="S2-ONLY", declaration={"knowledge": "UNKNOWN"}
    )
    evaluate = f"{API}/preventive-dues/evaluate"
    site_s2 = str(w.t.sites["S2"])

    assert client.post(evaluate, json={}).status_code == 401
    assert client.post(evaluate, headers=w.dispatcher.headers, json={}).status_code == 403
    assert client.post(evaluate, headers=chief_s1.headers, json={"site_id": site_s2}).status_code == 404
    # Sans site précisé, un chef du site S1 n'évalue que S1 : rien pour l'engin de S2.
    own = client.post(evaluate, headers=chief_s1.headers, json={})
    assert own.status_code == 200 and own.json()["plans_evaluated"] == 0
    assert (
        client.get(
            f"{API}/preventive-dues", headers=chief_s1.headers, params={"site_id": site_s2}
        ).status_code
        == 404
    )

    outsider = api.user(api.tenant(), "OPS_MANAGER")
    assert client.post(evaluate, headers=outsider.headers, json={"site_id": site_s2}).status_code == 404
    done = client.post(evaluate, headers=chief_s2.headers, json={"site_id": site_s2})
    assert done.status_code == 200 and done.json()["created"] == 1
    foreign = client.get(f"{API}/preventive-dues", headers=outsider.headers).json()
    assert foreign["total"] == 0
    mine = client.get(f"{API}/preventive-dues", headers=chief_s2.headers).json()
    assert [item["vehicle_id"] for item in mine["items"]] == [vehicle_s2]
