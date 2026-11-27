"""Persist historical technical evidence and its audit event in the caller's transaction."""

import hashlib
import json
from dataclasses import asdict
from uuid import UUID

from sqlalchemy import text

from app.audit.contracts import record
from app.authz.dependencies import Authorized
from app.authz.principal import evaluate
from app.core.errors import AppError
from app.dispatch.mining_readiness_snapshot import evaluate_snapshot, read_draft_snapshot

_VALIDATOR_VERSION = 1


def capture_draft_report(auth: Authorized, *, site_id: UUID, revision_id: UUID, tolerance_m: float) -> UUID:
    """One immutable report per actor and distinct set of inspected inputs.

    Repeating the same observation returns the original report and timestamp.
    Publication must separately revalidate the network and human decisions.
    """
    scope = evaluate(auth.principal, "dispatch.location.manage")
    if scope is None or not scope.covers_site(site_id):
        raise AppError("PERMISSION_DENIED")
    rows = read_draft_snapshot(auth, site_id=site_id, revision_id=revision_id, tolerance_m=tolerance_m)
    findings = evaluate_snapshot(
        rows, tenant_id=auth.tenant_id, site_id=site_id, revision_id=revision_id, tolerance_m=tolerance_m
    )
    # Row and category order are fixed by the snapshot query. Capture the exact
    # inputs of this validator, including missing policies and inactive-category filtering.
    evidence = [
        {k: v for k, v in row._mapping.items() if k != "inspected_at"}
        for row in rows
        if row.node_id is not None or row.segment_id is not None
    ]
    payload = json.dumps(evidence, default=str, sort_keys=True, allow_nan=False, separators=(",", ":"))
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    key = {
        "tenant": auth.tenant_id,
        "site": site_id,
        "revision": revision_id,
        "actor": auth.user_id,
        "version": _VALIDATOR_VERSION,
        "tolerance": tolerance_m,
        "digest": digest,
    }
    report_id = auth.db.execute(
        text(
            """
            INSERT INTO mining_draft_inspection_report
              (tenant_id, site_id, revision_id, inspected_by, inspected_at, validator_version,
               tolerance_m, evidence_sha256, evidence, findings)
            VALUES (:tenant, :site, :revision, :actor, :timestamp, :version, :tolerance, :digest,
                    CAST(:evidence AS jsonb), CAST(:findings AS jsonb))
            ON CONFLICT (tenant_id, site_id, revision_id, inspected_by, validator_version,
                         tolerance_m, evidence_sha256) DO NOTHING
            RETURNING report_id
            """
        ),
        {
            **key,
            "timestamp": rows[0].inspected_at,
            "evidence": payload,
            "findings": json.dumps([asdict(item) for item in findings], default=str),
        },
    ).scalar_one_or_none()
    if report_id is None:
        existing: UUID = auth.db.execute(
            text(
                """
                SELECT report_id FROM mining_draft_inspection_report
                WHERE tenant_id = :tenant AND site_id = :site AND revision_id = :revision
                  AND inspected_by = :actor AND validator_version = :version
                  AND tolerance_m = :tolerance AND evidence_sha256 = :digest
                """
            ),
            key,
        ).scalar_one()
        return existing
    record(
        auth.db,
        tenant_id=auth.tenant_id,
        site_id=site_id,
        actor_user_id=auth.user_id,
        action="dispatch.draft.inspect",
        entity_type="mining_draft_inspection_report",
        entity_id=report_id,
        after={
            "revision_id": revision_id,
            "validator_version": _VALIDATOR_VERSION,
            "evidence_sha256": digest.hex(),
            "finding_count": len(findings),
            "tolerance_m": tolerance_m,
        },
    )
    return UUID(str(report_id))
