"""Signal transactionnel pour les nouvelles positions GPS.

PostgreSQL ne délivre NOTIFY qu'au COMMIT : un rollback n'émet aucun signal.
Le message n'expose pas de coordonnées, d'identifiant de véhicule ou d'utilisateur.
Le payload tenant sert uniquement à écarter les wakeups étrangers ; les lectures
réelles restent authentifiées, filtrées par permissions et par RLS.
"""

import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

GPS_NOTIFICATION_CHANNEL = "minefleet_gps_positions"


def notify_gps_position(db: Session, tenant_id: uuid.UUID) -> None:
    """Inscrire un événement dans la transaction courante, sans committer.

    Ne pas appeler pour les doublons/rejets : seul l'appelant qui insère une
    position acceptée doit produire un événement.
    """
    db.execute(
        text("SELECT pg_notify(:channel, :payload)"),
        {"channel": GPS_NOTIFICATION_CHANNEL, "payload": str(tenant_id)},
    )
