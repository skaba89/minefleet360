"""Tickets de pesée rejouables depuis l'outbox terrain (Idempotency-Key, hors ligne).

Même contrat que les sorties de carburant (test_fuel_issue_offline) : clé liée au tenant ET au
compte authentifié, corps empreinté, un rejet métier ne consomme pas la clé, un rejeu réussi
renvoie le ticket d'origine sans nouvel événement d'audit ; la dédup métier RM-074 (pont + numéro
de ticket) reste intacte pour les renvois sans clé.
"""

import uuid

from fastapi.testclient import TestClient

from tests.conftest import API
from tests.test_assignment import World, w  # noqa: F401  (fixture w)
from tests.test_weighing import _loaded_mission, _ticket, _weighbridge


def _offline(client: TestClient, headers: dict[str, str], key: str, body: dict[str, object]):  # type: ignore[no-untyped-def]
    return client.post(f"{API}/weighing-tickets", headers={**headers, "Idempotency-Key": key}, json=body)


def test_offline_weighing_ticket_replay_creates_it_once(client: TestClient, w: World) -> None:  # noqa: F811
    _, mission = _loaded_mission(client, w)
    rotation = mission["rotations"][0]["rotation_id"]
    bridge = _weighbridge(client, w)
    key = str(uuid.uuid4())
    body = _ticket(rotation, bridge, "T-OFF-1")
    first = _offline(client, w.ops.headers, key, body)
    assert first.status_code == 201, first.text
    assert "Idempotency-Replayed" not in first.headers
    again = _offline(client, w.ops.headers, key, body)
    assert again.status_code == 201 and again.headers["Idempotency-Replayed"] == "true"
    ticket_id = first.json()["weighing_ticket_id"]
    assert again.json()["weighing_ticket_id"] == ticket_id
    assert again.json()["ticket_number"] == "T-OFF-1"
    listed = client.get(f"{API}/weighing-tickets", headers=w.ops.headers).json()
    assert sum(1 for t in listed["items"] if t["weighing_ticket_id"] == ticket_id) == 1
    audit = client.get(
        f"{API}/audit-events",
        headers=w.t.admin.headers,
        params={"action": "weighing_ticket.create", "entity_id": ticket_id},
    ).json()["items"]
    assert len(audit) == 1  # la pesée initiale seulement, le rejeu n'ajoute rien
    # Même clé, contenu altéré : refusé, jamais un second ticket ni un tonnage doublé.
    altered = _offline(client, w.ops.headers, key, _ticket(rotation, bridge, "T-OFF-1", gross_kg=42_424))
    assert (altered.status_code, altered.json()["code"]) == (422, "IDEMPOTENCY_KEY_REUSED")


def test_rejected_weighing_does_not_consume_the_key_and_key_is_per_account(
    client: TestClient,
    w: World,  # noqa: F811
) -> None:
    _, mission = _loaded_mission(client, w)
    rotation = mission["rotations"][0]["rotation_id"]
    bridge = _weighbridge(client, w)
    key = str(uuid.uuid4())
    unknown_bridge = _ticket(rotation, bridge, "T-OFF-2", weighbridge_location_id=str(uuid.uuid4()))
    rejected = _offline(client, w.ops.headers, key, unknown_bridge)
    assert rejected.status_code in (404, 409, 422), rejected.text  # pont hors portée : rejet métier
    # Le rejet a annulé la réservation de la clé : la pesée corrigée passe avec la même clé.
    ok = _offline(client, w.ops.headers, key, _ticket(rotation, bridge, "T-OFF-2"))
    assert ok.status_code == 201 and "Idempotency-Replayed" not in ok.headers
    # La clé est liée au compte : un autre compte (DISPATCHER, portée SITE) rejoue pour son propre
    # compte sur une autre rotation, sans reprendre la pesée d'autrui.
    _, second_mission = _loaded_mission(client, w)
    second_rotation = second_mission["rotations"][0]["rotation_id"]
    theirs = _offline(client, w.dispatcher.headers, key, _ticket(second_rotation, bridge, "T-OFF-3"))
    assert theirs.status_code == 201 and "Idempotency-Replayed" not in theirs.headers
    assert theirs.json()["weighing_ticket_id"] != ok.json()["weighing_ticket_id"]
    # Sans le droit de peser : refusé avant toute réservation.
    forbidden = _offline(client, w.hr.headers, str(uuid.uuid4()), _ticket(second_rotation, bridge, "T-OFF-4"))
    assert forbidden.status_code == 403, forbidden.text
