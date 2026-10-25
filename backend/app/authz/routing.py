"""Classe de route : expose la permission déclarée par `Require` dans OpenAPI (`x-permission`)."""

from collections.abc import Iterator
from typing import Any

from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute

from app.authz.dependencies import Require


def iter_requirements(dependant: Dependant) -> Iterator[Require]:
    for dep in dependant.dependencies:
        if isinstance(dep.call, Require):
            yield dep.call
        yield from iter_requirements(dep)


class SecuredRoute(APIRoute):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        permissions = sorted({req.permission for req in iter_requirements(self.dependant)})
        if len(permissions) > 1:
            raise ValueError(f"{self.path} : une seule permission par route ({permissions})")
        if permissions:
            self.permission: str | None = permissions[0]
            self.openapi_extra = {**(self.openapi_extra or {}), "x-permission": permissions[0]}
        else:
            self.permission = None
