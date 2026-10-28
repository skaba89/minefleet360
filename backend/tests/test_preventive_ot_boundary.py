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


def test_existing_create_work_order_owns_commit_and_cannot_be_reused_directly() -> None:
    source = inspect.getsource(service.create_work_order)
    assert "db.commit()" in source, (
        "Revoir l'architecture transactionnelle : le service de création OT a changé"
    )


def test_existing_create_work_order_generates_event_and_audit() -> None:
    source = inspect.getsource(service.create_work_order)
    assert "_next_number(auth)" in source
    assert '_event(auth, order, "REQUESTED"' in source
    assert '"work_order.request"' in source
