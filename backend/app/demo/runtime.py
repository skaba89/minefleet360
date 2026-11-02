"""Exécution d'un service sous l'identité d'un compte DEMO (session ouverte puis fermée à chaque appel)."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from app.authz.dependencies import Authorized
from app.seed import _Actor


@contextmanager
def as_actor(actor: _Actor, permission: str) -> Iterator[Authorized]:
    auth = actor.auth(permission)
    try:
        yield auth
    finally:
        auth.db.close()


def call[T](actor: _Actor, permission: str, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Service applicatif : `fn(auth, *args)`."""
    with as_actor(actor, permission) as auth:
        return fn(auth, *args, **kwargs)


def route[T](actor: _Actor, permission: str, fn: Callable[..., T], *args: Any) -> T:
    """Fonction de routeur dont la logique métier est portée par la route : `fn(*args, auth)`."""
    with as_actor(actor, permission) as auth:
        return fn(*args, auth)
