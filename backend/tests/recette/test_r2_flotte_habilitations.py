"""Recette R2 — référentiel flotte et habilitations (docs/RECETTE.md §R2).

Le parcours : référentiel des catégories fourni par la plateforme, véhicules posés par site avec numéro
de flotte unique, conducteurs créés par les RH avec permis (dates d'expiration) et habilitations de
conduite par catégorie, affectation planifiée qualifiée posée par le dispatcher (portée site), refus des
affectations non qualifiées (permis absent, mauvaise catégorie, permis expiré, habilitation manquante ou
expirée), puis prise de poste concurrente bloquée selon la politique assignment_safety_policy (D-41).
"""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from tests.conftest import API, Api
from tests.test_assignment import (  # noqa: F401  (fixtures w, block_policy)
    World,
    _create,
    _driver,
    _reasons,
    _vehicle,
    block_policy,
    w,
)

DEMAIN = datetime.now(UTC) + timedelta(days=1)
HIER = (datetime.now(UTC) - timedelta(days=1)).date().isoformat()


def _creer_vehicule(
    client: TestClient, monde: World, site: str, fleet_number: str, category: str = "RIGID_DUMP_TRUCK"
) -> str:
    resp = client.post(
        f"{API}/vehicles",
        headers=monde.t.admin.headers,
        json={
            "site_id": str(monde.t.sites[site]),
            "vehicle_category_id": monde.categories[category],
            "fleet_number": fleet_number,
        },
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["vehicle_id"])


def test_r2_flotte_habilitations_parcours_complet(client: TestClient, w: World, api: Api) -> None:  # noqa: F811
    # Le référentiel des catégories (permis exigés, habilitation interne obligatoire) vient de la plateforme.
    categories = client.get(f"{API}/vehicle-categories", headers=w.t.admin.headers)
    assert categories.status_code == 200, categories.text
    tomberau = next(c for c in categories.json() if c["code"] == "RIGID_DUMP_TRUCK")
    assert tomberau["requires_internal_authorization"] is True
    assert tomberau["required_license_categories"] == ["C"]

    # Véhicules par site : le numéro de flotte est unique sur tous les sites du tenant.
    flotte = f"R2-{uuid.uuid4().hex[:6].upper()}"
    engin = _creer_vehicule(client, w, "S1", flotte)
    for site in ("S1", "S2"):
        doublon = client.post(
            f"{API}/vehicles",
            headers=w.t.admin.headers,
            json={
                "site_id": str(w.t.sites[site]),
                "vehicle_category_id": w.categories["RIGID_DUMP_TRUCK"],
                "fleet_number": flotte,
            },
        )
        assert (doublon.status_code, doublon.json()["code"]) == (409, "DUPLICATE_FLEET_NUMBER"), site
    assert _creer_vehicule(client, w, "S2", f"R2-{uuid.uuid4().hex[:6].upper()}", "HYDRAULIC_EXCAVATOR")

    # Conducteurs : les RH posent le matricule (unique), le permis et l'habilitation de conduite.
    matricule = f"M-R2-{uuid.uuid4().hex[:6]}"
    corps = {
        "site_id": str(w.t.sites["S1"]),
        "employee_number": matricule,
        "last_name": "Nom-Test",
        "first_name": "Prénom",
    }
    premier = client.post(f"{API}/drivers", headers=w.hr.headers, json=corps)
    assert premier.status_code == 201, premier.text
    encore = client.post(f"{API}/drivers", headers=w.hr.headers, json=corps)
    assert (encore.status_code, encore.json()["code"]) == (409, "DUPLICATE_EMPLOYEE_NUMBER")
    conducteur = _driver(client, w)  # permis C valide + habilitation RIGID_DUMP_TRUCK

    # Affectation planifiée qualifiée, posée par le dispatcher à portée site (D-29 : éligibilité au départ).
    planifiee = _create(client, w, engin, conducteur, start=DEMAIN, headers=w.dispatcher.headers)
    assert planifiee.status_code == 201, planifiee.text
    assert planifiee.json()["status"] == "PLANNED"

    # Tentatives non qualifiées : chaque motif est nommé, aucune affectation n'est créée.
    sans_permis = _driver(client, w, license_category=None)  # habilitation posée, permis absent
    assert _reasons(_create(client, w, _vehicle(client, w), sans_permis)) == ["DRIVER_LICENSE_MISSING"]
    mauvaise_categorie = _driver(client, w, license_category="B")  # le tombereau exige un permis C
    assert _reasons(_create(client, w, _vehicle(client, w), mauvaise_categorie)) == [
        "DRIVER_LICENSE_CATEGORY_MISSING"
    ]
    permis_expire = _driver(client, w, license_expiry=HIER)
    assert _reasons(_create(client, w, _vehicle(client, w), permis_expire)) == ["DRIVER_LICENSE_EXPIRED"]
    sans_habilitation = _driver(client, w, authorization=None)  # permis C valide, habilitation absente
    assert _reasons(_create(client, w, _vehicle(client, w), sans_habilitation)) == [
        "DRIVER_QUALIFICATION_MISSING"
    ]
    habilitation_expiree = _driver(client, w, authorization_to=HIER)
    assert _reasons(_create(client, w, _vehicle(client, w), habilitation_expiree)) == [
        "DRIVER_QUALIFICATION_EXPIRED"
    ]

    # Le numéro de permis n'est jamais exposé hors des RH (D-15) ; les écritures restent auditées.
    permis = client.get(f"{API}/drivers/{conducteur}/licenses", headers=w.dispatcher.headers)
    assert permis.status_code == 200, permis.text
    assert all("license_number" not in lic for lic in permis.json())
    journal = client.get(
        f"{API}/audit-events", headers=w.t.admin.headers, params={"action": "vehicle.create"}
    ).json()
    assert journal["total"] >= 2  # l'engin de S1 et celui de S2


