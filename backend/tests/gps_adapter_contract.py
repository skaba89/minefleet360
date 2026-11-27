"""Harnais contractuel pour tout futur adaptateur de charge utile GPS.

Chaque décodeur doit passer ce contrat avant d'être enregistré dans le registre
fermé `GPS_PAYLOAD_ADAPTERS`. Le contrat couvre : métadonnées complètes, borne
de taille déclarée, décodage exact d'une charge valide, refus en
`VALIDATION_ERROR` de toute charge inanalysable, aucun transport d'identité
injectée (tenant, site, véhicule, secret) et aucun type d'exception brut.

Les scénarios dégradés de `INTEGRATION_GPS_OFFLINE.md` §1.3 sont répartis
ainsi : le décodeur **préserve** l'information (déterminisme sur doublon,
absence d'état caché entre appels, horodatage et séquence exacts) et **refuse
ou rend invariant-compatible** toute charge dégradée (coordonnées hors borne,
séquence négative/flottante/booléenne, horodatage sans fuseau, identité
d'appareil vide ou non nettoyée, grandeurs hors intervalle) ; les décisions
métier (retard, désordre chronologique, décalage d'horloge, horodatage futur,
quarantaine) restent au niveau du service d'ingestion.

Le passage du contrat est nécessaire mais jamais suffisant : la compatibilité
matérielle exige l'essai du couple modèle/firmware/réseau réel et un rapport
daté (GPS_FOURNISSEUR_CAHIER, D-DEL-06). Le registre reste fermé : l'ajout
d'un adaptateur est une décision relue, jamais un effet de bord.
"""

import math

from app.core.errors import AppError
from app.fleet.gps_gateway_contract import GpsDeviceMessage
from app.fleet.gps_payload_adapters import MAX_GPS_PAYLOAD_BYTES

# Balises de test à faible entropie et sans mot-clé de secret : la présence d'un
# mot-clé (secret, token, key…) suivi d'une longue valeur déclencherait à tort la
# règle générique de gitleaks sur une chaîne purement fictive.
_TENANT = "BALISE-TENANT-0001"
_SITE = "BALISE-SITE-0002"
_VEHICLE = "BALISE-VEHICULE-0003"
_BALISE_4 = "BALISE-IDENTITE-0004"
_IDENTITES = (_TENANT, _SITE, _VEHICLE, _BALISE_4)


def charges_inanalysables() -> list[tuple[str, bytes]]:
    """Charges qu'aucun adaptateur ne peut décoder avec succès."""
    profond = '{"a":' * 180 + "1" + "}" * 180
    return [
        ("vide", b""),
        ("binaire", bytes(range(256)) * 4),
        ("texte_non_json", b"ceci n'est pas une charge GPS"),
        ("utf8_invalide", b'{"device_id": "\xff\xfe\xfd"}'),
        ("cle_json_repetee", b'{"device_id": "A", "device_id": "B"}'),
        ("constante_non_finie", b'{"device_id": "A", "latitude": NaN}'),
        ("infini", b'{"device_id": "A", "longitude": Infinity}'),
        ("json_profond", profond.encode()),
    ]


def charges_avec_identites_injectees() -> list[tuple[str, bytes]]:
    """Charges plausibles tentant d'imposer une identité serveur depuis le corps."""
    corps = (
        '{"device_id": "A", "latitude": 9.5, "longitude": -13.5,'
        ' "recorded_at": "2026-11-26T12:00:00+00:00", "sequence": 1,'
        f' "tenant_id": "{_TENANT}", "site_id": "{_SITE}",'
        f' "vehicle_id": "{_VEHICLE}", "secret": "{_BALISE_4}"}}'
    )
    return [("identites_completes", corps.encode())]


