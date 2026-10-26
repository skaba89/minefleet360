"""Catalogue unique des codes d'erreur (D-05, D-26) et traduction en réponses HTTP normalisées.

Corps : {code, message_fr, details, request_id} (USER_STORIES CT-3). Aucun détail technique exposé.
"""

import logging
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DataError, DBAPIError, IntegrityError
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
    "DUPLICATE_FLEET_NUMBER": ErrorDef(
        409, "Ce numéro de parc est déjà utilisé (y compris par un véhicule réformé)."
    ),
    "DUPLICATE_REGISTRATION": ErrorDef(409, "Cette immatriculation est déjà utilisée."),
    "DUPLICATE_SERIAL_NUMBER": ErrorDef(409, "Ce numéro de série est déjà enregistré pour cette marque."),
    "DUPLICATE_EMPLOYEE_NUMBER": ErrorDef(409, "Ce matricule est déjà utilisé."),
    "DUPLICATE_LICENSE": ErrorDef(409, "Ce permis est déjà enregistré pour ce conducteur."),
    "DUPLICATE_QUALIFICATION": ErrorDef(409, "Une habilitation valide se chevauche déjà sur cette période."),
    "OPEN_ASSIGNMENTS_EXIST": ErrorDef(
        409, "Des affectations planifiées ou actives doivent d'abord être clôturées."
    ),
    "VEHICLE_ASSIGNMENT_OVERLAP": ErrorDef(409, "Le véhicule est déjà affecté sur cette période."),
    "DRIVER_ASSIGNMENT_OVERLAP": ErrorDef(409, "Le conducteur est déjà affecté sur cette période."),
    "ASSIGNMENT_STATE_INVALID": ErrorDef(
        409, "Cette action n'est pas possible dans l'état de l'affectation."
    ),
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
    "VEHICLE_STATUS_TRANSITION_INVALID": ErrorDef(
        422, "Ce changement de statut du véhicule n'est pas autorisé."
    ),
    "STATUS_REASON_REQUIRED": ErrorDef(422, "Un motif est obligatoire pour ce statut."),
    # D-29 : un seul code d'inéligibilité, `details.reasons[]` liste tous les motifs.
    "ASSIGNMENT_NOT_ELIGIBLE": ErrorDef(422, "L'affectation ne respecte pas les conditions d'éligibilité."),
    "END_BEFORE_START": ErrorDef(422, "La fin doit être postérieure au début."),
    "END_IN_FUTURE": ErrorDef(422, "La date de fin ne peut pas être dans le futur."),
    "END_BACKDATED": ErrorDef(
        422, "La fin ne peut pas être antérieure à maintenant, sauf à la date de fin prévue."
    ),
    # 503
    "SERVICE_BUSY": ErrorDef(503, "Service momentanément occupé. Réessayez dans quelques instants."),
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
    "uq_vehicle_tenant_fleet_number": "DUPLICATE_FLEET_NUMBER",
    "uq_vehicle_tenant_registration": "DUPLICATE_REGISTRATION",
    "uq_vehicle_tenant_serial": "DUPLICATE_SERIAL_NUMBER",
    "uq_driver_tenant_employee": "DUPLICATE_EMPLOYEE_NUMBER",
    "uq_driver_license_issue": "DUPLICATE_LICENSE",
    "ex_dq_no_overlap": "DUPLICATE_QUALIFICATION",
    "ex_va_vehicle_no_overlap": "VEHICLE_ASSIGNMENT_OVERLAP",
    "ex_va_driver_no_overlap": "DRIVER_ASSIGNMENT_OVERLAP",
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
        logger.warning("check_constraint_violation", extra={"constraint": name})
        return AppError("VALIDATION_ERROR")  # nom de contrainte journalisé, jamais exposé (QA1B)
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
            # Sans exc_info : le DETAIL PostgreSQL peut contenir des valeurs personnelles (SEC1B-01).
            logger.error(
                "integrity_error_unmapped",
                extra={"sqlstate": getattr(exc.orig, "sqlstate", None), "constraint": _constraint_name(exc)},
            )
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

    @app.exception_handler(DBAPIError)
    async def _database(_: Request, exc: DBAPIError) -> JSONResponse:
        """Erreurs base hors intégrité : jamais de requête, paramètre ni DETAIL dans les logs (SEC1B-01)."""
        sqlstate = getattr(exc.orig, "sqlstate", None) or ""
        logger.error("database_error", extra={"sqlstate": sqlstate, "error_type": type(exc.orig).__name__})
        if isinstance(exc, DataError) or sqlstate.startswith("22"):  # données invalides (octet NUL…)
            return error_response("VALIDATION_ERROR")
        if sqlstate in ("40001", "40P01"):  # sérialisation, interblocage
            return error_response("CONFLICT")
        if sqlstate in ("MF003", "MF004"):  # gardes d'affectation (course contournant le contrôle applicatif)
            return error_response("CONFLICT")
        if sqlstate in ("55P03", "57014"):  # délai de verrou ou de requête dépassé
            return error_response("SERVICE_BUSY", headers={"Retry-After": "2"})
        return error_response("INTERNAL_ERROR")

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_error", extra={"error_type": type(exc).__name__})
        return error_response("INTERNAL_ERROR")
