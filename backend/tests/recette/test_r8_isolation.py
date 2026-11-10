"""Recette R8 — isolation tenant et sécurité négative IDOR (docs/RECETTE.md §R8).

Parcours : deux sociétés créées par la plateforme, comptes de rôle identique (OPS_MANAGER) → le compte
de la société B tente de lire puis de modifier les ressources de la société A par identifiant direct
(véhicule, mission, pesée, document) : chaque réponse cross-tenant est indiscernable d'une ressource
inexistante (404, corps identique hors request_id, aucun contenu de A) et n'écrit aucune trace dans
l'audit de A → les échecs d'authentification sont limités par compte (au-delà du quota, 429 même avec
le bon mot de passe) puis par source (limite IP atteinte pour un compte pourtant sain) → les refus de
permission sont audités dans la société du compte (DENIED) comme les échecs de login (FAILURE) →
l'AUDITOR consulte l'audit de sa société sans y voir aucune donnée de l'autre → les identifiants
internes sont des UUID v4 non devinables.
"""

import uuid

from fastapi.testclient import TestClient

from app.core.config import get_settings
from tests.conftest import API, PASSWORD, Api
from tests.test_assignment import World, _vehicle, w  # noqa: F401  (fixture w)
from tests.test_dispatch import _assignment, _event, _mission, _refs
from tests.test_weighing import _ticket, _weighbridge

ETAG = {"If-Match": '"1"'}  # garde de version : passer l'entrée pour atteindre la ressource absente


def _strip(body: dict) -> dict:  # type: ignore[type-arg]
    """Le request_id varie d'une requête à l'autre : le reste de la réponse 404 doit être identique."""
    return {k: v for k, v in body.items() if k != "request_id"}


