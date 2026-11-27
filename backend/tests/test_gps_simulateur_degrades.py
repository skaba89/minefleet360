"""Simulateur service-level des scénarios dégradés §1.3 (`INTEGRATION_GPS_OFFLINE`).

Chaque comportement réellement implémenté par le service d'ingestion est simulé
par la **vraie API traceur** (authentification composite, anti-rejeu atomique,
schéma strict) avec l'assertion attendue par le tableau §1.3 :

- doublon (même séquence, mêmes octets) → 409 « ancien ou déjà reçu », aucune
  position de plus, compteur **non avancé** (la séquence suivante reste acceptée) ;
- hors ordre → 409, aucune position de plus ;
- coordonnées invalides (hors borne, NaN) → 422, aucune position de plus ;
- identités injectées dans le corps → 422, aucune position de plus ;
- horodatage antérieur à l'activation du traceur → 409 (pré-vol anti-attribution).

Écarts assumés, non simulés : le tableau §1.3 prévoit aussi « événement en
retard » (flag `late` + recalcul), « décalage d'horloge » (`clock_skew_suspect`),
« horodatage futur » (quarantaine) et la conservation brute (`telematics_raw_event`,
§1.5) — aucun n'est encore implémenté au service ; aucun test ne prétend les
couvrir. L'audit GPS (`AUDIT_GPS_2026-11-26.md` §4) garde ces chantiers ouverts.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import new_session
from app.core.tenancy import set_tenant_context
from tests.conftest import API
from tests.test_assignment import World, _vehicle, w  # noqa: F401

_ZONE = {"latitude": 9.5, "longitude": -13.7, "accuracy_m": 8.0}


def _tracker(client, w: World, vehicle: str) -> tuple[str, str]:  # noqa: F811
    """Provisionner un traceur réel par l'API (jeton composite audité)."""
    device = "fictif-" + uuid.uuid4().hex
    created = client.post(
        f"{API}/vehicles/{vehicle}/gps/tracker", headers=w.ops.headers, json={"device_id": device}
    )
    assert created.status_code == 201, created.text
    return device, created.json()["token"]


def _envoi(client, token: str, device: str, sequence: int, at: datetime, **surcharge) -> int:
    corps = {
        "device_id": device,
        **_ZONE,
        "recorded_at": at.isoformat(),
        "sequence": sequence,
        **surcharge,
    }
    resp = client.post(f"{API}/gps/telemetry", headers={"Authorization": f"Bearer {token}"}, json=corps)
    return resp.status_code


def _compte_positions(tenant_id) -> int:
    db: Session = new_session()
    try:
        set_tenant_context(db, tenant_id)
        return db.execute(text("SELECT count(*) FROM fleet_gps_position")).scalar_one()
    finally:
        db.close()


def test_doublon_sans_effet_et_compteur_non_avance(client, w: World) -> None:  # noqa: F811
    """§1.3 « Doublon (même clé) » : ignoré, aucune écriture, compteur intact."""
    vehicle = _vehicle(client, w)
    device, token = _tracker(client, w, vehicle)
    depart = datetime.now(UTC)  # jamais avant l'activation (refus anti-attribution)
    assert _envoi(client, token, device, 1, depart + timedelta(seconds=1)) == 204
    assert _compte_positions(w.t.tenant_id) == 1
    # Rejeu d'un doublon exact (même séquence) : refus 409, aucune écriture.
    assert _envoi(client, token, device, 1, depart + timedelta(seconds=1)) == 409
    assert _compte_positions(w.t.tenant_id) == 1
    # La preuve que le compteur n'a pas avancé : la séquence 2 suivante est acceptée.
    assert _envoi(client, token, device, 2, depart + timedelta(seconds=2)) == 204
    assert _compte_positions(w.t.tenant_id) == 2


def test_hors_ordre_refuse_et_historique_coherent(client, w: World) -> None:  # noqa: F811
    """§1.3 « Hors ordre » : l'ancien est refusé, le suivant reste accepté."""
    vehicle = _vehicle(client, w)
    device, token = _tracker(client, w, vehicle)
    depart = datetime.now(UTC)
    assert _envoi(client, token, device, 2, depart + timedelta(seconds=2)) == 204
    assert _envoi(client, token, device, 1, depart + timedelta(seconds=1)) == 409
    assert _compte_positions(w.t.tenant_id) == 1
    assert _envoi(client, token, device, 3, depart + timedelta(seconds=3)) == 204
    assert _compte_positions(w.t.tenant_id) == 2


def test_coordonnees_invalides_refusees_sans_ecriture(client, w: World) -> None:  # noqa: F811
    """§1.3 « Coordonnées invalides » : lat/lon hors borne et NaN refusés, rien écrit.

    La conservation brute en quarantaine (§1.5) n'est pas encore implémentée :
    le résultat observé est le refus propre — aucune géofence ne peut être
    calculée dessus, ce qui est le résultat attendu du tableau."""
    vehicle = _vehicle(client, w)
    device, token = _tracker(client, w, vehicle)
    depart = datetime.now(UTC)
    assert _envoi(client, token, device, 1, depart + timedelta(seconds=1), latitude=95.0) == 422
    assert _envoi(client, token, device, 1, depart + timedelta(seconds=1), longitude=-200.0) == 422
    resp = client.post(
        f"{API}/gps/telemetry",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        content=b'{"device_id": "' + device.encode() + b'", "latitude": NaN, "longitude": -13.7,'
        b' "recorded_at": "'
        + (depart + timedelta(seconds=1)).isoformat().encode()
        + b'", "sequence": 1, "accuracy_m": 8.0}',
    )
    assert resp.status_code == 422, resp.text
    assert _compte_positions(w.t.tenant_id) == 0


def test_identites_injectees_refusees_sans_ecriture(client, w: World) -> None:  # noqa: F811
    """Le corps ne peut jamais porter une identité serveur (extra="forbid")."""
    vehicle = _vehicle(client, w)
    device, token = _tracker(client, w, vehicle)
    depart = datetime.now(UTC)
    assert (
        _envoi(
            client,
            token,
            device,
            1,
            depart + timedelta(seconds=1),
            tenant_id=str(w.t.tenant_id),
            site_id=str(w.t.sites["S1"]),
        )
        == 422
    )
    assert _compte_positions(w.t.tenant_id) == 0


def test_horodatage_avant_activation_refuse(client, w: World) -> None:  # noqa: F811
    """Anti-attribution : une position d'avant l'activation du traceur est refusée.

    Le refus passe par le pré-vol d'ingestion (`recorded_at < binding.active_from`)
    et se traduit par le code générique CONFLICT — même famille que le rejeu :
    « message refusé, ancien ou déjà reçu », jamais une écriture."""
    vehicle = _vehicle(client, w)
    device, token = _tracker(client, w, vehicle)
    avant = datetime.now(UTC) - timedelta(hours=1)
    assert _envoi(client, token, device, 1, avant) == 409
    assert _compte_positions(w.t.tenant_id) == 0
