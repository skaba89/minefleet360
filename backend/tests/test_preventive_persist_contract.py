"""Contrats de persistance d'échéances : idempotence, audit et requête SQL.

Ces tests ne remplacent pas les tests d'accès RLS sur PostgreSQL réel.
"""

import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import insert

from app.maintenance.preventive_due_candidates import DueCandidate
from app.maintenance.preventive_models import MaintenanceDue
from app.maintenance.preventive_persist import persist_due


def _fixture() -> tuple[SimpleNamespace, uuid.UUID, DueCandidate]:
    tenant_id = uuid.uuid4()
    plan_id = uuid.uuid4()
    vehicle_id = uuid.uuid4()
    site_id = uuid.uuid4()
    plan = SimpleNamespace(maintenance_plan_id=plan_id, vehicle_id=vehicle_id)
    vehicle = SimpleNamespace(site_id=site_id)
    db = MagicMock()
    auth = SimpleNamespace(
        tenant_id=tenant_id,
        user_id=uuid.uuid4(),
        db=db,
        scope=SimpleNamespace(
            permission="maintenance.preventive.manage",
            covers_site=lambda site: site == site_id,
        ),
    )
    db.execute.side_effect = [
        MagicMock(scalar_one_or_none=lambda: plan),
        MagicMock(scalar_one_or_none=lambda: vehicle),
        MagicMock(scalar_one_or_none=lambda: None),
    ]
    candidate = DueCandidate("DAYS", "DAYS:2026-01-01", date(2026, 1, 31), None)
    return auth, plan_id, candidate


def test_duplicate_due_returns_false_without_audit_or_commit() -> None:
    auth, plan_id, candidate = _fixture()
    with patch("app.maintenance.preventive_persist.record") as audit:
        assert persist_due(auth, plan_id, candidate) is False
    audit.assert_not_called()
    auth.db.commit.assert_not_called()
    statement = auth.db.execute.call_args_list[2].args[0]
    compiled = str(statement.compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT ON CONSTRAINT uq_maintenance_due_idempotence DO NOTHING" in compiled
    assert "RETURNING maintenance_due.maintenance_due_id" in compiled


def test_new_due_commits_and_records_audit_once() -> None:
    auth, plan_id, candidate = _fixture()
    due_id = uuid.uuid4()
    auth.db.execute.side_effect[2].scalar_one_or_none = lambda: due_id
    with patch("app.maintenance.preventive_persist.record") as audit:
        assert persist_due(auth, plan_id, candidate) is True
    audit.assert_called_once()
    auth.db.commit.assert_called_once()
    assert audit.call_args.kwargs["entity_id"] == due_id
    assert audit.call_args.kwargs["tenant_id"] == auth.tenant_id


def test_duplicate_protection_uses_named_database_constraint() -> None:
    stmt = (
        insert(MaintenanceDue)
        .values(
            tenant_id=uuid.uuid4(),
            maintenance_plan_id=uuid.uuid4(),
            vehicle_id=uuid.uuid4(),
            trigger_kind="DAYS",
            trigger_key="DAYS:2026-01-01",
            due_on=date(2026, 1, 31),
            status="DUE",
        )
        .on_conflict_do_nothing(constraint="uq_maintenance_due_idempotence")
    )
    assert "uq_maintenance_due_idempotence" in str(stmt.compile(dialect=postgresql.dialect()))
