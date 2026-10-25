"""Accès base : moteur applicatif (rôle mf_app), sessions transactionnelles, métadonnées ORM."""

from collections.abc import Iterator

from sqlalchemy import MetaData, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

NAMING_CONVENTION = {
    "pk": "pk_%(table_name)s",
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s__%(referred_table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine, _session_factory
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(
            settings.database_url(),
            connect_args={"options": f"-c lock_timeout={settings.db_lock_timeout_ms}"},
            pool_pre_ping=True,
            pool_reset_on_return="rollback",
        )
        _session_factory = sessionmaker(bind=_engine, expire_on_commit=False, autoflush=True)
    return _engine


def new_session() -> Session:
    get_engine()
    assert _session_factory is not None
    return _session_factory()


def get_db() -> Iterator[Session]:
    """Une session par requête. Les services valident explicitement (commit) ; sinon rollback."""
    session = new_session()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def dispose_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
