"""Configuration par variables d'environnement (préfixe MF_). Aucun secret par défaut."""

import base64
import binascii
from datetime import timedelta
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

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
    # Affectations (D-13, US-1.22/1.23) : valeurs de développement à arbitrer (Q21, Q22).
    assignment_backdate_tolerance: timedelta = timedelta(minutes=15)
    assignment_end_future_tolerance: timedelta = timedelta(minutes=5)
    clock_skew_tolerance: timedelta = timedelta(minutes=5)
    # Statut de sécurité (immobilisation, atelier, suspension…) d'une ressource affectée (D-41) :
    #   block : refusé tant qu'une affectation est ouverte (D-11 d'origine) ;
    #   flag  : accepté, l'affectation reste ouverte et apparaît non conforme (défaut : la sécurité prime) ;
    #   close : accepté, les affectations ouvertes sont clôturées ou annulées automatiquement (audité).
    assignment_safety_policy: Literal["block", "flag", "close"] = "flag"
    # Horizon de planification (SEC1C-03) : valeur de développement, à arbitrer avec l'exploitation (C-11).
    assignment_max_horizon: timedelta = timedelta(days=31)
    # Filtre de conformité calculé en mémoire au lot 1 (D-12) : plafond des affectations actives évaluées.
    compliance_scan_max: int = 2000
    # Dispatch (lot 2b, PLAN_LOT2 §7) : valeurs de développement à valider avec l'exploitation.
    weighing_backdate_tolerance: timedelta = timedelta(days=7)  # saisie de tickets papier
    payload_alert_percent: int = Field(default=110, ge=100, le=200)  # RM-076, à valider (HSE)
    mission_max_rotations: int = Field(default=100, ge=1, le=1000)  # revue L2A-R-04
    rotation_min_cycle: timedelta = timedelta(minutes=5)  # en deçà : cycle suspect (indicateurs)
    indicators_max_period: timedelta = timedelta(days=92)

    # Délai max d'attente d'un verrou : échec rapide (409/500) plutôt qu'un blocage indéfini.
    db_lock_timeout_ms: int = 5000

    cookie_secure: bool = True
    allowed_origins: str = ""  # liste séparée par des virgules
    mail_capture_dir: str = "var/mail"
    mail_backend: Literal["capture", "smtp"] = "capture"
    mail_capture_ttl_seconds: int = Field(default=86400, ge=60, le=604800)
    smtp_host: str = ""
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str = ""
    smtp_password: SecretStr | None = None
    smtp_sender: str = ""
    smtp_use_ssl: bool = False
    smtp_timeout_seconds: int = Field(default=10, ge=1, le=60)
    # Double authentification TOTP (C-03, SEC-04). Clé AES-256 (base64url, 32 octets) obligatoire en
    # recette et production ; dérivée du secret JWT en local/test uniquement (développement).
    mfa_encryption_key: SecretStr | None = Field(default=None, validation_alias="MF_MFA_ENCRYPTION_KEY")
    # « enroll » : un rôle concerné sans second facteur n'accède qu'à son compte jusqu'à l'enrôlement.
    mfa_enforcement: Literal["enroll", "off"] = "enroll"
    # D-41 : direction et responsable des opérations ajoutés (vision large des données) ; modifiable.
    mfa_required_roles: tuple[str, ...] = (
        "PLATFORM_ADMIN",
        "TENANT_ADMIN",
        "DIRECTION",
        "OPS_MANAGER",
        "HR",
        "FINANCE",
    )
    mfa_challenge_ttl: timedelta = timedelta(minutes=5)
    mfa_issuer: str = "MINEFLEET 360"
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

    @model_validator(mode="after")
    def _mfa_key_required_on_servers(self) -> "Settings":
        if self.env in ("staging", "production") and self.mfa_encryption_key is None:
            raise ValueError("MF_MFA_ENCRYPTION_KEY est obligatoire en recette et en production")
        if self.mfa_encryption_key is not None:
            # Échec au démarrage plutôt qu'à la première connexion d'un utilisateur (revue MFA-R-07).
            raw = self.mfa_encryption_key.get_secret_value().strip()
            try:
                key = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
            except (ValueError, binascii.Error) as exc:
                raise ValueError("MF_MFA_ENCRYPTION_KEY n'est pas du base64url valide") from exc
            if len(key) != 32:
                raise ValueError("MF_MFA_ENCRYPTION_KEY doit contenir 32 octets (AES-256)")
        return self

    @property
    def allowed_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    def database_url(self, *, owner: bool = False) -> URL:
        if owner and self.owner_password is None:
            raise RuntimeError("MF_OWNER_PASSWORD requis pour les migrations (rôle mf_owner)")
        password = self.owner_password if owner and self.owner_password else self.app_password
        user = "mf_owner" if owner else "mf_app"
        return URL.create(
            drivername="postgresql+psycopg",
            username=user,
            password=password.get_secret_value(),
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )

    @property
    def destructive_migrations_allowed(self) -> bool:
        return self.env in ("local", "test", "ci")


@lru_cache
def get_settings() -> Settings:
    return Settings()
