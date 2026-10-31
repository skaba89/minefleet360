"""Upgrade réaliste d'une base 0004 déjà peuplée vers le head courant.

Cette suite est destructive pour la base de test et s'exécute séparément avant les tests applicatifs.
"""

import uuid
from pathlib import Path

import psycopg
import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError

from alembic import command
from app.core.config import get_settings
from app.core.tenancy import PLATFORM_TENANT_ID

TENANT_A = uuid.UUID("10000000-0000-4000-8000-000000000001")
TENANT_B = uuid.UUID("10000000-0000-4000-8000-000000000002")
SITE_A = uuid.UUID("20000000-0000-4000-8000-000000000001")
SITE_B = uuid.UUID("20000000-0000-4000-8000-000000000002")


def _alembic_config() -> Config:
    backend = Path(__file__).resolve().parent.parent
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "alembic"))
    return config


def _context(connection: Connection, tenant_id: uuid.UUID) -> None:
    connection.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_id)},
    )


def _prepare_0004(config: Config, app_engine: Engine) -> None:
    command.downgrade(config, "base")
    command.upgrade(config, "0004")
    with app_engine.begin() as connection:
        _context(connection, PLATFORM_TENANT_ID)
        connection.execute(
            text(
                "INSERT INTO tenant (tenant_id, code, kind, legal_name, display_name) VALUES"
                " (:a, 'upgrade-a', 'CUSTOMER', 'Société Upgrade A', 'Upgrade A'),"
                " (:b, 'upgrade-b', 'CUSTOMER', 'Société Upgrade B', 'Upgrade B')"
            ),
            {"a": str(TENANT_A), "b": str(TENANT_B)},
        )
        _context(connection, TENANT_A)
        connection.execute(
            text(
                "INSERT INTO site (site_id, tenant_id, code, name, site_type)"
                " VALUES (:site, :tenant, 'MINE-A', 'Mine Upgrade A', 'MINE')"
            ),
            {"site": str(SITE_A), "tenant": str(TENANT_A)},
        )
        _context(connection, TENANT_B)
        connection.execute(
            text(
                "INSERT INTO site (site_id, tenant_id, code, name, site_type)"
                " VALUES (:site, :tenant, 'MINE-B', 'Mine Upgrade B', 'MINE')"
            ),
            {"site": str(SITE_B), "tenant": str(TENANT_B)},
        )


def _category(connection: Connection, tenant_id: uuid.UUID) -> tuple[uuid.UUID, str, bool]:
    _context(connection, tenant_id)
    row = connection.execute(
        text(
            "SELECT vehicle_category_id, label_fr, is_system FROM vehicle_category"
            " WHERE code = 'LIGHT_VEHICLE'"
        )
    ).one()
    return row.vehicle_category_id, row.label_fr, row.is_system


def _assert_catalog(connection: Connection, tenant_id: uuid.UUID, *, customized: bool) -> uuid.UUID:
    _context(connection, tenant_id)
    assert connection.execute(text("SELECT count(*) FROM vehicle_category")).scalar_one() == 15
    category_id, label, is_system = _category(connection, tenant_id)
    assert (label, is_system) == (
        ("Véhicule léger système personnalisé", True)
        if customized
        else ("Véhicule léger (pick-up, 4x4)", True)
    )
    licenses = connection.execute(
        text(
            "SELECT license_category_code FROM vehicle_category_license_category"
            " WHERE vehicle_category_id = :category_id"
        ),
        {"category_id": category_id},
    ).scalars()
    assert list(licenses) == ["B"]
    return category_id


