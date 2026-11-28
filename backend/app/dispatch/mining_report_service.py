"""Internal historical report writer; never an operational approval."""

import json
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text

from app.audit.contracts import record
from app.authz.dependencies import Authorized
from app.authz.principal import evaluate
from app.core.errors import AppError
from app.dispatch.mining_readiness_snapshot import DraftReadinessEvidence, inspect_draft_evidence
from app.dispatch.mining_tolerance_service import load_qualified_tolerance


@dataclass(frozen=True)
class RecordedReadiness:
    report_id: UUID
    evidence: DraftReadinessEvidence


def record_draft_readiness(
    auth: Authorized,
    *,
    site_id: UUID,
    revision_id: UUID,
    tolerance_m: float,
    tolerance_qualification_id: UUID,
) -> RecordedReadiness:
    """Stage report and audit in the caller's transaction; caller owns commit/rollback.

    The tolerance must reference an approved site qualification carrying its survey
    provenance, method, precision, date, responsible surveyor, referential version
    and justification; the value must match exactly. Until a dedicated route
    permission is introduced, require existing location management permission as
    well as the inspection read permission. A report records historical evidence
    only, even when findings are empty.
    """
    scope = evaluate(auth.principal, "dispatch.location.manage")
    if auth.principal.tenant_kind != "CUSTOMER" or scope is None or not scope.covers_site(site_id):
        raise AppError("PERMISSION_DENIED")
    qualified = load_qualified_tolerance(auth, site_id=site_id, qualification_id=tolerance_qualification_id)
    if qualified.tolerance_m != tolerance_m:
        raise AppError("VALIDATION_ERROR")
    evidence = inspect_draft_evidence(auth, site_id=site_id, revision_id=revision_id, tolerance_m=tolerance_m)
    findings = [
        {"code": item.code, "segment_id": str(item.segment_id) if item.segment_id is not None else None}
        for item in evidence.findings
    ]
    if len(findings) > 3000:
        raise AppError("CONFLICT")
    report_id: UUID = auth.db.execute(
        text(
            """
            INSERT INTO mining_readiness_report
              (tenant_id, site_id, revision_id, digest_version, evidence_digest,
               tolerance_m, findings, actor_user_id, tolerance_qualification_id)
            VALUES (:tenant, :site, :revision, :version, :digest,
                    :tolerance, CAST(:findings AS jsonb), :actor, :qualification)
            RETURNING report_id
            """
        ),
        {
            "tenant": auth.tenant_id,
            "site": site_id,
            "revision": revision_id,
            "version": evidence.digest_version,
            "digest": evidence.digest,
            "tolerance": tolerance_m,
            "findings": json.dumps(findings),
            "actor": auth.user_id,
            "qualification": tolerance_qualification_id,
        },
    ).scalar_one()
    record(
        auth.db,
        tenant_id=auth.tenant_id,
        action="mining_readiness_report.create",
        entity_type="mining_readiness_report",
        entity_id=report_id,
        site_id=site_id,
        actor_user_id=auth.user_id,
        after={
            "revision_id": str(revision_id),
            "digest_version": evidence.digest_version,
            "evidence_digest": evidence.digest,
            "finding_count": len(findings),
            "tolerance_qualification_id": str(tolerance_qualification_id),
        },
    )
    return RecordedReadiness(report_id, evidence)
