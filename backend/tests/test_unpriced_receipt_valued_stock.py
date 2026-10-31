"""Une réception sans prix ne peut pas dévaluer silencieusement un stock valorisé."""

import uuid
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.db import new_session
from app.core.tenancy import set_tenant_context
from app.maintenance.parts_models import SparePartBalance
from app.maintenance.valued_receipts import record_valued_receipt
from tests.conftest import API, Api


def test_unpriced_receipt_rejected_for_valued_stock(client: TestClient, api: Api) -> None:
    tenant = api.tenant(sites=("MINE",))
    keeper = api.user(tenant, "STOREKEEPER", "SITE", "MINE")
    part_response = client.post(
        f"{API}/parts",
        headers=keeper.headers,
        json={"code": "PROTECTED-CMP-PART", "name": "Filtre", "unit": "EACH"},
    )
    assert part_response.status_code == 201, part_response.text
    store_response = client.post(
        f"{API}/part-stores",
        headers=keeper.headers,
        json={"site_id": str(tenant.sites["MINE"]), "code": "PROTECTED-CMP-STORE", "name": "Magasin"},
    )
    assert store_response.status_code == 201, store_response.text
    part_id = uuid.UUID(part_response.json()["spare_part_id"])
    store_id = uuid.UUID(store_response.json()["spare_part_store_id"])
    with new_session() as db:
        set_tenant_context(db, tenant.tenant_id)
        record_valued_receipt(
            db,
            tenant_id=tenant.tenant_id,
            site_id=tenant.sites["MINE"],
            store_id=store_id,
            part_id=part_id,
            user_id=keeper.user_id,
            quantity=Decimal("3"),
            unit_cost=Decimal("100"),
            currency="GNF",
            reference="PROTECTED-CMP-VALUED",
        )
        db.commit()
    rejected = client.post(
        f"{API}/part-movements/receipts",
        headers=keeper.headers,
        json={
            "spare_part_store_id": str(store_id),
            "spare_part_id": str(part_id),
            "quantity": "2.000",
            "reference": "PROTECTED-CMP-UNPRICED",
        },
    )
    assert rejected.status_code == 409, rejected.text
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
        assert balance.on_hand == Decimal("3")
        assert balance.stock_value == Decimal("300")
        assert balance.valuation_currency == "GNF"