def _assert_database_protections(owner_engine: Engine) -> None:
    with owner_engine.connect() as connection:
        temporary = connection.execute(
            text("SELECT count(*) FROM pg_policies WHERE policyname LIKE 'migration_0007_owner_%'")
        ).scalar_one()
        table_count, protections = connection.execute(
            text(
                "SELECT count(*), bool_and(relrowsecurity AND relforcerowsecurity)"
                " FROM pg_class WHERE oid IN"
                " ('tenant'::regclass, 'vehicle_category'::regclass,"
                "  'vehicle_category_license_category'::regclass)"
            )
        ).one()
        permanent = connection.execute(
            text(
                "SELECT count(*) FROM pg_policies"
                " WHERE schemaname = 'public' AND roles = ARRAY['mf_app']::name[] AND ("
                "  (tablename = 'tenant'"
                "   AND policyname IN ('tenant_select', 'tenant_insert', 'tenant_update'))"
                "  OR (tablename IN ('vehicle_category', 'vehicle_category_license_category')"
                "      AND policyname = 'tenant_isolation'))"
            )
        ).scalar_one()
        assert temporary == 0 and table_count == 3 and protections is True and permanent == 5
        assert connection.execute(text("SELECT count(*) FROM tenant")).scalar_one() == 0


def _assert_legal_insurance_tenant_isolation(app_engine: Engine) -> None:
    """Contracts and insurance records must never cross tenant boundaries."""
    contract_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    with app_engine.begin() as connection:
        _context(connection, TENANT_A)
        connection.execute(
            text(
                "INSERT INTO legal_contract "
                "(contract_id, tenant_id, site_id, reference, title, contract_type, "
                "counterparty_name, created_by) VALUES "
                "(:id, :tenant, :site, 'LEGAL-TEST-1', 'Transport', 'TRANSPORT', "
                "'Transporteur A', :actor)"
            ),
            {"id": contract_id, "tenant": TENANT_A, "site": SITE_A, "actor": actor_id},
        )
        connection.execute(
            text(
                "INSERT INTO insurance_policy "
                "(tenant_id, site_id, policy_number, insurer_name, coverage_type, "
                "coverage_start, coverage_end, contract_id, created_by) VALUES "
                "(:tenant, :site, 'INS-TEST-1', 'Assureur A', 'FLEET', "
                "'2026-01-01', '2026-12-31', :contract, :actor)"
            ),
            {"tenant": TENANT_A, "site": SITE_A, "contract": contract_id, "actor": actor_id},
        )
    with app_engine.connect() as connection:
        _context(connection, TENANT_B)
        assert connection.execute(text("SELECT count(*) FROM legal_contract")).scalar_one() == 0
        assert connection.execute(text("SELECT count(*) FROM insurance_policy")).scalar_one() == 0
        connection.rollback()
        _context(connection, TENANT_A)
        assert connection.execute(text("SELECT count(*) FROM legal_contract")).scalar_one() == 1
        assert connection.execute(text("SELECT count(*) FROM insurance_policy")).scalar_one() == 1
        connection.rollback()

    # A contract from tenant A cannot be attached to a policy of tenant B.
    with app_engine.connect() as connection:
        _context(connection, TENANT_B)
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "INSERT INTO insurance_policy "
                    "(tenant_id, site_id, policy_number, insurer_name, coverage_type, "
                    "coverage_start, coverage_end, contract_id, created_by) VALUES "
                    "(:tenant, :site, 'INS-FOREIGN', 'Assureur B', 'FLEET', "
                    "'2026-01-01', '2026-12-31', :contract, :actor)"
                ),
                {"tenant": TENANT_B, "site": SITE_B, "contract": contract_id, "actor": actor_id},
            )
        connection.rollback()

    # Invalid insurance coverage dates are rejected at database level.
    with app_engine.connect() as connection:
        _context(connection, TENANT_A)
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "INSERT INTO insurance_policy "
                    "(tenant_id, site_id, policy_number, insurer_name, coverage_type, "
                    "coverage_start, coverage_end, created_by) VALUES "
                    "(:tenant, :site, 'INS-INVALID-DATES', 'Assureur A', 'FLEET', "
                    "'2026-12-31', '2026-01-01', :actor)"
                ),
                {"tenant": TENANT_A, "site": SITE_A, "actor": actor_id},
            )
        connection.rollback()


