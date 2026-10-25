"""Validation des fuseaux IANA (stockage UTC, affichage par fuseau du tenant ou du site — H4)."""

from functools import lru_cache
from zoneinfo import available_timezones


@lru_cache
def _zones() -> frozenset[str]:
    return frozenset(available_timezones())


def is_valid_timezone(name: str) -> bool:
    return name in _zones()