def charges_degradees_generiques() -> list[tuple[str, bytes]]:
    """Charges dégradées de sémantique générique (§1.3) : refus ou invariants tenus.

    Les octets sont au format JSON natif : un adaptateur d'un autre constructeur
    les refusera (format inconnu) — ce qui satisfait le contrat. Un adaptateur
    capable de les analyser ne doit jamais produire un message qui viole les
    invariants attendus par le service d'ingestion.
    """
    corps = (
        '{{"device_id": "A", "latitude": {lat}, "longitude": {lon},'
        ' "recorded_at": "{ts}", "sequence": {seq}{extra}}}'
    )
    base = dict(lat=9.5, lon=-13.5, ts="2026-11-26T12:00:00+00:00", seq=1, extra="")

    def _charge(**surcharge) -> bytes:
        valeurs = {**base, **surcharge}
        return corps.format(**valeurs).encode()

    return [
        ("latitude_hors_borne", _charge(lat=95.0)),
        ("longitude_hors_borne", _charge(lon=-200.0)),
        ("recorded_at_sans_timezone", _charge(ts="2026-11-26T12:00:00")),
        ("sequence_negative", _charge(seq=-1)),
        ("sequence_flottante", _charge(seq=1.5)),
        ("sequence_booleenne", _charge(seq="true")),
        ("device_id_vide", _charge().replace(b'"device_id": "A"', b'"device_id": ""')),
        ("device_id_non_nettoye", _charge().replace(b'"device_id": "A"', b'"device_id": " A "')),
        ("vitesse_negative", _charge(extra=', "speed_kmh": -5.0')),
        ("cap_hors_cercle", _charge(extra=', "heading_deg": 400.0')),
    ]


def violations_d_invariants(message: GpsDeviceMessage) -> list[str]:
    """Invariants génériques que tout message décodé doit tenir (§1.3, contrat)."""
    problemes: list[str] = []
    if not isinstance(message.device_id, str) or not message.device_id.strip():
        problemes.append("device_id vide")
    elif message.device_id != message.device_id.strip() or len(message.device_id) > 120:
        problemes.append("device_id non nettoyé ou trop long")
    if not isinstance(message.sequence, int) or isinstance(message.sequence, bool):
        problemes.append(f"séquence non entière : {message.sequence!r}")
    elif not 0 <= message.sequence <= 9223372036854775807:
        problemes.append(f"séquence hors intervalle : {message.sequence!r}")
    if message.recorded_at.tzinfo is None or message.recorded_at.utcoffset() is None:
        problemes.append("horodatage sans fuseau")
    if not (math.isfinite(message.latitude) and -90 <= message.latitude <= 90):
        problemes.append(f"latitude hors [-90, 90] : {message.latitude!r}")
    if not (math.isfinite(message.longitude) and -180 <= message.longitude <= 180):
        problemes.append(f"longitude hors [-180, 180] : {message.longitude!r}")
    for champ, borne in (("speed_kmh", 250.0), ("accuracy_m", 10000.0)):
        valeur = getattr(message, champ)
        if valeur is not None and (not math.isfinite(valeur) or not 0 <= valeur <= borne):
            problemes.append(f"{champ} hors [0, {borne}] : {valeur!r}")
    cap = message.heading_deg
    if cap is not None and (not math.isfinite(cap) or not 0 <= cap < 360):
        problemes.append(f"heading_deg hors [0, 360[ : {cap!r}")
    return problemes


