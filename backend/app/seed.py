"""Jeu de données FICTIF (US-1.30) pour l'environnement de recette — jamais en production.

- Passe par les services applicatifs (audit, invariants et règles d'éligibilité réellement exercés),
  sous le rôle applicatif mf_app (A5).
- Refusé si MF_ENV=production (A3) ; refusé explicitement si déjà chargé (A4 : comportement retenu).
- Valeurs sentinelles reconnaissables (H9) : e-mails @example.com, téléphones +224000000xxx,
  noms « Nom-Test-NN », permis « PERMIS-FICTIF-NNNN » ; aucune donnée réelle, aucune position GPS.
- Les mots de passe sont générés à l'exécution et affichés UNE fois ; ils ne sont stockés nulle part en clair.
"""

import secrets
import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import select

from app.authz.dependencies import Authorized, load_grants
from app.authz.principal import Principal, evaluate
from app.core.clock import Clock, SystemClock
from app.core.config import Settings, get_settings
from app.core.db import new_session
from app.core.email import EmailMessage
from app.core.tenancy import PLATFORM_TENANT_ID, set_login_tenant_code, set_tenant_context
from app.fleet import service as fleet
from app.fleet.models import VehicleCategory
from app.fleet.schemas import VehicleCreate, VehicleStatusChange
from app.identity import service as identity
from app.identity.auth_service import AuthLimiters, accept_invitation
from app.identity.models import UserAccount, UserRoleAssignment
from app.identity.schemas import UserInvite
from app.organization import service as organization
from app.organization.models import Tenant
from app.organization.schemas import SiteCreate, TenantCreate
from app.workforce import service as workforce
from app.workforce.schemas import DriverCreate, LicenseCreate, QualificationCreate

TENANTS = (
    # code, raison sociale, sites (code, nom, type, fuseau) — S2 à décalage non nul pour les tests (D-23)
    (
        "fictif-minier",
        "Société Minière Fictive",
        (("MINE-A", "Mine fictive A", "MINE", None), ("PORT-B", "Port fictif B", "PORT", "Africa/Lagos")),
    ),
    (
        "fictif-transport",
        "Transports Fictifs",
        (
            ("DEPOT-1", "Dépôt fictif 1", "DEPOT", None),
            ("ATELIER-2", "Atelier fictif 2", "WORKSHOP", "Africa/Lagos"),
        ),
    ),
)
ROLES = ("OPS_MANAGER", "DISPATCHER", "HR", "WORKSHOP_CHIEF", "HSE", "DIRECTION", "FINANCE", "AUDITOR")
VEHICLES = (("RIGID_DUMP_TRUCK", 4), ("WHEEL_LOADER", 2), ("HYDRAULIC_EXCAVATOR", 1), ("LIGHT_VEHICLE", 3))


class SeedRefused(RuntimeError):
    pass


@dataclass
class SeedReport:
    accounts: list[tuple[str, str, str, str]] = field(
        default_factory=list
    )  # espace, e-mail, rôle, mot de passe
    counts: dict[str, int] = field(default_factory=dict)

    def add(self, key: str, n: int = 1) -> None:
        self.counts[key] = self.counts.get(key, 0) + n


class _Actor:
    """Exécute un service sous l'identité d'un compte fictif (contexte tenant reposé à chaque appel)."""

    def __init__(self, tenant_id: uuid.UUID, user_id: uuid.UUID, tenant_kind: str, clock: Clock) -> None:
        self.tenant_id, self.user_id, self.tenant_kind, self.clock = tenant_id, user_id, tenant_kind, clock

    def auth(self, permission: str) -> Authorized:
        db = new_session()
        set_tenant_context(db, self.tenant_id)
        principal = Principal(
            user_id=self.user_id,
            tenant_id=self.tenant_id,
            tenant_kind=self.tenant_kind,
            session_id=uuid.uuid4(),
            grants=load_grants(db, self.user_id, self.clock),
        )
        scope = evaluate(principal, permission)
        if scope is None:
            raise SeedRefused(f"le compte fictif n'a pas la permission {permission}")
        return Authorized(principal, scope, db, self.clock)


