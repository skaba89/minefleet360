"""Recette R7 — GPS : ingestion, position courante et alertes (docs/RECETTE.md §R7).

Le parcours : provisionnement du traceur par l'OPS_MANAGER (refusé au dispatcher) → politique de site
(vitesse et perte de signal, bornes invalides refusées) → préférences de notification personnelles →
ingestion de positions par l'appareil authentifié : schéma strict (coordonnées, cap, vitesse, séquence
et horodatage fusé refusés en 422, champ non déclaré refusé), authentification de l'appareil (jeton
absent, altéré ou device incohérent → 401), chronologie encadrée (futur > 2 min et passé > 24 h → 409)
→ parcours complet avec excès de vitesse ouvrant puis fermant l'alerte → anti-rejeu (doublon
d'horodatage, séquence non croissante → 409) → position courante reflétant le dernier point valide
(cap transmis tel quel ou null, jamais recalculé ; source active ; jamais aucun champ de tonnage) →
acquittement de l'alerte par le dispatcher du site (hors périmètre 404, sans droit 403, re-prise en
compte 409) et notification e-mail regroupée livrée une seule fois → perte de signal : seuls les engins
disponibles, équipés d'un traceur actif et silencieux au-delà du délai sont alertés par le balayage
SYSTEM (pas l'engin en maintenance ni celui sans traceur), une seule alerte ouverte par engin, fermée
au retour du signal → historique borné à 24 h avec finalité obligatoire et audité, refusé au
dispatcher → partage téléphone simulé (consentement explicite, relevé anti-rejeu, relevé trop ancien
refusé, arrêt idempotent puis relevé refusé, source_active redevenue False après l'arrêt).
"""

import time
import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.cli import main
from app.core.config import get_settings
from app.core.db import new_session
from app.core.email import MemoryEmailSender
from app.fleet.gps_alert_notify import deliver_pending
from tests.conftest import API, Api, TenantFixture


def _vehicule(client: TestClient, api: Api, tenant: TenantFixture, numero: str) -> str:
    """Camion disponible du site MINE (statut par défaut : AVAILABLE)."""
    admin = tenant.admin.headers
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
            "fleet_number": numero,
        },
    )
    assert vehicle.status_code == 201, vehicle.text
    return str(vehicle.json()["vehicle_id"])


def _traceur(client: TestClient, headers: dict[str, str], vehicle: str) -> tuple[str, str, object]:
    """Provisionne un traceur puis renvoie (device, token, send) ; send renvoie le statut HTTP.

    La première position doit être postérieure au provisionnement (start est pris après la 201).
    `send(seconds, speed, **extra)` construit un payload valide ; `extra` écrase n'importe quel
    champ (recorded_at, sequence, device_id…) pour les cas limites.
    """
    device = "fictif-" + uuid.uuid4().hex
    provision = client.post(
        f"{API}/vehicles/{vehicle}/gps/tracker", headers=headers, json={"device_id": device}
    )
    assert provision.status_code == 201, provision.text
    token = provision.json()["token"]
    assert token.startswith("gps_") and token.count(".") == 2
    start = datetime.now(UTC)
    state = {"seq": 0}

    def send(seconds: int, speed: float | None = None, **extra: object) -> int:
        state["seq"] += 1
        body: dict[str, object] = {
            "device_id": device,
            "sequence": state["seq"],
            "latitude": 10.0,
            "longitude": -12.0,
            "recorded_at": (start + timedelta(seconds=seconds)).isoformat(),
        }
        if speed is not None:
            body["speed_kmh"] = speed
        body.update(extra)
        return client.post(
            f"{API}/gps/telemetry", headers={"Authorization": f"Bearer {token}"}, json=body
        ).status_code

    return device, token, send


