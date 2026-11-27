"""Integration checks for technical evidence, not operational authorization."""

import uuid

from sqlalchemy import text

from app.core.db import new_session
from app.core.tenancy import set_tenant_context
from tests.conftest import Api
from tests.test_mining_route_graph import rejected


def test_technical_profile_constraints(api: Api) -> None:
    first = api.tenant()
    second = api.tenant()
    categories = api.client.get("/api/v1/vehicle-categories", headers=first.admin.headers)
    assert categories.status_code == 200, categories.text
    category = next(row for row in categories.json() if row["is_active"])
    created = api.client.post(
        "/api/v1/vehicles",
        headers=first.admin.headers,
        json={
            "site_id": str(first.sites["S1"]),
            "vehicle_category_id": category["vehicle_category_id"],
            "fleet_number": "PROFILE-TEST",
            "make": "Synthetic",
            "model": "Test",
        },
    )
    assert created.status_code == 201, created.text
    vehicle_id = uuid.UUID(created.json()["vehicle_id"])
    insert = text(
        "INSERT INTO mining_vehicle_profile "
        "(tenant_id, vehicle_id, version, tare_mass_kg, max_gross_mass_kg, "
        "height_mm, width_mm, length_mm, max_uphill_permille, max_downhill_permille, "
        "max_speed_kmh, provenance) "
        "VALUES (:t, :v, :version, 20000, :gross, 4000, 3000, 12000, 80, :down, 30, 'Synthetic')"
    )
    params = {"t": first.tenant_id, "v": vehicle_id, "version": 1, "gross": 40000, "down": 0}
    with new_session() as db:
        set_tenant_context(db, first.tenant_id)
        conn = db.connection()
        with rejected(conn, "23514"):
            conn.execute(insert, {**params, "gross": 19999})
        with rejected(conn, "23514"):
            conn.execute(insert, {**params, "down": -1})
        conn.execute(insert, params)
        with rejected(conn, "23505"):
            conn.execute(insert, params)
        conn.execute(insert, {**params, "version": 2})
        with rejected(conn, "42501"):
            conn.execute(text("UPDATE mining_vehicle_profile SET status = 'APPROVED'"))
        with rejected(conn, "42501"):
            conn.execute(text("DELETE FROM mining_vehicle_profile"))
        db.commit()
    with new_session() as db:
        set_tenant_context(db, second.tenant_id)
        conn = db.connection()
        assert conn.execute(text("SELECT count(*) FROM mining_vehicle_profile")).scalar_one() == 0
        with rejected(conn, "23503"):
            conn.execute(insert, {**params, "t": second.tenant_id})
