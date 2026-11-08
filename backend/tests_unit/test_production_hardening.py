"""Durcissement production : OpenAPI non publiée et secrets serveur dédiés (aucune dépendance PostgreSQL).

En production, /openapi.json et /docs exposent la cartographie des permissions (x-permission) et
élargissent la surface de reconnaissance : ils sont désactivés quand MF_ENV=production. Les autres
environnements (local, test, ci, staging) les conservent pour le contrat OpenAPI et le support.

La clé HMAC des compteurs de limitation (rate-limiting) est dédiée du secret JWT : obligatoire en
recette/production (MF_RATE_LIMIT_KEY), dérivée du secret JWT en local/test/ci uniquement.
"""

import base64
import hashlib
import hmac
import os
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

# app.main instancie l'application au niveau module (app = create_app(), point d'entrée uvicorn) :
# l'environnement doit donc être valide AVANT l'import. Valeurs synthétiques, comme tests_unit/test_config.py.
os.environ.setdefault("MF_ENV", "ci")
os.environ.setdefault("MF_APP_PASSWORD", "synthetic-app:p@ss/word#with%reserved")
os.environ.setdefault("MF_JWT_SECRET", "cle-de-test-production-au-moins-32-caracteres")

from app.core.config import get_settings
from app.main import create_app

JWT_SECRET = "cle-de-test-production-au-moins-32-caracteres"
RATE_LIMIT_KEY = "cle-rate-limit-dediee-test-au-moins-32-caracteres"
# Clé MFA factice : 32 octets nuls encodés en base64url (validation : longueur décodée == 32).
MFA_KEY = base64.urlsafe_b64encode(b"\x00" * 32).decode()


def _install_env(monkeypatch: pytest.MonkeyPatch, env: str) -> None:
    monkeypatch.setenv("MF_ENV", env)
    monkeypatch.setenv("MF_JWT_SECRET", JWT_SECRET)
    # SMTP minimal : la capture email est interdite en production (garde-fou existant, revu ici).
    if env == "production":
        monkeypatch.setenv("MF_MAIL_BACKEND", "smtp")
        monkeypatch.setenv("MF_SMTP_HOST", "smtp.internal")
        monkeypatch.setenv("MF_SMTP_SENDER", "no-reply@example.com")
        monkeypatch.setenv("MF_PUBLIC_WEB_URL", "https://minefleet.example.com")
    if env in ("staging", "production"):
        monkeypatch.setenv("MF_MFA_ENCRYPTION_KEY", MFA_KEY)
        monkeypatch.setenv("MF_RATE_LIMIT_KEY", RATE_LIMIT_KEY)
    else:
        monkeypatch.delenv("MF_MFA_ENCRYPTION_KEY", raising=False)
        monkeypatch.delenv("MF_RATE_LIMIT_KEY", raising=False)
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _settings_isolation(monkeypatch: pytest.MonkeyPatch):
    """Restaure l'environnement et purge le cache Settings après chaque test, dans cet ordre."""
    yield
    monkeypatch.undo()
    get_settings.cache_clear()


def test_openapi_et_docs_non_publies_en_production(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_env(monkeypatch, "production")
    app = create_app()

    assert app.openapi_url is None
    assert app.docs_url is None

    client = TestClient(app)
    assert client.get("/api/v1/openapi.json").status_code == 404
    assert client.get("/api/v1/docs").status_code == 404


@pytest.mark.parametrize("env", ["local", "test", "ci", "staging"])
def test_openapi_conserve_hors_production(monkeypatch: pytest.MonkeyPatch, env: str) -> None:
    _install_env(monkeypatch, env)
    app = create_app()

    assert app.openapi_url == "/api/v1/openapi.json"
    assert app.docs_url == "/api/v1/docs"


def test_health_reste_disponible_en_production(monkeypatch: pytest.MonkeyPatch) -> None:
    # Le contrôle de rôle base de données appartient au lifespan (lancement réel), pas à la construction.
    _install_env(monkeypatch, "production")
    app = create_app()
    client = TestClient(app)

    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers.get("cache-control") == "no-store"


def test_secret_jwt_faible_refuse_en_production(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_env(monkeypatch, "production")
    monkeypatch.setenv("MF_JWT_SECRET", "trop-court")
    get_settings.cache_clear()

    with pytest.raises(ValueError, match="MF_JWT_SECRET"):
        get_settings()


@pytest.mark.parametrize("env", ["staging", "production"])
def test_cle_rate_limit_obligatoire_sur_serveurs(monkeypatch: pytest.MonkeyPatch, env: str) -> None:
    _install_env(monkeypatch, env)
    monkeypatch.delenv("MF_RATE_LIMIT_KEY", raising=False)
    get_settings.cache_clear()

    with pytest.raises(ValueError, match="MF_RATE_LIMIT_KEY"):
        get_settings()


def test_cle_rate_limit_trop_courte_refusee(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_env(monkeypatch, "ci")
    monkeypatch.setenv("MF_RATE_LIMIT_KEY", "trop-court")
    get_settings.cache_clear()

    with pytest.raises(ValueError, match="MF_RATE_LIMIT_KEY"):
        get_settings()


def test_cle_rate_limit_dediee_utilisee_si_fournie(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_env(monkeypatch, "ci")
    monkeypatch.setenv("MF_RATE_LIMIT_KEY", RATE_LIMIT_KEY)
    get_settings.cache_clear()

    settings = get_settings()
    assert settings.rate_limit_hmac_key == RATE_LIMIT_KEY.encode()
    assert settings.rate_limit_hmac_key != JWT_SECRET.encode()


def test_cle_rate_limit_derivee_du_jwt_en_developpement(monkeypatch: pytest.MonkeyPatch) -> None:
    # local supprime MF_RATE_LIMIT_KEY : le harnais de développement dérive la clé du secret JWT.
    _install_env(monkeypatch, "local")

    settings = get_settings()
    assert settings.rate_limit_hmac_key == JWT_SECRET.encode()


def test_compteurs_limitation_haches_avec_la_cle_dediee(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.ratelimit import FailureLimiter

    _install_env(monkeypatch, "ci")
    monkeypatch.setenv("MF_RATE_LIMIT_KEY", RATE_LIMIT_KEY)
    get_settings.cache_clear()
    limiter = FailureLimiter("login:user", 5, timedelta(minutes=15))

    expected = hmac.new(RATE_LIMIT_KEY.encode(), b"login:user:+224-620-00-00-00", hashlib.sha256)
    assert limiter._key("+224-620-00-00-00") == expected.hexdigest()
    jwt_derived = hmac.new(JWT_SECRET.encode(), b"login:user:+224-620-00-00-00", hashlib.sha256)
    assert limiter._key("+224-620-00-00-00") != jwt_derived.hexdigest()