def _position_sql(tenant: TenantFixture, vehicle: str, device: str, minutes_ago: int) -> datetime:
    """Dernière mesure avant panne : écrite directement en base sous contexte RLS.

    L'API refuse une mesure antérieure à l'activation du traceur ; le balayage, lui, ne juge que
    la fraîcheur de la dernière position — c'est exactement le cas simulé ici.
    """
    at = datetime.now(UTC) - timedelta(minutes=minutes_ago)
    engine = create_engine(get_settings().database_url())
    try:
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant.tenant_id)})
            conn.execute(
                text(
                    "INSERT INTO fleet_gps_position (tenant_id, vehicle_id, site_id, device_id, latitude, "
                    "longitude, speed_kmh, recorded_at, received_at) "
                    "VALUES (:t, :v, :s, :d, 10.0, -12.0, 0, :at, :at)"
                ),
                {
                    "t": str(tenant.tenant_id),
                    "v": vehicle,
                    "s": str(tenant.sites["MINE"]),
                    "d": device,
                    "at": at,
                },
            )
    finally:
        engine.dispose()
    return at


def _alertes(client: TestClient, headers: dict[str, str], **params: object) -> list[dict]:  # type: ignore[type-arg]
    resp = client.get(f"{API}/gps/alerts", headers=headers, params={"page_size": 100, **params})
    assert resp.status_code == 200, resp.text
    return resp.json()["items"]  # type: ignore[no-any-return]


def _outbox_lignes(tenant_id: uuid.UUID) -> list[tuple[uuid.UUID, str, str]]:
    db = new_session()
    try:
        db.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)})
        rows = db.execute(
            text(
                "SELECT user_account_id, channel, status FROM notification_outbox "
                "WHERE tenant_id = :t ORDER BY channel, user_account_id"
            ),
            {"t": str(tenant_id)},
        ).all()
        return [tuple(r) for r in rows]  # type: ignore[no-any-return]
    finally:
        db.close()


def _livrer(tenant_id: uuid.UUID) -> tuple[int, list[str]]:
    email = MemoryEmailSender()
    db = new_session()
    try:
        db.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)})
        report = deliver_pending(db, tenant_id, settings=get_settings(), email_sender=email, sms_sender=None)
        db.commit()
    finally:
        db.close()
    return report.sent, [m.body for m in email.outbox]


