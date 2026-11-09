"""Recette R6 — carburant bout en bout (docs/RECETTE.md §R6).

Le parcours : cuve DIESEL avec seuil bas posée par le responsable carburant → fournisseur puis achat
de 10 000 L double-validé par l'OPS_MANAGER (le créateur ne décide pas) avec livraison partielle
(4 000 L puis 6 000 L) → réception directe complémentaire → alerte de seuil déclenchée, acquittée
puis résolue automatiquement quand le stock repasse au-dessus → réservations : une sortie en attente
réserve le stock (le disponible baisse, l'excès est refusé), le rejet libère sans trace dans le
journal → ravitaillement plein complet validé en double décision (auto-validation interdite) →
pompe branchée sur la cuve, relevés de compteur monotones et idempotents → rapprochements pompe
(écart compteur/sorties approuvées au-delà de la tolérance) → dossier d'anomalie qualifié puis
acquitté, justifié et clôturé par un tiers → inventaire de cuve corrigeant le stock → consommation
plein-à-plein du véhicule → dashboard ventilant distribué / reçu / écart d'inventaire / anomalies /
alertes, avec période inversée ou trop longue refusée. Chaque écriture clé est auditée.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from tests.conftest import API, Api, TenantFixture

D = Decimal


def _vehicule_conducteur(client: TestClient, api: Api, tenant: TenantFixture) -> tuple[str, str, str]:
    """Camion DIESEL du site MINE avec conducteur habilité et affecté (compteur connu)."""
    admin = tenant.admin.headers
    hr = api.user(tenant, "HR")
    ops = api.user(tenant, "OPS_MANAGER")
    category = next(
        c
        for c in client.get(f"{API}/vehicle-categories", headers=admin).json()
        if c["code"] == "RIGID_DUMP_TRUCK"
    )
    vehicle = client.post(
        f"{API}/vehicles",
        headers=admin,
        json={
            "site_id": str(tenant.sites["MINE"]),
            "vehicle_category_id": category["vehicle_category_id"],
            "fleet_number": "R6-CAMION-01",
            "fuel_type": "DIESEL",
        },
    )
    assert vehicle.status_code == 201, vehicle.text
    driver = client.post(
        f"{API}/drivers",
        headers=hr.headers,
        json={
            "site_id": str(tenant.sites["MINE"]),
            "employee_number": "R6-COND-01",
            "last_name": "Kankan",
            "first_name": "Mamadou",
        },
    )
    assert driver.status_code == 201, driver.text
    driver_id = driver.json()["driver_id"]
    license_code = (category.get("required_license_categories") or ["C"])[0]
    permis = client.post(
        f"{API}/drivers/{driver_id}/licenses",
        headers=hr.headers,
        json={
            "license_number": "R6-PERMIS-01",
            "category_code": license_code,
            "issue_date": "2020-01-01",
            "expiry_date": "2035-01-01",
        },
    )
    assert permis.status_code == 201, permis.text
    habilitation = client.post(
        f"{API}/drivers/{driver_id}/qualifications",
        headers=hr.headers,
        json={
            "qualification_type": "DRIVING_AUTHORIZATION",
            "vehicle_category_id": category["vehicle_category_id"],
            "valid_from": "2020-01-01",
        },
    )
    assert habilitation.status_code == 201, habilitation.text
    affectation = client.post(
        f"{API}/vehicle-assignments",
        headers=ops.headers,
        json={
            "vehicle_id": vehicle.json()["vehicle_id"],
            "driver_id": driver_id,
            "valid_from": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
        },
    )
    assert affectation.status_code == 201, affectation.text
    meter_kind = (
        "ODOMETER" if category["has_odometer"] else "HOUR_METER" if category["has_hour_meter"] else None
    )
    assert meter_kind is not None, "la catégorie de recette doit avoir un compteur"
    return vehicle.json()["vehicle_id"], driver_id, meter_kind


def _cuve_etat(client: TestClient, headers: dict[str, str], tank_id: str) -> dict[str, object]:
    listing = client.get(f"{API}/fuel/tanks", headers=headers)
    assert listing.status_code == 200, listing.text
    return next(item for item in listing.json()["items"] if item["fuel_tank_id"] == tank_id)


def test_r6_carburant_bout_en_bout(client: TestClient, api: Api) -> None:
    t = api.tenant(sites=("MINE",))
    carburant = api.user(t, "FUEL_MANAGER", "SITE", "MINE")
    ops = api.user(t, "OPS_MANAGER")
    admin = t.admin.headers
    site = str(t.sites["MINE"])
    camion, conducteur, meter_kind = _vehicule_conducteur(client, api, t)
    now = datetime.now(UTC).replace(microsecond=0)

    # --- Cuves et seuils ------------------------------------------------------
    # La cuve démarre vide et sans seuil : un seuil posé sur une cuve vide déclencherait
    # immédiatement une alerte ; le seuil est posé plus bas, quand le stock le justifie.
    cuve = client.post(
        f"{API}/fuel/tanks",
        headers=carburant.headers,
        json={
            "site_id": site,
            "code": "CUVE-GO-1",
            "fuel_type": "DIESEL",
            "capacity_liters": "20000.000",
        },
    )
    assert cuve.status_code == 201, cuve.text
    tank_id = cuve.json()["fuel_tank_id"]
    assert cuve.json()["code"] == "CUVE-GO-1" and cuve.json()["fuel_type"] == "DIESEL"
    assert D(cuve.json()["capacity_liters"]) == D("20000")
    assert cuve.json()["low_stock"] is False
    assert D(cuve.json()["balance_liters"]) == D("0")

    # Un seuil au-dessus de la capacité est refusé.
    seuil_ko = client.post(
        f"{API}/fuel/tanks/{tank_id}/threshold",
        headers=carburant.headers,
        json={"low_stock_threshold_liters": "21000.000"},
    )
    assert (seuil_ko.status_code, seuil_ko.json()["code"]) == (422, "VALIDATION_ERROR")

    # --- Fournisseurs et achats (livraison partielle) -------------------------
    fournisseur = client.post(
        f"{API}/fuel/suppliers",
        headers=carburant.headers,
        json={"site_id": site, "code": "FOURN-GO", "name": "Pétrolier Kankan SARL"},
    )
    assert fournisseur.status_code == 201, fournisseur.text
    fournisseur_id = fournisseur.json()["fuel_supplier_id"]

    achat = client.post(
        f"{API}/fuel/purchases",
        headers=carburant.headers,
        json={
            "fuel_supplier_id": fournisseur_id,
            "fuel_tank_id": tank_id,
            "reference": "BC-R6-001",
            "quantity_liters": "10000.000",
            "unit_price": "12000.00",
            "currency": "GNF",
            "ordered_at": (now - timedelta(minutes=90)).isoformat(),
        },
    )
    assert achat.status_code == 201, achat.text
    achat_id = achat.json()["fuel_purchase_order_id"]
    assert achat.json()["status"] == "PENDING_APPROVAL"
    assert D(achat.json()["received_liters"]) == D("0")
    assert D(achat.json()["remaining_liters"]) == D("10000")
    assert D(achat.json()["total_amount"]) == D("120000000")

    # Réception avant décision : refusée (l'achat n'est pas approuvé).
    avant_decision = client.post(
        f"{API}/fuel/purchases/{achat_id}/receipts",
        headers=carburant.headers,
        json={
            "liters": "4000.000",
            "delivery_reference": "BL-R6-001",
            "occurred_at": (now - timedelta(minutes=60)).isoformat(),
        },
    )
    assert avant_decision.status_code == 409, avant_decision.text

    # Double validation : le créateur (FUEL_MANAGER) n'a pas le droit de décider.
    par_createur = client.post(
        f"{API}/fuel/purchases/{achat_id}/decision",
        headers=carburant.headers,
        json={"decision": "APPROVED"},
    )
    assert (par_createur.status_code, par_createur.json()["code"]) == (403, "PERMISSION_DENIED")
    decide = client.post(
        f"{API}/fuel/purchases/{achat_id}/decision",
        headers=ops.headers,
        json={"decision": "APPROVED"},
    )
    assert decide.status_code == 200, decide.text
    assert decide.json()["status"] == "APPROVED" and decide.json()["decided_by"] == str(ops.user_id)

    # Un créateur habilité ne peut pas non plus décider sa propre commande.
    achat2 = client.post(
        f"{API}/fuel/purchases",
        headers=admin,
        json={
            "fuel_supplier_id": fournisseur_id,
            "fuel_tank_id": tank_id,
            "reference": "BC-R6-002",
            "quantity_liters": "500.000",
            "unit_price": "11500.00",
            "currency": "GNF",
            "ordered_at": (now - timedelta(minutes=80)).isoformat(),
        },
    )
    assert achat2.status_code == 201, achat2.text
    auto_decision = client.post(
        f"{API}/fuel/purchases/{achat2.json()['fuel_purchase_order_id']}/decision",
        headers=admin,
        json={"decision": "APPROVED"},
    )
    assert (auto_decision.status_code, auto_decision.json()["code"]) == (409, "CONFLICT")

    # Livraison partielle : 4 000 L sur les 10 000 commandés.
    partielle = client.post(
        f"{API}/fuel/purchases/{achat_id}/receipts",
        headers=carburant.headers,
        json={
            "liters": "4000.000",
            "delivery_reference": "BL-R6-001",
            "occurred_at": (now - timedelta(minutes=60)).isoformat(),
        },
    )
    assert partielle.status_code == 201, partielle.text
    en_cours = client.get(
        f"{API}/fuel/purchases", headers=admin, params={"status": "PARTIALLY_RECEIVED"}
    ).json()
    assert en_cours["total"] == 1
    (partielle_po,) = en_cours["items"]
    assert partielle_po["fuel_purchase_order_id"] == achat_id
    assert D(partielle_po["received_liters"]) == D("4000")
    assert D(partielle_po["remaining_liters"]) == D("6000")

    # Livraison excédentaire refusée, puis solde qui clôt la commande.
    trop = client.post(
        f"{API}/fuel/purchases/{achat_id}/receipts",
        headers=carburant.headers,
        json={
            "liters": "7000.000",
            "delivery_reference": "BL-R6-X",
            "occurred_at": (now - timedelta(minutes=55)).isoformat(),
        },
    )
    assert trop.status_code == 409, trop.text
    solde = client.post(
        f"{API}/fuel/purchases/{achat_id}/receipts",
        headers=carburant.headers,
        json={
            "liters": "6000.000",
            "delivery_reference": "BL-R6-002",
            "occurred_at": (now - timedelta(minutes=50)).isoformat(),
        },
    )
    assert solde.status_code == 201, solde.text
    recus = client.get(f"{API}/fuel/purchases", headers=admin, params={"status": "RECEIVED"}).json()
    assert recus["total"] == 1 and recus["items"][0]["fuel_purchase_order_id"] == achat_id
    assert D(recus["items"][0]["received_liters"]) == D("10000")
    assert D(recus["items"][0]["remaining_liters"]) == D("0")

    # Bon de livraison antidaté avant la commande : refusé.
    antidate = client.post(
        f"{API}/fuel/purchases/{achat_id}/receipts",
        headers=carburant.headers,
        json={
            "liters": "100.000",
            "delivery_reference": "BL-R6-003",
            "occurred_at": (now - timedelta(minutes=95)).isoformat(),
        },
    )
    assert (antidate.status_code, antidate.json()["code"]) == (422, "VALIDATION_ERROR")

    # --- Réception directe de stock ------------------------------------------
    livraison = client.post(
        f"{API}/fuel/tanks/{tank_id}/receipts",
        headers=carburant.headers,
        json={
            "liters": "500.000",
            "reference": "RET-R6-001",
            "occurred_at": (now - timedelta(minutes=45)).isoformat(),
        },
    )
    assert livraison.status_code == 201, livraison.text
    etat = _cuve_etat(client, carburant.headers, tank_id)
    assert D(etat["balance_liters"]) == D("10500")
    assert D(etat["reserved_liters"]) == D("0") and D(etat["available_liters"]) == D("10500")

    # --- Seuil bas : alerte déclenchée puis acquittée -------------------------
    seuil = client.post(
        f"{API}/fuel/tanks/{tank_id}/threshold",
        headers=carburant.headers,
        json={"low_stock_threshold_liters": "11000.000"},
    )
    assert seuil.status_code == 200, seuil.text
    assert seuil.json()["low_stock"] is True
    assert D(seuil.json()["low_stock_threshold_liters"]) == D("11000")
    assert D(seuil.json()["balance_liters"]) == D("10500")
    alertes = client.get(f"{API}/fuel/alerts", headers=carburant.headers, params={"active_only": True}).json()
    assert alertes["total"] == 1
    (alerte,) = alertes["items"]
    alerte_id = alerte["fuel_stock_alert_id"]
    assert alerte["tank_code"] == "CUVE-GO-1"
    assert D(alerte["threshold_liters"]) == D("11000") and D(alerte["balance_liters"]) == D("10500")
    assert alerte["acknowledged_at"] is None and alerte["resolved_at"] is None
    acquittement = client.post(f"{API}/fuel/alerts/{alerte_id}/acknowledge", headers=carburant.headers)
    assert acquittement.status_code == 200, acquittement.text
    assert acquittement.json()["acknowledged_by"] == str(carburant.user_id)
    re_acquittement = client.post(f"{API}/fuel/alerts/{alerte_id}/acknowledge", headers=carburant.headers)
    assert re_acquittement.status_code == 409

    # --- Pompe et tolérance d'anomalie ----------------------------------------
    pompe = client.post(
        f"{API}/fuel/pumps",
        headers=carburant.headers,
        json={"fuel_tank_id": tank_id, "code": "POMPE-GO-1", "name": "Pompe cuve GO"},
    )
    assert pompe.status_code == 201, pompe.text
    pump_id = pompe.json()["fuel_pump_id"]
    assert pompe.json()["fuel_tank_id"] == tank_id
    tolerance = client.put(
        f"{API}/fuel/pumps/{pump_id}/anomaly-tolerance",
        headers=carburant.headers,
        json={"tolerance_liters": "8.000", "tolerance_percent": "2.000"},
    )
    assert tolerance.status_code == 200, tolerance.text
    assert D(tolerance.json()["anomaly_tolerance_liters"]) == D("8")
    assert D(tolerance.json()["anomaly_tolerance_percent"]) == D("2")

    # --- Réservations : la sortie en attente réserve le stock ------------------
    sortie1 = client.post(
        f"{API}/fuel/issues",
        headers=carburant.headers,
        json={
            "fuel_tank_id": tank_id,
            "fuel_pump_id": pump_id,
            "vehicle_id": camion,
            "driver_id": conducteur,
            "liters": "8000.000",
            "meter_kind": meter_kind,
            "meter_value": "9000.0",
            "requested_at": (now - timedelta(minutes=30)).isoformat(),
        },
    )
    assert sortie1.status_code == 201, sortie1.text
    issue1_id = sortie1.json()["fuel_issue_id"]
    assert sortie1.json()["status"] == "PENDING_APPROVAL"
    # La projection de réponse relit le référentiel après commit (contexte RLS rétabli).
    assert sortie1.json()["tank_code"] == "CUVE-GO-1"
    assert sortie1.json()["vehicle_fleet_number"] == "R6-CAMION-01"
    etat = _cuve_etat(client, carburant.headers, tank_id)
    assert D(etat["balance_liters"]) == D("10500") and D(etat["reserved_liters"]) == D("8000")
    assert D(etat["available_liters"]) == D("2500")
    en_attente = client.get(f"{API}/fuel/issues", headers=admin, params={"status": "PENDING_APPROVAL"}).json()
    assert en_attente["total"] == 1 and en_attente["items"][0]["fuel_issue_id"] == issue1_id

    # Sortie au-delà du disponible (réservation comprise) : refusée.
    exces = client.post(
        f"{API}/fuel/issues",
        headers=carburant.headers,
        json={
            "fuel_tank_id": tank_id,
            "vehicle_id": camion,
            "driver_id": conducteur,
            "liters": "3000.000",
            "meter_kind": meter_kind,
            "meter_value": "9050.0",
            "requested_at": (now - timedelta(minutes=28)).isoformat(),
        },
    )
    assert exces.status_code == 409, exces.text

    # Le rejet libère la réservation sans trace dans le journal de stock.
    rejet = client.post(
        f"{API}/fuel/issues/{issue1_id}/decision",
        headers=ops.headers,
        json={"decision": "REJECTED", "reason_code": "INVALID_QUANTITY"},
    )
    assert rejet.status_code == 200, rejet.text
    assert rejet.json()["status"] == "REJECTED" and rejet.json()["reason_code"] == "INVALID_QUANTITY"
    assert rejet.json()["decided_by"] == str(ops.user_id)
    etat = _cuve_etat(client, carburant.headers, tank_id)
    assert D(etat["balance_liters"]) == D("10500") and D(etat["reserved_liters"]) == D("0")

    # --- Ravitaillement plein complet, double décision -------------------------
    plein1 = client.post(
        f"{API}/fuel/issues",
        headers=carburant.headers,
        json={
            "fuel_tank_id": tank_id,
            "fuel_pump_id": pump_id,
            "vehicle_id": camion,
            "driver_id": conducteur,
            "liters": "200.000",
            "meter_kind": meter_kind,
            "meter_value": "10000.0",
            "full_tank": True,
            "requested_at": (now - timedelta(minutes=30)).isoformat(),
        },
    )
    assert plein1.status_code == 201, plein1.text
    plein1_id = plein1.json()["fuel_issue_id"]
    auto_valide = client.post(
        f"{API}/fuel/issues/{plein1_id}/decision",
        headers=carburant.headers,
        json={"decision": "APPROVED"},
    )
    assert (auto_valide.status_code, auto_valide.json()["code"]) == (409, "CONFLICT")
    approuve = client.post(
        f"{API}/fuel/issues/{plein1_id}/decision",
        headers=ops.headers,
        json={"decision": "APPROVED"},
    )
    assert approuve.status_code == 200, approuve.text
    assert approuve.json()["status"] == "APPROVED" and approuve.json()["decided_by"] == str(ops.user_id)
    etat = _cuve_etat(client, carburant.headers, tank_id)
    assert D(etat["balance_liters"]) == D("10300") and D(etat["reserved_liters"]) == D("0")

    # --- Inventaire : impossible de compter sous le réservé --------------------
    sortie2 = client.post(
        f"{API}/fuel/issues",
        headers=carburant.headers,
        json={
            "fuel_tank_id": tank_id,
            "vehicle_id": camion,
            "driver_id": conducteur,
            "liters": "5000.000",
            "meter_kind": meter_kind,
            "meter_value": "10050.0",
            "requested_at": (now - timedelta(minutes=25)).isoformat(),
        },
    )
    assert sortie2.status_code == 201, sortie2.text
    issue2_id = sortie2.json()["fuel_issue_id"]
    inventaire_ko = client.post(
        f"{API}/fuel/tanks/{tank_id}/stocktakes",
        headers=carburant.headers,
        json={
            "counted_liters": "4000.000",
            "reference": "INV-R6-KO",
            "reason_code": "MEASUREMENT",
            "occurred_at": (now - timedelta(minutes=24)).isoformat(),
        },
    )
    assert inventaire_ko.status_code == 409, inventaire_ko.text
    rejet2 = client.post(
        f"{API}/fuel/issues/{issue2_id}/decision",
        headers=ops.headers,
        json={"decision": "REJECTED", "reason_code": "OTHER"},
    )
    assert rejet2.status_code == 200, rejet2.text

    # --- Pompe : relevés de compteur monotones et idempotents ------------------
    lect_0 = (now - timedelta(minutes=40), "1000.000", "RELEVE-R6-001")
    lect_1 = (now - timedelta(minutes=20), "1200.000", "RELEVE-R6-002")
    lect_2 = (now - timedelta(minutes=10), "1210.000", "RELEVE-R6-003")

    def _releve(moment: datetime, cumul: str, reference: str) -> object:
        return client.post(
            f"{API}/fuel/pumps/{pump_id}/meter-readings",
            headers=carburant.headers,
            json={
                "cumulative_liters": cumul,
                "measured_at": moment.isoformat(),
                "source": "MANUAL",
                "source_reference": reference,
            },
        )

    r0_rep = _releve(*lect_0)
    assert r0_rep.status_code == 201, r0_rep.text
    r0 = r0_rep.json()
    r1 = _releve(*lect_1).json()
    r2 = _releve(*lect_2).json()

    # Idempotence : le même relevé rejoué ne crée pas de doublon.
    rejeu = _releve(*lect_0)
    assert rejeu.status_code == 201, rejeu.text
    assert rejeu.json()["fuel_pump_meter_reading_id"] == r0["fuel_pump_meter_reading_id"]
    historique = client.get(f"{API}/fuel/pumps/{pump_id}/meter-readings", headers=admin).json()
    assert historique["total"] == 3

    # Compteur qui recule : refusé. Horodatage futur : refusé.
    recule = _releve(now - timedelta(minutes=9), "1209.999", "RELEVE-R6-KO")
    assert recule.status_code == 409, recule.text
    futur = client.post(
        f"{API}/fuel/pumps/{pump_id}/meter-readings",
        headers=carburant.headers,
        json={
            "cumulative_liters": "1300.000",
            "measured_at": (now + timedelta(hours=1)).isoformat(),
            "source": "DEVICE",
            "source_reference": "RELEVE-R6-FUT",
        },
    )
    assert futur.status_code == 422, futur.text

    # --- Rapprochements pompe --------------------------------------------------
    rapprochements = client.get(f"{API}/fuel/pumps/{pump_id}/reconciliations", headers=admin).json()
    assert rapprochements["total"] == 2
    dernier, precedent = rapprochements["items"]
    # R1→R2 : 10 L passés au compteur sans sortie approuvée → écart au-delà de la tolérance.
    assert dernier["start_reading_id"] == r1["fuel_pump_meter_reading_id"]
    assert dernier["end_reading_id"] == r2["fuel_pump_meter_reading_id"]
    assert D(dernier["meter_delta_liters"]) == D("10")
    assert D(dernier["approved_issue_liters"]) == D("0")
    assert D(dernier["variance_liters"]) == D("10") and D(dernier["variance_percent"]) == D("100")
    assert dernier["is_anomaly"] is True
    # R0→R1 : 200 L au compteur = 200 L approuvés (sortie via la pompe) → écart nul.
    assert precedent["start_reading_id"] == r0["fuel_pump_meter_reading_id"]
    assert precedent["end_reading_id"] == r1["fuel_pump_meter_reading_id"]
    assert D(precedent["meter_delta_liters"]) == D("200")
    assert D(precedent["approved_issue_liters"]) == D("200")
    assert D(precedent["variance_liters"]) == D("0") and precedent["is_anomaly"] is False

    # --- Anomalies : qualification, acquittement, clôture contradictoire -------
    cas_url = f"{API}/fuel/pumps/{pump_id}/anomaly-cases"
    hors_ecart = client.post(
        cas_url,
        headers=carburant.headers,
        json={
            "start_reading_id": precedent["start_reading_id"],
            "end_reading_id": precedent["end_reading_id"],
        },
    )
    assert (hors_ecart.status_code, hors_ecart.json()["code"]) == (409, "FUEL_INTERVAL_NOT_ANOMALOUS")
    assert hors_ecart.json()["details"]["variance_liters"] == "0.000"
    non_consecutif = client.post(
        cas_url,
        headers=carburant.headers,
        json={
            "start_reading_id": r0["fuel_pump_meter_reading_id"],
            "end_reading_id": r2["fuel_pump_meter_reading_id"],
        },
    )
    assert non_consecutif.status_code == 409, non_consecutif.text
    dossier = client.post(
        cas_url,
        headers=carburant.headers,
        json={
            "start_reading_id": dernier["start_reading_id"],
            "end_reading_id": dernier["end_reading_id"],
        },
    )
    assert dossier.status_code == 201, dossier.text
    dossier_id = dossier.json()["fuel_pump_anomaly_case_id"]
    assert dossier.json()["status"] == "OPEN" and dossier.json()["created_by"] == str(carburant.user_id)
    assert dossier.json()["qualification_reason"] == "METER_VOLUME_EXCEEDS_APPROVED_ISSUES"
    assert D(dossier.json()["variance_liters"]) == D("10")
    assert D(dossier.json()["tolerance_liters"]) == D("8")
    assert D(dossier.json()["tolerance_percent"]) == D("2")

    # Workflow strict : OPEN → ACKNOWLEDGED → JUSTIFIED → CLOSED, par d'autres acteurs.
    saute = client.post(
        f"{API}/fuel/anomaly-cases/{dossier_id}/events",
        headers=ops.headers,
        json={"event_type": "JUSTIFIED", "justification": "Étape d'acquittement sautée"},
    )
    assert saute.status_code == 409, saute.text
    par_createur_clos = client.post(
        f"{API}/fuel/anomaly-cases/{dossier_id}/events",
        headers=carburant.headers,
        json={"event_type": "CLOSED", "justification": "Clôture tentée par le créateur"},
    )
    assert par_createur_clos.status_code == 409, par_createur_clos.text
    acquittee = client.post(
        f"{API}/fuel/anomaly-cases/{dossier_id}/events",
        headers=ops.headers,
        json={"event_type": "ACKNOWLEDGED", "justification": "Écart constaté par le pompiste"},
    )
    assert acquittee.status_code == 201, acquittee.text
    assert acquittee.json()["event_type"] == "ACKNOWLEDGED"
    justifiee = client.post(
        f"{API}/fuel/anomaly-cases/{dossier_id}/events",
        headers=ops.headers,
        json={"event_type": "JUSTIFIED", "justification": "Amorçage de pompe documenté, BL joint"},
    )
    assert justifiee.status_code == 201, justifiee.text
    cloture = client.post(
        f"{API}/fuel/anomaly-cases/{dossier_id}/events",
        headers=admin,
        json={"event_type": "CLOSED", "justification": "Justification recevue, dossier clos"},
    )
    assert cloture.status_code == 201, cloture.text
    clos = client.get(f"{API}/fuel/anomaly-cases", headers=admin, params={"status": "CLOSED"}).json()
    assert clos["total"] == 1 and clos["items"][0]["fuel_pump_anomaly_case_id"] == dossier_id
    rouverture = client.post(
        f"{API}/fuel/anomaly-cases/{dossier_id}/events",
        headers=admin,
        json={"event_type": "JUSTIFIED", "justification": "Réouverture tardive refusée"},
    )
    assert rouverture.status_code == 409
    evenements = client.get(f"{API}/fuel/anomaly-cases/{dossier_id}/events", headers=admin).json()
    assert evenements["total"] == 3
    assert [e["event_type"] for e in evenements["items"]] == ["ACKNOWLEDGED", "JUSTIFIED", "CLOSED"]

    # --- Inventaire de cuve : correction du stock ------------------------------
    inventaire = client.post(
        f"{API}/fuel/tanks/{tank_id}/stocktakes",
        headers=carburant.headers,
        json={
            "counted_liters": "9700.000",
            "reference": "INV-R6-001",
            "reason_code": "LOSS",
            "occurred_at": (now - timedelta(minutes=1)).isoformat(),
        },
    )
    assert inventaire.status_code == 201, inventaire.text
    assert D(inventaire.json()["expected_liters"]) == D("10300")
    assert D(inventaire.json()["counted_liters"]) == D("9700")
    assert D(inventaire.json()["delta_liters"]) == D("-600")
    assert inventaire.json()["reason_code"] == "LOSS"
    etat = _cuve_etat(client, carburant.headers, tank_id)
    assert D(etat["balance_liters"]) == D("9700")
    inventaires = client.get(f"{API}/fuel/stocktakes", headers=admin).json()
    assert inventaires["total"] == 1

    # --- Deuxième plein complet puis consommation plein-à-plein ----------------
    plein2 = client.post(
        f"{API}/fuel/issues",
        headers=carburant.headers,
        json={
            "fuel_tank_id": tank_id,
            "vehicle_id": camion,
            "driver_id": conducteur,
            "liters": "180.000",
            "meter_kind": meter_kind,
            "meter_value": "10500.0",
            "full_tank": True,
            "requested_at": (now - timedelta(minutes=2)).isoformat(),
        },
    )
    assert plein2.status_code == 201, plein2.text
    plein2_id = plein2.json()["fuel_issue_id"]
    approuve2 = client.post(
        f"{API}/fuel/issues/{plein2_id}/decision",
        headers=ops.headers,
        json={"decision": "APPROVED"},
    )
    assert approuve2.status_code == 200, approuve2.text
    etat = _cuve_etat(client, carburant.headers, tank_id)
    assert D(etat["balance_liters"]) == D("9520")

    conso = client.get(
        f"{API}/fuel/vehicles/{camion}/consumption", headers=admin, params={"meter_kind": meter_kind}
    ).json()
    assert conso["total"] == 1
    (intervalle,) = conso["items"]
    assert intervalle["fuel_issue_id"] == plein2_id
    assert intervalle["vehicle_fleet_number"] == "R6-CAMION-01"
    assert D(intervalle["fuel_liters"]) == D("180") and D(intervalle["meter_delta"]) == D("500")
    taux_attendu = D("36.000") if meter_kind == "ODOMETER" else D("0.360")
    assert D(intervalle["rate_liters_per_unit"]) == taux_attendu
    assert intervalle["comparison_median_rate"] is None
    assert intervalle["comparison_interval_count"] == 0 and intervalle["is_anomaly"] is False

    # --- Alerte de seuil résolue automatiquement --------------------------------
    baisse = client.post(
        f"{API}/fuel/tanks/{tank_id}/threshold",
        headers=carburant.headers,
        json={"low_stock_threshold_liters": "9000.000"},
    )
    assert baisse.status_code == 200, baisse.text
    assert baisse.json()["low_stock"] is False
    actives = client.get(f"{API}/fuel/alerts", headers=carburant.headers, params={"active_only": True}).json()
    assert actives["total"] == 0
    historique_alertes = client.get(
        f"{API}/fuel/alerts", headers=carburant.headers, params={"active_only": False}
    ).json()
    assert historique_alertes["total"] == 1
    (alerte_finie,) = historique_alertes["items"]
    assert alerte_finie["fuel_stock_alert_id"] == alerte_id
    assert alerte_finie["resolved_at"] is not None
    assert D(alerte_finie["resolution_balance_liters"]) == D("9520")
    assert alerte_finie["acknowledged_by"] == str(carburant.user_id)

    # --- Stock cohérent : réceptions − sorties ± corrections --------------------
    etat = _cuve_etat(client, carburant.headers, tank_id)
    # 10 500 reçus − 380 distribués − 600 écart inventaire
    assert D(etat["balance_liters"]) == D("9520")
    assert D(etat["reserved_liters"]) == D("0") and D(etat["available_liters"]) == D("9520")

    # --- Dashboard de consommation ----------------------------------------------
    # Fenêtre fraîche et non tronquée : le dossier d'anomalie vient d'être créé, il faut
    # que period_end soit strictement postérieur à created_at (filtre created_at < end).
    fin = datetime.now(UTC)
    tableau = client.get(
        f"{API}/fuel/dashboard",
        headers=admin,
        params={"from": (fin - timedelta(days=1)).isoformat(), "to": fin.isoformat()},
    ).json()
    assert D(tableau["distributed_liters"]) == D("380")  # 200 + 180
    assert D(tableau["received_liters"]) == D("10500")  # 4 000 + 6 000 (achat) + 500 (direct)
    assert D(tableau["stocktake_variance_liters"]) == D("-600")
    assert D(tableau["qualified_anomaly_variance_liters"]) == D("10")
    assert (tableau["open_anomaly_cases"], tableau["closed_anomaly_cases"]) == (0, 1)
    assert tableau["average_resolution_hours"] is not None
    assert (tableau["active_stock_alerts"], tableau["unacknowledged_stock_alerts"]) == (0, 0)
    assert [(v["vehicle_fleet_number"], D(v["liters"])) for v in tableau["vehicle_consumption"]] == [
        ("R6-CAMION-01", D("380"))
    ]
    assert [(s["site_code"], D(s["liters"])) for s in tableau["site_consumption"]] == [("MINE", D("380"))]
    assert len(tableau["daily_trend"]) == 2
    assert sum(D(j["distributed_liters"]) for j in tableau["daily_trend"]) == D("380")
    assert sum(D(j["received_liters"]) for j in tableau["daily_trend"]) == D("10500")

    # Périodes invalides : bornées et ordonnées.
    inversee = client.get(
        f"{API}/fuel/dashboard",
        headers=admin,
        params={"from": now.isoformat(), "to": (now - timedelta(days=1)).isoformat()},
    )
    assert (inversee.status_code, inversee.json()["code"]) == (422, "VALIDATION_ERROR")
    trop_longue = client.get(
        f"{API}/fuel/dashboard",
        headers=admin,
        params={"from": (now - timedelta(days=400)).isoformat(), "to": now.isoformat()},
    )
    assert trop_longue.status_code == 422

    # --- Chaque écriture clé est auditée ----------------------------------------
    # L'entité auditée est l'objet créé (mouvement, réception, relevé, dossier), pas la cuve.
    def _actions(**params: object) -> set[str]:
        items = client.get(f"{API}/audit-events", headers=admin, params=params).json()["items"]
        return {e["action"] for e in items}

    journal_cuve = _actions(entity_id=tank_id)
    assert {"fuel.tank.create", "fuel.stock.threshold.update"} <= journal_cuve
    journal_reception = _actions(entity_id=livraison.json()["fuel_stock_movement_id"])
    assert journal_reception == {"fuel.stock.receive"}
    journal_inventaire = _actions(entity_id=inventaire.json()["fuel_stocktake_id"])
    assert journal_inventaire == {"fuel.stocktake.record"}
    journal_achat = _actions(entity_id=achat_id)
    assert {"fuel.purchase.create", "fuel.purchase.decide"} <= journal_achat
    journal_bl = _actions(entity_id=solde.json()["fuel_purchase_receipt_id"])
    assert journal_bl == {"fuel.purchase.receive"}
    journal_fournisseur = _actions(entity_id=fournisseur_id)
    assert journal_fournisseur == {"fuel.supplier.create"}
    journal_sortie = _actions(entity_id=plein1_id)
    assert journal_sortie == {"fuel.issue.request", "fuel.issue.decide"}
    journal_pompe = _actions(entity_id=pump_id)
    assert "fuel.pump.create" in journal_pompe
    releves_audit = client.get(
        f"{API}/audit-events", headers=admin, params={"action": "fuel.pump.meter.record"}
    ).json()["items"]
    assert len(releves_audit) >= 3
    journal_dossier = _actions(entity_id=dossier_id)
    assert {"fuel.pump.anomaly.open", "fuel.pump.anomaly.event"} <= journal_dossier
    journal_alerte = _actions(entity_id=alerte_id)
    assert journal_alerte == {
        "fuel.stock.alert.trigger",
        "fuel.stock.alert.acknowledge",
        "fuel.stock.alert.resolve",
    }
