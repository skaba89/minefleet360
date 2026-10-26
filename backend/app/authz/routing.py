"""Classe de route : expose la permission déclarée par `Require` dans OpenAPI (`x-permission`) et refuse
les paramètres de requête inconnus (422 VALIDATION_ERROR, CT-9 ; `tenant_id` en paramètre refusé, CT-1).
"""

from collections.abc import Callable, Iterator
from typing import Any

from fastapi import Request, params
from fastapi.dependencies.models import Dependant
from fastapi.dependencies.utils import get_parameterless_sub_dependant
from fastapi.routing import APIRoute

from app.authz.dependencies import Require
from app.core.errors import AppError


def iter_requirements(dependant: Dependant) -> Iterator[Require]:
    for dep in dependant.dependencies:
        if isinstance(dep.call, Require):
            yield dep.call
        yield from iter_requirements(dep)


def _query_names(dependant: Dependant) -> set[str]:
    names = {field.alias for field in dependant.query_params}
    for dep in dependant.dependencies:
        names |= _query_names(dep)
    return names


def _strict_query(allowed: frozenset[str]) -> Callable[[Request], None]:
    def reject_unknown_query(request: Request) -> None:
        unknown = sorted(set(request.query_params) - allowed)
        if unknown:
            raise AppError(
                "VALIDATION_ERROR", details=[{"field": name, "type": "unknown_parameter"} for name in unknown]
            )

    return reject_unknown_query


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
        # Ajoutée en DERNIER : évaluée après 401/403 (ordre D-05a).
        check = _strict_query(frozenset(_query_names(self.dependant)))
        self.dependant.dependencies.append(
            get_parameterless_sub_dependant(depends=params.Depends(check), path=self.path_format)
        )