def _token(message: EmailMessage) -> str:
    return message.body.split("#token=")[1].split()[0]


def _activate(message: EmailMessage, password: str, clock: Clock, settings: Settings) -> None:
    db = new_session()
    try:
        accept_invitation(
            db,
            raw_token=_token(message),
            password=password,
            clock=clock,
            settings=settings,
            limiters=AuthLimiters(settings),
        )
    finally:
        db.close()


def _password() -> str:
    return "Fictif-" + secrets.token_urlsafe(12)


def _platform_admin(clock: Clock) -> _Actor:
    db = new_session()
    try:
        set_tenant_context(db, PLATFORM_TENANT_ID)
        user_id = db.execute(
            select(UserRoleAssignment.user_account_id).where(
                UserRoleAssignment.role_code == "PLATFORM_ADMIN", UserRoleAssignment.revoked_at.is_(None)
            )
        ).scalar_one_or_none()
    finally:
        db.close()
    if user_id is None:
        raise SeedRefused("aucun PLATFORM_ADMIN : exécuter d'abord `minefleet create-platform-admin`")
    return _Actor(PLATFORM_TENANT_ID, user_id, "PLATFORM", clock)


def _already_loaded(code: str) -> bool:
    db = new_session()
    try:
        set_login_tenant_code(db, code)
        return db.execute(select(Tenant.tenant_id).where(Tenant.code == code)).first() is not None
    finally:
        db.close()


def _user_id(tenant_id: uuid.UUID, email: str) -> uuid.UUID:
    db = new_session()
    try:
        set_tenant_context(db, tenant_id)
        return db.execute(select(UserAccount.user_account_id).where(UserAccount.email == email)).scalar_one()
    finally:
        db.close()


def _category_ids(tenant_id: uuid.UUID) -> dict[str, uuid.UUID]:
    db = new_session()
    try:
        set_tenant_context(db, tenant_id)
        return {c.code: c.vehicle_category_id for c in db.execute(select(VehicleCategory)).scalars()}
    finally:
        db.close()


def _mark_fictitious(tenant_id: uuid.UUID) -> None:
    """Drapeau `is_demo` (champ de gouvernance : contexte plateforme requis par tg_tenant_guard)."""
    db = new_session()
    try:
        set_tenant_context(db, PLATFORM_TENANT_ID)
        tenant = db.get(Tenant, tenant_id)
        assert tenant is not None
        tenant.is_demo = True
        db.commit()
    finally:
        db.close()


