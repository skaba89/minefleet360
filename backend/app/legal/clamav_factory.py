"""Construct a ClamAV adapter only when explicitly enabled."""

from app.core.config import Settings
from app.legal.clamav_scanner import ClamAVScanner


def build_contract_malware_scanner(settings: Settings) -> ClamAVScanner:
    if not settings.legal_malware_scan_enabled:
        raise RuntimeError("contract malware scanner is disabled")
    if not settings.legal_malware_scan_host.strip():
        raise RuntimeError("contract malware scanner host is missing")
    return ClamAVScanner(
        host=settings.legal_malware_scan_host,
        port=settings.legal_malware_scan_port,
        timeout=settings.legal_malware_scan_timeout,
    )