def test_r2_prise_de_poste_concurrente_politique_par_defaut(client: TestClient, w: World) -> None:  # noqa: F811
    engin_1, engin_2 = _vehicle(client, w), _vehicle(client, w)
    conducteur = _driver(client, w)
    en_cours = _create(client, w, engin_1, conducteur, end=datetime.now(UTC) + timedelta(hours=8))
    assert en_cours.status_code == 201 and en_cours.json()["status"] == "ACTIVE"

    # Un engin ou un conducteur déjà pris ne peut pas être repris en parallèle (chevauchements, US-1.22).
    autre_conducteur = _driver(client, w)
    sur_engin = _create(client, w, engin_1, autre_conducteur, start=datetime.now(UTC) + timedelta(hours=1))
    assert (sur_engin.status_code, sur_engin.json()["code"]) == (409, "VEHICLE_ASSIGNMENT_OVERLAP")
    sur_conducteur = _create(client, w, engin_2, conducteur, start=datetime.now(UTC) + timedelta(hours=2))
    assert (sur_conducteur.status_code, sur_conducteur.json()["code"]) == (409, "DRIVER_ASSIGNMENT_OVERLAP")

    # Politique « flag » (défaut) : l'indisponibilité est enregistrée, puis toute prise de poste est
    # refusée par l'éligibilité dérivée (DRIVER_NOT_ACTIVE).
    url_conducteur = f"{API}/drivers/{conducteur}"
    version = client.get(url_conducteur, headers=w.hr.headers).headers["ETag"]
    indisponible = client.post(
        f"{url_conducteur}/status",
        headers={**w.hr.headers, "If-Match": version},
        json={"status": "UNAVAILABLE", "unavailability_reason": "LEAVE"},
    )
    assert indisponible.status_code == 200, indisponible.text
    assert _reasons(_create(client, w, engin_2, conducteur, start=DEMAIN)) == ["DRIVER_NOT_ACTIVE"]

    # De retour actif, le conducteur redevient affectable sur le créneau libre.
    retour = client.post(
        f"{url_conducteur}/status",
        headers={
            **w.hr.headers,
            "If-Match": client.get(url_conducteur, headers=w.hr.headers).headers["ETag"],
        },
        json={"status": "ACTIVE"},
    )
    assert retour.status_code == 200, retour.text
    reprise = _create(client, w, engin_2, conducteur, start=DEMAIN)
    assert reprise.status_code == 201 and reprise.json()["status"] == "PLANNED"


def test_r2_politique_block_refuse(client: TestClient, w: World, block_policy: None) -> None:  # noqa: F811
    # D-41 « block » : l'affectation ouverte du conducteur bloque le changement de statut de sécurité.
    conducteur = _driver(client, w)
    assert _create(client, w, _vehicle(client, w), conducteur).status_code == 201
    url_conducteur = f"{API}/drivers/{conducteur}"
    refuse = client.post(
        f"{url_conducteur}/status",
        headers={
            **w.hr.headers,
            "If-Match": client.get(url_conducteur, headers=w.hr.headers).headers["ETag"],
        },
        json={"status": "UNAVAILABLE", "unavailability_reason": "LEAVE"},
    )
    assert (refuse.status_code, refuse.json()["code"]) == (409, "OPEN_ASSIGNMENTS_EXIST")
