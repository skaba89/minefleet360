"""Recette R3 — mission de transport bout en bout avec pesées pont bascule (docs/RECETTE.md §R3).

Parcours complet : référentiels (lieux, matériau), affectation active, mission à 2 rotations, pesée
mesurée valide sur la rotation 1, pesée dégradée avec double validation sur la rotation 2, clôture.
Un second test vérifie le signalement de surcharge contre le payload nominal du véhicule.
"""

from fastapi.testclient import TestClient

from tests.conftest import API, Api
from tests.test_assignment import World, w  # noqa: F401  (fixture w)
from tests.test_dispatch import _assignment, _event, _mission, _refs
from tests.test_weighing import _loaded_mission, _set_payload, _ticket, _weighbridge


def test_r3_mission_complete_avec_pesee_mesuree_et_pesee_degradee(
    client: TestClient,
    w: World,  # noqa: F811
    api: Api,
) -> None:
    refs = _refs(client, w)
    assignment = _assignment(client, w)
    mission = _mission(client, w, assignment, refs).json()
    mid = mission["mission_id"]
    assert mission["status"] == "ASSIGNED" and mission["rotations_completed"] == 0

    pont = _weighbridge(client, w)

    # Rotation 1 — cycle complet avec pesée mesurée (pont bascule).
    for event in ("DEPARTED", "ARRIVED_LOADING", "LOADED"):
        assert _event(client, w, mid, event).status_code == 200, event
    rotation_1 = client.get(f"{API}/missions/{mid}", headers=w.ops.headers).json()["rotations"][0]
    ticket_1 = client.post(
        f"{API}/weighing-tickets",
        headers=w.dispatcher.headers,
        json=_ticket(rotation_1["rotation_id"], pont, "R3-T1"),
    ).json()
    assert (ticket_1["status"], ticket_1["source"], ticket_1["net_kg"]) == ("VALID", "WEIGHBRIDGE", 34_000)
    for event in ("ARRIVED_UNLOADING", "UNLOADED"):
        assert _event(client, w, mid, event).status_code == 200, event

    # Rotation 2 — pont en panne : saisie dégradée puis double validation.
    for event in ("DEPARTED", "ARRIVED_LOADING", "LOADED"):
        assert _event(client, w, mid, event).status_code == 200, event
    rotation_2 = client.get(f"{API}/missions/{mid}", headers=w.ops.headers).json()["rotations"][1]
    ticket_2 = client.post(
        f"{API}/weighing-tickets",
        headers=w.ops.headers,
        json=_ticket(
            rotation_2["rotation_id"],
            pont,
            "R3-T2",
            source="MANUAL_DEGRADED",
            degraded_reason="WEIGHBRIDGE_DOWN",
        ),
    ).json()
    assert ticket_2["status"] == "PENDING_APPROVAL"

    url_approbation = f"{API}/weighing-tickets/{ticket_2['weighing_ticket_id']}/approve"
    # Auto-approbation interdite : celui qui a saisi ne peut pas valider.
    auto = client.post(url_approbation, headers=w.ops.headers, json={})
    assert (auto.status_code, auto.json()["code"]) == (422, "SELF_APPROVAL_FORBIDDEN")
    # Le dispatcher n'a pas le droit d'approuver.
    assert client.post(url_approbation, headers=w.dispatcher.headers, json={}).status_code == 403
    # Un second OPS_MANAGER approuve : décision tracée.
    autre_ops = api.user(w.t, "OPS_MANAGER")
    approuve = client.post(url_approbation, headers=autre_ops.headers, json={})
    assert approuve.status_code == 200 and approuve.json()["status"] == "VALID"
    assert approuve.json()["decisions"][0]["decided_by"] == str(autre_ops.user_id)

    # Clôture de la mission après ses deux rotations.
    assert _event(client, w, mid, "COMPLETED").status_code == 200
    detail = client.get(f"{API}/missions/{mid}", headers=w.ops.headers).json()
    assert detail["status"] == "COMPLETED"
    assert len(detail["rotations"]) == 2


def test_r3_surcharge_signalee_contre_payload_nominal(client: TestClient, w: World) -> None:  # noqa: F811
    assignment, mission = _loaded_mission(client, w)
    # Payload nominal abaissé à 30 t : 34 t nets dépasse 30 t + 10 % de tolérance.
    _set_payload(client, w, assignment["vehicle_id"], 30_000)
    pont = _weighbridge(client, w)
    ticket = client.post(
        f"{API}/weighing-tickets",
        headers=w.ops.headers,
        json=_ticket(mission["rotations"][0]["rotation_id"], pont),
    ).json()
    assert ticket["overload"] is True and ticket["rated_payload_kg"] == 30_000

    # Le ticket surchargé est filtrable pour le suivi HSE/ops.
    surcharges = client.get(
        f"{API}/weighing-tickets", headers=w.ops.headers, params={"overload": "true"}
    ).json()
    assert ticket["weighing_ticket_id"] in {t["weighing_ticket_id"] for t in surcharges["items"]}
