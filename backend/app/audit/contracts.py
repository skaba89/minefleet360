"""Contrat public du module audit (ADR-001 : les autres modules n'importent que ce fichier).

Règles (CT-2, ADR-005, D-17) :
- une écriture métier réussie produit son événement dans la MÊME transaction (audit en échec = tout échoue) ;
- un refus 403 (ou un refus de sécurité 422) produit un événement DENIED dans une transaction distincte,
  validée même si la requête échoue ;
- jamais de valeur sensible : seuls les NOMS des champs sensibles modifiés sont listés.
"""

import logging
import uuid
from collections.abc import Iterable, Mapping
from typing import Any

from sqlalchemy.orm import Session

from app.audit.models import AuditEvent
from app.core.db import new_session
from app.core.request_context import get_request_meta
from app.core.tenancy import set_tenant_context

logger = logging.getLogger("minefleet.audit")

SENSITIVE_FIELDS = frozenset({"password", "password_hash", "token", "token_hash", "phone", "email", "secret"})


def _clean(data: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if data is None:
        return None
    return {
        k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in data.items() if k not in SENSITIVE_FIELDS
    }


def record(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    actor_kind: str = "USER",
    outcome: str = "SUCCESS",
    site_id: uuid.UUID | None = None,
    reason: str | None = None,
    before: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
    changed_fields: Iterable[str] | None = None,
) -> None:
    """Ajoute l'événement à la transaction courante (le contexte tenant doit être celui de tenant_id)."""
    meta = get_request_meta()
    db.add(
        AuditEvent(
            tenant_id=tenant_id,
            site_id=site_id,
            actor_user_id=actor_user_id,
            actor_kind=actor_kind if actor_user_id or actor_kind != "USER" else "ANONYMOUS",
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            outcome=outcome,
            reason=reason,
            changed_fields=sorted(changed_fields) if changed_fields is not None else None,
            before_data=_clean(before),
            after_data=_clean(after),
            request_id=meta.request_id if meta else None,
            ip_address=meta.ip_address if meta else None,
            user_agent=(meta.user_agent or "")[:300] if meta and meta.user_agent else None,
        )
    )
    db.flush()


def record_detached(*, tenant_id: uuid.UUID, **kwargs: Any) -> None:
    """Événement validé dans sa propre transaction (refus 403, refus de sécurité, échec de connexion)."""
    session = new_session()
    try:
        set_tenant_context(session, tenant_id)
        record(session, tenant_id=tenant_id, **kwargs)
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("audit_detached_failed", extra={"action": kwargs.get("action")})
        raise
    finally:
        session.close()
