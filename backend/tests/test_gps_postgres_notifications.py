"""Intégration NOTIFY réelle : COMMIT, ROLLBACK et fan-out tenant.

Exécuté uniquement par la suite tests/ sur la base éphémère *_test.
Aucun secret ou payload GPS n'est enregistré par ces tests.
"""

import asyncio
import uuid

import psycopg

from app.core.config import get_settings
from app.core.db import new_session
from app.fleet.gps_notification_listener import GpsNotificationHub
from app.fleet.gps_notifications import GPS_NOTIFICATION_CHANNEL, notify_gps_position


def _dsn() -> str:
    settings = get_settings()
    assert settings.env == "test" and settings.db_name.endswith("_test")
    return settings.database_url().set(drivername="postgresql").render_as_string(hide_password=False)


def _send(tenant_id: uuid.UUID, *, commit: bool) -> None:
    with new_session() as session:
        notify_gps_position(session, tenant_id)
        if commit:
            session.commit()
        else:
            session.rollback()


def test_notify_delivered_after_commit_not_before() -> None:
    tenant_id = uuid.uuid4()
    with psycopg.connect(_dsn(), autocommit=True) as listener:
        listener.execute(f"LISTEN {GPS_NOTIFICATION_CHANNEL}")
        with new_session() as sender:
            notify_gps_position(sender, tenant_id)
            # PostgreSQL n'émet rien avant la validation de cette transaction.
            assert list(listener.notifies(timeout=0.1, stop_after=1)) == []
            sender.commit()
        messages = list(listener.notifies(timeout=2, stop_after=1))
    assert len(messages) == 1
    assert messages[0].channel == GPS_NOTIFICATION_CHANNEL
    assert messages[0].payload == str(tenant_id)


def test_notify_rollback_emits_nothing() -> None:
    tenant_id = uuid.uuid4()
    with psycopg.connect(_dsn(), autocommit=True) as listener:
        listener.execute(f"LISTEN {GPS_NOTIFICATION_CHANNEL}")
        _send(tenant_id, commit=False)
        assert list(listener.notifies(timeout=0.3, stop_after=1)) == []


def test_hub_dispatches_only_to_matching_tenant_with_real_database() -> None:
    async def scenario() -> None:
        tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
        hub = GpsNotificationHub()
        async with hub.subscribe(tenant_a) as a, hub.subscribe(tenant_b) as b:
            # L'abonnement démarre son propre listener en arrière-plan.
            # Attendre son réveil initial : LISTEN est alors effectivement actif.
            await asyncio.wait_for(a.get(), timeout=5)
            await asyncio.wait_for(b.get(), timeout=5)
            await asyncio.to_thread(_send, tenant_a, commit=True)
            await asyncio.wait_for(a.get(), timeout=5)
            assert b.empty()
            # Une transaction annulée ne doit réveiller aucun abonnement.
            await asyncio.to_thread(_send, tenant_a, commit=False)
            assert b.empty()
            assert a.empty()

    asyncio.run(scenario())
