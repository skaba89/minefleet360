"""Contrat d'intégration PostgreSQL des réceptions valorisées.

Tests sur une base *_test, via le rôle applicatif et les politiques RLS.
"""

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.db import new_session
from app.core.tenancy import set_tenant_context
from app.maintenance.parts_models import SparePartBalance, SparePartMovement
from app.maintenance.valued_receipts import record_valued_receipt
from tests.conftest import API, Api


def test_valued_receipts_persist_price_and_cmp(client: TestClient, api: Api) -> None:
    tenant = api.tenant(sites=("MINE",))
    keeper = api.user(tenant, "STOREKEEPER", "SITE", "MINE")
    part_result = client.post(
        f"{API}/parts",
        headers=keeper.headers,
        json={"code": "VALUED-FILTER", "name": "Filtre", "unit": "EACH"},
    )
    assert part_result.status_code == 201, part_result.text
    store_result = client.post(
        f"{API}/part-stores",
        headers=keeper.headers,
        json={"site_id": str(tenant.sites["MINE"]), "code": "VALUED-STORE", "name": "Magasin"},
    )
    assert store_result.status_code == 201, store_result.text
    part_id = uuid.UUID(part_result.json()["spare_part_id"])
    store_id = uuid.UUID(store_result.json()["spare_part_store_id"])
    site_id = tenant.sites["MINE"]
    with new_session() as db:
        set_tenant_context(db, tenant.tenant_id)
        for qty, unit_cost, ref in (
            (Decimal("3"), Decimal("100"), "VALUED-RECEIPT-1"),
            (Decimal("2"), Decimal("150"), "VALUED-RECEIPT-2"),
        ):
            movement = record_valued_receipt(
                db,
                tenant_id=tenant.tenant_id,
                site_id=site_id,
                store_id=store_id,
                part_id=part_id,
                user_id=keeper.user_id,
                quantity=qty,
                unit_cost=unit_cost,
                currency="GNF",
                reference=ref,
            )
            assert movement.total_cost == qty * unit_cost
        db.commit()
    with new_session() as db:
        set_tenant_context(db, tenant.tenant_id)
        balance = db.scalar(
            select(SparePartBalance).where(
                SparePartBalance.tenant_id == tenant.tenant_id,
                SparePartBalance.spare_part_store_id == store_id,
                SparePartBalance.spare_part_id == part_id,
            )
        )
        assert balance is not None
        assert balance.on_hand == Decimal("5")
        assert balance.stock_value == Decimal("600")
        assert balance.valuation_currency == "GNF"
        movements = db.scalars(
            select(SparePartMovement).where(
                SparePartMovement.tenant_id == tenant.tenant_id,
                SparePartMovement.spare_part_store_id == store_id,
            )
        ).all()
        assert sorted(row.total_cost for row in movements) == [Decimal("300"), Decimal("300")]


def test_historical_unvalued_stock_is_not_repriced(client: TestClient, api: Api) -> None:
    tenant = api.tenant(sites=("MINE",))
    keeper = api.user(tenant, "STOREKEEPER", "SITE", "MINE")
    part_result = client.post(
        f"{API}/parts",
        headers=keeper.headers,
        json={"code": "HISTORIC-FILTER", "name": "Filtre", "unit": "EACH"},
    )
    assert part_result.status_code == 201, part_result.text
    store_result = client.post(
        f"{API}/part-stores",
        headers=keeper.headers,
        json={"site_id": str(tenant.sites["MINE"]), "code": "HISTORIC-STORE", "name": "Magasin"},
    )
    assert store_result.status_code == 201, store_result.text
    part_id = uuid.UUID(part_result.json()["spare_part_id"])
    store_id = uuid.UUID(store_result.json()["spare_part_store_id"])
    received = client.post(
        f"{API}/part-movements/receipts",
        headers=keeper.headers,
        json={
            "spare_part_store_id": str(store_id),
            "spare_part_id": str(part_id),
            "quantity": "3.000",
            "reference": "HISTORIC-RECEIPT",
        },
    )
    assert received.status_code == 201, received.text
    with new_session() as db:
        set_tenant_context(db, tenant.tenant_id)
        with pytest.raises(ValueError, match="historique"):
            record_valued_receipt(
                db,
                tenant_id=tenant.tenant_id,
                site_id=tenant.sites["MINE"],
                store_id=store_id,
                part_id=part_id,
                user_id=keeper.user_id,
                quantity=Decimal("1"),
                unit_cost=Decimal("10"),
                currency="GNF",
                reference="HISTORIC-VALUED-ATTEMPT",
            )
        db.rollback()
    balance_result = client.get(f"{API}/part-balances", headers=keeper.headers)
    assert balance_result.status_code == 200, balance_result.text
    matching = [row for row in balance_result.json()["items"] if row["spare_part_id"] == str(part_id)]
    assert len(matching) == 1
    assert matching[0]["on_hand"] == 3.0