def test_r7_gps_bout_en_bout(client: TestClient, api: Api) -> None:
    t = api.tenant(sites=("MINE", "DEPOT"))
    admin = t.admin.headers
    ops = api.user(t, "OPS_MANAGER")
    dispatcher = api.user(t, "DISPATCHER", "SITE", "MINE")
    dispatcher_depot = api.user(t, "DISPATCHER", "SITE", "DEPOT")
    auditor = api.user(t, "AUDITOR")
    outsider = api.user(api.tenant(), "OPS_MANAGER")
    site = str(t.sites["MINE"])
    depot = str(t.sites["DEPOT"])
    now = datetime.now(UTC).replace(microsecond=0)

    veh1 = _vehicule(client, api, t, "R7-CAMION-01")
    veh2 = _vehicule(client, api, t, "R7-CAMION-02")
    veh3 = _vehicule(client, api, t, "R7-CAMION-03")
    veh4 = _vehicule(client, api, t, "R7-CAMION-04")

    # --- Préférences de notification (posées avant les alertes : elles fixent les destinataires) ---
    initial = client.get(f"{API}/me/alert-notifications", headers=ops.headers).json()
    assert (initial["email_enabled"], initial["sms_enabled"], initial["phone_e164"]) == (False, False, None)
    for mauvais in (
        {"email_enabled": False, "sms_enabled": True},  # SMS sans numéro
        {"email_enabled": False, "sms_enabled": True, "phone_e164": "0620000001"},  # pas E.164
        {"email_enabled": "true", "sms_enabled": False},  # booléen strict
    ):
        assert (
            client.put(f"{API}/me/alert-notifications", headers=ops.headers, json=mauvais).status_code == 422
        )
    prefere = client.put(
        f"{API}/me/alert-notifications",
        headers=ops.headers,
        json={"email_enabled": True, "sms_enabled": False},
    )
    assert prefere.status_code == 200 and prefere.json()["email_enabled"] is True

    # --- Provisionnement des traceurs -------------------------------------------------------------
    refuse = client.post(
        f"{API}/vehicles/{veh1}/gps/tracker", headers=dispatcher.headers, json={"device_id": "fictif-x"}
    )
    assert refuse.status_code == 403, refuse.text  # fleet.gps.manage absent du dispatcher
    device1, token1, send1 = _traceur(client, ops.headers, veh1)
    deja = client.post(
        f"{API}/vehicles/{veh1}/gps/tracker", headers=ops.headers, json={"device_id": "fictif-autre"}
    )
    assert deja.status_code == 409, deja.text  # un seul traceur actif par véhicule
    consulte = client.get(f"{API}/vehicles/{veh1}/gps/tracker", headers=ops.headers)
    assert consulte.status_code == 200 and consulte.json()["device_id"] == device1
    assert consulte.json()["revoked_at"] is None
    assert client.get(f"{API}/vehicles/{veh4}/gps/tracker", headers=ops.headers).json() is None
    device2, _, send2 = _traceur(client, ops.headers, veh2)
    device3, _, _send3 = _traceur(client, ops.headers, veh3)

    # --- Politique de site : vitesse et perte de signal -------------------------------------------
    assert (
        client.put(f"{API}/sites/{site}/gps-policy", headers=dispatcher.headers, json={}).status_code == 403
    )
    for mauvais in ({"signal_loss_minutes": 4}, {"signal_loss_minutes": 1441}, {"signal_loss_minutes": "10"}):
        assert (
            client.put(f"{API}/sites/{site}/gps-policy", headers=ops.headers, json=mauvais).status_code == 422
        )
    for mauvais in ({"speed_limit_kmh": 0}, {"speed_limit_kmh": 300}):
        assert (
            client.put(f"{API}/sites/{site}/gps-policy", headers=ops.headers, json=mauvais).status_code == 422
        )
    politique = client.put(
        f"{API}/sites/{site}/gps-policy",
        headers=ops.headers,
        json={"speed_limit_kmh": 50, "signal_loss_minutes": 10},
    )
    assert politique.status_code == 200, politique.text
    assert (politique.json()["speed_limit_kmh"], politique.json()["signal_loss_minutes"]) == ("50.0", 10)
    relue = client.get(f"{API}/sites/{site}/gps-policy", headers=dispatcher.headers)
    assert relue.status_code == 200 and relue.json()["signal_loss_minutes"] == 10

    # --- Ingestion : schéma strict (422) -----------------------------------------------------------
    for mauvais in (
        {"latitude": 95.0},  # hors monde
        {"longitude": -200.0},
        {"heading_deg": 360.0},  # cap dans [0, 360)
        {"heading_deg": -5.0},
        {"speed_kmh": -1.0},
        {"sequence": "1"},  # entier strict
        {"recorded_at": now.replace(tzinfo=None).isoformat()},  # horodatage sans fuseau
        {"tenant_id": str(t.tenant_id)},  # champ non déclaré
    ):
        resp = client.post(
            f"{API}/gps/telemetry",
            headers={"Authorization": f"Bearer {token1}"},
            json={
                "device_id": device1,
                "sequence": 1,
                "latitude": 10.0,
                "longitude": -12.0,
                "recorded_at": (now + timedelta(seconds=1)).isoformat(),
                **mauvais,
            },
        )
        assert resp.status_code == 422, (mauvais, resp.text)

    # --- Ingestion : authentification de l'appareil (401) ------------------------------------------
    payload = {
        "device_id": device1,
        "sequence": 1,
        "latitude": 10.0,
        "longitude": -12.0,
        "recorded_at": (now + timedelta(seconds=1)).isoformat(),
    }
    assert client.post(f"{API}/gps/telemetry", json=payload).status_code == 401  # sans jeton
    assert (
        client.post(
            f"{API}/gps/telemetry", headers={"Authorization": "Bearer abc.def.ghi"}, json=payload
        ).status_code
        == 401
    )  # jeton sans préfixe gps_
    morceaux = token1.removeprefix("gps_").split(".")
    faux_secret = "x" * 44
    jeton_altere = f"gps_{morceaux[0]}.{morceaux[1]}.{faux_secret}"
    assert (
        client.post(
            f"{API}/gps/telemetry", headers={"Authorization": f"Bearer {jeton_altere}"}, json=payload
        ).status_code
        == 401
    )  # empreinte du secret sans correspondance
    assert send1(1, 10.0, device_id="fictif-ailleurs") == 401  # device du payload ≠ appareil appairé
    assert (
        client.post(
            f"{API}/gps/telemetry?source=demo",
            headers={"Authorization": f"Bearer {token1}"},
            json=payload,
        ).status_code
        == 422
    )  # paramètre de requête non déclaré

    # --- Ingestion : chronologie encadrée (409) -----------------------------------------------------
    assert send1(0, None, recorded_at=(now + timedelta(minutes=3)).isoformat()) == 409  # futur > 2 min
    assert send1(0, None, recorded_at=(now - timedelta(hours=25)).isoformat()) == 409  # passé > 24 h

    # --- Ingestion du parcours et alerte d'excès de vitesse ----------------------------------------
    # Horodatages légèrement postérieurs au provisionnement (GPS-23) : +1 s à +4 s, l'horloge
    # les rattrape avant la lecture de l'historique (même convention que test_gps_heading).
    assert send1(1, 45.0, heading_deg=90.0, accuracy_m=8.0) == 204  # sous la limite : aucune alerte
    assert send1(2, 80.0) == 204  # excès : alerte ouverte, pic 80
    assert send1(3, 40.0) == 204  # retour sous la limite : alerte fermée
    assert send1(4, 50.0) == 204  # dernier point valide, cap absent
    surcharge = _alertes(client, ops.headers, kind="OVERSPEED")
    assert len(surcharge) == 1
    (alerte,) = surcharge
    assert alerte["vehicle_id"] == veh1 and alerte["closed_at"] is not None
    assert (alerte["peak_speed_kmh"], alerte["speed_limit_kmh"]) == (80.0, "50.0")

    # --- Anti-rejeu (409) ---------------------------------------------------------------------------
    assert send1(3, 40.0) == 409  # même horodatage re-joué : doublon (device, temps)
    assert send1(0, 45.0, sequence=1) == 409  # séquence non croissante

    # --- Position courante : le dernier point valide, jamais un tonnage ----------------------------
    courantes = client.get(f"{API}/vehicles/gps/latest", headers=ops.headers)
    assert courantes.status_code == 200, courantes.text
    (ligne1,) = [p for p in courantes.json() if p["vehicle_id"] == veh1]
    assert ligne1["heading_deg"] is None  # cap transmis tel quel, jamais recalculé
    assert ligne1["source"] == "TRACKER" and ligne1["source_active"] is True
    assert ligne1["speed_kmh"] == 50.0  # le dernier point valide est bien le quatrième (50 km/h)
    interdits = {"payload_kg", "rated_payload_kg", "tonnage", "measured_tonnage", "load_kg", "charge_kg"}
    assert all(not (set(p) & interdits) for p in courantes.json())  # le GPS n'est pas une preuve de charge
    sur_mine = client.get(f"{API}/vehicles/gps/latest", headers=ops.headers, params={"site_id": site})
    assert [p["vehicle_id"] for p in sur_mine.json()] == [veh1]
    assert (
        client.get(f"{API}/vehicles/gps/latest", headers=ops.headers, params={"site_id": depot}).json() == []
    )
    assert client.get(f"{API}/vehicles/gps/latest", headers=dispatcher_depot.headers).json() == []
    assert client.get(f"{API}/vehicles/gps/latest", headers=outsider.headers).json() == []

    # --- Acquittement de l'alerte -------------------------------------------------------------------
    url = f"{API}/gps/alerts/{alerte['gps_alert_id']}/acknowledge"
    assert client.post(url, headers=dispatcher_depot.headers, json={}).status_code == 404  # hors périmètre
    assert client.post(url, headers=outsider.headers, json={}).status_code == 404
    assert client.post(url, headers=auditor.headers, json={}).status_code == 403  # lecture sans gestion
    assert _alertes(client, dispatcher_depot.headers) == []  # le site DEPOT n'a aucune alerte
    assert len(_alertes(client, auditor.headers, unacknowledged=True)) == 1
    prise = client.post(url, headers=dispatcher.headers, json={"note": "R7 : conducteur prévenu"})
    assert prise.status_code == 200, prise.text
    assert prise.json()["acknowledged_by"] == str(dispatcher.user_id)
    assert client.post(url, headers=dispatcher.headers, json={}).status_code == 409  # déjà acquittée
    assert _alertes(client, auditor.headers, unacknowledged=True) == []

    # --- Notification e-mail : regroupée, livrée une seule fois -------------------------------------
    # Seul l'OPS_MANAGER a choisi un canal ; une ligne par (destinataire, alerte), aucun doublon.
    assert _outbox_lignes(t.tenant_id) == [(ops.user_id, "EMAIL", "PENDING")]
    envoyes, corps = _livrer(t.tenant_id)
    assert envoyes == 1 and any("R7-CAMION-01" in b for b in corps)
    assert _outbox_lignes(t.tenant_id) == [(ops.user_id, "EMAIL", "SENT")]
    assert _livrer(t.tenant_id)[0] == 0  # rien de nouveau à livrer

    # --- Perte de signal : balayage SYSTEM, cibles exactes ------------------------------------------
    panne2 = _position_sql(t, veh2, device2, minutes_ago=30)  # batterie à plat il y a 30 min
    _position_sql(t, veh3, device3, minutes_ago=30)
    _position_sql(t, veh4, "aucun-traceur", minutes_ago=30)
    immobilise = client.post(
        f"{API}/vehicles/{veh3}/status",
        headers={
            **ops.headers,
            "If-Match": client.get(f"{API}/vehicles/{veh3}", headers=ops.headers).headers["ETag"],
        },
        json={"status": "IN_MAINTENANCE", "reason_code": "BREAKDOWN"},
    )
    assert immobilise.status_code == 200, immobilise.text
    assert main(["sweep-gps-signal"]) == 0
    assert main(["sweep-gps-signal"]) == 0  # rejeu : toujours une seule alerte ouverte
    pertes = _alertes(client, ops.headers, kind="SIGNAL_LOST")
    assert len(pertes) == 1
    (panne,) = pertes
    assert panne["vehicle_id"] == veh2 and panne["closed_at"] is None
    assert datetime.fromisoformat(panne["last_measured_at"]) == panne2
    assert datetime.fromisoformat(panne["opened_at"]) > panne2

    # --- Notification de la perte de signal puis retour du signal -----------------------------------
    envoyes, corps = _livrer(t.tenant_id)
    assert envoyes == 1 and any("R7-CAMION-02" in b for b in corps)
    retour = send2(0, 30.0)
    assert retour == 204, retour  # le traceur réapparaît : la position suivante ferme l'alerte
    (fermee,) = _alertes(client, ops.headers, kind="SIGNAL_LOST")
    assert fermee["closed_at"] is not None

    # --- Historique : finalité obligatoire, borné, audité -------------------------------------------
    time.sleep(4.5)  # le dernier point (horodaté +4 s) doit être passé pour figurer dans le trajet
    debut = (now - timedelta(hours=1)).isoformat()
    fin = (now + timedelta(hours=1)).isoformat()
    piste = client.get(
        f"{API}/vehicles/{veh1}/gps/track",
        headers=ops.headers,
        params={"purpose": "INCIDENT_INVESTIGATION", "from": debut, "to": fin},
    )
    assert piste.status_code == 200, piste.text
    piste_json = piste.json()
    assert [p["heading_deg"] for p in piste_json["points"]] == [90.0, None, None, None]
    assert piste_json["signal"] in ("FRESH", "STALE") and piste_json["late_points"] == 0
    assert piste_json["ignored_points"] == 0 and piste_json["truncated"] is False
    assert (
        client.get(
            f"{API}/vehicles/{veh1}/gps/track", headers=ops.headers, params={"from": debut, "to": fin}
        ).status_code
        == 422
    )  # finalité obligatoire
    assert (
        client.get(
            f"{API}/vehicles/{veh1}/gps/track",
            headers=ops.headers,
            params={
                "purpose": "INCIDENT_INVESTIGATION",
                "from": (now - timedelta(hours=30)).isoformat(),
                "to": fin,
            },
        ).status_code
        == 422
    )  # fenêtre > 24 h
    assert (
        client.get(
            f"{API}/vehicles/{veh1}/gps/track",
            headers=ops.headers,
            params={"purpose": "CURIOSITE", "from": debut, "to": fin},
        ).status_code
        == 422
    )  # finalité hors liste
    assert (
        client.get(
            f"{API}/vehicles/{veh1}/gps/track",
            headers=dispatcher.headers,
            params={"purpose": "INCIDENT_INVESTIGATION", "from": debut, "to": fin},
        ).status_code
        == 403
    )  # le dispatcher n'a pas fleet.gps.history
    assert (
        client.get(
            f"{API}/vehicles/{veh1}/gps/track",
            headers=outsider.headers,
            params={"purpose": "INCIDENT_INVESTIGATION", "from": debut, "to": fin},
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"{API}/vehicles/{veh1}/gps/track",
            headers=auditor.headers,
            params={"purpose": "INCIDENT_INVESTIGATION", "from": debut, "to": fin},
        ).status_code
        == 200
    )

    # --- Téléphone (adaptateur simulé) : consentement, relevés, arrêt --------------------------------
    assert (
        client.post(
            f"{API}/me/gps/shares", headers=ops.headers, json={"vehicle_id": veh2, "consent": False}
        ).status_code
        == 422
    )  # le consentement doit être explicite
    partage = client.post(
        f"{API}/me/gps/shares", headers=ops.headers, json={"vehicle_id": veh2, "consent": True}
    )
    assert partage.status_code == 201, partage.text
    share_id = partage.json()["phone_share_id"]
    chemin = f"{API}/me/gps/shares/{share_id}/positions"
    point = {
        "latitude": 9.9,
        "longitude": -12.1,
        "accuracy_m": 8.0,
        "speed_kmh": 12.0,
        "heading_deg": 180.0,
        "recorded_at": datetime.now(UTC).isoformat(),
    }
    assert client.post(chemin, headers=ops.headers, json=point).status_code == 204
    assert client.post(chemin, headers=ops.headers, json=point).status_code == 409  # relevé déjà reçu
    trop_ancien = {**point, "recorded_at": (datetime.now(UTC) - timedelta(minutes=5)).isoformat()}
    assert client.post(chemin, headers=ops.headers, json=trop_ancien).status_code == 422  # > 2 min
    courantes = client.get(f"{API}/vehicles/gps/latest", headers=ops.headers).json()
    ligne2 = next(p for p in courantes if p["vehicle_id"] == veh2)
    assert ligne2["source"] == "PHONE" and ligne2["heading_deg"] == 180.0
    arret = client.post(f"{API}/me/gps/shares/{share_id}/stop", headers=ops.headers)
    assert arret.status_code == 204, arret.text
    assert client.post(f"{API}/me/gps/shares/{share_id}/stop", headers=ops.headers).status_code == 204
    assert client.post(chemin, headers=ops.headers, json=point).status_code == 409  # partage arrêté
    ligne2 = next(
        p
        for p in client.get(f"{API}/vehicles/gps/latest", headers=ops.headers).json()
        if p["vehicle_id"] == veh2
    )
    assert ligne2["source_active"] is False  # plus de partage actif : la source n'est plus vivante

    # --- Chaque écriture clé est auditée -------------------------------------------------------------
    journal = client.get(f"{API}/audit-events", headers=admin, params={"page_size": 200}).json()["items"]
    balayages = [e for e in journal if e["action"] == "fleet.gps.signal_loss.sweep"]
    assert len(balayages) == 1 and balayages[0]["actor_kind"] == "SYSTEM"  # audit si alerte ouverte seulement
    prises = [e for e in journal if e["action"] == "fleet.gps.alert.acknowledge"]
    assert any(
        e["entity_id"] == alerte["gps_alert_id"] and e["reason"] == "R7 : conducteur prévenu" for e in prises
    )
    lectures = client.get(
        f"{API}/audit-events", headers=admin, params={"action": "fleet.gps.track.read"}
    ).json()["items"]
    assert any(
        e["entity_id"] == veh1 and e["reason"] == "INCIDENT_INVESTIGATION"
        for e in lectures  # chaque lecture d'historique est tracée avec sa finalité
    )