def check_adapter_contract(
    adapter: object,
    *,
    charge_valide: bytes,
    attendu: GpsDeviceMessage,
) -> list[str]:
    """Vérifier un adaptateur et renvoyer la liste des violations (vide = conforme)."""
    violations: list[str] = []

    metadata = getattr(adapter, "metadata", None)
    if (
        metadata is None
        or not getattr(metadata, "adapter_id", "")
        or not getattr(metadata, "vendor", "")
        or not getattr(metadata, "protocol", "")
        or not getattr(metadata, "version", "")
    ):
        violations.append("metadata incomplète (adapter_id/vendor/protocol/version)")
    limite = getattr(adapter, "max_payload_bytes", 0)
    if not isinstance(limite, int) or not 0 < limite <= MAX_GPS_PAYLOAD_BYTES:
        violations.append(f"borne de taille invalide : {limite!r} (max registre {MAX_GPS_PAYLOAD_BYTES})")

    try:
        obtenu = adapter.decode(charge_valide)
        if obtenu != attendu:
            violations.append(f"charge valide mal décodée : {obtenu!r}")
        if type(obtenu) is not GpsDeviceMessage:
            violations.append(f"type retourné {type(obtenu).__name__} ≠ GpsDeviceMessage exact")
    except Exception as exc:  # noqa: BLE001 — le harnais rapporte toute exception brute d'un adaptateur tiers
        violations.append(f"charge valide lève {type(exc).__name__}")

    # Doublons (§1.3) : la même charge décodée à nouveau donne le même message —
    # le service déduplique en comparant des entrées stables, jamais reconstruites.
    try:
        repeté = adapter.decode(charge_valide)
        if repeté != attendu:
            violations.append(f"doublon : décodage non déterministe : {repeté!r}")
    except Exception as exc:  # noqa: BLE001 — exception brute d'un adaptateur tiers
        violations.append(f"doublon : second décodage lève {type(exc).__name__}")

    # Désordre d'appels (§1.3) : un refus intercalé ne corrompt pas l'état du
    # décodeur — aucun compteur, aucune file interne, aucune reconstruction.
    try:
        adapter.decode(charges_inanalysables()[0][1])
    except Exception:  # noqa: BLE001, S110 — refus attendu ; seul l'état d'après nous importe
        pass
    try:
        après = adapter.decode(charge_valide)
        if après != attendu:
            violations.append(f"désordre : décodage modifié après un refus : {après!r}")
    except Exception as exc:  # noqa: BLE001 — exception brute d'un adaptateur tiers
        violations.append(f"désordre : décodage après refus lève {type(exc).__name__}")

    for label, payload in charges_inanalysables():
        try:
            obtenu = adapter.decode(payload)
            violations.append(f"{label} : décodée sans refus → {obtenu!r}")
        except AppError as exc:
            if exc.code != "VALIDATION_ERROR":
                violations.append(f"{label} : code d'erreur {exc.code} ≠ VALIDATION_ERROR")
        except Exception as exc:  # noqa: BLE001 — une exception non normalisée est elle-même une violation
            violations.append(f"{label} : exception brute {type(exc).__name__}")

    for label, payload in charges_avec_identites_injectees():
        try:
            obtenu = adapter.decode(payload)
            if type(obtenu) is not GpsDeviceMessage:
                violations.append(f"{label} : type {type(obtenu).__name__} transportable")
                continue
            # device_id est maîtrisé par l'appareil et revérifié côté serveur :
            # il ne constitue pas une fuite. Les autres champs sont typés et
            # ne peuvent pas porter une chaîne d'identité.
            empreinte = repr(obtenu).replace(repr(obtenu.device_id), "", 1)
            for identite in _IDENTITES:
                if identite in empreinte:
                    violations.append(f"{label} : identité {identite[:22]}… transportée")
        except AppError:
            continue  # refus explicite : acceptable
        except Exception as exc:  # noqa: BLE001 — une exception non normalisée est elle-même une violation
            violations.append(f"{label} : exception brute {type(exc).__name__}")

    for label, payload in charges_degradees_generiques():
        try:
            message = adapter.decode(payload)
        except AppError as exc:
            if exc.code != "VALIDATION_ERROR":
                violations.append(f"{label} : code d'erreur {exc.code} ≠ VALIDATION_ERROR")
        except Exception as exc:  # noqa: BLE001 — une exception non normalisée est elle-même une violation
            violations.append(f"{label} : exception brute {type(exc).__name__}")
        else:
            if type(message) is not GpsDeviceMessage:
                violations.append(f"{label} : type {type(message).__name__} transportable")
                continue
            for probleme in violations_d_invariants(message):
                violations.append(f"{label} : {probleme}")

    return violations
