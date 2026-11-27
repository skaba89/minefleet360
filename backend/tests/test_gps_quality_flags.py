"""Flags de qualité §1.3 évalués à l'ingestion : `late` et `clock_skew_suspect`.

Chaque scénario passe par la **vraie API traceur** (authentification composite,
anti-rejeu atomique) puis vérifie les drapeaux stockés sur la ligne. Le retard
est **réel** : l'horodatage appareil est posé juste après l'activation du
traceur, puis l'émission attend réellement — aucune horloge n'est décalée
artificiellement côté client. Les seuils sont resserrés par variables
d'environnement (lues avant toute instanciation de `Settings`, pendant la
collecte pytest) pour rendre les marges déterministes : retard 10 s,
tolérance de décalage 2 s. Aucun horodatage n'est corrigé : les drapeaux
capturent l'évaluation faite à l'ingestion.

Écart assumé (§1.3) : le « recalcul des états/géofences » après position
tardive n'est pas implémenté — le drapeau est stocké, l'historique reste
cohérent ; la quarantaine brute (§1.5) reste ouverte.
"""

import os
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import new_session
from app.core.tenancy import set_tenant_context
from tests.test_assignment import World, _vehicle, w  # noqa: F401
from tests.test_gps_simulateur_degrades import _compte_positions, _envoi, _tracker

os.environ.setdefault("MF_GPS_LATE_THRESHOLD_SECONDS", "10")
os.environ.setdefault("MF_GPS_CLOCK_SKEW_TOLERANCE_SECONDS", "2")


def _drapeaux(tenant_id, device: str) -> tuple[bool | None, bool | None]:
    db: Session = new_session()
    try:
        set_tenant_context(db, tenant_id)
        ligne = db.execute(
            text(
                "SELECT late, clock_skew_suspect FROM fleet_gps_position"
                " WHERE device_id = :d ORDER BY received_at DESC LIMIT 1"
            ),
            {"d": device},
        ).one()
        return ligne.late, ligne.clock_skew_suspect
    finally:
        db.close()


def test_position_normale_sans_drapeau(client, w: World) -> None:  # noqa: F811
    """§1.3 : un point reçu dans la tolérance ne porte aucun drapeau."""
    vehicle = _vehicle(client, w)
    device, token = _tracker(client, w, vehicle)
    depart = datetime.now(UTC)
    assert _envoi(client, token, device, 1, depart + timedelta(seconds=1)) == 204
    assert _compte_positions(w.t.tenant_id) == 1
    late, skew = _drapeaux(w.t.tenant_id, device)
    assert late is False
    assert skew is False


def test_decalage_hors_tolerance_sans_etre_tardif(client, w: World) -> None:  # noqa: F811
    """§1.3 « Décalage d'horloge » : hors tolérance (2 s) mais sous le seuil de retard (10 s)."""
    vehicle = _vehicle(client, w)
    device, token = _tracker(client, w, vehicle)
    depart = datetime.now(UTC)
    time.sleep(4)  # attente réelle : l'écart dépasse la tolérance, pas le seuil de retard
    assert _envoi(client, token, device, 1, depart + timedelta(seconds=1)) == 204
    assert _compte_positions(w.t.tenant_id) == 1
    late, skew = _drapeaux(w.t.tenant_id, device)
    assert late is False
    assert skew is True


def test_position_tardive_stockee_avec_drapeaux(client, w: World) -> None:  # noqa: F811
    """§1.3 « Événement en retard » : stockée, drapeaux `late` + skew, horodatages intacts.

    L'appareil se tait puis renvoie un point daté de son silence : la position
    est enregistrée et marquée, jamais corrigée ni rejetée."""
    vehicle = _vehicle(client, w)
    device, token = _tracker(client, w, vehicle)
    depart = datetime.now(UTC)
    time.sleep(13)  # attente réelle : le point date d'avant la réception de plus de 10 s
    assert _envoi(client, token, device, 1, depart + timedelta(seconds=1)) == 204
    assert _compte_positions(w.t.tenant_id) == 1
    late, skew = _drapeaux(w.t.tenant_id, device)
    assert late is True
    assert skew is True


def test_horodatage_futur_refuse_sans_ecriture(client, w: World) -> None:  # noqa: F811
    """§1.3 « Horodatage futur » : au-delà de la tolérance, aucun point n'est écrit."""
    vehicle = _vehicle(client, w)
    device, token = _tracker(client, w, vehicle)
    depart = datetime.now(UTC)
    # Futur de 5 minutes (> 2 minutes tolérées par valid_gps_position) : refus.
    assert _envoi(client, token, device, 1, depart + timedelta(minutes=5)) == 409
    assert _compte_positions(w.t.tenant_id) == 0
    # La séquence suivante reste acceptée : le compteur anti-rejeu n'a pas avancé.
    assert _envoi(client, token, device, 2, depart + timedelta(seconds=2)) == 204
    assert _compte_positions(w.t.tenant_id) == 1
