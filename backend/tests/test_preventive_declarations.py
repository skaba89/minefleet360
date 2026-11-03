"""Dernier entretien connu, point de départ des plans préventifs : déclaration, décision, état calculé.

Couvre la règle des compteurs (jalon validé + hausses des relevés depuis, baisse => non fiable), l'entretien
initial quand le dernier entretien est inconnu, la séparation des tâches, et l'isolation société / site.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.core.config import get_settings
from app.maintenance.preventive import CurrentMeters, ServiceBaseline, ServiceRule, evaluate_due
from app.maintenance.preventive_due_candidates import due_candidates
from app.maintenance.preventive_meters_since import rise_since
from tests.conftest import API, Api
from tests.test_assignment import World, _vehicle, w  # noqa: F401

D = Decimal


def test_rise_since_adds_rises_between_raw_readings() -> None:
    # Cumul déclaré 120 000 alors que le compteur brut affichait 100 000 : seules les hausses brutes comptent.
    assert rise_since(D("120000"), D("100000"), [D("100200"), D("100700")]) == D("120700")
    # Sans relevé antérieur, le premier relevé est comparé au cumul déclaré.
    assert rise_since(D("5000"), None, [D("5100"), D("5100"), D("5400")]) == D("5400")
    assert rise_since(D("5000"), None, []) == D("5000")


def test_rise_since_refuses_any_decrease() -> None:
    assert rise_since(D("5000"), None, [D("5100"), D("40")]) is None
    assert rise_since(D("5000"), D("8000"), [D("7999")]) is None


def test_unknown_last_service_makes_initial_service_due() -> None:
    day = datetime(2026, 11, 1, tzinfo=UTC).date()
    baseline = ServiceBaseline(initial_due_on=day, initial_key="decl-1", source="INITIAL_REQUIRED")
    rule = ServiceRule(days_interval=90)
    result = evaluate_due(rule, baseline, CurrentMeters(), day)
    assert result.status == "DUE" and result.due_triggers == ("INITIAL",) and result.due_on == day
    (candidate,) = due_candidates(rule, baseline, CurrentMeters(), day)
    assert (candidate.trigger_kind, candidate.trigger_key, candidate.due_on) == (
        "INITIAL",
        "INITIAL:decl-1",
        day,
    )


def _plan(client: TestClient, w: World, vehicle: str, code: str, **intervals: int) -> None:  # noqa: F811
    created = client.post(
        f"{API}/preventive-plans",
        headers=w.ops.headers,
        json={"vehicle_id": vehicle, "code": code, **intervals},
    )
    assert created.status_code == 201, created.text


def _status(client: TestClient, w: World, vehicle: str, code: str) -> dict:  # type: ignore[type-arg]  # noqa: F811
    resp = client.get(f"{API}/vehicles/{vehicle}/preventive-status", headers=w.ops.headers)
    assert resp.status_code == 200, resp.text
    return next(item for item in resp.json() if item["code"] == code)


def _reading(client: TestClient, w: World, vehicle: str, value: str) -> None:  # noqa: F811
    resp = client.post(
        f"{API}/vehicles/{vehicle}/meter-readings",
        headers=w.ops.headers,
        json={"meter_kind": "ODOMETER_KM", "value": value},
    )
    assert resp.status_code == 201, resp.text


def test_declared_last_service_starts_the_plan_after_four_eyes_approval(
    client: TestClient,
    api: Api,
    w: World,  # noqa: F811
) -> None:
    vehicle = _vehicle(client, w)
    _plan(client, w, vehicle, "VIDANGE", km_interval=5000, days_interval=180)
    before = _status(client, w, vehicle, "VIDANGE")
    assert before["status"] == "INSUFFICIENT_DATA" and before["baseline_source"] == "NONE"

    serviced = (datetime.now(UTC) - timedelta(days=30)).replace(microsecond=0)
    declared = client.post(
        f"{API}/preventive-declarations",
        headers=w.ops.headers,
        json={
            "vehicle_id": vehicle,
            "plan_code": "VIDANGE",
            "knowledge": "KNOWN",
            "serviced_at": serviced.isoformat(),
            "odometer_km": "10000",
        },
    )
    assert declared.status_code == 201, declared.text
    declaration = declared.json()
    assert declaration["status"] == "PENDING"
    # En attente : rien ne change encore.
    assert _status(client, w, vehicle, "VIDANGE")["baseline_source"] == "NONE"

    # Une seule déclaration en attente par engin et plan.
    again = client.post(
        f"{API}/preventive-declarations",
        headers=w.ops.headers,
        json={"vehicle_id": vehicle, "plan_code": "VIDANGE", "knowledge": "UNKNOWN"},
    )
    assert again.status_code == 409 and again.json()["code"] == "PREVENTIVE_DECLARATION_PENDING"

    decide = f"{API}/preventive-declarations/{declaration['service_declaration_id']}/decide"
    self_approval = client.post(decide, headers=w.ops.headers, json={"decision": "APPROVE"})
    assert self_approval.status_code == 422, self_approval.text
    assert self_approval.json()["code"] == "PREVENTIVE_SELF_APPROVAL_FORBIDDEN"

    chief = api.user(w.t, "WORKSHOP_CHIEF", "SITE", "S1")
    approved = client.post(decide, headers=chief.headers, json={"decision": "APPROVE", "note": "carnet vu"})
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED" and approved.json()["decided_by"] == str(chief.user_id)
    replay = client.post(decide, headers=chief.headers, json={"decision": "REJECT", "note": "trop tard"})
    assert replay.status_code == 409 or replay.status_code == 422, replay.text

    # Un relevé après le jalon (la vraisemblance D-43 interdit d'en enchaîner de gros en quelques secondes ;
    # l'enchaînement des hausses est couvert par test_rise_since_*).
    _reading(client, w, vehicle, "10300")
    state = _status(client, w, vehicle, "VIDANGE")
    assert state["baseline_source"] == "DECLARATION"
    assert state["serviced_on"] == serviced.date().isoformat()
    assert D(state["current_km"]) == D("10300") and D(state["remaining_km"]) == D("4700")
    assert state["status"] == "UPCOMING" and state["km_reliable"] is True
    assert state["due_on"] == (serviced.date() + timedelta(days=180)).isoformat()

    # Compteur remis à zéro : non fiable jusqu'à un nouveau jalon validé, jamais « rien à faire ».
    reset = client.post(
        f"{API}/vehicles/{vehicle}/meter-resets",
        headers=w.ops.headers,
        json={"meter_kind": "ODOMETER_KM", "value": "5", "reset_reason": "METER_REPLACED"},
    )
    assert reset.status_code == 201, reset.text
    after_reset = _status(client, w, vehicle, "VIDANGE")
    assert after_reset["km_reliable"] is False and after_reset["current_km"] is None
    assert "KM" in after_reset["unknown_triggers"]

    history = client.get(f"{API}/vehicles/{vehicle}/preventive-declarations", headers=w.dispatcher.headers)
    assert history.status_code == 200 and [d["status"] for d in history.json()] == ["APPROVED"]


def test_unknown_last_service_gives_an_initial_due_storable_in_db(
    client: TestClient,
    api: Api,
    w: World,  # noqa: F811
) -> None:
    vehicle = _vehicle(client, w)
    _plan(client, w, vehicle, "GRAISSAGE", days_interval=30)
    declared = client.post(
        f"{API}/preventive-declarations",
        headers=w.ops.headers,
        json={
            "vehicle_id": vehicle,
            "plan_code": "GRAISSAGE",
            "knowledge": "UNKNOWN",
            "note": "engin repris",
        },
    ).json()
    chief = api.user(w.t, "WORKSHOP_CHIEF", "SITE", "S1")
    rejected = client.post(
        f"{API}/preventive-declarations/{declared['service_declaration_id']}/decide",
        headers=chief.headers,
        json={"decision": "REJECT"},
    )
    assert rejected.status_code == 422, rejected.text  # motif obligatoire
    ok = client.post(
        f"{API}/preventive-declarations/{declared['service_declaration_id']}/decide",
        headers=chief.headers,
        json={"decision": "APPROVE"},
    )
    assert ok.status_code == 200, ok.text
    state = _status(client, w, vehicle, "GRAISSAGE")
    assert state["status"] == "DUE" and state["due_triggers"] == ["INITIAL"]
    assert state["baseline_source"] == "INITIAL_REQUIRED"

    # La base accepte une échéance INITIAL (date, pas de compteur) ; la clé reste unique par plan.
    plan_id = client.get(f"{API}/vehicles/{vehicle}/preventive-plans", headers=w.ops.headers).json()[0][
        "maintenance_plan_id"
    ]
    engine = create_engine(get_settings().database_url())
    try:
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(w.t.tenant_id)})
            conn.execute(
                text(
                    "INSERT INTO maintenance_due (tenant_id, maintenance_plan_id, vehicle_id, trigger_kind, "
                    "trigger_key, due_on) VALUES (:t, :p, :v, 'INITIAL', :k, current_date)"
                ),
                {
                    "t": str(w.t.tenant_id),
                    "p": plan_id,
                    "v": vehicle,
                    "k": "INITIAL:" + declared["service_declaration_id"],
                },
            )
    finally:
        engine.dispose()


def test_declaration_rejects_inconsistent_or_unknown_inputs(client: TestClient, w: World) -> None:  # noqa: F811
    vehicle = _vehicle(client, w)
    _plan(client, w, vehicle, "PLAN-A", days_interval=30)
    url = f"{API}/preventive-declarations"
    future = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    cases = [
        ({"vehicle_id": vehicle, "plan_code": "PLAN-A", "knowledge": "KNOWN"}, 422),  # date manquante
        ({"vehicle_id": vehicle, "plan_code": "PLAN-A", "knowledge": "UNKNOWN", "odometer_km": "1"}, 422),
        ({"vehicle_id": vehicle, "plan_code": "PLAN-A", "knowledge": "KNOWN", "serviced_at": future}, 422),
        ({"vehicle_id": vehicle, "plan_code": "AUTRE", "knowledge": "UNKNOWN"}, 422),  # aucun plan actif
        ({"vehicle_id": str(uuid.uuid4()), "plan_code": "PLAN-A", "knowledge": "UNKNOWN"}, 404),
    ]
    for body, expected in cases:
        resp = client.post(url, headers=w.ops.headers, json=body)
        assert resp.status_code == expected, (body, resp.text)


def test_declarations_are_isolated_by_tenant_site_and_permission(
    client: TestClient,
    api: Api,
    w: World,  # noqa: F811
) -> None:
    vehicle_s2 = _vehicle(client, w, site="S2")
    _plan(client, w, vehicle_s2, "PLAN-S2", days_interval=30)
    declared = client.post(
        f"{API}/preventive-declarations",
        headers=w.ops.headers,
        json={"vehicle_id": vehicle_s2, "plan_code": "PLAN-S2", "knowledge": "UNKNOWN"},
    ).json()
    decide = f"{API}/preventive-declarations/{declared['service_declaration_id']}/decide"

    # Chef d'atelier d'un autre site : l'engin et la déclaration n'existent pas pour lui.
    chief_s1 = api.user(w.t, "WORKSHOP_CHIEF", "SITE", "S1")
    assert client.post(decide, headers=chief_s1.headers, json={"decision": "APPROVE"}).status_code == 404
    assert (
        client.get(f"{API}/vehicles/{vehicle_s2}/preventive-status", headers=chief_s1.headers).status_code
        == 404
    )
    # Lecteur sans droit de gestion : refus explicite.
    assert (
        client.post(
            f"{API}/preventive-declarations",
            headers=w.dispatcher.headers,
            json={"vehicle_id": vehicle_s2, "plan_code": "PLAN-S2", "knowledge": "UNKNOWN"},
        ).status_code
        == 403
    )
    # Autre société : ni lecture ni décision.
    other = api.tenant()
    outsider = api.user(other, "OPS_MANAGER")
    assert client.post(decide, headers=outsider.headers, json={"decision": "APPROVE"}).status_code == 404
    for path in ("preventive-declarations", "preventive-status"):
        assert client.get(f"{API}/vehicles/{vehicle_s2}/{path}", headers=outsider.headers).status_code == 404
    # La déclaration est restée en attente.
    history = client.get(f"{API}/vehicles/{vehicle_s2}/preventive-declarations", headers=w.ops.headers).json()
    assert history[0]["status"] == "PENDING"
