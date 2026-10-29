import uuid

from sqlalchemy import select

from app.authz.dependencies import Authorized
from app.fleet.gps_binding_models import FleetGpsDeviceBinding
from app.fleet.gps_credential_models import FleetGpsDeviceCredential
from app.fleet.gps_models import FleetGpsPosition
from app.fleet.gps_phone_models import FleetGpsPhoneShare
from app.identity.models import AuthSession, UserAccount


def active_sources(auth: Authorized, positions: list[FleetGpsPosition]) -> set[uuid.UUID]:
    """État du partage, sans exposer l'identité du compte ou les secrets aux lecteurs GPS."""
    now = auth.clock.now()
    phones = auth.db.scalars(
        select(FleetGpsPhoneShare.phone_share_id)
        .join(
            AuthSession,
            (AuthSession.tenant_id == FleetGpsPhoneShare.tenant_id)
            & (AuthSession.auth_session_id == FleetGpsPhoneShare.auth_session_id),
        )
        .join(
            UserAccount,
            (UserAccount.tenant_id == FleetGpsPhoneShare.tenant_id)
            & (UserAccount.user_account_id == FleetGpsPhoneShare.user_account_id),
        )
        .where(
            FleetGpsPhoneShare.tenant_id == auth.tenant_id,
            FleetGpsPhoneShare.phone_share_id.in_([p.phone_share_id for p in positions if p.phone_share_id]),
            FleetGpsPhoneShare.stopped_at.is_(None),
            FleetGpsPhoneShare.expires_at > now,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > now,
            UserAccount.status == "ACTIVE",
        )
    )
    phone_ids = set(phones)
    active = {p.gps_position_id for p in positions if p.phone_share_id in phone_ids}
    trackers = auth.db.scalars(
        select(FleetGpsDeviceBinding)
        .join(
            FleetGpsDeviceCredential,
            (FleetGpsDeviceCredential.tenant_id == FleetGpsDeviceBinding.tenant_id)
            & (FleetGpsDeviceCredential.gps_device_binding_id == FleetGpsDeviceBinding.gps_device_binding_id),
        )
        .where(
            FleetGpsDeviceBinding.tenant_id == auth.tenant_id,
            FleetGpsDeviceBinding.device_id.in_([p.device_id for p in positions if p.source == "TRACKER"]),
            FleetGpsDeviceBinding.revoked_at.is_(None),
            FleetGpsDeviceBinding.active_from <= now,
            FleetGpsDeviceCredential.revoked_at.is_(None),
            FleetGpsDeviceCredential.active_from <= now,
        )
    )
    bindings = list(trackers)
    active.update(
        p.gps_position_id
        for p in positions
        if p.source == "TRACKER"
        and any(
            b.device_id == p.device_id
            and b.vehicle_id == p.vehicle_id
            and b.site_id == p.site_id
            and b.active_from <= p.recorded_at
            for b in bindings
        )
    )
    return active
