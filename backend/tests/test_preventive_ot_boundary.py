"""Contrats de sécurité préalables au raccordement échéance → ordre de travail.

Les services actuels de création d'OT gèrent leur propre transaction.
Un futur orchestrateur préventif ne doit pas appeler create_work_order() puis
lier l'échéance dans une seconde transaction : panne entre les deux = OT orphelin.
"""

import inspect

from app.maintenance import service
from app.maintenance.models import WorkOrder
from app.maintenance.preventive_models import MaintenanceDue


def test_work_order_and_due_models_expose_linking_fields() -> None:
    assert "work_order_id" in MaintenanceDue.__table__.columns
    assert "tenant_id" in MaintenanceDue.__table__.columns
    assert "vehicle_id" in MaintenanceDue.__table__.columns
    assert "kind" in WorkOrder.__table__.columns
    assert "vehicle_id" in WorkOrder.__table__.columns
    assert "tenant_id" in WorkOrder.__table__.columns


def test_public_create_commits_but_internal_core_does_not() -> None:
    public = inspect.getsource(service.create_work_order)
    internal = inspect.getsource(service._create_work_order_uncommitted)
    assert "auth.db.commit()" in public
    assert "_create_work_order_uncommitted(auth, body)" in public
    assert ".commit()" not in internal


def test_uncommitted_core_generates_event_and_audit() -> None:
    source = inspect.getsource(service._create_work_order_uncommitted)
    assert "_next_number(auth)" in source
    assert '_event(auth, order, "REQUESTED"' in source
    assert '"work_order.request"' in source
