"""Recette R10 — consolidation des coûts et rentabilité (docs/RECETTE.md §R10).

Le parcours, construit sur les sources des scénarios R3-R6 : taux horaire posé par la finance
(chaque anomalie refusée) → sortie de carburant approuvée valorisée au prix d'achat de la commande
(une sortie laissée en attente ne crée aucun coût) → ordre de travail avec main-d'œuvre (heures ×
taux) et consommation de pièce valorisée au CMP → immobilisation lue comme indicateur de fiabilité
(downtime_hours), jamais comme un montant → historique de coûts par véhicule (mensuel UTC) →
indicateurs par période : les bornes effectives sont ré-affichées, les totaux de site sont la somme
des lignes détaillées, les devises ne sont jamais mélangées (pièce en USD : total INSUFFICIENT),
chaque montant se réconcilie avec son mouvement d'origine (litres × prix d'achat, quantité × CMP,
minutes × taux) → périodes invalides refusées, permissions strictes, isolation site et tenant sans
fuite. La devise de référence est le GNF ; aucun montant n'est inventé : les lignes sont recalculées
à la lecture depuis les mouvements d'origine.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from tests.conftest import API, Api
from tests.test_assignment import OffsetClock
from tests.test_costs import _consume_valued_part, _issue, _meters, _priced_fuel, _work_order_with_labour
from tests.test_fuel_pumps import _assigned_vehicle_and_driver
from tests.test_maintenance import _act


def _strip(body: dict) -> dict:  # type: ignore[type-arg]
    """Le request_id varie d'une requête à l'autre : le reste d'une 404 doit être identique."""
    return {k: v for k, v in body.items() if k != "request_id"}