def seed(clock: Clock | None = None, settings: Settings | None = None) -> SeedReport:
    settings = settings or get_settings()
    clock = clock or SystemClock()
    if settings.env == "production":
        raise SeedRefused("chargement de données fictives refusé en production (US-1.30 A3)")
    if any(_already_loaded(code) for code, _, _ in TENANTS):
        raise SeedRefused("données fictives déjà chargées (US-1.30 A4 : réexécution refusée)")
    report = SeedReport()
    platform = _platform_admin(clock)
    today = clock.now().date()

    for t_index, (code, legal_name, sites) in enumerate(TENANTS, start=1):
        admin_email = f"admin@{code}.example.com"
        auth = platform.auth("organization.tenant.create")
        try:
            tenant, message = organization.create_tenant(
                auth,
                TenantCreate(
                    code=code,
                    legal_name=legal_name,
                    display_name=legal_name,
                    admin_email=admin_email,
                    admin_display_name="Admin Fictif",
                ),
                settings,
            )
        finally:
            auth.db.close()
        admin_password = _password()
        _activate(message, admin_password, clock, settings)
        _mark_fictitious(tenant.tenant_id)
        report.accounts.append((code, admin_email, "TENANT_ADMIN", admin_password))
        report.add("tenants")
        admin = _Actor(tenant.tenant_id, _user_id(tenant.tenant_id, admin_email), "CUSTOMER", clock)

        site_ids: list[uuid.UUID] = []
        for site_code, name, site_type, tz in sites:
            auth = admin.auth("organization.site.create")
            try:
                site = organization.create_site(
                    auth,
                    SiteCreate(code=site_code, name=name, site_type=site_type, timezone=tz),
                )
            finally:
                auth.db.close()
            site_ids.append(site.site_id)
            report.add("sites")

        actors: dict[str, _Actor] = {}
        for role in ROLES:
            scope, site_id = ("SITE", site_ids[0]) if role == "DISPATCHER" else ("TENANT", None)
            email = f"{role.lower()}@{code}.example.com"
            auth = admin.auth("identity.user.create")
            try:
                _, message = identity.invite_user(
                    auth,
                    UserInvite(
                        email=email,
                        display_name=f"Nom-Test {role}",
                        role_code=role,
                        scope_type=scope,
                        site_id=site_id,
                    ),
                    settings,
                )
            finally:
                auth.db.close()
            password = _password()
            _activate(message, password, clock, settings)
            report.accounts.append((code, email, role, password))
            actors[role] = _Actor(tenant.tenant_id, _user_id(tenant.tenant_id, email), "CUSTOMER", clock)
            report.add("users")

        categories = _category_ids(tenant.tenant_id)
        ops, hr = actors["OPS_MANAGER"], actors["HR"]
        n = 0
        for category_code, count in VEHICLES:
            for _ in range(count):
                n += 1
                auth = ops.auth("fleet.vehicle.create")
                try:
                    vehicle = fleet.create_vehicle(
                        auth,
                        VehicleCreate(
                            site_id=site_ids[n % 2],
                            vehicle_category_id=categories[category_code],
                            fleet_number=f"F{t_index}-{n:03d}",
                            registration_number=f"FICTIF-{t_index}{n:03d}"
                            if category_code != "WHEEL_LOADER"
                            else None,
                            make="MarqueFictive",
                            model=f"Modèle-{category_code[:4]}",
                            model_year=2020 + n % 5,
                        ),
                    )
                finally:
                    auth.db.close()
                report.add("vehicles")
                if n == 3:  # un engin immobilisé pour les tests d'éligibilité
                    auth = ops.auth("fleet.vehicle.update_status")
                    try:
                        fleet.change_status(
                            auth,
                            vehicle.vehicle_id,
                            VehicleStatusChange(status="IMMOBILIZED", reason_code="BREAKDOWN"),
                            vehicle.row_version,
                        )
                    finally:
                        auth.db.close()

        for d in range(1, 9):
            site_id = site_ids[d % 2]
            auth = hr.auth("workforce.driver.create")
            try:
                driver, _ = workforce.create_driver(
                    auth,
                    DriverCreate(
                        site_id=site_id,
                        employee_number=f"MAT-{t_index}{d:03d}",
                        last_name=f"Nom-Test-{d:02d}",
                        first_name="Prénom-Test",
                        phone=f"+224000000{t_index}{d:02d}",
                    ),
                )
            finally:
                auth.db.close()
            report.add("drivers")
            # Échéances variées : valide, proche, expirée (tests d'éligibilité et de la liste des échéances).
            expiry = {1: today - timedelta(days=30), 2: today + timedelta(days=10)}.get(
                d % 4, today + timedelta(days=1500)
            )
            auth = hr.auth("workforce.driver_license.manage")
            try:
                workforce.create_license(
                    auth,
                    driver.driver_id,
                    LicenseCreate(
                        license_number=f"PERMIS-FICTIF-{t_index}{d:03d}",
                        category_code="C",
                        issue_date=date(2019, 1, 15),
                        expiry_date=expiry,
                    ),
                )
            finally:
                auth.db.close()
            report.add("licenses")
            auth = hr.auth("workforce.driver_qualification.manage")
            try:
                workforce.create_qualification(
                    auth,
                    driver.driver_id,
                    QualificationCreate(
                        qualification_type="DRIVING_AUTHORIZATION",
                        vehicle_category_id=categories["RIGID_DUMP_TRUCK"],
                        valid_from=date(2024, 1, 1),
                        valid_to=today + timedelta(days=700),
                    ),
                )
            finally:
                auth.db.close()
            report.add("qualifications")
    return report
