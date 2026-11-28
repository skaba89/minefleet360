"""Survey tolerance qualification lifecycle; never an operational authorization.

A tolerance is a measured, justified and independently approved site value. There
is no universal tolerance: each qualification binds one tolerance to its survey
provenance, method, instrument precision, date, responsible surveyor, referential
version and technical justification. The service owns the current-state checks
(the triggers only guard tenant scope and field immutability).
"""

from dataclasses import dataclass
from datetime import date
from math import isfinite
from uuid import UUID

from sqlalchemy import text

from app.audit.contracts import record
from app.authz.dependencies import Authorized
from app.authz.principal import evaluate
from app.core.errors import AppError


@dataclass(frozen=True)
class QualifiedTolerance:
    qualification_id: UUID
    tolerance_m: float


def _bounded(value: str, limit: int) -> str:
    value = value.strip()
    if not 1 <= len(value) <= limit or chr(0) in value:
        raise AppError("VALIDATION_ERROR")
    return value


def _require_manager(auth: Authorized, site_id: UUID) -> None:
    scope = evaluate(auth.principal, "dispatch.location.manage")
    if auth.principal.tenant_kind != "CUSTOMER" or scope is None or not scope.covers_site(site_id):
        raise AppError("PERMISSION_DENIED")
    if auth.principal.mfa_enrollment_pending:
        raise AppError("MFA_ENROLLMENT_REQUIRED")


def propose_tolerance_qualification(
    auth: Authorized,
    *,
    site_id: UUID,
    tolerance_m: float,
    survey_source: str,
    measurement_method: str,
    instrument_precision_m: float,
    surveyed_on: date,
    referential_version: str,
    justification: str,
    responsible_user_id: UUID,
) -> UUID:
    """Stage a PROPOSED qualification and audit together; caller owns commit/rollback.

    Temporary internal policy: location management permission on this site, as for
    readiness reports, until dedicated permissions are introduced. Proposing is not
    approving: an independent approver records the approval afterwards.
    """
    _require_manager(auth, site_id)
    if not isfinite(tolerance_m) or tolerance_m < 0:
        raise AppError("VALIDATION_ERROR")
    if not isfinite(instrument_precision_m) or instrument_precision_m < 0:
        raise AppError("VALIDATION_ERROR")
    if surveyed_on > date.today():
        raise AppError("VALIDATION_ERROR")
    survey_source = _bounded(survey_source, 100)
    measurement_method = _bounded(measurement_method, 100)
    referential_version = _bounded(referential_version, 100)
    justification = _bounded(justification, 500)
    if not auth.db.execute(
        text("SELECT 1 FROM user_account WHERE tenant_id = :tenant AND user_account_id = :user"),
        {"tenant": auth.tenant_id, "user": responsible_user_id},
    ).scalar_one_or_none():
        raise AppError("NOT_FOUND")
    qualification_id: UUID = auth.db.execute(
        text(
            """
            INSERT INTO mining_tolerance_qualification
              (tenant_id, site_id, tolerance_m, survey_source, measurement_method,
               instrument_precision_m, surveyed_on, responsible_user_id, referential_version,
               justification, proposed_by)
            VALUES (:tenant, :site, :tolerance, :source, :method, :precision, :surveyed_on,
                    :responsible, :referential, :justification, :actor)
            RETURNING qualification_id
            """
        ),
        {
            "tenant": auth.tenant_id,
            "site": site_id,
            "tolerance": tolerance_m,
            "source": survey_source,
            "method": measurement_method,
            "precision": instrument_precision_m,
            "surveyed_on": surveyed_on,
            "responsible": responsible_user_id,
            "referential": referential_version,
            "justification": justification,
            "actor": auth.user_id,
        },
    ).scalar_one()
    record(
        auth.db,
        tenant_id=auth.tenant_id,
        action="mining_tolerance_qualification.propose",
        entity_type="mining_tolerance_qualification",
        entity_id=qualification_id,
        site_id=site_id,
        actor_user_id=auth.user_id,
        after={
            "tolerance_m": tolerance_m,
            "survey_source": survey_source,
            "measurement_method": measurement_method,
            "referential_version": referential_version,
            "responsible_user_id": str(responsible_user_id),
        },
    )
    return qualification_id


