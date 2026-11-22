"""Vecteurs publics de recette du futur coffre Android, jamais utilisés en production."""

from itertools import combinations
from unittest import TestCase
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# Ordre contractuel : tenant, compte, session, site, véhicule, partage, point.
_SCOPE = tuple(UUID(int=i) for i in range(1, 8))
_PREFIX = b"MF-GPS-V1\x00"
# Vecteur synthétique public : ne jamais réutiliser ces valeurs pour un chiffrement réel.
_KEY = bytes(range(32))
_NONCE = bytes(range(12))
_POINT = b"minefleet-synthetic-point"
_EXPECTED = bytes.fromhex(
    "2a6bb87ea389a77ef96ce4f2df9d1008f7bfe419801436124cf0bd5b566acb5eb4ff174d0e64adb1c4"
)


def _aad(scope: tuple[UUID, ...]) -> bytes:
    """Référence de recette uniquement ; représentation UUID réseau, sans séparateur."""
    if len(scope) != 7:
        raise ValueError("invalid scope")
    return _PREFIX + b"".join(value.bytes for value in scope)


class TestAndroidVaultVectors(TestCase):
    def test_public_known_answer(self) -> None:
        cipher = AESGCM(_KEY)
        aad = _aad(_SCOPE)
        self.assertEqual(len(aad), len(_PREFIX) + 7 * 16)
        self.assertEqual(cipher.encrypt(_NONCE, _POINT, aad), _EXPECTED)
        self.assertEqual(cipher.decrypt(_NONCE, _EXPECTED, aad), _POINT)

    def test_each_scope_component_is_authenticated(self) -> None:
        cipher = AESGCM(_KEY)
        for index in range(len(_SCOPE)):
            scope = list(_SCOPE)
            scope[index] = UUID(int=100 + index)
            with self.subTest(index=index), self.assertRaises(InvalidTag):
                cipher.decrypt(_NONCE, _EXPECTED, _aad(tuple(scope)))

    def test_all_scope_transpositions_are_rejected(self) -> None:
        cipher = AESGCM(_KEY)
        for left, right in combinations(range(len(_SCOPE)), 2):
            scope = list(_SCOPE)
            scope[left], scope[right] = scope[right], scope[left]
            with self.subTest(left=left, right=right), self.assertRaises(InvalidTag):
                cipher.decrypt(_NONCE, _EXPECTED, _aad(tuple(scope)))

    def test_ciphertext_tag_nonce_and_version_tampering(self) -> None:
        cipher = AESGCM(_KEY)
        aad = _aad(_SCOPE)
        for index in range(len(_EXPECTED)):
            mutated = bytearray(_EXPECTED)
            mutated[index] ^= 1
            with self.subTest(index=index), self.assertRaises(InvalidTag):
                cipher.decrypt(_NONCE, bytes(mutated), aad)
        wrong_nonce = bytes([_NONCE[0] ^ 1]) + _NONCE[1:]
        with self.assertRaises(InvalidTag):
            cipher.decrypt(wrong_nonce, _EXPECTED, aad)
        with self.assertRaises(InvalidTag):
            cipher.decrypt(_NONCE, _EXPECTED, b"MF-GPS-V2\x00" + aad[len(_PREFIX) :])

    def test_wrong_scope_size_and_key(self) -> None:
        with self.assertRaises(ValueError):
            _aad(_SCOPE[:-1])
        with self.assertRaises(InvalidTag):
            AESGCM(bytes(reversed(_KEY))).decrypt(_NONCE, _EXPECTED, _aad(_SCOPE))
