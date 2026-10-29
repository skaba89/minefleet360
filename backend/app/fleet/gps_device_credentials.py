"""Vérification de secrets de traceurs sans stocker les secrets en clair.

Primitive interne seulement : l'enrôlement, la rotation, la limitation de débit,
la révocation persistée et la validation des identités restent obligatoires.
"""

import hashlib
import hmac
import secrets


def new_device_secret() -> str:
    """Générer 256 bits d'aléa à transmettre une seule fois au propriétaire."""
    return secrets.token_urlsafe(32)


def fingerprint_device_secret(secret: str) -> str:
    """Conserver seulement un empreinte SHA-256 d'un secret fort généré."""
    if len(secret) < 32 or len(secret) > 256 or secret.strip() != secret:
        raise ValueError("Invalid device secret")
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def verify_device_secret(stored_fingerprint: str | None, supplied_secret: str) -> bool:
    """Comparer en temps constant, refuser l'absence de secret ou une empreinte malformée."""
    if not isinstance(supplied_secret, str) or not 32 <= len(supplied_secret) <= 256:
        return False
    if supplied_secret.strip() != supplied_secret:
        return False
    if stored_fingerprint is None or len(stored_fingerprint) != 64:
        return False
    if any(char not in "0123456789abcdef" for char in stored_fingerprint):
        return False
    calculated = hashlib.sha256(supplied_secret.encode("utf-8")).hexdigest()
    return hmac.compare_digest(stored_fingerprint, calculated)
