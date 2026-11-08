"""Durcissement production : la spécification OpenAPI n'est pas publiée (aucune dépendance PostgreSQL).

En production, /openapi.json et /docs exposent la cartographie des permissions (x-permission) et
élargissent la surface de reconnaissance : ils sont désactivés quand MF_ENV=production. Les autres
environnements (local, test, ci, staging) les conservent pour le contrat OpenAPI et le support.
"""

import base64
import os

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
    else:
        monkeypatch.delenv("MF_MFA_ENCRYPTION_KEY", raising=False)
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
