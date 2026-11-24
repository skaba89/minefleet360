"""Contract tests for the opt-in additive geofence dwell threshold migration."""

from importlib import import_module


def test_dwell_threshold_migration_is_additive_and_disabled_by_default() -> None:
    migration = import_module("alembic.versions.0077_geofence_dwell_threshold")
    assert migration.revision == "0077"
    assert migration.down_revision == "0076"

    upgrade = migration.UPGRADE
    assert "ALTER TABLE site_geofence" in upgrade
    assert "ADD COLUMN dwell_threshold_minutes integer" in upgrade
    assert "CHECK (dwell_threshold_minutes BETWEEN 1 AND 1440)" in upgrade
    # Nullable column with no DEFAULT means existing geofences are not monitored.
    assert "NOT NULL" not in upgrade
    assert "DEFAULT" not in upgrade
    assert "UPDATE " not in upgrade
    assert "gps_alert" not in upgrade
    assert "fleet_gps_position" not in upgrade


def test_downgrade_is_explicitly_guarded() -> None:
    migration = import_module("alembic.versions.0077_geofence_dwell_threshold")
    assert "guard_destructive" in migration.downgrade.__code__.co_names
