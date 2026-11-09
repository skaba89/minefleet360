"""Recette R4 — parcours panne transversal (docs/RECETTE.md §R4, vision produit §Processus).

Le parcours : mission en route → panne bloquante signalée par le dispatcher → mission suspendue par le
système, véhicule immobilisé → clôture impossible → réaffectation sur un engin de substitution (relais
tracé) → ordre de travail approuvé par le chef d'atelier, diagnostic et exécution par le mécanicien,
réservation puis sortie de pièces par le magasinier (le stock réservé n'est pas vendable ailleurs) →
contrôle qualité, remise en service, reprise de la mission → consolidation des coûts (pièces +
main-d'œuvre en GNF) et de l'immobilisation, avec chaque transition auditée.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from tests.conftest import API, Api
from tests.test_assignment import World, w  # noqa: F401  (fixture w)
from tests.test_dispatch import _assignment, _event, _mission, _refs
from tests.test_maintenance import _act, _report, _vehicle_status

PRIX_HEURE = "50000.00"  # GNF par heure de main-d'œuvre
PRIX_PIECE = "150000"  # GNF par pièce (réception valorisée, CMP)


def test_r4_panne_transversale_bout_en_bout(client: TestClient, w: World, api: Api) -> None:  # noqa: F811
    chef = api.user(w.t, "WORKSHOP_CHIEF")
    mecanicien = api.user(w.t, "MECHANIC", "SITE", "S1")
    magasinier = api.user(w.t, "STOREKEEPER", "SITE", "S1")
    finance = api.user(w.t, "FINANCE")

    # Mission en route sur l'engin de roulage, cycle de chargement commencé.
    refs = _refs(client, w)
    affectation = _assignment(client, w)
    engin = affectation["vehicle_id"]
    mission = _mission(client, w, affectation, refs).json()
    mid = mission["mission_id"]
    for evenement in ("DEPARTED", "ARRIVED_LOADING"):
        assert _event(client, w, mid, evenement).status_code == 200, evenement

    # Panne bloquante signalée par le dispatcher : immobilisation et suspension système (D-44).
    panne = _report(client, w, engin, immobilize=True, mission_id=mid, description="Freinage dégradé")
    assert panne.status_code == 201, panne.text
    ot = panne.json()
    oid = ot["work_order_id"]
    assert ot["status"] == "REQUESTED" and ot["reference"].startswith("OT-")
    assert _vehicle_status(client, w, engin) == "IMMOBILIZED"
    suspendue = client.get(f"{API}/missions/{mid}", headers=w.ops.headers).json()
    assert suspendue["status"] == "SUSPENDED" and suspendue["status_reason"] == "BREAKDOWN"
    assert suspendue["events"][-1]["source"] == "SYSTEM"

    # La mission suspendue ne peut pas être clôturée sans réaffectation ni reprise.
    cloture = _event(client, w, mid, "COMPLETED")
    assert (cloture.status_code, cloture.json()["code"]) == (409, "MISSION_STATE_INVALID")

    # Réaffectation sur un engin de substitution : cycle perdu, relais tracé (L2A-R-01).
    substitution = _assignment(client, w)
    reaffectee = _event(
        client, w, mid, "REASSIGNED", vehicle_assignment_id=substitution["vehicle_assignment_id"]
    )
    assert reaffectee.status_code == 200, reaffectee.text
    corps = reaffectee.json()
    assert corps["vehicle_id"] == substitution["vehicle_id"] and corps["status"] == "SUSPENDED"
    assert [r["status"] for r in corps["rotations"]] == ["ABORTED"]
    relais = client.get(
        f"{API}/audit-events",
        headers=w.t.admin.headers,
        params={"entity_id": mid, "action": "mission.reassigned"},
    ).json()["items"]
    assert relais[0]["before_data"]["driver_id"] == affectation["driver_id"]
    assert relais[0]["after_data"]["driver_id"] == substitution["driver_id"]

    # L'atelier prend le relais : approbation, affectation au mécanicien, diagnostic.
    pret = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    assert (
        _act(client, "decision", oid, chef.headers, action="APPROVE", expected_ready_at=pret).status_code
        == 200
    )
    assigne = _act(
        client, "decision", oid, chef.headers, action="ASSIGN", assigned_to=str(mecanicien.user_id)
    )
    assert assigne.status_code == 200 and assigne.json()["status"] == "ASSIGNED"
    demarre = _act(
        client, "progress", oid, mecanicien.headers, action="START", diagnosis="Plaquettes avant usées"
    )
    assert demarre.status_code == 200 and demarre.json()["status"] == "IN_PROGRESS"
    assert _vehicle_status(client, w, engin) == "IN_MAINTENANCE"

    # Pièces : réception valorisée, réservation pour l'OT posée par le magasinier.
    piece = client.post(
        f"{API}/parts",
        headers=magasinier.headers,
        json={"code": f"R4-P-{uuid.uuid4().hex[:6].upper()}", "name": "Plaquette de frein", "unit": "EACH"},
    ).json()
    magasin = client.post(
        f"{API}/part-stores",
        headers=magasinier.headers,
        json={
            "site_id": ot["site_id"],
            "code": f"R4-MAG-{uuid.uuid4().hex[:6].upper()}",
            "name": "Magasin atelier",
        },
    ).json()
    stock = {"spare_part_id": piece["spare_part_id"], "spare_part_store_id": magasin["spare_part_store_id"]}
    reception = client.post(
        f"{API}/part-movements/valued-receipts",
        headers=magasinier.headers,
        json={**stock, "quantity": "4", "unit_cost": PRIX_PIECE, "currency": "GNF", "reference": "R4-BL"},
    )
    assert reception.status_code == 201, reception.text
    reservation = client.post(
        f"{API}/part-reservations",
        headers=magasinier.headers,
        json={**stock, "work_order_id": oid, "quantity": "2", "reference": "R4-RES"},
    )
    assert reservation.status_code == 201 and reservation.json()["status"] == "ACTIVE"

    # Les pièces réservées ne sont pas vendables ailleurs : sortie directe au-delà du disponible refusée.
    emport = client.post(
        f"{API}/part-movements/valued-issues",
        headers=magasinier.headers,
        json={**stock, "quantity": "3", "reference": "R4-EMPORT"},
    )
    assert (emport.status_code, emport.json()["code"]) == (409, "CONFLICT")

    # Sortie réelle pour l'OT : la réservation est consommée, le solde reflète disponible et réservé.
    consommee = client.post(
        f"{API}/part-reservations/{reservation.json()['spare_part_reservation_id']}/consume",
        headers=magasinier.headers,
    )
    assert consommee.status_code == 200 and consommee.json()["status"] == "CONSUMED"
    solde = client.get(f"{API}/part-balances", headers=magasinier.headers).json()["items"][0]
    assert (solde["on_hand"], solde["reserved"]) == (2.0, 0.0)

    # Main-d'œuvre, compte rendu, contrôle qualité par le chef d'atelier (jamais par l'exécutant).
    travail = client.post(
        f"{API}/work-orders/{oid}/labour",
        headers=mecanicien.headers,
        json={"minutes": 120, "performed_on": date.today().isoformat(), "note": "Dépose et remplacement"},
    )
    assert travail.status_code == 201 and travail.json()["labour_minutes"] == 120
    soumis = _act(
        client, "progress", oid, mecanicien.headers, action="SUBMIT", work_done="Plaquettes remplacées, purge"
    )
    assert soumis.status_code == 200 and soumis.json()["status"] == "QUALITY_CHECK"
    assert _act(client, "decision", oid, mecanicien.headers, action="QC_PASS").status_code == 403
    clos = _act(client, "decision", oid, chef.headers, action="QC_PASS")
    assert clos.status_code == 200 and clos.json()["status"] == "CLOSED"
    assert _vehicle_status(client, w, engin) == "AVAILABLE"

    # La mission reprend sur l'engin de substitution, le cycle redémarre du départ.
    reprise = _event(client, w, mid, "RESUMED")
    assert reprise.status_code == 200 and reprise.json()["status"] == "ASSIGNED"
    assert _event(client, w, mid, "DEPARTED").status_code == 200

    # Coûts consolidés en GNF : pièces valorisées (2 × 150 000) et main-d'œuvre (120 min × 50 000 GNF/h).
    taux = client.post(
        f"{API}/costs/labour-rates",
        headers=finance.headers,
        json={"hourly_rate": PRIX_HEURE, "currency": "GNF", "valid_from": "2026-01-01"},
    )
    assert taux.status_code == 201, taux.text
    couts = client.get(f"{API}/costs/vehicles", headers=finance.headers).json()
    ligne = next(v for v in couts["vehicles"] if v["vehicle_id"] == engin)
    assert ligne["parts"]["amount"] == "300000.00" and ligne["parts"]["status"] == "COMPLETE"
    assert ligne["labour"]["amount"] == "100000.00" and ligne["labour"]["status"] == "COMPLETE"
    assert ligne["total"] == "400000.00" and ligne["total_status"] == "COMPLETE"
    assert ligne["currency"] == "GNF"

    # Immobilisation consolidée : au moins une panne, un temps d'immobilisation positif.
    fiabilite = client.get(f"{API}/maintenance/reliability", headers=chef.headers).json()
    immobilisation = next(v for v in fiabilite["vehicles"] if v["vehicle_id"] == engin)
    assert immobilisation["failures"] >= 1 and Decimal(immobilisation["downtime_hours"]) > 0

    # Chaque transition est auditée : signalement, décisions d'atelier, exécution, contrôle.
    journal = client.get(f"{API}/audit-events", headers=w.t.admin.headers, params={"entity_id": oid}).json()
    assert {e["action"] for e in journal["items"]} >= {
        "work_order.request",
        "work_order.approve",
        "work_order.assign",
        "work_order.start",
        "work_order.submit",
        "work_order.qc_pass",
    }
