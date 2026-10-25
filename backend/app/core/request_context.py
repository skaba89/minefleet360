"""Métadonnées de requête (corrélation, IP, agent) pour logs structurés, audit et corps d'erreur."""

import uuid
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True)
class RequestMeta:
    request_id: uuid.UUID
    ip_address: str | None
    user_agent: str | None


_meta: ContextVar[RequestMeta | None] = ContextVar("request_meta", default=None)


def set_request_meta(meta: RequestMeta | None) -> None:
    _meta.set(meta)


def get_request_meta() -> RequestMeta | None:
    return _meta.get()


def get_request_id() -> str | None:
    meta = _meta.get()
    return str(meta.request_id) if meta else None
