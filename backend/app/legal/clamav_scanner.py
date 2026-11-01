"""ClamAV clamd INSTREAM adapter with strict response parsing.

Use only on a private trusted network. The scanner is not provisioned here.
"""

import socket

from app.legal.malware_scan import ScanVerdict


class ClamAVScanner:
    def __init__(self, *, host: str, port: int = 3310, timeout: float = 10.0) -> None:
        if not host or port < 1 or port > 65535 or timeout <= 0:
            raise ValueError("invalid ClamAV connection settings")
        self.host = host
        self.port = port
        self.timeout = timeout

    def scan(self, content: bytes) -> ScanVerdict:
        try:
            with socket.create_connection((self.host, self.port), timeout=self.timeout) as conn:
                conn.settimeout(self.timeout)
                conn.sendall(b"zINSTREAM\x00")
                for offset in range(0, len(content), 65536):
                    chunk = content[offset : offset + 65536]
                    conn.sendall(len(chunk).to_bytes(4, "big") + chunk)
                conn.sendall(b"\x00\x00\x00\x00")
                response = bytearray()
                while len(response) <= 4096:
                    part = conn.recv(min(4096, 4097 - len(response)))
                    if not part:
                        break
                    response.extend(part)
                    if b"\x00" in part:
                        break
        except (OSError, TimeoutError):
            return ScanVerdict.ERROR
        if not response or len(response) > 4096 or b"\x00" not in response:
            return ScanVerdict.ERROR
        result = bytes(response).split(b"\x00", 1)[0]
        if result == b"stream: OK":
            return ScanVerdict.CLEAN
        if result.startswith(b"stream: ") and result.endswith(b" FOUND"):
            return ScanVerdict.INFECTED
        return ScanVerdict.ERROR
