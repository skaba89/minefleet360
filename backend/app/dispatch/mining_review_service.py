"""Record historical rejection only; positive approval is deliberately unavailable."""

from uuid import UUID

from sqlalchemy import text

from app.audit.contracts import record
from app.authz.dependencies import Authorized
from app.authz.principal import evaluate
from app.core.errors import AppError
from app.dispatch.mining_approval_policy import ReviewStage
from app.dispatch.mining_report_read import get_readiness_report
from app.dispatch.mining_review_read import load_review_history


def reject_readiness_report(
    auth: Authorized, *, site_id: UUID, revision_id: UUID, report_id: UUID, stage: ReviewStage, reason: str
) -> UUID:
    """Stage a rejection and audit together; caller owns commit and rollback.

    Temporary internal policy: technical rejection by OPS_MANAGER, HSE by HSE,
    both with location read permission on this site. Never approves a network.
    """
    if stage not in ("TECHNICAL", "HSE"):
        raise AppError("VALIDATION_ERROR")
    role = "OPS_MANAGER" if stage == "TECHNICAL" else "HSE"
    scope = evaluate(auth.principal, "dispatch.location.read")
    if auth.principal.tenant_kind != "CUSTOMER" or scope is None or role not in scope.roles_for_site(site_id):
        raise AppError("PERMISSION_DENIED")
    if auth.principal.mfa_enrollment_pending:
        raise AppError("MFA_ENROLLMENT_REQUIRED")
    reason = reason.strip()
    if not 1 <= len(reason) <= 500 or chr(0) in reason:
        raise AppError("VALIDATION_ERROR")
    report = get_readiness_report(auth, site_id=site_id, revision_id=revision_id, report_id=report_id)
    history = load_review_history(auth, site_id=site_id, revision_id=revision_id, report_id=report_id)
    if report.summary.actor_user_id == auth.user_id:
        raise AppError("SELF_APPROVAL_FORBIDDEN")
    if any(item.stage == stage for item in history.decisions):
        raise AppError("CONFLICT")
    if stage == "HSE":
        prior = history.technical_review()
        if prior is None or prior.decision != "APPROVED" or prior.actor_user_id == auth.user_id:
            raise AppError("CONFLICT")
    decision_id: UUID | None = auth.db.execute(
        text(
            """
            INSERT INTO mining_review_decision
              (tenant_id, site_id, revision_id, report_id, stage, decision, actor_user_id, reason)
            VALUES (:tenant, :site, :revision, :report, :stage, 'REJECTED', :actor, :reason)
            ON CONFLICT (report_id, stage) DO NOTHING
            RETURNING decision_id
            """
        ),
        {
            "tenant": auth.tenant_id,
            "site": site_id,
            "revision": revision_id,
            "report": report_id,
            "stage": stage,
            "actor": auth.user_id,
            "reason": reason,
        },
    ).scalar_one_or_none()
    if decision_id is None:
        raise AppError("CONFLICT")
    record(
        auth.db,
        tenant_id=auth.tenant_id,
        site_id=site_id,
        actor_user_id=auth.user_id,
        action="mining_review_decision.reject",
        entity_type="mining_review_decision",
        entity_id=decision_id,
        after={"report_id": str(report_id), "stage": stage, "decision": "REJECTED"},
    )
    return decision_id