def test_01_upgrade_repairs_existing_tenants_and_is_idempotent() -> None:
    settings = get_settings()
    config = _alembic_config()
    app_engine = create_engine(settings.database_url())
    owner_engine = create_engine(settings.database_url(owner=True))
    try:
        _prepare_0004(config, app_engine)
        command.upgrade(config, "0006")
        with app_engine.begin() as connection:
            _context(connection, TENANT_A)
            assert connection.execute(text("SELECT count(*) FROM vehicle_category")).scalar_one() == 0
            connection.execute(
                text(
                    "INSERT INTO vehicle_category"
                    " (tenant_id, code, label_fr, family, is_system)"
                    " VALUES (:tenant_id, 'LIGHT_VEHICLE', 'Véhicule léger système personnalisé',"
                    " 'LIGHT_VEHICLE', true)"
                ),
                {"tenant_id": str(TENANT_A)},
            )

        command.upgrade(config, "head")
        with app_engine.connect() as connection:
            category_a = _assert_catalog(connection, TENANT_A, customized=True)
            connection.rollback()
            category_b = _assert_catalog(connection, TENANT_B, customized=False)
            connection.rollback()
            _context(connection, TENANT_A)
            assert (
                connection.execute(
                    text("SELECT count(*) FROM vehicle_category WHERE tenant_id = :other"),
                    {"other": str(TENANT_B)},
                ).scalar_one()
                == 0
            )
            connection.rollback()

        with app_engine.begin() as connection:
            _context(connection, TENANT_A)
            connection.execute(
                text(
                    "INSERT INTO vehicle"
                    " (tenant_id, site_id, vehicle_category_id, fleet_number)"
                    " VALUES (:tenant, :site, :category, 'UPGRADE-OK')"
                ),
                {"tenant": str(TENANT_A), "site": str(SITE_A), "category": category_a},
            )
        with app_engine.connect() as connection:
            _context(connection, TENANT_A)
            with pytest.raises(IntegrityError):
                connection.execute(
                    text(
                        "INSERT INTO vehicle"
                        " (tenant_id, site_id, vehicle_category_id, fleet_number)"
                        " VALUES (:tenant, :site, :category, 'UPGRADE-FOREIGN')"
                    ),
                    {"tenant": str(TENANT_A), "site": str(SITE_A), "category": category_b},
                )
            connection.rollback()

        _assert_legal_insurance_tenant_isolation(app_engine)

        _assert_database_protections(owner_engine)

        # Le downgrade conserve volontairement les données réparées; le second upgrade ne duplique rien.
        command.downgrade(config, "0006")
        command.upgrade(config, "head")
        with app_engine.connect() as connection:
            _assert_catalog(connection, TENANT_A, customized=True)
            connection.rollback()
            _assert_catalog(connection, TENANT_B, customized=False)
        _assert_database_protections(owner_engine)
    finally:
        app_engine.dispose()
        owner_engine.dispose()


def test_02_custom_category_collision_rolls_back_atomically() -> None:
    settings = get_settings()
    config = _alembic_config()
    app_engine = create_engine(settings.database_url())
    owner_engine = create_engine(settings.database_url(owner=True))
    try:
        _prepare_0004(config, app_engine)
        command.upgrade(config, "0006")
        with app_engine.begin() as connection:
            _context(connection, TENANT_A)
            connection.execute(
                text(
                    "INSERT INTO vehicle_category"
                    " (tenant_id, code, label_fr, family, is_system)"
                    " VALUES (:tenant_id, 'LIGHT_VEHICLE', 'Catégorie personnalisée',"
                    " 'LIGHT_VEHICLE', false)"
                ),
                {"tenant_id": str(TENANT_A)},
            )

        with pytest.raises(psycopg.Error, match="custom category conflicts"):
            command.upgrade(config, "head")

        with owner_engine.connect() as connection:
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0006"
        _assert_database_protections(owner_engine)
        with app_engine.connect() as connection:
            _context(connection, TENANT_A)
            assert connection.execute(text("SELECT count(*) FROM vehicle_category")).scalar_one() == 1
            _context(connection, TENANT_B)
            assert connection.execute(text("SELECT count(*) FROM vehicle_category")).scalar_one() == 0
    finally:
        app_engine.dispose()
        owner_engine.dispose()
