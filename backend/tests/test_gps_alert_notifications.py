"""Notifications des alertes GPS (0063) : choix e-mail / SMS, destinataires, anti-avalanche, livraison."""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import new_session
from app.core.email import MemoryEmailSender
from app.core.sms import MemorySmsSender
from app.fleet.gps_alert_notify import deliver_pending
from tests.conftest import API, Api
from tests.test_assignment import World, _vehicle, w  # noqa: F401

PHONE = "+224620000001"  # numéro fictif


def _tracker(client: TestClient, w: World, vehicle: str):  # type: ignore[no-untyped-def]  # noqa: F811
    device = "fictif-" + uuid.uuid4().hex
    token = client.post(
        f"{API}/vehicles/{vehicle}/gps/tracker", headers=w.ops.headers, json={"device_id": device}
    ).json()["token"]
    start = datetime.now(UTC)
    seq = {"n": 0}

    def send(seconds: int, speed: float) -> None:
        seq["n"] += 1
        resp = client.post(
            f"{API}/gps/telemetry",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "device_id": device,
                "sequence": seq["n"],
                "latitude": 10.0,
                "longitude": -12.0,
                "speed_kmh": speed,
                "recorded_at": (start + timedelta(seconds=seconds)).isoformat(),
            },
        )
        assert resp.status_code == 204, resp.text

    return send


def _outbox(tenant_id: uuid.UUID) -> list[tuple[uuid.UUID, str, str, str | None]]:
    db = new_session()
    try:
        db.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)})
        rows = db.execute(
            text(
                "SELECT user_account_id, channel, status, last_error_code FROM notification_outbox "
                "WHERE tenant_id = :t ORDER BY channel, user_account_id"
            ),
            {"t": tenant_id},
        ).all()
        return [tuple(r) for r in rows]  # type: ignore[misc]
    finally:
        db.close()


def _deliver(tenant_id: uuid.UUID, email: MemoryEmailSender, sms: MemorySmsSender | None):  # type: ignore[no-untyped-def]
    db = new_session()
    try:
        db.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)})
        report = deliver_pending(db, tenant_id, settings=get_settings(), email_sender=email, sms_sender=sms)
        db.commit()
        return report
    finally:
        db.close()


def test_preferences_are_personal_and_validated(client: TestClient, w: World) -> None:  # noqa: F811
    url = f"{API}/me/alert-notifications"
    initial = client.get(url, headers=w.ops.headers).json()
    assert (initial["email_enabled"], initial["sms_enabled"], initial["phone_e164"]) == (False, False, None)
    for body in (
        {"email_enabled": False, "sms_enabled": True},  # SMS sans numéro
        {"email_enabled": False, "sms_enabled": True, "phone_e164": "0620000001"},  # pas au format E.164
        {"email_enabled": "true", "sms_enabled": False},
        {"email_enabled": True, "sms_enabled": False, "user_account_id": str(uuid.uuid4())},
    ):
        assert client.put(url, headers=w.ops.headers, json=body).status_code == 422, body
    saved = client.put(
        url, headers=w.ops.headers, json={"email_enabled": True, "sms_enabled": True, "phone_e164": PHONE}
    )
    assert saved.status_code == 200 and saved.json()["phone_e164"] == PHONE
    assert client.get(url, headers=w.dispatcher.headers).json()["email_enabled"] is False  # réglage personnel
    events = client.get(f"{API}/audit-events", headers=w.t.admin.headers, params={"page_size": 200}).json()[
        "items"
    ]
    assert any(e["action"] == "fleet.gps.alert_notification.update" for e in events)
    assert PHONE not in str(events)  # jamais de numéro dans l'audit


