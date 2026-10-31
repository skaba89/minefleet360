"""Tests for the Alembic readiness comparison (no database required)."""

from app.core.check_schema_revision import revisions_match


def test_exact_head_matches() -> None:
    assert revisions_match({"0041"}, {"0041"})


def test_stale_database_blocks_pilot() -> None:
    assert not revisions_match({"0040"}, {"0041"})


def test_missing_or_extra_head_blocks_pilot() -> None:
    assert not revisions_match(set(), {"0041"})
    assert not revisions_match({"0041", "orphan"}, {"0041"})
    assert not revisions_match({"0041"}, {"0041", "other"})
