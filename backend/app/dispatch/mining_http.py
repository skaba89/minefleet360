"""HTTP exposure of readiness reports and review decisions (Phase 6).

Read endpoints serve the immutable historical evidence; decision endpoints stage
rejection or approval. Every authorization rule beyond the coarse permission
gate lives in the services (stage-matching role, four eyes, current tolerance
qualification, evidence integrity, transactional pinning): the HTTP layer only
translates the contract.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.authz.dependencies import Authorized, Require
from app.authz.routing import SecuredRoute
from app.dispatch.mining_report_read import (
    get_readiness_report as get_report,
)
from app.dispatch.mining_report_read import (
    list_readiness_reports as list_reports,
)
from app.dispatch.mining_report_read import (
    list_site_revisions,
)
from app.dispatch.mining_report_schemas import (
    ReadinessDecisionOut,
    ReadinessReportCreate,
    ReadinessReportDetailOut,
    ReadinessReportPageOut,
    ReadinessReviewCreate,
    ReadinessReviewHistoryOut,
    ReadinessRevisionOut,
)
from app.dispatch.mining_report_service import record_draft_readiness
from app.dispatch.mining_review_read import HistoricalDecision, load_review_history
from app.dispatch.mining_review_service import (
    approve_readiness_report as approve_service,
)
from app.dispatch.mining_review_service import (
    reject_readiness_report as reject_service,
)

router = APIRouter(tags=["dispatch"], route_class=SecuredRoute)

ReadinessRead = Annotated[Authorized, Depends(Require("dispatch.readiness.read"))]
ReadinessRecord = Annotated[Authorized, Depends(Require("dispatch.readiness.record"))]
ReadinessReject = Annotated[Authorized, Depends(Require("dispatch.readiness.reject"))]
ReadinessApprove = Annotated[Authorized, Depends(Require("dispatch.readiness.approve"))]


@router.get(
    "/sites/{site_id}/mining/revisions",
    response_model=list[ReadinessRevisionOut],
)
def list_mining_revisions(
    site_id: uuid.UUID,
    auth: ReadinessRead,
    limit: int = 50,
) -> list[ReadinessRevisionOut]:
    """Survey revisions of one site, newest first; the UI picks one to browse its reports."""
    return [
        ReadinessRevisionOut.from_revision(revision)
        for revision in list_site_revisions(auth, site_id=site_id, limit=limit)
    ]


@router.post(
    "/sites/{site_id}/mining/revisions/{revision_id}/readiness-reports",
    status_code=201,
    response_model=ReadinessReportDetailOut,
)
def record_readiness_report(
    site_id: uuid.UUID,
    revision_id: uuid.UUID,
    body: ReadinessReportCreate,
    auth: ReadinessRecord,
) -> ReadinessReportDetailOut:
    """Record one immutable snapshot of the draft graph at the survey tolerance."""
    recorded = record_draft_readiness(
        auth,
        site_id=site_id,
        revision_id=revision_id,
        tolerance_m=body.tolerance_m,
        tolerance_qualification_id=body.tolerance_qualification_id,
    )
    report = get_report(auth, site_id=site_id, revision_id=revision_id, report_id=recorded.report_id)
    auth.db.commit()  # the record service stages in the caller's transaction; the route is the caller
    return ReadinessReportDetailOut.from_report(report)


@router.get(
    "/sites/{site_id}/mining/revisions/{revision_id}/readiness-reports",
    response_model=ReadinessReportPageOut,
)
def list_readiness_reports(
    site_id: uuid.UUID,
    revision_id: uuid.UUID,
    auth: ReadinessRead,
    limit: int = 50,
    before: uuid.UUID | None = None,
) -> ReadinessReportPageOut:
    """Newest-first historical reports; opaque cursor pagination inside scope."""
    summaries, cursor = list_reports(
        auth, site_id=site_id, revision_id=revision_id, limit=limit, before=before
    )
    return ReadinessReportPageOut.from_page(summaries, cursor)


@router.get(
    "/sites/{site_id}/mining/revisions/{revision_id}/readiness-reports/{report_id}",
    response_model=ReadinessReportDetailOut,
)
def get_readiness_report(
    site_id: uuid.UUID, revision_id: uuid.UUID, report_id: uuid.UUID, auth: ReadinessRead
) -> ReadinessReportDetailOut:
    report = get_report(auth, site_id=site_id, revision_id=revision_id, report_id=report_id)
    return ReadinessReportDetailOut.from_report(report)


@router.get(
    "/sites/{site_id}/mining/revisions/{revision_id}/readiness-reports/{report_id}/review",
    response_model=ReadinessReviewHistoryOut,
)
def get_review_history(
    site_id: uuid.UUID, revision_id: uuid.UUID, report_id: uuid.UUID, auth: ReadinessRead
) -> ReadinessReviewHistoryOut:
    history = load_review_history(auth, site_id=site_id, revision_id=revision_id, report_id=report_id)
    return ReadinessReviewHistoryOut.from_history(history)


@router.post(
    "/sites/{site_id}/mining/revisions/{revision_id}/readiness-reports/{report_id}/reject",
    status_code=201,
    response_model=ReadinessDecisionOut,
)
def reject_readiness_report(
    site_id: uuid.UUID,
    revision_id: uuid.UUID,
    report_id: uuid.UUID,
    body: ReadinessReviewCreate,
    auth: ReadinessReject,
) -> ReadinessDecisionOut:
    decision_id = reject_service(
        auth,
        site_id=site_id,
        revision_id=revision_id,
        report_id=report_id,
        stage=body.stage,
        reason=body.reason,
    )
    staged = _staged_decision(auth, site_id, revision_id, report_id, decision_id)
    auth.db.commit()  # the decision service stages in the caller's transaction; the route is the caller
    return ReadinessDecisionOut.from_decision(report_id, staged)


@router.post(
    "/sites/{site_id}/mining/revisions/{revision_id}/readiness-reports/{report_id}/approve",
    status_code=201,
    response_model=ReadinessDecisionOut,
)
def approve_readiness_report(
    site_id: uuid.UUID,
    revision_id: uuid.UUID,
    report_id: uuid.UUID,
    body: ReadinessReviewCreate,
    auth: ReadinessApprove,
) -> ReadinessDecisionOut:
    decision_id = approve_service(
        auth,
        site_id=site_id,
        revision_id=revision_id,
        report_id=report_id,
        stage=body.stage,
        reason=body.reason,
    )
    staged = _staged_decision(auth, site_id, revision_id, report_id, decision_id)
    auth.db.commit()  # the decision service stages in the caller's transaction; the route is the caller
    return ReadinessDecisionOut.from_decision(report_id, staged)


def _staged_decision(
    auth: Authorized, site_id: uuid.UUID, revision_id: uuid.UUID, report_id: uuid.UUID, decision_id: uuid.UUID
) -> HistoricalDecision:
    """Read back the just-staged decision in the caller's transaction."""
    history = load_review_history(auth, site_id=site_id, revision_id=revision_id, report_id=report_id)
    for item in history.decisions:
        if item.decision_id == decision_id:
            return item
    raise AssertionError("staged decision vanished from the same transaction")  # pragma: no cover
