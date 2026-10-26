import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from app.core.http import StrictModel

ScopeType = Literal["PLATFORM", "TENANT", "SITE"]
PHONE_PATTERN = r"^\+[1-9][0-9]{6,14}$"


# --- Authentification ---------------------------------------------------------------------------------


class LoginRequest(StrictModel):
    workspace_code: str = Field(min_length=1, max_length=64)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class PlatformLoginRequest(StrictModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class SessionUser(BaseModel):
    user_account_id: uuid.UUID
    display_name: str
    workspace_code: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 (type de jeton OAuth2, pas un secret)
    expires_in: int
    user: SessionUser


class TokenPasswordRequest(StrictModel):
    token: str = Field(min_length=10, max_length=200)
    password: str = Field(min_length=1, max_length=256)


class ResetRequest(StrictModel):
    workspace_code: str = Field(min_length=1, max_length=64)
    email: str = Field(min_length=3, max_length=254)


class ChangePasswordRequest(StrictModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


# --- Utilisateurs -------------------------------------------------------------------------------------


class UserInvite(StrictModel):
    email: EmailStr
    display_name: str = Field(min_length=2, max_length=100)
    phone: str | None = Field(default=None, pattern=PHONE_PATTERN)
    role_code: str = Field(min_length=2, max_length=40)
    scope_type: ScopeType
    site_id: uuid.UUID | None = None


class UserUpdate(StrictModel):
    display_name: str | None = Field(default=None, min_length=2, max_length=100)
    phone: str | None = Field(default=None, pattern=PHONE_PATTERN)


class UserOut(BaseModel):
    """email et phone sont ABSENTS de la réponse pour les rôles non autorisés (D-15, field_policies)."""

    user_account_id: uuid.UUID
    display_name: str
    status: str
    email: str | None = None
    phone: str | None = None
    last_login_at: datetime | None = None
    created_at: datetime
    row_version: int


class GrantOut(BaseModel):
    role_code: str
    scope_type: str
    site_id: uuid.UUID | None


class MeOut(BaseModel):
    user_account_id: uuid.UUID
    display_name: str
    email: str
    workspace_code: str
    tenant_display_name: str
    timezone: str
    grants: list[GrantOut]


# --- Rôles --------------------------------------------------------------------------------------------


class RoleOut(BaseModel):
    role_code: str
    label_fr: str
    allowed_scopes: list[str]
    is_optional: bool


class RoleAssignmentCreate(StrictModel):
    user_account_id: uuid.UUID
    role_code: str = Field(min_length=2, max_length=40)
    scope_type: ScopeType
    site_id: uuid.UUID | None = None


class RoleAssignmentOut(BaseModel):
    user_role_assignment_id: uuid.UUID
    user_account_id: uuid.UUID
    role_code: str
    scope_type: str
    site_id: uuid.UUID | None
    valid_from: datetime
    valid_to: datetime | None
    granted_by: uuid.UUID
    revoked_at: datetime | None
    revoked_by: uuid.UUID | None
    row_version: int
