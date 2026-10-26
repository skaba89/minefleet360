"""Aides HTTP : concurrence optimiste (If-Match/ETag, D-19), pagination (CT-9), schémas stricts."""

import re
from typing import Annotated, Any, TypeVar

from fastapi import Depends, Header, Query
from pydantic import BaseModel, ConfigDict, field_validator

from app.core.config import get_settings
from app.core.errors import AppError

T = TypeVar("T")

_ETAG = re.compile(r'^(?:W/)?"(\d{1,9})"$')


class StrictModel(BaseModel):
    """Corps de requête : tout champ inconnu (dont tenant_id) est refusé (422, RBAC §4.2 règle 7)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @field_validator("*", mode="after")
    @classmethod
    def _no_nul_byte(cls, value: Any) -> Any:
        """PostgreSQL refuse l'octet NUL dans un texte : rejet en 422 dès la validation (SEC1B-01)."""
        if isinstance(value, str) and chr(0) in value:
            raise ValueError("caractère NUL interdit")
        return value


def etag(row_version: int) -> str:
    return f'"{row_version}"'


def require_if_match(if_match: Annotated[str | None, Header()] = None) -> int:
    if if_match is None:
        raise AppError("IF_MATCH_REQUIRED")
    match = _ETAG.match(if_match.strip())
    if not match:
        raise AppError("VALIDATION_ERROR", details=[{"field": "If-Match", "type": "format"}])
    return int(match.group(1))


IfMatch = Annotated[int, Depends(require_if_match)]


def check_version(expected: int, current: int) -> None:
    if expected != current:
        raise AppError("VERSION_CONFLICT")


class PageParams(BaseModel):
    page: int
    page_size: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def page_params(
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int | None, Query(ge=1)] = None,
) -> PageParams:
    settings = get_settings()
    size = page_size or settings.page_size_default
    if size > settings.page_size_max:
        raise AppError("VALIDATION_ERROR", details=[{"field": "page_size", "type": "less_than_equal"}])
    return PageParams(page=page, page_size=size)


Pagination = Annotated[PageParams, Depends(page_params)]


class Page[T](BaseModel):
    items: list[T]
    page: int
    page_size: int
    total: int
