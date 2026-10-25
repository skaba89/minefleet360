"""Catalogue unique des codes d'erreur (D-05, D-26) et traduction en réponses HTTP normalisées.

Corps : {code, message_fr, details, request_id} (USER_STORIES CT-3). Aucun détail technique exposé.
"""

import logging
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.request_context import get_request_id

logger = logging.getLogger("minefleet.errors")


@dataclass(frozen=True)
class ErrorDef:
    status: int
    message_fr: str


CATALOG: dict[str, ErrorDef] = {
    # 401
    "AUTH_REQUIRED": ErrorDef(401, "Authentification requise."),
    "INVALID_CREDENTIALS": ErrorDef(401, "Identifiants invalides."),
    # 403
    "PERMISSION_DENIED": ErrorDef(403, "Vous n'avez pas l'autorisation d'effectuer cette action."),
    # 404
    "NOT_FOUND": ErrorDef(404, "Ressource introuvable."),
    # 405 (méthode non prise en charge sur une route existante)
    "METHOD_NOT_ALLOWED": ErrorDef(405, "Méthode non autorisée."),
    # 409
    "VERSION_CONFLICT": ErrorDef(409, "La ressource a été modifiée entre-temps. Rechargez puis réessayez."),
    "DUPLICATE_WORKSPACE_CODE": ErrorDef(409, "Ce code d'espace de travail est déjà utilisé."),
    "DUPLICATE_TENANT_NAME": ErrorDef(409, "Un tenant porte déjà ce nom."),
    "DUPLICATE_SITE_CODE": ErrorDef(409, "Un site porte déjà ce code."),
    "DUPLICATE_EMAIL": ErrorDef(409, "Un utilisateur utilise déjà cette adresse e-mail."),
    "DUPLICATE_ROLE_ASSIGNMENT": ErrorDef(409, "Cette attribution de rôle existe déjà."),
    "LAST_TENANT_ADMIN": ErrorDef(409, "Le dernier administrateur actif du tenant ne peut pas être retiré."),
    "SITE_HAS_ACTIVE_RESOURCES": ErrorDef(409, "Le site possède encore des ressources actives."),
    "STATE_TRANSITION_INVALID": ErrorDef(409, "Cette action n'est pas possible dans l'état actuel."),
    "CONFLICT": ErrorDef(409, "Conflit avec l'état actuel des données."),
    # 422
    "VALIDATION_ERROR": ErrorDef(422, "Les données envoyées sont invalides."),
    "IF_MATCH_REQUIRED": ErrorDef(422, "L'en-tête If-Match est obligatoire pour une modification."),
    "REFERENCE_NOT_FOUND": ErrorDef(422, "Une ressource référencée est introuvable."),
    "SELF_ROLE_CHANGE_FORBIDDEN": ErrorDef(
        422, "Vous ne pouvez pas modifier vos propres droits ni désactiver votre propre compte."
    ),
    "ROLE_NOT_ASSIGNABLE": ErrorDef(422, "Ce rôle ne peut pas être attribué."),
    "SCOPE_NOT_ALLOWED_FOR_ROLE": ErrorDef(422, "Cette portée n'est pas autorisée pour ce rôle."),
    "PASSWORD_POLICY_VIOLATION": ErrorDef(422, "Le mot de passe ne respecte pas la politique de sécurité."),
    "TOKEN_INVALID": ErrorDef(422, "Ce lien est invalide ou a expiré."),
    "TENANT_CODE_RESERVED": ErrorDef(422, "Ce code d'espace de travail est réservé."),
    # 429
    "RATE_LIMITED": ErrorDef(429, "Trop de tentatives. Réessayez plus tard."),
    # 500
    "INTERNAL_ERROR": ErrorDef(500, "Erreur interne. Si le problème persiste, contactez le support."),
}

# Contraintes de base → code métier (MODELE_PHYSIQUE_LOT1 §7). Messages sans révéler d'autre tenant.
CONSTRAINT_CODES: dict[str, str] = {
    "uq_tenant_code": "DUPLICATE_WORKSPACE_CODE",
    "uq_tenant_legal_name_norm": "DUPLICATE_TENANT_NAME",
    "uq_site_tenant_code": "DUPLICATE_SITE_CODE",
    "uq_user_account_tenant_email": "DUPLICATE_EMAIL",
    "ex_ura_no_duplicate": "DUPLICATE_ROLE_ASSIGNMENT",
}


class AppError(Exception):
    def __init__(
        self,
        code: str,
        details: Any = None,
        message_fr: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        if code not in CATALOG:
            raise ValueError(f"Code d'erreur hors catalogue : {code}")
        self.code = code
        self.status = CATALOG[code].status
        self.message_fr = message_fr or CATALOG[code].message_fr
        self.details = details
        self.headers = headers
        super().__init__(code)


def error_body(code: str, details: Any = None, message_fr: str | None = None) -> dict[str, Any]:
    return {
        "code": code,
        "message_fr": message_fr or CATALOG[code].message_fr,
        "details": details,
        "request_id": get_request_id(),
    }


def error_response(
    code: str,
    details: Any = None,
    message_fr: str | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    merged = dict(headers or {})
    if CATALOG[code].status == 401:
        merged.setdefault("WWW-Authenticate", "Bearer")
    return JSONResponse(
        status_code=CATALOG[code].status,
        content=error_body(code, details, message_fr),
        headers=merged or None,
    )


def _constraint_name(exc: DBAPIError) -> str | None:
    diag = getattr(exc.orig, "diag", None)
    name = getattr(diag, "constraint_name", None)
    return name if isinstance(name, str) else None


def map_integrity_error(exc: IntegrityError) -> AppError:
    sqlstate = getattr(exc.orig, "sqlstate", None)
    name = _constraint_name(exc)
    if name and name in CONSTRAINT_CODES:
        return AppError(CONSTRAINT_CODES[name])
    if sqlstate == "23503":
        return AppError("REFERENCE_NOT_FOUND")
    if sqlstate in ("23505", "23P01"):
        return AppError("CONFLICT")
    if sqlstate == "23514":
        return AppError("VALIDATION_ERROR")
    raise exc


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return error_response(exc.code, exc.details, exc.message_fr, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"field": ".".join(str(p) for p in err.get("loc", ())[1:]), "type": err.get("type")}
            for err in exc.errors()
        ]
        return error_response("VALIDATION_ERROR", details)

    @app.exception_handler(IntegrityError)
    async def _integrity(_: Request, exc: IntegrityError) -> JSONResponse:
        try:
            mapped = map_integrity_error(exc)
        except IntegrityError:
            logger.exception("integrity_error_unmapped")
            return error_response("INTERNAL_ERROR")
        return error_response(mapped.code, mapped.details)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code == 404:
            return error_response("NOT_FOUND")
        if exc.status_code == 405:
            return error_response("METHOD_NOT_ALLOWED")
        logger.error("http_exception", extra={"status": exc.status_code})
        return error_response("INTERNAL_ERROR")

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_error", extra={"error_type": type(exc).__name__})
        return error_response("INTERNAL_ERROR")
