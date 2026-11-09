"""Recette R5 — maintenance préventive (docs/RECETTE.md §R5).

Le parcours : plan préventif kilométrique posé par l'OPS_MANAGER → dernier entretien déclaré puis
approuvé par le chef d'atelier (double décision) → relevés de compteur sous puis au-delà du seuil →
évaluation des échéances du site (idempotente : le même relevé rejoué ne double rien) → planification
de l'OT préventif (rejouable, même OT) → exécution atelier complète (approbation, affectation,
diagnostic, main-d'œuvre, contrôle qualité) → finalisation de l'échéance avec cumul figé depuis les
relevés → suspension d'un second plan et révision du premier sous concurrence optimiste, chaque
écriture auditée.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import API, Api
from tests.test_assignment import World, _vehicle, w  # noqa: F401  (fixture w)
from tests.test_maintenance import _act

D = Decimal


def _statut(client: TestClient, w: World, vehicle: str, code: str) -> dict[str, Any]:  # noqa: F811
    resp = client.get(f"{API}/vehicles/{vehicle}/preventive-status", headers=w.ops.headers)
    assert resp.status_code == 200, resp.text
    return next(item for item in resp.json() if item["code"] == code)


def _releve(client: TestClient, w: World, vehicle: str, value: str, *, read_at: datetime) -> Any:  # noqa: F811
    resp = client.post(
        f"{API}/vehicles/{vehicle}/meter-readings",
        headers=w.ops.headers,
        json={"meter_kind": "ODOMETER_KM", "value": value, "read_at": read_at.isoformat()},
    )
    assert resp.status_code == 201, resp.text
    return resp


def test_r5_maintenance_preventive_bout_en_bout(
    client: TestClient,
    w: World,  # noqa: F811  (fixture w)
    api: Api,
) -> None:
    chef = api.user(w.t, "WORKSHOP_CHIEF", "SITE", "S1")
    mecanicien = api.user(w.t, "MECHANIC", "SITE", "S1")
    site_s1 = str(w.t.sites["S1"])
    evaluate = f"{API}/preventive-dues/evaluate"

    # Référentiel : un engin de roulage et son plan préventif kilométrique posé par l'OPS_MANAGER.
    engin = _vehicle(client, w)
    plan = client.post(
        f"{API}/preventive-plans",
        headers=w.ops.headers,
        json={"vehicle_id": engin, "code": "R5-VIDANGE", "km_interval": "5000", "days_interval": 365},
    )
    assert plan.status_code == 201, plan.text
    assert plan.json()["version"] == 1

    # Sans point de départ connu, le plan est en données insuffisantes.
    avant = _statut(client, w, engin, "R5-VIDANGE")
    assert avant["status"] == "INSUFFICIENT_DATA" and avant["baseline_source"] == "NONE"

    # Dernier entretien déclaré par l'OPS_MANAGER, approuvé par le chef d'atelier (double décision).
    serviced = (datetime.now(UTC) - timedelta(days=30)).replace(microsecond=0)
    declaree = client.post(
        f"{API}/preventive-declarations",
        headers=w.ops.headers,
        json={
            "vehicle_id": engin,
            "plan_code": "R5-VIDANGE",
            "knowledge": "KNOWN",
            "serviced_at": serviced.isoformat(),
            "odometer_km": "10000",
        },
    )
    assert declaree.status_code == 201, declaree.text
    decision = f"{API}/preventive-declarations/{declaree.json()['service_declaration_id']}/decide"
    auto = client.post(decision, headers=w.ops.headers, json={"decision": "APPROVE"})
    assert (auto.status_code, auto.json()["code"]) == (422, "PREVENTIVE_SELF_APPROVAL_FORBIDDEN")
    approuvee = client.post(decision, headers=chef.headers, json={"decision": "APPROVE", "note": "carnet vu"})
    assert approuvee.status_code == 200, approuvee.text
    assert approuvee.json()["status"] == "APPROVED" and approuvee.json()["decided_by"] == str(chef.user_id)
    assert _statut(client, w, engin, "R5-VIDANGE")["baseline_source"] == "DECLARATION"

    # Relevé sous le seuil (10 000 + 5 000), daté dans le passé proche : la progression reste
    # physiquement plausible (RM-103, 60 km/h max sur la catégorie) et l'échéance est à venir.
    _releve(client, w, engin, "12000", read_at=datetime.now(UTC) - timedelta(hours=6))
    premiere = client.post(evaluate, headers=chef.headers, json={"site_id": site_s1})
    assert premiere.status_code == 200, premiere.text
    assert premiere.json() == {
        "plans_evaluated": 1,
        "due_now": 0,
        "created": 0,
        "already_recorded": 0,
        "upcoming": 1,
        "insufficient_data": 0,
    }

    # Au-delà du seuil : 3 100 km sur 6 heures, progression plausible ; l'évaluation enregistre
    # l'échéance kilométrique à 15 000 km.
    _releve(client, w, engin, "15100", read_at=datetime.now(UTC))
    seconde = client.post(evaluate, headers=chef.headers, json={"site_id": site_s1})
    assert seconde.status_code == 200, seconde.text
    assert seconde.json()["created"] == 1
    dues = client.get(
        f"{API}/preventive-dues", headers=chef.headers, params={"status": "DUE", "site_id": site_s1}
    ).json()
    assert dues["total"] == 1
    (due,) = dues["items"]
    assert (due["vehicle_id"], due["trigger_kind"], due["plan_code"]) == (engin, "KM", "R5-VIDANGE")
    assert D(due["due_meter"]) == D("15000") and due["work_order_id"] is None

    # Idempotence : le même relevé rejoué ne pousse pas le cumul (hausse nulle) et ne double pas
    # l'échéance ; rejouer l'évaluation ne crée rien de plus.
    _releve(client, w, engin, "15100", read_at=datetime.now(UTC))
    rejeu = client.post(evaluate, headers=chef.headers, json={"site_id": site_s1})
    assert rejeu.status_code == 200, rejeu.text
    assert (rejeu.json()["created"], rejeu.json()["already_recorded"]) == (0, 1)
    toujours = client.get(
        f"{API}/preventive-dues", headers=chef.headers, params={"status": "DUE", "site_id": site_s1}
    ).json()
    assert toujours["total"] == 1

    # Planification : l'atelier ouvre l'OT préventif ; rejouer retourne le même OT (une échéance,
    # au plus un OT).
    planifie = client.post(
        f"{API}/preventive-dues/{due['maintenance_due_id']}/schedule", headers=chef.headers
    )
    assert planifie.status_code == 200, planifie.text
    oid = planifie.json()["work_order_id"]
    rejoue = client.post(f"{API}/preventive-dues/{due['maintenance_due_id']}/schedule", headers=chef.headers)
    assert rejoue.status_code == 200 and rejoue.json()["work_order_id"] == oid
    ordre = client.get(f"{API}/work-orders/{oid}", headers=w.ops.headers).json()
    assert ordre["kind"] == "PREVENTIVE" and ordre["status"] == "REQUESTED"
    planifiee = client.get(
        f"{API}/preventive-dues", headers=chef.headers, params={"status": "SCHEDULED", "site_id": site_s1}
    ).json()
    assert [d["maintenance_due_id"] for d in planifiee["items"]] == [due["maintenance_due_id"]]

    # Exécution atelier : approbation, affectation, diagnostic, main-d'œuvre, contrôle qualité.
    pret = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    assert (
        _act(client, "decision", oid, chef.headers, action="APPROVE", expected_ready_at=pret).status_code
        == 200
    )
    affecte = _act(
        client, "decision", oid, chef.headers, action="ASSIGN", assigned_to=str(mecanicien.user_id)
    )
    assert affecte.status_code == 200 and affecte.json()["status"] == "ASSIGNED"
    demarre = _act(
        client, "progress", oid, mecanicien.headers, action="START", diagnosis="Vidange et filtres"
    )
    assert demarre.status_code == 200 and demarre.json()["status"] == "IN_PROGRESS"
    travail = client.post(
        f"{API}/work-orders/{oid}/labour",
        headers=mecanicien.headers,
        json={"minutes": 90, "performed_on": datetime.now(UTC).date().isoformat(), "note": "Vidange moteur"},
    )
    assert travail.status_code == 201 and travail.json()["labour_minutes"] == 90
    soumis = _act(client, "progress", oid, mecanicien.headers, action="SUBMIT", work_done="Vidange faite")
    assert soumis.status_code == 200 and soumis.json()["status"] == "QUALITY_CHECK"
    clos = _act(client, "decision", oid, chef.headers, action="QC_PASS")
    assert clos.status_code == 200 and clos.json()["status"] == "CLOSED"

    # Finalisation : cumul de clôture calculé depuis le jalon validé et les relevés (hausse nette).
    contexte = client.get(f"{API}/work-orders/{oid}/preventive-completion", headers=w.ops.headers)
    assert contexte.status_code == 200, contexte.text
    (compteur,) = contexte.json()["meters"]
    assert compteur["meter_kind"] == "ODOMETER_KM" and D(compteur["computed_total"]) == D("15100")
    finalise = client.post(f"{API}/work-orders/{oid}/complete-preventive", headers=w.ops.headers, json={})
    assert finalise.status_code == 200 and finalise.json()["changed"] is True
    terminee = client.get(
        f"{API}/preventive-dues", headers=chef.headers, params={"status": "COMPLETED", "site_id": site_s1}
    ).json()
    assert [d["maintenance_due_id"] for d in terminee["items"]] == [due["maintenance_due_id"]]
    rejoue_final = client.post(f"{API}/work-orders/{oid}/complete-preventive", headers=w.ops.headers, json={})
    assert rejoue_final.status_code == 200 and rejoue_final.json()["changed"] is False

    # Le cycle repart du cumul figé à la clôture (jalon WORK_ORDER) : prochaine échéance à 20 100 km.
    statut = _statut(client, w, engin, "R5-VIDANGE")
    assert statut["baseline_source"] == "WORK_ORDER" and D(statut["current_km"]) == D("15100")
    assert statut["status"] == "UPCOMING"

    # Suspension d'un second plan (raison tracée), puis révision du premier sous concurrence
    # optimiste : mauvaise version refusée, la révision crée une nouvelle version immuable.
    graissage = client.post(
        f"{API}/preventive-plans",
        headers=w.ops.headers,
        json={"vehicle_id": engin, "code": "R5-GRAISSAGE", "hours_interval": "250"},
    )
    assert graissage.status_code == 201, graissage.text
    suspendu = client.post(
        f"{API}/preventive-plans/{graissage.json()['maintenance_plan_id']}/suspend",
        headers={**w.ops.headers, "If-Match": str(graissage.json()["row_version"])},
        json={"reason": "Engin consigné pour expertise"},
    )
    assert suspendu.status_code == 200, suspendu.text
    assert (
        suspendu.json()["active"] is False
        and suspendu.json()["suspension_reason"] == "Engin consigné pour expertise"
    )

    plans = client.get(f"{API}/vehicles/{engin}/preventive-plans", headers=w.ops.headers).json()
    actuel = next(p for p in plans if p["active"] and p["code"] == "R5-VIDANGE")
    revise_url = f"{API}/preventive-plans/{actuel['maintenance_plan_id']}/revise"
    corps = {"vehicle_id": engin, "code": "R5-VIDANGE", "km_interval": "4000", "days_interval": 365}
    conflit = client.post(
        revise_url, headers={**w.ops.headers, "If-Match": str(actuel["row_version"] - 1)}, json=corps
    )
    assert (conflit.status_code, conflit.json()["code"]) == (409, "VERSION_CONFLICT")
    revise = client.post(
        revise_url, headers={**w.ops.headers, "If-Match": str(actuel["row_version"])}, json=corps
    )
    assert revise.status_code == 200, revise.text
    nouveau = revise.json()
    assert nouveau["version"] == actuel["version"] + 1 and D(nouveau["km_interval"]) == D("4000")
    assert nouveau["maintenance_plan_id"] != actuel["maintenance_plan_id"]
    plans = client.get(f"{API}/vehicles/{engin}/preventive-plans", headers=w.ops.headers).json()
    assert [p["code"] for p in plans if p["active"]] == ["R5-VIDANGE"]
    assert D(next(p for p in plans if p["active"])["km_interval"]) == D("4000")

    # Chaque écriture est auditée : plan (création, suspension, révision), échéances, ordre de travail.
    admin = w.t.admin.headers
    journal_graissage = client.get(
        f"{API}/audit-events", headers=admin, params={"entity_id": graissage.json()["maintenance_plan_id"]}
    ).json()["items"]
    assert {e["action"] for e in journal_graissage} >= {
        "maintenance.plan.create",
        "maintenance.plan.suspend",
    }
    journal_revision = client.get(
        f"{API}/audit-events", headers=admin, params={"entity_id": nouveau["maintenance_plan_id"]}
    ).json()["items"]
    assert {e["action"] for e in journal_revision} >= {"maintenance.plan.revise"}
    journal_due = client.get(
        f"{API}/audit-events", headers=admin, params={"entity_id": due["maintenance_due_id"]}
    ).json()["items"]
    assert {e["action"] for e in journal_due} >= {"maintenance.due.create"}
    evaluations = client.get(
        f"{API}/audit-events", headers=admin, params={"action": "maintenance.due.evaluate"}
    ).json()["items"]
    assert len(evaluations) >= 3
    journal_ot = client.get(f"{API}/audit-events", headers=admin, params={"entity_id": oid}).json()["items"]
    assert {e["action"] for e in journal_ot} >= {
        "work_order.request",
        "work_order.approve",
        "work_order.assign",
        "work_order.start",
        "work_order.submit",
        "work_order.qc_pass",
    }
