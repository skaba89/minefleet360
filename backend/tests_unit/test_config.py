"""Tests de configuration sans dépendance à PostgreSQL."""

import pytest
from pydantic import SecretStr
from sqlalchemy.engine import URL, make_url

from app.core.config import Settings

APP_PASSWORD = "synthetic-app:p@ss/word#with%reserved"
OWNER_PASSWORD = "synthetic-owner:p@ss/word#with%reserved"


def _settings() -> Settings:
    return Settings(
        MF_APP_PASSWORD=APP_PASSWORD,
        MF_OWNER_PASSWORD=OWNER_PASSWORD,
        jwt_secret=SecretStr("synthetic-jwt-secret-at-least-32-characters"),
        db_host="db.internal",
        db_port=5544,
        db_name="minefleet_test",
    )


@pytest.mark.parametrize(
    ("owner", "expected_user", "expected_password"),
    ((False, "mf_app", APP_PASSWORD), (True, "mf_owner", OWNER_PASSWORD)),
)
def test_database_url_preserves_reserved_characters(
    owner: bool, expected_user: str, expected_password: str
) -> None:
    url = _settings().database_url(owner=owner)

    assert isinstance(url, URL)
    assert (url.drivername, url.username, url.password) == (
        "postgresql+psycopg",
        expected_user,
        expected_password,
    )
    assert (url.host, url.port, url.database) == ("db.internal", 5544, "minefleet_test")
    assert make_url(url.render_as_string(hide_password=False)).password == expected_password
    assert expected_password not in str(url)
    assert expected_password not in repr(url)


def test_owner_database_url_requires_owner_secret() -> None:
    settings = Settings(
        MF_APP_PASSWORD=APP_PASSWORD,
        jwt_secret=SecretStr("synthetic-jwt-secret-at-least-32-characters"),
    )

    with pytest.raises(RuntimeError, match="MF_OWNER_PASSWORD requis"):
        settings.database_url(owner=True)
