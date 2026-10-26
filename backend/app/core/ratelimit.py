"""Compteurs partagés PostgreSQL, indépendants du rollback de la requête d'authentification."""

import hashlib
import hmac
from datetime import datetime, timedelta
from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.core.config import get_settings


@lru_cache(maxsize=1)
def _limiter_engine() -> Engine:
    # Pool séparé : une requête détenant sa transaction métier ne doit pas attendre une seconde
    # connexion du même pool pour enregistrer un échec qui survivra à son rollback.
    return create_engine(
        get_settings().database_url(),
        pool_pre_ping=True,
        hide_parameters=True,
        pool_size=2,
        max_overflow=5,
        connect_args={"options": "-c lock_timeout=5000 -c statement_timeout=10000"},
    )


@lru_cache(maxsize=1)
def _test_owner_engine() -> Engine:
    return create_engine(get_settings().database_url(owner=True), hide_parameters=True)


class FailureLimiter:
    """Fenêtre glissante partagée; clés HMAC, cardinalité et rétention bornées côté PostgreSQL."""

    def __init__(self, namespace: str, max_failures: int, window: timedelta) -> None:
        self.namespace = namespace
        self.max_failures = max_failures
        self.window = window

    def _key(self, key: str) -> str:
        secret = get_settings().jwt_secret.get_secret_value().encode()
        return hmac.new(secret, f"{self.namespace}:{key}".encode(), hashlib.sha256).hexdigest()

    def _call(self, operation: str, key: str) -> bool:
        with _limiter_engine().begin() as connection:
            return bool(
                connection.execute(
                    text("SELECT app.auth_limit(:ns, :key, :maximum, :window, :operation)"),
                    {
                        "ns": self.namespace,
                        "key": self._key(key),
                        "maximum": self.max_failures,
                        "window": int(self.window.total_seconds()),
                        "operation": operation,
                    },
                ).scalar_one()
            )

    def is_blocked(self, key: str, now: datetime) -> bool:
        del now  # horloge DB partagée : une instance ne peut avancer l'expiration des autres
        return self._call("check", key)

    def record_failure(self, key: str, now: datetime) -> None:
        del now
        self._call("record", key)

    def reset(self, key: str) -> None:
        with _limiter_engine().begin() as connection:
            connection.execute(
                text("SELECT app.auth_limit_reset(:ns, :key)"),
                {"ns": self.namespace, "key": self._key(key)},
            )

    def clear(self) -> None:
        """Harnais seulement : le rôle API ne peut jamais vider globalement les compteurs."""
        settings = get_settings()
        if settings.env != "test" or not settings.db_name.endswith("_test"):
            raise RuntimeError("Le vidage des limites est réservé à une base *_test en MF_ENV=test")
        with _test_owner_engine().begin() as connection:
            connection.execute(
                text("DELETE FROM app.auth_failure_bucket WHERE namespace = :ns"), {"ns": self.namespace}
            )
