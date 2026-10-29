"""Parcours téléphone et provisionnement GPS, sous identité et périmètre explicites."""

import uuid
from datetime import timedelta

from sqlalchemy import Select, or_, select

from app.assignment.models import VehicleAssignment
from app.audit.contracts import record
from app.authz.dependencies import Authorized
from app.core.errors import AppError
from app.core.security import CompositeToken
from app.fleet.gps_binding_models import FleetGpsDeviceBinding
from app.fleet.gps_credential_models import FleetGpsDeviceCredential
from app.fleet.gps_device_credentials import fingerprint_device_secret, new_device_secret
from app.fleet.gps_live_schemas import (
    DriverAccountIn,
    PhonePointIn,
    PhoneShareOut,
    PhoneStartIn,
    TrackerCreateIn,
    TrackerProvisionOut,
)
from app.fleet.gps_models import FleetGpsPosition
from app.fleet.gps_phone_models import FleetGpsPhoneShare
from app.fleet.models import Vehicle
from app.identity.models import UserAccount, UserRoleAssignment
from app.workforce.models import Driver

MANAGERS = frozenset({"TENANT_ADMIN", "OPS_MANAGER", "DISPATCHER"})


def _event(auth: Authorized, action: str, entity: uuid.UUID, site: uuid.UUID) -> None:
    # Aucun secret, nom, numéro de téléphone ou coordonnée dans le journal métier.
    record(
        auth.db,
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        action=action,
        entity_type="gps",
        entity_id=entity,
        site_id=site,
    )


def _driver_vehicle_ids(auth: Authorized) -> Select[uuid.UUID]:
    now = auth.clock.now()
    return (
        select(VehicleAssignment.vehicle_id)
        .join(
            Driver,
            (Driver.tenant_id == VehicleAssignment.tenant_id)
            & (Driver.driver_id == VehicleAssignment.driver_id),
        )
        .where(
            VehicleAssignment.tenant_id == auth.tenant_id,
            Driver.user_account_id == auth.user_id,
            Driver.status == "ACTIVE",
            VehicleAssignment.status == "ACTIVE",
            VehicleAssignment.valid_from <= now,
            or_(VehicleAssignment.valid_to.is_(None), VehicleAssignment.valid_to > now),
        )
    )


def sharing_vehicles(auth: Authorized) -> list[Vehicle]:
    stmt = select(Vehicle).where(Vehicle.tenant_id == auth.tenant_id, Vehicle.status != "RETIRED")
    if not auth.scope.tenant_wide:
        stmt = stmt.where(Vehicle.site_id.in_(auth.scope.site_ids))
    # Un rôle conducteur sur S1 ne transforme pas un rôle manager sur S2 en accès manager sur S1.
    manager_sites = [site for role, site in auth.scope.role_grants if role in MANAGERS]
    if None not in manager_sites:
        stmt = stmt.where(
            or_(
                Vehicle.site_id.in_([s for s in manager_sites if s is not None]),
                Vehicle.vehicle_id.in_(_driver_vehicle_ids(auth)),
            )
        )
    return list(auth.db.scalars(stmt.order_by(Vehicle.fleet_number).limit(200)))


def _vehicle(auth: Authorized, vehicle_id: uuid.UUID, *, sharing: bool = False) -> Vehicle:
    vehicle = auth.db.scalar(
        select(Vehicle)
        .where(
            Vehicle.tenant_id == auth.tenant_id,
            Vehicle.vehicle_id == vehicle_id,
        )
        .with_for_update()
    )
    if vehicle is None or not auth.scope.covers_site(vehicle.site_id):
        raise AppError("NOT_FOUND")
    if vehicle.status == "RETIRED":
        raise AppError("CONFLICT")
    if sharing and not (auth.scope.roles_for_site(vehicle.site_id) & MANAGERS):
        assigned = auth.db.scalar(
            _driver_vehicle_ids(auth).where(
                VehicleAssignment.vehicle_id == vehicle_id,
                VehicleAssignment.site_id == vehicle.site_id,
            )
        )
        if assigned is None:
            raise AppError("NOT_FOUND")
    return vehicle


def _lock_user(auth: Authorized) -> None:
    auth.db.scalar(
        select(UserAccount)
        .where(
            UserAccount.tenant_id == auth.tenant_id,
            UserAccount.user_account_id == auth.user_id,
        )
        .with_for_update(key_share=True)
    )


