"""Harnais contractuel pour tout futur adaptateur de charge utile GPS.

Chaque décodeur doit passer ce contrat avant d'être enregistré dans le registre
fermé `GPS_PAYLOAD_ADAPTERS`. Le contrat couvre : métadonnées complètes, borne
de taille déclarée, décodage exact d'une charge valide, refus en
`VALIDATION_ERROR` de toute charge inanalysable, aucun transport d'identité
injectée (tenant, site, véhicule, secret) et aucun type d'exception brut.

Le passage du contrat est nécessaire mais jamais suffisant : la compatibilité
matérielle exige l'essai du couple modèle/firmware/réseau réel et un rapport
daté (GPS_FOURNISSEUR_CAHIER, D-DEL-06). Le registre reste fermé : l'ajout
d'un adaptateur est une décision relue, jamais un effet de bord.
"""

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

    return violations
