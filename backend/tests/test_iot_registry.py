"""PostgreSQL contract tests for migration 0078, using the restricted application role."""

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.exc import DBAPIError

from app.core.config import get_settings
from tests.conftest import Api


@contextmanager
def rejected(conn: Connection, code: str) -> Iterator[None]:
    with pytest.raises(DBAPIError) as error:
        with conn.begin_nested():
            yield
    assert getattr(error.value.orig, "sqlstate", None) == code


def test_registry_constraints_and_rls(api: Api) -> None:
    first = api.tenant()
    second = api.tenant()
    engine = create_engine(get_settings().database_url(), pool_size=1, max_overflow=0)
    manufacturer = text(
        "INSERT INTO iot_manufacturer (tenant_id, name) VALUES (:t, :name) RETURNING manufacturer_id"
    )
    gateway = text(
        "INSERT INTO iot_gateway (tenant_id, site_id, manufacturer_id, external_id, model, source_kind) "
        "VALUES (:t, :site, :m, :external, 'Test model', :source) RETURNING gateway_id"
    )
    sensor = text(
        "INSERT INTO iot_sensor (tenant_id, site_id, gateway_id, manufacturer_id, external_id, "
        "model, source_kind, sensor_kind) "
        "VALUES (:t, :site, :g, :m, :external, 'Test sensor', :source, :kind) RETURNING sensor_id"
    )
    try:
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(first.tenant_id)})
            t = first.tenant_id
            m = conn.execute(manufacturer, {"t": t, "name": "Demo OEM"}).scalar_one()
            with rejected(conn, "23505"):
                conn.execute(manufacturer, {"t": t, "name": " demo oem "})
            with rejected(conn, "42501"):
                conn.execute(manufacturer, {"t": second.tenant_id, "name": "Forbidden"})
            params = {"t": t, "site": first.sites["S1"], "m": m, "external": "G1", "source": "SIMULATED"}
            g = conn.execute(gateway, params).scalar_one()
            with rejected(conn, "23505"):
                conn.execute(gateway, params)
            with rejected(conn, "23503"):
                conn.execute(gateway, {**params, "site": second.sites["S1"], "external": "G2"})
            sp = {**params, "g": g, "external": "S1", "kind": "TPMS"}
            sid = conn.execute(sensor, sp).scalar_one()
            with rejected(conn, "23505"):
                conn.execute(sensor, sp)
            with rejected(conn, "23503"):
                conn.execute(sensor, {**sp, "site": first.sites["S2"], "external": "S2"})
            with rejected(conn, "23503"):
                conn.execute(sensor, {**sp, "source": "PHYSICAL", "external": "S3"})
            with rejected(conn, "23514"):
                conn.execute(sensor, {**sp, "kind": "INVALID", "external": "S4"})
            with rejected(conn, "42501"):
                conn.execute(text("UPDATE iot_sensor SET status = 'RETIRED' WHERE sensor_id = :id"), {"id": sid})
            with rejected(conn, "42501"):
                conn.execute(text("DELETE FROM iot_gateway WHERE gateway_id = :id"), {"id": g})

        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(second.tenant_id)})
            assert conn.execute(text("SELECT count(*) FROM iot_manufacturer")).scalar_one() == 0
            assert conn.execute(text("SELECT count(*) FROM iot_gateway")).scalar_one() == 0
            assert conn.execute(text("SELECT count(*) FROM iot_sensor")).scalar_one() == 0
            other_m = conn.execute(manufacturer, {"t": second.tenant_id, "name": "Demo OEM"}).scalar_one()
            with rejected(conn, "23503"):
                conn.execute(gateway, {**params, "t": second.tenant_id, "site": second.sites["S1"]})
            with rejected(conn, "23503"):
                conn.execute(
                    sensor, {**sp, "t": second.tenant_id, "site": second.sites["S1"], "m": other_m}
                )
    finally:
        engine.dispose()