def test_alert_notifications_reach_chosen_channels_once_and_are_delivered(
    client: TestClient,
    api: Api,
    w: World,  # noqa: F811
) -> None:
    url = f"{API}/me/alert-notifications"
    client.put(
        url, headers=w.ops.headers, json={"email_enabled": True, "sms_enabled": True, "phone_e164": PHONE}
    )
    client.put(url, headers=w.dispatcher.headers, json={"email_enabled": True, "sms_enabled": False})
    other_site = api.user(w.t, "DISPATCHER", "SITE", "S2")
    client.put(url, headers=other_site.headers, json={"email_enabled": True, "sms_enabled": False})
    silent = api.user(w.t, "HSE")  # lit les alertes mais n'a rien choisi
    assert client.get(url, headers=silent.headers).status_code == 200

    client.put(
        f"{API}/sites/{w.t.sites['S1']}/gps-policy", headers=w.ops.headers, json={"speed_limit_kmh": 50}
    )
    vehicle = _vehicle(client, w)
    send = _tracker(client, w, vehicle)
    send(5, 70.0)  # excès : alerte ouverte
    queued = _outbox(w.t.tenant_id)
    assert sorted((str(u), c) for u, c, _, _ in queued) == sorted(
        [(str(w.ops.user_id), "EMAIL"), (str(w.ops.user_id), "SMS"), (str(w.dispatcher.user_id), "EMAIL")]
    )
    send(10, 40.0)  # fin de l'excès
    send(15, 80.0)  # nouvel excès moins de 30 min plus tard : anti-avalanche, rien de plus
    assert len(_outbox(w.t.tenant_id)) == 3

    email, sms = MemoryEmailSender(), MemorySmsSender()
    report = _deliver(w.t.tenant_id, email, sms)
    assert (report.sent, report.failed) == (3, 0)
    assert sorted(m.to for m in email.outbox) == sorted([w.ops.email, w.dispatcher.email])
    (message,) = sms.outbox
    assert message.to == PHONE and "Excès de vitesse" in message.body and "70 km/h pour 50.0" in message.body
    assert "10.0" not in message.body and "-12.0" not in message.body  # aucune coordonnée
    assert "/flotte-gps/alertes" in message.body
    assert all(status == "SENT" for _, _, status, _ in _outbox(w.t.tenant_id))
    assert _deliver(w.t.tenant_id, MemoryEmailSender(), MemorySmsSender()).sent == 0  # déjà livrées


def test_sms_without_provider_fails_explicitly(client: TestClient, api: Api, w: World) -> None:  # noqa: F811
    client.put(
        f"{API}/me/alert-notifications",
        headers=w.ops.headers,
        json={"email_enabled": False, "sms_enabled": True, "phone_e164": PHONE},
    )
    assert client.get(f"{API}/me/alert-notifications", headers=w.ops.headers).json()["sms_available"] is False
    client.put(
        f"{API}/sites/{w.t.sites['S1']}/gps-policy", headers=w.ops.headers, json={"speed_limit_kmh": 20}
    )
    _tracker(client, w, _vehicle(client, w))(5, 45.0)
    report = _deliver(w.t.tenant_id, MemoryEmailSender(), None)
    assert (report.sent, report.failed) == (0, 1)
    ((_, channel, status, code),) = _outbox(w.t.tenant_id)
    assert (channel, status, code) == ("SMS", "FAILED", "SMS_PROVIDER_NOT_CONFIGURED")
    # Autre société : ni ligne en file, ni préférences héritées.
    other = api.tenant()
    outsider = api.user(other, "OPS_MANAGER")
    assert _outbox(other.tenant_id) == []
    assert (
        client.get(f"{API}/me/alert-notifications", headers=outsider.headers).json()["sms_enabled"] is False
    )


def test_many_alerts_are_grouped_into_one_message_per_channel(client: TestClient, w: World) -> None:  # noqa: F811
    client.put(
        f"{API}/me/alert-notifications",
        headers=w.ops.headers,
        json={"email_enabled": True, "sms_enabled": True, "phone_e164": PHONE},
    )
    client.put(
        f"{API}/sites/{w.t.sites['S1']}/gps-policy", headers=w.ops.headers, json={"speed_limit_kmh": 30}
    )
    for _ in range(3):
        _tracker(client, w, _vehicle(client, w))(5, 50.0)
    assert len(_outbox(w.t.tenant_id)) == 6  # 3 alertes × 2 canaux, en file
    email, sms = MemoryEmailSender(), MemorySmsSender()
    report = _deliver(w.t.tenant_id, email, sms)
    assert report.sent == 2  # un e-mail et un SMS, pas six messages
    (mail,) = email.outbox
    assert (
        mail.subject == "MineFleet 360 — 3 nouvelles alertes GPS" and mail.body.count("Excès de vitesse") == 3
    )
    (text_message,) = sms.outbox
    assert "3 alertes GPS (3 excès de vitesse)" in text_message.body and len(text_message.body) <= 160
    assert all(status == "SENT" for _, _, status, _ in _outbox(w.t.tenant_id))