def start_phone(auth: Authorized, body: PhoneStartIn) -> PhoneShareOut:
    _lock_user(auth)
    vehicle = _vehicle(auth, body.vehicle_id, sharing=True)
    now = auth.clock.now()
    for old in auth.db.scalars(
        select(FleetGpsPhoneShare)
        .where(
            FleetGpsPhoneShare.tenant_id == auth.tenant_id,
            FleetGpsPhoneShare.user_account_id == auth.user_id,
            FleetGpsPhoneShare.stopped_at.is_(None),
        )
        .with_for_update()
    ):
        old.stopped_at = now
        _event(auth, "gps.phone.stop", old.phone_share_id, old.site_id)
    share = FleetGpsPhoneShare(
        tenant_id=auth.tenant_id,
        user_account_id=auth.user_id,
        auth_session_id=auth.principal.session_id,
        vehicle_id=vehicle.vehicle_id,
        site_id=vehicle.site_id,
        started_at=now,
        expires_at=now + timedelta(hours=12),
    )
    auth.db.add(share)
    auth.db.flush()
    _event(auth, "gps.phone.start", share.phone_share_id, share.site_id)
    out = PhoneShareOut.model_validate(share)
    auth.db.commit()
    return out


def _share(auth: Authorized, share_id: uuid.UUID) -> FleetGpsPhoneShare:
    share = auth.db.scalar(
        select(FleetGpsPhoneShare)
        .where(
            FleetGpsPhoneShare.tenant_id == auth.tenant_id,
            FleetGpsPhoneShare.phone_share_id == share_id,
            FleetGpsPhoneShare.user_account_id == auth.user_id,
        )
        .with_for_update()
    )
    if share is None:
        raise AppError("NOT_FOUND")
    return share


def stop_phone(auth: Authorized, share_id: uuid.UUID) -> None:
    _lock_user(auth)
    share = _share(auth, share_id)
    if share.stopped_at is None:
        share.stopped_at = auth.clock.now()
        _event(auth, "gps.phone.stop", share.phone_share_id, share.site_id)
    auth.db.commit()


def phone_point(auth: Authorized, share_id: uuid.UUID, body: PhonePointIn) -> None:
    _lock_user(auth)
    share = _share(auth, share_id)
    now = auth.clock.now()
    if share.stopped_at is not None or share.expires_at <= now:
        raise AppError("CONFLICT", message_fr="Le partage est arrêté ou expiré.")
    if share.auth_session_id != auth.principal.session_id:
        raise AppError("NOT_FOUND")
    vehicle = _vehicle(auth, share.vehicle_id, sharing=True)
    if vehicle.site_id != share.site_id:
        raise AppError("CONFLICT", message_fr="Le véhicule a changé de site. Recommencez le partage.")
    if (
        not max(share.started_at, now - timedelta(minutes=2))
        <= body.recorded_at
        <= now + timedelta(seconds=5)
    ):
        raise AppError("VALIDATION_ERROR", message_fr="Le relevé du téléphone est trop ancien ou futur.")
    if share.last_recorded_at is not None and body.recorded_at <= share.last_recorded_at:
        raise AppError("CONFLICT")
    if share.last_received_at is not None and now - share.last_received_at < timedelta(seconds=5):
        raise AppError("RATE_LIMITED", headers={"Retry-After": "5"})
    auth.db.add(
        FleetGpsPosition(
            tenant_id=auth.tenant_id,
            vehicle_id=vehicle.vehicle_id,
            site_id=share.site_id,
            device_id=f"phone:{share.phone_share_id}",
            source="PHONE",
            phone_share_id=share.phone_share_id,
            latitude=body.latitude,
            longitude=body.longitude,
            accuracy_m=body.accuracy_m,
            speed_kmh=body.speed_kmh,
            recorded_at=body.recorded_at,
            received_at=now,
        )
    )
    share.last_received_at = now
    share.last_recorded_at = body.recorded_at
    # La position est son propre enregistrement immuable ; pas de copie des coordonnées dans l'audit.
    auth.db.commit()


def tracker_for_vehicle(auth: Authorized, vehicle_id: uuid.UUID) -> FleetGpsDeviceBinding | None:
    _vehicle(auth, vehicle_id)
    return auth.db.scalar(
        select(FleetGpsDeviceBinding)
        .where(
            FleetGpsDeviceBinding.tenant_id == auth.tenant_id,
            FleetGpsDeviceBinding.vehicle_id == vehicle_id,
            FleetGpsDeviceBinding.revoked_at.is_(None),
        )
        .with_for_update()
    )