def test_r10_consolidation_couts_bout_en_bout(
    client: TestClient, api: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    t = api.tenant(sites=("MINE", "PORT"))
    ops, vehicule, conducteur, meter = _assigned_vehicle_and_driver(client, api, t)
    finance = api.user(t, "FINANCE")
    auditeur = api.user(t, "AUDITOR")
    dispatcher = api.user(t, "DISPATCHER", "SITE", "MINE")  # sans cost.vehicle.read
    fin_port = api.user(t, "FINANCE", "SITE", "PORT")
    etranger = api.user(api.tenant(), "FINANCE")  # même rôle, autre société
    port = str(t.sites["PORT"])
    now = datetime.now(UTC)

    # --- Taux horaire : la source de la main-d'œuvre, tenue par la finance ------------------------
    taux = client.post(
        f"{API}/costs/labour-rates",
        headers=finance.headers,
        json={"hourly_rate": "50000.00", "currency": "GNF", "valid_from": "2026-01-01"},
    )
    assert taux.status_code == 201 and taux.json()["currency"] == "GNF", taux.text
    assert (
        client.post(
            f"{API}/costs/labour-rates",
            headers=finance.headers,
            json={"hourly_rate": "60000.00", "currency": "GNF", "valid_from": "2026-01-01"},
        ).status_code
        == 409
    )  # un seul taux par (portée, date)
    for mauvais in (
        {"hourly_rate": "0", "currency": "GNF", "valid_from": "2026-01-01"},  # taux non positif
        {"hourly_rate": "50000.00", "currency": "gnf", "valid_from": "2026-01-01"},  # devise en majuscules
    ):
        assert (
            client.post(f"{API}/costs/labour-rates", headers=finance.headers, json=mauvais).status_code == 422
        )
    # Un taux de société ne peut pas être posé par un compte de portée site.
    assert (
        client.post(
            f"{API}/costs/labour-rates",
            headers=fin_port.headers,
            json={"hourly_rate": "40000.00", "currency": "GNF", "valid_from": "2026-01-02"},
        ).status_code
        == 403
    )
    taux_port = client.post(
        f"{API}/costs/labour-rates",
        headers=fin_port.headers,
        json={"hourly_rate": "40000.00", "currency": "GNF", "valid_from": "2026-01-02", "site_id": port},
    )
    assert taux_port.status_code == 201, taux_port.text

    # --- Carburant : achat prixé → sortie approuvée = 100 L × 12 000 GNF --------------------------
    cuve = _priced_fuel(client, api, t, ops, "12000.00")
    _issue(client, t, ops, cuve, vehicule, conducteur, meter)
    # Une sortie laissée en attente de décision ne crée aucun coût : le stock est réservé, pas sorti.
    corps_attente: dict[str, object] = {
        "fuel_tank_id": cuve["fuel_tank_id"],
        "vehicle_id": vehicule,
        "driver_id": conducteur,
        "liters": "100.000",
        "requested_at": (now - timedelta(hours=1)).isoformat(),
    }
    if meter:
        corps_attente.update(
            {"meter_kind": meter, "meter_value": "1600.0"}
        )  # croissant après le dernier relevé
    en_attente = client.post(f"{API}/fuel/issues", headers=ops, json=corps_attente)
    assert en_attente.status_code == 201, en_attente.text

    # --- Atelier : main-d'œuvre (120 min × 50 000) et pièce valorisée (2 × CMP 150 000) -----------
    ot = _work_order_with_labour(client, api, t, ops, vehicule, 120)
    _consume_valued_part(client, api, t, ot, "150000")
    kind = "ODOMETER_KM" if meter == "ODOMETER" else "HOUR_METER"
    _meters(client, ops, vehicule, kind)

    # Réconciliation partielle avant l'engin à devises mixtes : total de site = somme des lignes.
    partielle = client.get(f"{API}/costs/vehicles", headers=finance.headers)
    assert partielle.status_code == 200, partielle.text
    ligne1 = next(v for v in partielle.json()["vehicles"] if v["vehicle_id"] == vehicule)
    assert ligne1["fuel"] == {"amount": "1200000.00", "status": "ESTIMATED", "currency": "GNF", "missing": []}
    assert ligne1["labour"]["amount"] == "100000.00" and ligne1["labour"]["status"] == "COMPLETE"
    assert ligne1["parts"]["amount"] == "300000.00" and ligne1["parts"]["status"] == "COMPLETE"
    assert ligne1["tyres"] == {"amount": "0", "status": "COMPLETE", "currency": None, "missing": []}
    assert ligne1["total"] == "1600000.00" and ligne1["total_status"] == "ESTIMATED"
    assert ligne1["currency"] == "GNF"  # devise de référence, explicitement affichée
    denominateur, ratio = (("km", "cost_per_km"), ("hours", "cost_per_hour"))[kind != "ODOMETER_KM"]
    mesure = Decimal("500") if kind == "ODOMETER_KM" else Decimal("6")
    assert Decimal(ligne1[denominateur]) == mesure
    assert Decimal(ligne1[ratio]) == (Decimal("1600000") / mesure).quantize(Decimal("0.01"))
    site_mine = next(s for s in partielle.json()["sites"] if s["site_id"] == str(t.sites["MINE"]))
    assert site_mine["total"] == "1600000.00"  # totaux du dashboard = somme des lignes détaillées

    # --- Deuxième engin : pièce reçue en USD → devises jamais mélangées ---------------------------
    admin = t.admin.headers
    categorie = next(
        c
        for c in client.get(f"{API}/vehicle-categories", headers=admin).json()
        if c["code"] == "RIGID_DUMP_TRUCK"
    )
    vehicule2 = client.post(
        f"{API}/vehicles",
        headers=admin,
        json={
            "site_id": str(t.sites["MINE"]),
            "vehicle_category_id": categorie["vehicle_category_id"],
            "fleet_number": "R10-VEH-02",
        },
    ).json()["vehicle_id"]
    ot2 = _work_order_with_labour(client, api, t, ops, vehicule2, 60)
    _consume_valued_part(client, api, t, ot2, "250000", "USD")

    # --- Immobilisation : indicateur de fiabilité, jamais un montant de coût ----------------------
    # Un troisième engin sans ordre de travail ouvert : la remise en service ne doit pas être masquée
    # par un autre OT en cours.
    chef = api.user(t, "WORKSHOP_CHIEF")
    mecanicien = api.user(t, "MECHANIC", "SITE", "MINE")
    vehicule3 = client.post(
        f"{API}/vehicles",
        headers=admin,
        json={
            "site_id": str(t.sites["MINE"]),
            "vehicle_category_id": categorie["vehicle_category_id"],
            "fleet_number": "R10-VEH-03",
        },
    ).json()["vehicle_id"]
    panne = client.post(
        f"{API}/work-orders",
        headers=ops,
        json={"vehicle_id": vehicule3, "symptom_code": "BRAKES", "priority": "CRITICAL", "immobilize": True},
    )
    assert panne.status_code == 201, panne.text
    oid_panne = panne.json()["work_order_id"]
    assert client.get(f"{API}/vehicles/{vehicule3}", headers=ops).json()["status"] == "IMMOBILIZED"
    # L'atelier dépanne : l'horloge applicative avance de 11 min pour mesurer une immobilisation
    # réelle entre le signalement et la remise en service (même convention que R4).
    monkeypatch.setattr(client.app.state, "clock", OffsetClock(timedelta(minutes=11)))  # type: ignore[attr-defined]
    for executeur, acte, corps in (
        (chef.headers, "decision", {"action": "APPROVE"}),
        (chef.headers, "decision", {"action": "ASSIGN", "assigned_to": str(mecanicien.user_id)}),
        (mecanicien.headers, "progress", {"action": "START", "diagnosis": "Freins à refaire"}),
        (mecanicien.headers, "progress", {"action": "SUBMIT", "work_done": "Plaquettes remplacées"}),
    ):
        assert _act(client, acte, oid_panne, executeur, **corps).status_code == 200, acte
    clos = _act(client, "decision", oid_panne, chef.headers, action="QC_PASS")
    assert clos.status_code == 200 and clos.json()["status"] == "CLOSED"
    assert client.get(f"{API}/vehicles/{vehicule3}", headers=ops).json()["status"] == "AVAILABLE"
    fiabilite = client.get(f"{API}/maintenance/reliability", headers=finance.headers)
    assert fiabilite.status_code == 200, fiabilite.text
    immobilisation = next(v for v in fiabilite.json()["vehicles"] if v["vehicle_id"] == vehicule3)
    assert immobilisation["failures"] >= 1 and Decimal(immobilisation["downtime_hours"]) > 0

    # --- Historique de coûts par véhicule (mois civils UTC) ---------------------------------------
    historique = client.get(
        f"{API}/costs/vehicles/{vehicule}/history", headers=finance.headers, params={"months": 2}
    )
    assert historique.status_code == 200, historique.text
    mois = historique.json()["months"]
    assert len(mois) == 2 and mois[-1]["cost"]["total"] == "1600000.00"
    assert all(len(m["month"]) == 7 for m in mois)  # format "YYYY-MM"
    absent = client.get(f"{API}/costs/vehicles/{uuid.uuid4()}/history", headers=finance.headers)
    assert absent.status_code == 404

    # --- Indicateurs par période : bornes UTC ré-affichées, réconciliation complète ---------------
    debut = (now - timedelta(days=30)).isoformat()
    lue = client.get(
        f"{API}/costs/vehicles",
        headers=finance.headers,
        params={"from": debut, "to": datetime.now(UTC).isoformat()},  # horloge réelle, pas l'app décalée
    )
    assert lue.status_code == 200, lue.text
    # Affichage explicite de la période retenue (bornes renvoyées au format UTC).
    assert datetime.fromisoformat(lue.json()["period_start"].replace("Z", "+00:00")) == now - timedelta(
        days=30
    )
    assert datetime.fromisoformat(lue.json()["period_end"].replace("Z", "+00:00")) >= now
    lignes = {v["vehicle_id"]: v for v in lue.json()["vehicles"]}
    ligne1, ligne2 = lignes[vehicule], lignes[vehicule2]
    # La sortie en attente n'est toujours pas un coût : le carburant de l'engin 1 est inchangé.
    assert ligne1["fuel"]["amount"] == "1200000.00"
    assert ligne2["parts"]["currency"] == "USD" and ligne2["parts"]["amount"] == "500000.00"
    assert ligne2["labour"]["currency"] == "GNF" and ligne2["labour"]["amount"] == "50000.00"
    assert ligne2["total"] is None and ligne2["total_status"] == "INSUFFICIENT"
    assert "devises multiples sans conversion" in ligne2["missing"]
    site = next(s for s in lue.json()["sites"] if s["site_id"] == str(t.sites["MINE"]))
    # Le total de site somme les lignes connues et signale la part incomplète : jamais de mélange.
    assert (site["total"], site["total_status"]) == ("1600000.00", "PARTIAL")

    # --- Périodes invalides -----------------------------------------------------------------------
    inversee = client.get(
        f"{API}/costs/vehicles",
        headers=finance.headers,
        params={"from": now.isoformat(), "to": (now - timedelta(days=1)).isoformat()},
    )
    assert (inversee.status_code, inversee.json()["code"]) == (422, "END_BEFORE_START")
    trop_longue = client.get(
        f"{API}/costs/vehicles",
        headers=finance.headers,
        params={"from": (now - timedelta(days=400)).isoformat(), "to": now.isoformat()},
    )
    assert trop_longue.status_code == 422
    assert any(d.get("type") == "period_too_long" for d in trop_longue.json()["details"])
    sans_fuseau = client.get(
        f"{API}/costs/vehicles",
        headers=finance.headers,
        params={"from": "2026-01-01T00:00:00", "to": now.replace(tzinfo=None).isoformat()},
    )
    assert sans_fuseau.status_code == 422  # datetime naïf : fuseau obligatoire
    inconnu = client.get(f"{API}/costs/vehicles", headers=finance.headers, params={"foo": 1})
    assert inconnu.status_code == 422  # paramètre de requête non déclaré

    # --- Permissions et isolation -----------------------------------------------------------------
    assert (
        client.get(f"{API}/costs/vehicles", headers=dispatcher.headers).status_code == 403
    )  # le dispatcher n'a pas cost.vehicle.read
    assert client.get(f"{API}/costs/vehicles", headers=auditeur.headers).status_code == 200
    hors_site = client.get(f"{API}/costs/vehicles", headers=fin_port.headers)
    assert hors_site.status_code == 200 and all(
        v["vehicle_id"] not in (vehicule, vehicule2) for v in hors_site.json()["vehicles"]
    )
    assert (
        client.get(
            f"{API}/costs/vehicles", headers=fin_port.headers, params={"site_id": str(t.sites["MINE"])}
        ).status_code
        == 404
    )
    assert client.get(f"{API}/costs/vehicles/{vehicule}/history", headers=fin_port.headers).status_code == 404
    vide = client.get(f"{API}/costs/vehicles", headers=etranger.headers)
    assert vide.status_code == 200 and vide.json()["vehicles"] == []
    croise = client.get(f"{API}/costs/vehicles/{vehicule}/history", headers=etranger.headers)
    assert croise.status_code == 404 and _strip(croise.json()) == _strip(absent.json())
    assert "1600000" not in vide.text  # aucun montant de la société A ne fuite vers l'extérieur
