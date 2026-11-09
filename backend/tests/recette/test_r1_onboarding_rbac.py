"""Recette R1 — onboarding d'un tenant multi-sites et contrôle d'accès par rôle (docs/RECETTE.md §R1).

Le parcours : création du tenant par la plateforme (2 sites), invitations et activation des comptes
métiers, authentification de chaque rôle, puis vérification qu'un rôle à portée restreinte ne peut pas
créer un référentiel global.
"""

import uuid

from fastapi.testclient import TestClient

from tests.conftest import API, Api
from tests.test_assignment import World, w  # noqa: F401  (fixture w)

ROLES_METIERS = (
    "OPS_MANAGER",
    "HR",
    "WORKSHOP_CHIEF",
    "MECHANIC",
    "STOREKEEPER",
    "HSE",
    "FINANCE",
    "AUDITOR",
)


def test_r1_onboarding_tenant_sites_et_comptes(client: TestClient, w: World, api: Api) -> None:  # noqa: F811
    # Le tenant de la fixture w est déjà passé par le parcours complet : plateforme → tenant →
    # sites S1/S2 → OPS_MANAGER + HR + DISPATCHER (portée site S1).
    assert set(w.t.sites) == {"S1", "S2"}

    # Tous les rôles métiers sont invités, activés (e-mail) et authentifiés.
    comptes = {role: api.user(w.t, role) for role in ROLES_METIERS}
    comptes["OPS"] = w.ops
    comptes["RH"] = w.hr
    comptes["DISPATCH"] = w.dispatcher
    for cle, compte in comptes.items():
        me = client.get(f"{API}/me", headers=compte.headers)
        assert me.status_code == 200, (cle, me.text)

    # Un compte à portée restreinte ne crée pas de référentiel global.
    refus = client.post(
        f"{API}/materials",
        headers=w.dispatcher.headers,
        json={"code": f"R1-{uuid.uuid4().hex[:6]}", "name": "Interdit au dispatcher"},
    )
    assert refus.status_code == 403, refus.text

    # L'admin consulte le référentiel catégories (lecture globale de référence).
    categories = client.get(f"{API}/vehicle-categories", headers=w.t.admin.headers)
    assert categories.status_code == 200, categories.text
