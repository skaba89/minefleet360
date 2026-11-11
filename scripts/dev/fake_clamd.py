"""Faux démon ClamAV (protocole clamd INSTREAM) pour le harnais E2E documentaire.

Implémente strictement le dialogue utilisé par app.legal.clamav_scanner :
  client -> "zINSTREAM\\0"
  client -> <taille 4 octets big endian><contenu>... puis <0 0 0 0>
  serveur -> "stream: OK\\0" ou "stream: <nom> FOUND\\0"

Le verdict est positif uniquement si la charge contient la signature de test
EICAR : ce service est un harnais éphémère, jamais un antivirus réel.
"""

from __future__ import annotations

import argparse
import socketserver

EICAR_MARKER = b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE"
MAX_TOTAL = 32 * 1024 * 1024


class ClamdHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        try:
            magic = self._read_until_nul()
            if magic != b"zINSTREAM":
                return
            chunks: list[bytes] = []
            total = 0
            while True:
                header = self._read_exact(4)
                if header is None:
                    return
                size = int.from_bytes(header, "big")
                if size == 0:
                    break
                if total + size > MAX_TOTAL:
                    return
                payload = self._read_exact(size)
                if payload is None:
                    return
                chunks.append(payload)
                total += size
            content = b"".join(chunks)
            if EICAR_MARKER in content:
                verdict = b"stream: EICAR-Test-Signature FOUND\x00"
            else:
                verdict = b"stream: OK\x00"
            self.wfile.write(verdict)
        except (ConnectionError, OSError):
            return

    def _read_until_nul(self) -> bytes | None:
        buffer = bytearray()
        while len(buffer) < 64:
            byte = self.rfile.read(1)
            if not byte:
                return None
            if byte == b"\x00":
                return bytes(buffer)
            buffer.extend(byte)
        return None

    def _read_exact(self, count: int) -> bytes | None:
        buffer = bytearray()
        while len(buffer) < count:
            part = self.rfile.read(count - len(buffer))
            if not part:
                return None
            buffer.extend(part)
        return bytes(buffer)


class ThreadedClamd(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Faux clamd INSTREAM pour le harnais E2E documentaire."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3310)
    args = parser.parse_args()

    with ThreadedClamd((args.host, args.port), ClamdHandler) as server:
        print(f"[fake-clamd] écoute tcp://{args.host}:{args.port}", flush=True)
        server.serve_forever(poll_interval=0.2)


if __name__ == "__main__":
    main()
