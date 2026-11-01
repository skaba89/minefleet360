"""ClamAV INSTREAM protocol tests without real network activity."""

from unittest.mock import patch

from app.legal.clamav_scanner import ClamAVScanner
from app.legal.malware_scan import ScanVerdict


class FakeSocket:
    def __init__(self, response: bytes) -> None:
        self.response = response
        self.sent = bytearray()

    def __enter__(self) -> "FakeSocket":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def settimeout(self, timeout: float) -> None:
        assert timeout == 10.0

    def sendall(self, data: bytes) -> None:
        self.sent.extend(data)

    def recv(self, size: int) -> bytes:
        data = self.response[:size]
        self.response = self.response[size:]
        return data


def test_clean_response_and_framing() -> None:
    conn = FakeSocket(b"stream: OK\x00")
    with patch("socket.create_connection", return_value=conn):
        assert ClamAVScanner(host="clamav").scan(b"test") == ScanVerdict.CLEAN
    assert bytes(conn.sent) == b"zINSTREAM\x00\x00\x00\x00\x04test\x00\x00\x00\x00"


def test_infected_response() -> None:
    conn = FakeSocket(b"stream: Eicar-Test-Signature FOUND\x00")
    with patch("socket.create_connection", return_value=conn):
        assert ClamAVScanner(host="clamav").scan(b"test") == ScanVerdict.INFECTED


def test_unknown_response_fails_closed() -> None:
    conn = FakeSocket(b"stream: ERROR\x00")
    with patch("socket.create_connection", return_value=conn):
        assert ClamAVScanner(host="clamav").scan(b"test") == ScanVerdict.ERROR


def test_connection_failure_fails_closed() -> None:
    with patch("socket.create_connection", side_effect=OSError("offline")):
        assert ClamAVScanner(host="clamav").scan(b"test") == ScanVerdict.ERROR
