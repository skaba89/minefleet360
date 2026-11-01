"""ClamAV configuration remains disabled and fail-closed by default."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.legal.clamav_factory import build_contract_malware_scanner


def settings(**overrides: object) -> Settings:
    fields = {
        "MF_APP_PASSWORD": "test-password",
        "MF_JWT_SECRET": "a" * 40,
        "legal_malware_scan_enabled": True,
        "legal_malware_scan_host": "clamav",
    }
    fields.update(overrides)
    return Settings(**fields)


def test_clamav_factory_configuration() -> None:
    adapter = build_contract_malware_scanner(settings())
    assert adapter.host == "clamav"
    assert adapter.port == 3310


def test_disabled_scanner_fails_closed() -> None:
    with pytest.raises(RuntimeError, match="disabled"):
        build_contract_malware_scanner(settings(legal_malware_scan_enabled=False))


@pytest.mark.parametrize(
    "overrides",
    [
        {"legal_malware_scan_host": ""},
        {"legal_malware_scan_port": 0},
        {"legal_malware_scan_timeout": -1},
    ],
)
def test_bad_scanner_configuration_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        settings(**overrides)