def approve_tolerance_qualification(auth: Authorized, *, site_id: UUID, qualification_id: UUID) -> UUID:
    """Approve a PROPOSED qualification; caller owns commit/rollback.

    The approver must be independent from the proposer and the responsible
    surveyor. The conditional UPDATE is the concurrency guard: a concurrent
    decision either wins and returns its id, or loses and raises CONFLICT.
    """
    _require_manager(auth, site_id)
    row = auth.db.execute(
        text(
            """
            SELECT status, proposed_by, responsible_user_id FROM mining_tolerance_qualification
            WHERE tenant_id = :tenant AND site_id = :site AND qualification_id = :qualification
            """
        ),
        {"tenant": auth.tenant_id, "site": site_id, "qualification": qualification_id},
    ).one_or_none()
    if row is None:
        raise AppError("NOT_FOUND")
    if auth.user_id in (row.proposed_by, row.responsible_user_id):
        raise AppError("SELF_APPROVAL_FORBIDDEN")
    if row.status != "PROPOSED":
        raise AppError("CONFLICT")
    approved_id: UUID | None = auth.db.execute(
        text(
            """
            UPDATE mining_tolerance_qualification
            SET status = 'APPROVED', approved_by = :actor, approved_at = now()
            WHERE tenant_id = :tenant AND site_id = :site AND qualification_id = :qualification
              AND status = 'PROPOSED' AND proposed_by <> :actor AND responsible_user_id <> :actor
            RETURNING qualification_id
            """
        ),
        {
            "tenant": auth.tenant_id,
            "site": site_id,
            "qualification": qualification_id,
            "actor": auth.user_id,
        },
    ).scalar_one_or_none()
    if approved_id is None:
        raise AppError("CONFLICT")
    record(
        auth.db,
        tenant_id=auth.tenant_id,
        action="mining_tolerance_qualification.approve",
        entity_type="mining_tolerance_qualification",
        entity_id=approved_id,
        site_id=site_id,
        actor_user_id=auth.user_id,
        after={"qualification_id": str(qualification_id), "status": "APPROVED"},
    )
    return approved_id


def retire_tolerance_qualification(auth: Authorized, *, site_id: UUID, qualification_id: UUID) -> UUID:
    """Retire an approved or proposed qualification; caller owns commit/rollback.

    Retiring does not rewrite history: existing reports keep their historical
    binding, while new reports and later approvals must use another qualification.
    """
    _require_manager(auth, site_id)
    retired_id: UUID | None = auth.db.execute(
        text(
            """
            UPDATE mining_tolerance_qualification
            SET status = 'RETIRED', retired_at = now()
            WHERE tenant_id = :tenant AND site_id = :site AND qualification_id = :qualification
              AND status IN ('PROPOSED', 'APPROVED')
            RETURNING qualification_id
            """
        ),
        {"tenant": auth.tenant_id, "site": site_id, "qualification": qualification_id},
    ).scalar_one_or_none()
    if retired_id is None:
        row = auth.db.execute(
            text(
                "SELECT 1 FROM mining_tolerance_qualification "
                "WHERE tenant_id = :tenant AND site_id = :site AND qualification_id = :qualification"
            ),
            {"tenant": auth.tenant_id, "site": site_id, "qualification": qualification_id},
        ).one_or_none()
        if row is None:
            raise AppError("NOT_FOUND")
        raise AppError("CONFLICT")
    record(
        auth.db,
        tenant_id=auth.tenant_id,
        action="mining_tolerance_qualification.retire",
        entity_type="mining_tolerance_qualification",
        entity_id=retired_id,
        site_id=site_id,
        actor_user_id=auth.user_id,
        after={"qualification_id": str(qualification_id), "status": "RETIRED"},
    )
    return retired_id


def load_qualified_tolerance(
    auth: Authorized, *, site_id: UUID, qualification_id: UUID
) -> QualifiedTolerance:
    """Return an APPROVED qualification, refusing missing or not-approved state.

    Scoped by tenant and site: a foreign identifier is indistinguishable from a
    missing one. A report may only be computed with this value.
    """
    row = auth.db.execute(
        text(
            """
            SELECT status, tolerance_m FROM mining_tolerance_qualification
            WHERE tenant_id = :tenant AND site_id = :site AND qualification_id = :qualification
            """
        ),
        {"tenant": auth.tenant_id, "site": site_id, "qualification": qualification_id},
    ).one_or_none()
    if row is None:
        raise AppError("NOT_FOUND")
    if row.status != "APPROVED":
        raise AppError("CONFLICT")
    return QualifiedTolerance(qualification_id, row.tolerance_m)
