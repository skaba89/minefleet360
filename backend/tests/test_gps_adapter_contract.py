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
    charges_degradees_generiques,
    charges_inanalysables,
    check_adapter_contract,
    violations_d_invariants,
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


def test_invariants_tenus_sur_le_message_valide():
    """Les invariants génériques (§1.3) sont tenus par un message correct."""
    _, attendu = _charge_et_attendu()
    assert violations_d_invariants(attendu) == []


def test_scenarios_degrades_tous_refuses_par_le_contrat_v1():
    """Coordonnées hors borne, séquences invalides, horodatage naïf, identité vide :
    le contrat natif refuse chaque charge dégradée en VALIDATION_ERROR."""
    adapter = MineFleetJsonV1Adapter()
    for label, payload in charges_degradees_generiques():
        try:
            adapter.decode(payload)
        except AppError as exc:
            assert exc.code == "VALIDATION_ERROR", f"{label} : code {exc.code}"
        else:
            raise AssertionError(f"{label} : charge dégradée décodée sans refus")


def test_harnais_attrape_invariant_violee():
    """Un décodeur qui « décode » une coordonnée hors borne est signalé."""
    charge, attendu = _charge_et_attendu()

    class HorsBorne:
        metadata = GpsAdapterMetadata(adapter_id="x-hors-borne", vendor="x", protocol="json", version="1")
        max_payload_bytes = 1024

        def decode(self, payload: bytes) -> GpsDeviceMessage:
            return GpsDeviceMessage(
                device_id="A",
                latitude=95.0,
                longitude=2.0,
                recorded_at=datetime(2026, 11, 26, tzinfo=UTC),
                sequence=1,
            )

    violations = check_adapter_contract(HorsBorne(), charge_valide=charge, attendu=attendu)
    assert any("latitude hors [-90, 90]" in v for v in violations)


def test_harnais_attrape_decodeur_non_deterministe():
    """Le même doublon décodé deux fois doit donner exactement le même message."""
    charge, attendu = _charge_et_attendu()

    class Instable:
        metadata = GpsAdapterMetadata(adapter_id="x-instable", vendor="x", protocol="json", version="1")
        max_payload_bytes = 1024
        appels = 0

        def decode(self, payload: bytes) -> GpsDeviceMessage:
            self.appels += 1
            if self.appels >= 2:
                return GpsDeviceMessage(
                    device_id="A",
                    latitude=1.0,
                    longitude=2.0,
                    recorded_at=datetime(2026, 11, 26, tzinfo=UTC),
                    sequence=2,
                )
            return attendu

    violations = check_adapter_contract(Instable(), charge_valide=charge, attendu=attendu)
    assert any("doublon : décodage non déterministe" in v for v in violations)


def test_harnais_attrape_etat_cache_apres_refus():
    """Un refus intercalé ne doit pas corrompre les décodages suivants (désordre)."""
    charge, attendu = _charge_et_attendu()

    class EtatCache:
        metadata = GpsAdapterMetadata(adapter_id="x-etat", vendor="x", protocol="json", version="1")
        max_payload_bytes = 1024
        valides_vus = 0

        def decode(self, payload: bytes) -> GpsDeviceMessage:
            if payload == b"":
                raise AppError("VALIDATION_ERROR")
            self.valides_vus += 1
            if self.valides_vus >= 3:
                return GpsDeviceMessage(
                    device_id="A",
                    latitude=3.0,
                    longitude=4.0,
                    recorded_at=datetime(2026, 11, 26, tzinfo=UTC),
                    sequence=3,
                )
            return attendu

    violations = check_adapter_contract(EtatCache(), charge_valide=charge, attendu=attendu)
    assert any("désordre : décodage modifié après un refus" in v for v in violations)


def test_registre_reste_explicite():
    """Invariant du registre fermé : liste d'adaptateurs pilotée par décision."""
    identifiants = tuple(m.adapter_id for m in GPS_PAYLOAD_ADAPTERS.metadata)
    assert identifiants == (DEFAULT_GPS_ADAPTER_ID,)
    assert all(m.hardware_certified is False for m in GPS_PAYLOAD_ADAPTERS.metadata)
