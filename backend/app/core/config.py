"""Configuration par variables d'environnement (préfixe MF_). Aucun secret par défaut."""

from datetime import timedelta
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "test", "ci", "staging", "production"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MF_", extra="ignore")

    env: Environment = "local"

    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "minefleet"
    app_password: SecretStr = Field(validation_alias="MF_APP_PASSWORD")
    # Absent du processus API en déploiement (moindre privilège) : requis seulement pour les migrations.
    owner_password: SecretStr | None = Field(default=None, validation_alias="MF_OWNER_PASSWORD")

    jwt_secret: SecretStr
    jwt_algorithm: Literal["HS256"] = "HS256"

    # Valeurs de développement provisoires (USER_STORIES §0.5) : à arbitrer avant pilote (Q21, Q22).
    access_token_ttl: timedelta = timedelta(minutes=15)
    session_max_age: timedelta = timedelta(hours=12)
    refresh_grace_period: timedelta = timedelta(seconds=30)
    invitation_ttl: timedelta = timedelta(days=7)
    reset_token_ttl: timedelta = timedelta(hours=1)
    login_max_failures: int = 5
    # Par adresse IP : seuil plus haut (plusieurs utilisateurs d'un site derrière un même NAT).
    login_ip_max_failures: int = 50
    login_lockout_duration: timedelta = timedelta(minutes=15)
    password_min_length: int = 12
    password_max_length: int = 128
    expiry_warning_days: int = 30  # EXPIRY_WARNING_DAYS (Q21, valeur de développement)
    page_size_default: int = 50
    page_size_max: int = 200
    blocking_list_max: int = 20

    # Délai max d'attente d'un verrou : échec rapide (409/500) plutôt qu'un blocage indéfini.
    db_lock_timeout_ms: int = 5000

    cookie_secure: bool = True
    allowed_origins: str = ""  # liste séparée par des virgules
    mail_capture_dir: str = "var/mail"
    platform_tenant_code: str = "mf-platform"
    # Codes d'espace refusés à la création d'un tenant client (MATRICE_RBAC §1.3).
    reserved_tenant_codes: tuple[str, ...] = ("mf-platform", "admin", "api", "platform", "support", "www")
    public_web_url: str = "http://localhost:5173"

    @field_validator("jwt_secret")
    @classmethod
    def _jwt_secret_strength(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError("MF_JWT_SECRET doit contenir au moins 32 caractères")
        return value

    @property
    def allowed_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    def database_url(self, *, owner: bool = False) -> str:
        if owner and self.owner_password is None:
            raise RuntimeError("MF_OWNER_PASSWORD requis pour les migrations (rôle mf_owner)")
        password = self.owner_password if owner and self.owner_password else self.app_password
        user = "mf_owner" if owner else "mf_app"
        return (
            f"postgresql+psycopg://{user}:{password.get_secret_value()}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def destructive_migrations_allowed(self) -> bool:
        return self.env in ("local", "test", "ci")


@lru_cache
def get_settings() -> Settings:
    return Settings()
