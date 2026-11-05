"""Abonnement LISTEN/NOTIFY partagé par worker, sans conserver de positions.

Une seule connexion PostgreSQL autocommit par processus avec abonnés actifs.
Les notifications ne sont PAS des autorisations : elles déclenchent une lecture
sous RLS, dans une transaction distincte. Les pertes sont compensées par la
relecture périodique du snapshot initial complet.
"""

import asyncio
import logging
import uuid
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import psycopg

from app.core.config import get_settings
from app.fleet.gps_notifications import GPS_NOTIFICATION_CHANNEL

logger = logging.getLogger("minefleet.gps.notifications")


class GpsNotificationHub:
    """Un abonné DB par processus, files coalescentes, aucun contenu métier."""

    def __init__(self) -> None:
        self._subscribers: dict[uuid.UUID, set[asyncio.Queue[None]]] = defaultdict(set)
        self._task: asyncio.Task[None] | None = None

    def _broadcast(self, tenant_id: uuid.UUID) -> None:
        for queue in tuple(self._subscribers.get(tenant_id, ())):
            if queue.empty():
                queue.put_nowait(None)

    def _wake_all(self) -> None:
        for tenant_id in tuple(self._subscribers):
            self._broadcast(tenant_id)

    async def _listen(self) -> None:
        # Une connexion de service distincte du pool RLS, ouverte dans le worker
        # actif (jamais avant le fork). Aucune coordonnée n'est transmise.
        while self._subscribers:
            try:
                url = get_settings().database_url().set(drivername="postgresql").render_as_string(
                    hide_password=False
                )
                async with await psycopg.AsyncConnection.connect(
                    url, autocommit=True, connect_timeout=5
                ) as connection:
                    await connection.execute(f"LISTEN {GPS_NOTIFICATION_CHANNEL}")
                    # Relecture immédiate après chaque reconnexion : tous les
                    # abonnés rechargent leur propre snapshot sous RLS.
                    self._wake_all()
                    while self._subscribers:
                        async for message in connection.notifies(timeout=10):
                            try:
                                tenant_id = uuid.UUID(message.payload)
                            except ValueError:
                                continue
                            if message.channel == GPS_NOTIFICATION_CHANNEL:
                                self._broadcast(tenant_id)
            except asyncio.CancelledError:
                raise
            except (psycopg.Error, OSError):
                # Ne jamais logger l'URL avec mot de passe, ni le payload.
                logger.warning("GPS notification listener indisponible")
                self._wake_all()
                await asyncio.sleep(2)

    @asynccontextmanager
    async def subscribe(self, tenant_id: uuid.UUID) -> AsyncIterator[asyncio.Queue[None]]:
        queue: asyncio.Queue[None] = asyncio.Queue(maxsize=1)
        self._subscribers[tenant_id].add(queue)
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._listen())
        try:
            yield queue
        finally:
            subscribers = self._subscribers.get(tenant_id)
            if subscribers is not None:
                subscribers.discard(queue)
                if not subscribers:
                    del self._subscribers[tenant_id]
            if not self._subscribers and self._task is not None:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
                self._task = None


gps_notification_hub = GpsNotificationHub()