def test_r8_isolation_tenant_et_securite_negative(client: TestClient, api: Api, w: World) -> None:  # noqa: F811
    a, b = w, api.tenant()
    b_ops = api.user(b, "OPS_MANAGER")
    b_auditor = api.user(b, "AUDITOR")

    # --- Société A : véhicule, mission chargée, pesée mesurée, document ---------------------------
    refs = _refs(client, a)
    assignment = _assignment(client, a)
    mission = _mission(client, a, assignment, refs).json()
    mid = mission["mission_id"]
    for event in ("DEPARTED", "ARRIVED_LOADING", "LOADED"):
        assert _event(client, a, mid, event).status_code == 200, event
    rotation = client.get(f"{API}/missions/{mid}", headers=a.ops.headers).json()["rotations"][0]
    pont = _weighbridge(client, a)
    ticket = client.post(
        f"{API}/weighing-tickets",
        headers=a.dispatcher.headers,
        json=_ticket(rotation["rotation_id"], pont, "R8-T1"),
    ).json()
    assert (ticket["status"], ticket["source"]) == ("VALID", "WEIGHBRIDGE")
    tid = ticket["weighing_ticket_id"]
    veh_a = _vehicle(client, a)
    document = client.post(
        f"{API}/vehicles/{veh_a}/documents",
        headers=a.t.admin.headers,
        json={"doc_type": "ROAD_PERMIT", "reference": "RP-R8-1", "valid_until": "2030-01-01"},
    )
    assert document.status_code == 201, document.text
    doc_id = document.json()["vehicle_document_id"]

    # Aucun identifiant interne devinable : UUID v4 aléatoires, jamais séquentiels.
    for interne in (mid, tid, doc_id, str(a.t.tenant_id), str(b.tenant_id)):
        assert uuid.UUID(interne).version == 4

    avant_a = client.get(f"{API}/audit-events", headers=a.t.admin.headers).json()["total"]

    # --- Sonde de référence : ressource vraiment inexistante --------------------------------------
    inconnu_veh = client.get(f"{API}/vehicles/{uuid.uuid4()}", headers=b_ops.headers)
    inconnu_miss = client.get(f"{API}/missions/{uuid.uuid4()}", headers=b_ops.headers)
    inconnu_tick = client.get(f"{API}/weighing-tickets/{uuid.uuid4()}", headers=b_ops.headers)
    inconnu_doc = client.get(f"{API}/vehicles/{uuid.uuid4()}/documents", headers=b_ops.headers)
    for probe in (inconnu_veh, inconnu_miss, inconnu_tick, inconnu_doc):
        assert probe.status_code == 404, probe.text

    # --- IDOR lecture (B → A) : 404 indiscernable de l'inconnu, aucune fuite ----------------------
    croise_veh = client.get(f"{API}/vehicles/{veh_a}", headers=b_ops.headers)
    croise_miss = client.get(f"{API}/missions/{mid}", headers=b_ops.headers)
    croise_tick = client.get(f"{API}/weighing-tickets/{tid}", headers=b_ops.headers)
    croise_doc = client.get(f"{API}/vehicles/{veh_a}/documents", headers=b_ops.headers)
    for probe in (croise_veh, croise_miss, croise_tick, croise_doc):
        assert probe.status_code == 404, probe.text
    for croisee, inconnue in (
        (croise_veh, inconnu_veh),
        (croise_miss, inconnu_miss),
        (croise_tick, inconnu_tick),
        (croise_doc, inconnu_doc),
    ):
        assert _strip(croisee.json()) == _strip(inconnue.json())
    for corps in (croise_veh, croise_miss, croise_tick, croise_doc):
        assert "R8-T1" not in corps.text and "RP-R8-1" not in corps.text
        assert veh_a not in corps.text and mid not in corps.text
        assert tid not in corps.text and doc_id not in corps.text
        assert str(a.t.tenant_id) not in corps.text

    # --- IDOR écriture (B → A) : 404, la ressource de A reste intacte -----------------------------
    assert (
        client.patch(
            f"{API}/vehicles/{veh_a}", headers={**b_ops.headers, **ETAG}, json={"notes": "intrusion"}
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"{API}/missions/{mid}/events",
            headers={**b_ops.headers, **ETAG},
            json={"event_type": "COMPLETED"},
        ).status_code
        == 404
    )
    assert (
        client.post(f"{API}/weighing-tickets/{tid}/approve", headers=b_ops.headers, json={}).status_code
        == 404
    )
    assert (
        client.post(
            f"{API}/vehicle-documents/{doc_id}/withdraw",
            headers={**b_ops.headers, **ETAG},
            json={"reason_code": "ENTRY_ERROR"},
        ).status_code
        == 404
    )
    intacte = client.get(f"{API}/missions/{mid}", headers=a.ops.headers).json()
    assert intacte["status"] == "EN_ROUTE_LOADED" and intacte["rotations_completed"] == 0

    # --- Un 404 cross-tenant n'écrit rien dans l'audit de A ---------------------------------------
    apres_a = client.get(f"{API}/audit-events", headers=a.t.admin.headers).json()["total"]
    assert apres_a == avant_a

    # --- Refus de permission : 403 audité dans la société du compte -------------------------------
    refus = client.get(f"{API}/audit-events", headers=b_ops.headers)
    assert (refus.status_code, refus.json()["code"]) == (403, "PERMISSION_DENIED")

    # --- Quota d'authentification : par compte -----------------------------------------------------
    seuil = get_settings().login_max_failures
    for _ in range(seuil):
        echec = client.post(
            f"{API}/auth/login", json={"workspace_code": b.code, "email": b_ops.email, "password": "faux"}
        )
        assert (echec.status_code, echec.json()["code"]) == (401, "INVALID_CREDENTIALS")
    bloque = client.post(
        f"{API}/auth/login", json={"workspace_code": b.code, "email": b_ops.email, "password": PASSWORD}
    )
    assert (bloque.status_code, bloque.json()["code"]) == (429, "RATE_LIMITED")
    assert "retry-after" in bloque.headers
    # Le blocage est propre au compte : un compte sain du même tenant se connecte encore.
    sain = client.post(
        f"{API}/auth/login", json={"workspace_code": b.code, "email": b_auditor.email, "password": PASSWORD}
    )
    assert sain.status_code == 200, sain.text

    # --- Quota d'authentification : par source -----------------------------------------------------
    restant = get_settings().login_ip_max_failures - seuil
    for i in range(restant):
        echec = client.post(
            f"{API}/auth/login",
            json={"workspace_code": b.code, "email": f"r8-source-{i}@fictif.mf", "password": "faux"},
        )
        assert echec.status_code == 401, echec.text  # comptes distincts : seule la source s'accumule
    for_source = client.post(
        f"{API}/auth/login", json={"workspace_code": b.code, "email": b_auditor.email, "password": PASSWORD}
    )
    assert (for_source.status_code, for_source.json()["code"]) == (429, "RATE_LIMITED")

    # --- Consultation de l'audit par l'AUDITOR de B ------------------------------------------------
    journal = client.get(f"{API}/audit-events", headers=b_auditor.headers, params={"page_size": 200})
    assert journal.status_code == 200, journal.text
    evenements = journal.json()["items"]
    denied = [e for e in evenements if e["action"] == "audit.event.read"]
    assert any(
        e["outcome"] == "DENIED"
        and e["reason"] == "PERMISSION_DENIED"
        and e["actor_user_id"] == str(b_ops.user_id)
        for e in denied
    ), "le refus de permission doit être audité avec le compte et l'action"
    logins = [e for e in evenements if e["action"] == "auth.login"]
    assert any(
        e["outcome"] == "FAILURE"
        and e["reason"] == "INVALID_CREDENTIALS"
        and e["actor_user_id"] == str(b_ops.user_id)
        for e in logins
    ), "les échecs d'authentification doivent être audités avec le contexte"
    texte = str(evenements)
    for secret in (veh_a, mid, tid, doc_id, "R8-T1", "RP-R8-1", str(a.t.tenant_id)):
        assert secret not in texte, secret  # l'audit de B ne contient aucune donnée de A
