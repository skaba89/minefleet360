"""Faux serveur S3 (sous-ensemble REST) pour le harnais E2E du cycle documentaire.

Implémente uniquement les trois opérations utilisées par le produit :
  - put_object        -> PUT /{bucket}/{key}   (exige x-amz-server-side-encryption: AES256)
  - get_object        -> GET /{bucket}/{key}
  - list_objects_v2   -> GET /{bucket}?list-type=2&prefix=...

TLS obligatoire (auto-signé : le processus uvicorn du harnais lui fait confiance
via AWS_CA_BUNDLE). Les signatures SigV4 sont vérifiées en présence uniquement
(jamais cryptographiquement) : ce service est un harnais de test éphémère, sans
données réelles, jamais déployable tel quel.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit

XML_HEAD = '<?xml version="1.0" encoding="UTF-8"?>\n'
S3_NS = "http://s3.amazonaws.com/doc/2006-03-01/"


class ObjectStore:
    """Stockage thread-safe, en mémoire puis persisté sur disque si --data-dir est fourni.

    La persistance évite les faux « missing » à la réconciliation quand le harnais
    redémarre pendant qu'une base de développement conserve ses registres.
    """

    def __init__(self, data_dir: str | None = None) -> None:
        self._lock = threading.Lock()
        self._objects: dict[str, tuple[bytes, str]] = {}
        self._data_dir = data_dir
        if data_dir:
            os.makedirs(data_dir, exist_ok=True)
            self._load()

    def _path_for(self, key: str) -> str:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return os.path.join(self._data_dir or "", f"{digest}.obj")

    def _load(self) -> None:
        index_path = os.path.join(self._data_dir or "", "index.json")
        if not os.path.exists(index_path):
            return
        with open(index_path, encoding="utf-8") as handle:
            index: dict[str, list[str]] = json.load(handle)
        for key, entry in index.items():
            path = self._path_for(key)
            if os.path.exists(path):
                with open(path, "rb") as handle:
                    body = handle.read()
                self._objects[key] = (body, str(entry[1]))

    def _persist(self) -> None:
        if not self._data_dir:
            return
        index_path = os.path.join(self._data_dir or "", "index.json")
        index = {
            key: [self._path_for(key), content_type]
            for key, (_, content_type) in self._objects.items()
        }
        tmp_path = index_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(index, handle)
        os.replace(tmp_path, index_path)

    def put(self, key: str, body: bytes, content_type: str) -> None:
        with self._lock:
            self._objects[key] = (body, content_type or "application/octet-stream")
            if self._data_dir:
                with open(self._path_for(key), "wb") as handle:
                    handle.write(body)
                self._persist()

    def get(self, key: str) -> tuple[bytes, str] | None:
        with self._lock:
            return self._objects.get(key)

    def keys_with_prefix(self, prefix: str) -> list[str]:
        with self._lock:
            return sorted(k for k in self._objects if k.startswith(prefix))


STORE = ObjectStore(os.environ.get("FAKE_S3_DATA_DIR") or None)


class FakeS3Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "FakeS3/1.0"
    bucket = "legal-private"

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[fake-s3] {self.address_string()} {fmt % args}", flush=True)

    # --- helpers -----------------------------------------------------------------
    def _send(
        self,
        status: int,
        body: bytes,
        content_type: str,
        extra: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for name, value in (extra or {}).items():
            self.send_header(name, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_xml(self, status: int, payload: str) -> None:
        self._send(status, (XML_HEAD + payload).encode("utf-8"), "application/xml")

    def _authorize(self) -> bool:
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("AWS4-HMAC-SHA256"):
            self._send_xml(
                403,
                "<Error><Code>InvalidAccessKeyId</Code>"
                "<Message>La requête n'est pas signée SigV4.</Message></Error>",
            )
            return False
        return True

    def _object_key(self) -> str | None:
        path = unquote(urlsplit(self.path).path).lstrip("/")
        bucket, _, key = path.partition("/")
        if bucket != self.bucket or not key:
            self._send_xml(
                404,
                f"<Error><Code>NoSuchBucket</Code><Message>Seul {self.bucket!r} est servi.</Message></Error>",
            )
            return None
        return key

    # --- lecture du corps : HTTP chunked (transport) PUIS aws-chunked (application) ---
    def _read_body(self) -> bytes:
        if "chunked" in self.headers.get("Transfer-Encoding", "").lower():
            body = self._read_http_chunked()
        else:
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        if "aws-chunked" in self.headers.get("Content-Encoding", "").lower():
            body = self._decode_aws_chunked(body)
        return body

    def _read_http_chunked(self) -> bytes:
        """Décode le transfert HTTP chunked : <hex>\\r\\n<octets>\\r\\n ... 0\\r\\n<trailers>."""
        payload = bytearray()
        while True:
            size_line = self.rfile.readline(65536).strip()
            if not size_line:
                break
            size = int(size_line.split(b";", 1)[0], 16)
            if size == 0:
                while True:
                    trailer = self.rfile.readline(65536)
                    if trailer in (b"\r\n", b"\n", b""):
                        break
                break
            payload.extend(self.rfile.read(size))
            self.rfile.read(2)  # CRLF du cadrage
        return bytes(payload)

    def _decode_aws_chunked(self, raw: bytes) -> bytes:
        """Décode le cadrage applicatif aws-chunked (tailles = longueurs décodées)."""
        payload = bytearray()
        pos = 0
        while pos < len(raw):
            end = raw.find(b"\r\n", pos)
            if end < 0:
                break
            size = int(raw[pos:end].split(b";", 1)[0], 16)
            pos = end + 2
            if size == 0:
                break  # trailers (x-amz-checksum-*) ignorés
            payload.extend(raw[pos : pos + size])
            pos += size + 2
        return bytes(payload)

    # --- verbs --------------------------------------------------------------------
    def do_PUT(self) -> None:
        if not self._authorize():
            return
        key = self._object_key()
        if key is None:
            return
        if self.headers.get("x-amz-server-side-encryption") != "AES256":
            self._send_xml(
                400,
                "<Error><Code>InvalidRequest</Code>"
                "<Message>Le chiffrement côté serveur AES256 est exigé.</Message></Error>",
            )
            return
        body = self._read_body()
        content_type = self.headers.get("Content-Type", "application/octet-stream")
        STORE.put(key, body, content_type)
        etag = hashlib.md5(body).hexdigest()
        self._send(200, b"", "application/xml", {"ETag": f'"{etag}"'})

    def do_GET(self) -> None:
        if not self._authorize():
            return
        split = urlsplit(self.path)
        query = parse_qs(split.query)
        if query.get("list-type", [""])[0] == "2":
            self._list_objects(query)
            return
        key = self._object_key()
        if key is None:
            return
        found = STORE.get(key)
        if found is None:
            self._send_xml(
                404,
                "<Error><Code>NoSuchKey</Code><Message>Objet introuvable.</Message></Error>",
            )
            return
        body, content_type = found
        etag = hashlib.md5(body).hexdigest()
        self._send(200, body, content_type, {"ETag": f'"{etag}"'})

    def _list_objects(self, query: dict[str, list[str]]) -> None:
        prefix = query.get("prefix", [""])[0]
        max_keys = int(query.get("max-keys", ["1000"])[0])
        keys = STORE.keys_with_prefix(prefix)[:max_keys]
        entries = "".join(
            f"<Contents><Key>{key}</Key><LastModified>2026-11-11T00:00:00.000Z</LastModified>"
            f"<Size>1</Size><StorageClass>STANDARD</StorageClass></Contents>"
            for key in keys
        )
        payload = (
            f'<ListBucketResult xmlns="{S3_NS}">'
            f"<Name>{self.bucket}</Name>"
            f"<Prefix>{prefix}</Prefix>"
            f"<KeyCount>{len(keys)}</KeyCount>"
            f"<MaxKeys>{max_keys}</MaxKeys>"
            f"<IsTruncated>false</IsTruncated>"
            f"{entries}</ListBucketResult>"
        )
        self._send(200, payload.encode("utf-8"), "application/xml")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Faux S3 HTTPS pour le harnais E2E documentaire."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9443)
    parser.add_argument("--bucket", default="legal-private")
    parser.add_argument("--cert", required=True)
    parser.add_argument("--key", required=True)
    args = parser.parse_args()

    FakeS3Handler.bucket = args.bucket
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(args.cert, args.key)
    server = ThreadingHTTPServer((args.host, args.port), FakeS3Handler)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    print(
        f"[fake-s3] écoute https://{args.host}:{args.port} bucket={args.bucket}",
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
