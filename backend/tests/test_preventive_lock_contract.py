"""Contrat de verrouillage de l'échéance lors de l'ordonnancement préventif.

Ces tests ciblent la requête émise par le service. Ils ne remplacent pas
un scénario concurrent avec deux connexions PostgreSQL réelles.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from app.core.errors import AppError
from app.maintenance.preventive_schedule import schedule_preventive_order


def test_due_is_selected_for_update_before_any_write() -> None:
    """La première requête verrouille l'échéance du bon tenant et identifiant."""
    tenant_id = uuid.uuid4()
    due_id = uuid.uuid4()
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = None
    auth = SimpleNamespace(
        db=db,
        tenant_id=tenant_id,
        scope=SimpleNamespace(permission="maintenance.preventive.manage"),
    )

    with pytest.raises(AppError) as error:
        schedule_preventive_order(auth, due_id)

    assert error.value.code == "NOT_FOUND"
    query = db.execute.call_args.args[0]
    sql = str(query.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert "FOR UPDATE" in sql
    assert f"maintenance_due.tenant_id = '{tenant_id}'" in sql
    assert f"maintenance_due.maintenance_due_id = '{due_id}'" in sql
    db.flush.assert_not_called()
    db.commit.assert_not_called()


def test_existing_order_short_circuits_before_plan_or_creation() -> None:
    """Après verrouillage, un OT déjà rattaché est renvoyé sans nouvelle création."""
    order_id = uuid.uuid4()
    due = SimpleNamespace(work_order_id=order_id, vehicle_id=uuid.uuid4(), status="SCHEDULED")
    db = MagicMock()
    db.execute.side_effect = [
        MagicMock(scalar_one_or_none=lambda: due),
        MagicMock(scalar_one_or_none=lambda: SimpleNamespace(site_id=uuid.uuid4())),
    ]
    auth = SimpleNamespace(
        db=db,
        tenant_id=uuid.uuid4(),
        scope=SimpleNamespace(permission="maintenance.preventive.manage", covers_site=lambda _: True),
    )

    assert schedule_preventive_order(auth, uuid.uuid4()) == order_id
    assert db.execute.call_count == 2
    db.flush.assert_not_called()
    db.commit.assert_not_called()