def provision_tracker(auth: Authorized, vehicle_id: uuid.UUID, body: TrackerCreateIn) -> TrackerProvisionOut:
    vehicle = _vehicle(auth, vehicle_id)
    if tracker_for_vehicle(auth, vehicle_id) is not None:
        raise AppError("CONFLICT", message_fr="Révoquez le traceur actuel avant d'en associer un autre.")
    if body.device_id.startswith("phone:"):
        raise AppError("VALIDATION_ERROR")
    now = auth.clock.now()
    binding = FleetGpsDeviceBinding(
        tenant_id=auth.tenant_id,
        vehicle_id=vehicle_id,
        site_id=vehicle.site_id,
        device_id=body.device_id,
        active_from=now,
    )
    auth.db.add(binding)
    auth.db.flush()
    secret = new_device_secret()
    auth.db.add(
        FleetGpsDeviceCredential(
            tenant_id=auth.tenant_id,
            gps_device_binding_id=binding.gps_device_binding_id,
            secret_fingerprint=fingerprint_device_secret(secret),
            active_from=now,
        )
    )
    token = "gps_" + CompositeToken(auth.tenant_id, binding.gps_device_binding_id, secret).encode()
    _event(auth, "gps.tracker.provision", binding.gps_device_binding_id, vehicle.site_id)
    out = TrackerProvisionOut(
        **{
            k: getattr(binding, k)
            for k in ("gps_device_binding_id", "device_id", "active_from", "revoked_at")
        },
        token=token,
    )
    auth.db.commit()
    return out


def revoke_tracker(auth: Authorized, vehicle_id: uuid.UUID) -> None:
    binding = tracker_for_vehicle(auth, vehicle_id)
    if binding is not None:
        # Les contraintes historiques exigent revoked_at > active_from même avec une horloge figée.
        now = max(auth.clock.now(), binding.active_from + timedelta(microseconds=1))
        binding.revoked_at = now
        for credential in auth.db.scalars(
            select(FleetGpsDeviceCredential)
            .where(
                FleetGpsDeviceCredential.tenant_id == auth.tenant_id,
                FleetGpsDeviceCredential.gps_device_binding_id == binding.gps_device_binding_id,
                FleetGpsDeviceCredential.revoked_at.is_(None),
            )
            .with_for_update()
        ):
            credential.revoked_at = now
        _event(auth, "gps.tracker.revoke", binding.gps_device_binding_id, binding.site_id)
    auth.db.commit()


def driver_account(
    auth: Authorized, driver_id: uuid.UUID, body: DriverAccountIn | None = None
) -> uuid.UUID | None:
    driver = auth.db.scalar(
        select(Driver)
        .where(
            Driver.tenant_id == auth.tenant_id,
            Driver.driver_id == driver_id,
        )
        .with_for_update()
    )
    if driver is None or not auth.scope.covers_site(driver.site_id):
        raise AppError("NOT_FOUND")
    if body is None:
        return driver.user_account_id
    if body.user_account_id is not None:
        account = auth.db.scalar(
            select(UserAccount)
            .where(
                UserAccount.tenant_id == auth.tenant_id,
                UserAccount.user_account_id == body.user_account_id,
                UserAccount.status == "ACTIVE",
            )
            .with_for_update()
        )
        now = auth.clock.now()
        grant = auth.db.scalar(
            select(UserRoleAssignment.user_role_assignment_id)
            .where(
                UserRoleAssignment.tenant_id == auth.tenant_id,
                UserRoleAssignment.user_account_id == body.user_account_id,
                UserRoleAssignment.role_code == "DRIVER",
                UserRoleAssignment.site_id == driver.site_id,
                UserRoleAssignment.revoked_at.is_(None),
                UserRoleAssignment.valid_from <= now,
                or_(UserRoleAssignment.valid_to.is_(None), UserRoleAssignment.valid_to > now),
            )
            .limit(1)
        )
        duplicate = auth.db.scalar(
            select(Driver.driver_id)
            .where(
                Driver.tenant_id == auth.tenant_id,
                Driver.user_account_id == body.user_account_id,
                Driver.driver_id != driver_id,
            )
            .limit(1)
        )
        if account is None or grant is None or duplicate is not None:
            raise AppError("REFERENCE_NOT_FOUND")
    previous = driver.user_account_id
    driver.user_account_id = body.user_account_id
    if previous is not None and previous != body.user_account_id:
        for share in auth.db.scalars(
            select(FleetGpsPhoneShare)
            .where(
                FleetGpsPhoneShare.tenant_id == auth.tenant_id,
                FleetGpsPhoneShare.user_account_id == previous,
                FleetGpsPhoneShare.stopped_at.is_(None),
            )
            .with_for_update()
        ):
            share.stopped_at = auth.clock.now()
    _event(auth, "gps.driver.link_account", driver_id, driver.site_id)
    auth.db.commit()
    return driver.user_account_id
