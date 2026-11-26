"""Le harnais contractuel : minefleet-json-v1 passe, des adaptateurs défaillants sont attrapés.

Ces tests verrouillent aussi l'invariant du registre fermé : aucun adaptateur
n'apparaît dans `GPS_PAYLOAD_ADAPTERS` sans décision relue (l'ajout futur d'un
décodeur constructeur mettra ce test à jour consciemment, avec ses fixtures
propres et son essai matériel séparé).
"""

import json
from datetime import UTC, datetime

from app.core.errors import AppError
from app.fleet.gps_gateway_contract import GpsDeviceMessage
from app.fleet.gps_payload_adapters import (
    DEFAULT_GPS_ADAPTER_ID,
    GPS_PAYLOAD_ADAPTERS,
    GpsAdapterMetadata,
    MineFleetJsonV1Adapter,
)
from tests.gps_adapter_contract import (
    charges_avec_identites_injectees,
    charges_inanalysables,
    check_adapter_contract,
)


def _charge_et_attendu() -> tuple[bytes, GpsDeviceMessage]:
    attendu = GpsDeviceMessage(
        device_id="FIX-1",
        latitude=9.641,
        longitude=-13.578,
        recorded_at=datetime(2026, 11, 26, 12, 0, 0, tzinfo=UTC),
        sequence=42,
        speed_kmh=35.0,
        accuracy_m=8.0,
        heading_deg=270.0,
    )
    charge = json.dumps(
        {
            "device_id": "FIX-1",
            "latitude": 9.641,
            "longitude": -13.578,
            "recorded_at": "2026-11-26T12:00:00+00:00",
            "sequence": 42,
            "speed_kmh": 35.0,
            "accuracy_m": 8.0,
            "heading_deg": 270.0,
        }
    ).encode()
    return charge, attendu


def test_minefleet_json_v1_passe_le_contrat():
    charge, attendu = _charge_et_attendu()
    assert check_adapter_contract(MineFleetJsonV1Adapter(), charge_valide=charge, attendu=attendu) == []


def _adaptateur_permissif() -> object:
    class Permissif:
        metadata = GpsAdapterMetadata(adapter_id="x-permissif", vendor="x", protocol="json", version="1")
        max_payload_bytes = 1024

        def decode(self, payload: bytes) -> GpsDeviceMessage:
            return GpsDeviceMessage(
                device_id="A",
                latitude=1.0,
                longitude=2.0,
                recorded_at=datetime(2026, 11, 26, tzinfo=UTC),
                sequence=1,
            )

    return Permissif()


def test_harnais_attrape_adaptateur_permissif():
    charge, attendu = _charge_et_attendu()
    violations = check_adapter_contract(_adaptateur_permissif(), charge_valide=charge, attendu=attendu)
    decodes_sans_refus = [v for v in violations if "décodée sans refus" in v]
    # Toutes les charges inanalysables doivent être signalées.
    assert len(decodes_sans_refus) >= len(charges_inanalysables())


def test_harnais_attrape_exception_brute():
    charge, attendu = _charge_et_attendu()

    class Brut:
        metadata = GpsAdapterMetadata(adapter_id="x-brut", vendor="x", protocol="json", version="1")
        max_payload_bytes = 1024

        def decode(self, payload: bytes) -> GpsDeviceMessage:
            raise ValueError("erreur non normalisée")

    violations = check_adapter_contract(Brut(), charge_valide=charge, attendu=attendu)
    assert any("exception brute ValueError" in v for v in violations)
    assert any("charge valide lève ValueError" in v for v in violations)


def test_harnais_attrape_code_derreur_incorrect():
    charge, attendu = _charge_et_attendu()

    class MauvaisCode:
        metadata = GpsAdapterMetadata(adapter_id="x-code", vendor="x", protocol="json", version="1")
        max_payload_bytes = 1024

        def decode(self, payload: bytes) -> GpsDeviceMessage:
            raise AppError("AUTH_REQUIRED")

    violations = check_adapter_contract(MauvaisCode(), charge_valide=charge, attendu=attendu)
    assert any("≠ VALIDATION_ERROR" in v for v in violations)


def test_harnais_attrape_borne_taille_invalide():
    charge, attendu = _charge_et_attendu()

    class TropGrand:
        metadata = GpsAdapterMetadata(adapter_id="x-grand", vendor="x", protocol="json", version="1")
        max_payload_bytes = 2 * 1024 * 1024

        def decode(self, payload: bytes) -> GpsDeviceMessage:
            raise AppError("VALIDATION_ERROR")

    violations = check_adapter_contract(TropGrand(), charge_valide=charge, attendu=attendu)
    assert any("borne de taille invalide" in v for v in violations)


def test_harnais_charge_valide_mal_decodee():
    charge, attendu = _charge_et_attendu()

    class Decale:
        metadata = GpsAdapterMetadata(adapter_id="x-decale", vendor="x", protocol="json", version="1")
        max_payload_bytes = 1024

        def decode(self, payload: bytes) -> GpsDeviceMessage:
            return GpsDeviceMessage(
                device_id="FIX-1",
                latitude=0.0,
                longitude=0.0,
                recorded_at=datetime(2026, 11, 26, tzinfo=UTC),
                sequence=1,
            )

    violations = check_adapter_contract(Decale(), charge_valide=charge, attendu=attendu)
    assert any("charge valide mal décodée" in v for v in violations)


def test_identites_injectees_jamais_transportees_par_le_contrat_v1():
    adapter = MineFleetJsonV1Adapter()
    for label, payload in charges_avec_identites_injectees():
        # Le contrat strict refuse (extra="forbid") : aucune identité ne passe.
        try:
            adapter.decode(payload)
        except AppError as exc:
            assert exc.code == "VALIDATION_ERROR"
        else:
            raise AssertionError(f"{label} : une identité injectée serait passée")


def test_registre_reste_explicite():
    """Invariant du registre fermé : liste d'adaptateurs pilotée par décision."""
    identifiants = tuple(m.adapter_id for m in GPS_PAYLOAD_ADAPTERS.metadata)
    assert identifiants == (DEFAULT_GPS_ADAPTER_ID,)
    assert all(m.hardware_certified is False for m in GPS_PAYLOAD_ADAPTERS.metadata)
