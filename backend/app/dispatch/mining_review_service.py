"""Record historical review decisions; every stage exactly once, transactionally pinned."""

from uuid import UUID

from sqlalchemy import text

from app.audit.contracts import record
from app.authz.dependencies import Authorized
from app.authz.principal import evaluate
from app.core.errors import AppError
from app.dispatch.mining_approval_policy import ReviewStage
from app.dispatch.mining_readiness_snapshot import inspect_draft_evidence
from app.dispatch.mining_report_read import get_readiness_report
from app.dispatch.mining_review_locks import lock_review_sources
from app.dispatch.mining_review_read import load_review_history
from app.dispatch.mining_tolerance_service import load_qualified_tolerance


def reject_readiness_report(
    auth: Authorized, *, site_id: UUID, revision_id: UUID, report_id: UUID, stage: ReviewStage, reason: str
) -> UUID:
    """Stage a rejection and audit together; caller owns commit and rollback.

    The decision transaction first pins the review sources in a fixed order
    (site, referenced vehicle categories, revision), then re-verifies that the
    current evidence digest still equals the reviewed report before writing: a
    writer that committed in between yields EVIDENCE_STALE, a writer that starts
    during the decision blocks until it commits. Permission: dedicated
    dispatch.readiness.reject on this site — technical rejection by OPS_MANAGER,
    HSE rejection by HSE, the stage-matching role is enforced on top. Never
    approves a network.
    """
    if stage not in ("TECHNICAL", "HSE"):
        raise AppError("VALIDATION_ERROR")
    role = "OPS_MANAGER" if stage == "TECHNICAL" else "HSE"
    scope = evaluate(auth.principal, "dispatch.readiness.reject")
    if auth.principal.tenant_kind != "CUSTOMER" or scope is None or role not in scope.roles_for_site(site_id):
        raise AppError("PERMISSION_DENIED")
    if auth.principal.mfa_enrollment_pending:
        raise AppError("MFA_ENROLLMENT_REQUIRED")
    reason = reason.strip()
    if not 1 <= len(reason) <= 500 or chr(0) in reason:
        raise AppError("VALIDATION_ERROR")
    lock_review_sources(auth, site_id=site_id, revision_id=revision_id)
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
    evidence = inspect_draft_evidence(
        auth, site_id=site_id, revision_id=revision_id, tolerance_m=report.summary.tolerance_m
    )
    if (evidence.digest_version, evidence.digest) != (
        report.summary.digest_version,
        report.summary.evidence_digest,
    ):
        raise AppError("EVIDENCE_STALE")
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


def approve_readiness_report(
    auth: Authorized, *, site_id: UUID, revision_id: UUID, report_id: UUID, stage: ReviewStage, reason: str
) -> UUID:
    """Stage a positive approval and audit together; caller owns commit and rollback.

    Same transactional contract as rejection: the decision transaction first pins
    the review sources in a fixed order (site, referenced vehicle categories,
    revision), then re-verifies that the current evidence digest still equals the
    reviewed report before writing; a writer that committed in between yields
    EVIDENCE_STALE, a writer that starts during the decision blocks until it
    commits. Permission: dedicated dispatch.readiness.approve on this site —
    technical approval by OPS_MANAGER, HSE approval by HSE, the stage-matching
    role is enforced on top. The unique index keeps one decision per stage, and
    the database trigger refuses an approval by the report author, an approval of
    findings, and an HSE approval without an independent prior technical approval.
    On top of the recorded evidence, the CURRENT state of the bound tolerance
    qualification is required: a grandfathered report without qualification, or
    one whose qualification has since been proposed or retired, is CONFLICT and
    can never be approved.
    """
    if stage not in ("TECHNICAL", "HSE"):
        raise AppError("VALIDATION_ERROR")
    role = "OPS_MANAGER" if stage == "TECHNICAL" else "HSE"
    scope = evaluate(auth.principal, "dispatch.readiness.approve")
    if auth.principal.tenant_kind != "CUSTOMER" or scope is None or role not in scope.roles_for_site(site_id):
        raise AppError("PERMISSION_DENIED")
    if auth.principal.mfa_enrollment_pending:
        raise AppError("MFA_ENROLLMENT_REQUIRED")
    reason = reason.strip()
    if not 1 <= len(reason) <= 500 or chr(0) in reason:
        raise AppError("VALIDATION_ERROR")
    lock_review_sources(auth, site_id=site_id, revision_id=revision_id)
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
    if report.summary.tolerance_qualification_id is None:
        raise AppError("CONFLICT")
    load_qualified_tolerance(
        auth, site_id=site_id, qualification_id=report.summary.tolerance_qualification_id
    )
    if report.summary.finding_count != 0:
        raise AppError("CONFLICT")
    evidence = inspect_draft_evidence(
        auth, site_id=site_id, revision_id=revision_id, tolerance_m=report.summary.tolerance_m
    )
    if (evidence.digest_version, evidence.digest) != (
        report.summary.digest_version,
        report.summary.evidence_digest,
    ):
        raise AppError("EVIDENCE_STALE")
    decision_id: UUID | None = auth.db.execute(
        text(
            """
            INSERT INTO mining_review_decision
              (tenant_id, site_id, revision_id, report_id, stage, decision, actor_user_id, reason)
            VALUES (:tenant, :site, :revision, :report, :stage, 'APPROVED', :actor, :reason)
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
        action="mining_review_decision.approve",
        entity_type="mining_review_decision",
        entity_id=decision_id,
        after={"report_id": str(report_id), "stage": stage, "decision": "APPROVED"},
    )
    return decision_id
