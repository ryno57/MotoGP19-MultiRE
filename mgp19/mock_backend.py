"""Faux backend MileNet local (HTTPS + crypto RSA/AES).

Ce module implémente uniquement le "control plane" : clé publique, login,
profil, régions, stockage. Les sessions de jeu (`Create` / `ReserveSpot`)
seront ajoutées dans un morceau ultérieur.

Dépendance : `cryptography` (installée dans `.venv`).
Le reste du projet reste sans dépendance externe.
"""

from __future__ import annotations

import base64
import ipaddress
import json
import os
import secrets
import ssl
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

try:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.x509.oid import NameOID

    HAVE_CRYPTO = True
except ImportError:
    HAVE_CRYPTO = False

OAEP_SHA1 = None
if HAVE_CRYPTO:
    OAEP_SHA1 = padding.OAEP(
        mgf=padding.MGF1(algorithm=hashes.SHA1()),
        algorithm=hashes.SHA1(),
        label=None,
    )

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8443
REGIONS = [
    "eu-central-1",
    "us-east-1",
    "us-west-1",
    "ap-southeast-1",
    "ap-southeast-2",
    "ap-northeast-1",
]


def _require_crypto() -> None:
    if not HAVE_CRYPTO:
        raise RuntimeError(
            "Le mock MileNet nécessite le paquet 'cryptography'. "
            "Installe-le dans le venv du projet : "
            ".venv\\Scripts\\pip install cryptography"
        )


# ---------------------------------------------------------------------------
# Crypto
# ---------------------------------------------------------------------------

def pkcs7_pad(data: bytes, block: int = 16) -> bytes:
    n = block - (len(data) % block)
    return data + bytes([n]) * n


def pkcs7_unpad(data: bytes) -> bytes:
    if not data:
        raise ValueError("buffer vide")
    pad = data[-1]
    if not 1 <= pad <= 16 or data[-pad:] != bytes([pad]) * pad:
        raise ValueError(f"padding PKCS7 invalide (dernier octet = {pad})")
    return data[:-pad]


def aes_cbc_encrypt(key: bytes, iv: bytes, plaintext: bytes) -> bytes:
    encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    return encryptor.update(pkcs7_pad(plaintext)) + encryptor.finalize()


def aes_cbc_decrypt(key: bytes, iv: bytes, ciphertext: bytes) -> bytes:
    decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    return pkcs7_unpad(decryptor.update(ciphertext) + decryptor.finalize())


def rsa_oaep_encrypt(public_key, data: bytes) -> bytes:
    return public_key.encrypt(data, OAEP_SHA1)


def rsa_oaep_decrypt(private_key, data: bytes) -> bytes:
    return private_key.decrypt(data, OAEP_SHA1)


def encrypt_payload(public_key, obj) -> bytes:
    """RSA-OAEP(clé+IV) + AES-128-CBC(JSON), encodé en base64."""
    plaintext = json.dumps(obj, separators=(",", ":")).encode("utf-8")
    key, iv = os.urandom(16), os.urandom(16)
    rsa_blob = rsa_oaep_encrypt(public_key, key + iv)
    ciphertext = aes_cbc_encrypt(key, iv, plaintext)
    return base64.b64encode(rsa_blob + ciphertext)


def decrypt_payload(private_key, body: bytes):
    """Déchiffre un corps base64 du client."""
    raw = base64.b64decode(body.strip(), validate=False)
    key_size = private_key.key_size // 8
    if len(raw) <= key_size:
        raise ValueError("corps trop court")
    key_iv = rsa_oaep_decrypt(private_key, raw[:key_size])
    key, iv = key_iv[:16], key_iv[16:32]
    plaintext = aes_cbc_decrypt(key, iv, raw[key_size:])
    return json.loads(plaintext.decode("utf-8"))


def load_client_public_key(value: str):
    """Charge la clé publique du client (PEM ou DER base64)."""
    data = value.encode("utf-8")
    try:
        return serialization.load_pem_public_key(data)
    except ValueError:
        pass
    try:
        return serialization.load_der_public_key(base64.b64decode(value))
    except Exception as error:
        raise ValueError(f"clé publique client illisible : {error}") from error


# ---------------------------------------------------------------------------
# TLS / clés serveur
# ---------------------------------------------------------------------------

def _write_private_key(path: Path, key) -> None:
    path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )


def load_or_create_server_keypair(cert_dir: Path):
    cert_dir.mkdir(parents=True, exist_ok=True)
    private_path = cert_dir / "server_rsa_private.pem"
    if private_path.exists():
        private_key = serialization.load_pem_private_key(
            private_path.read_bytes(), password=None
        )
    else:
        try:
            private_key = rsa.generate_private_key(public_exponent=65537, key_size=1024)
        except ValueError:
            private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        _write_private_key(private_path, private_key)

    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_key, public_pem


def load_or_create_tls_cert(cert_dir: Path):
    cert_dir.mkdir(parents=True, exist_ok=True)
    cert_path = cert_dir / "tls_cert.pem"
    key_path = cert_dir / "tls_key.pem"
    if cert_path.exists() and key_path.exists():
        return cert_path, key_path

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "localhost")]
    )
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName("localhost"),
                    x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                ]
            ),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return cert_path, key_path


# ---------------------------------------------------------------------------
# État et handler
# ---------------------------------------------------------------------------

@dataclass
class MockState:
    private_key: object
    public_pem: bytes
    log_path: Path | None = None
    clients: dict[str, object] = field(default_factory=dict)
    last_client_key: object | None = None
    log_lock: threading.Lock = field(default_factory=threading.Lock)

    def log(self, message: str) -> None:
        line = f"{datetime.now().isoformat(timespec='seconds')} {message}"
        print(line, flush=True)
        if self.log_path:
            with self.log_lock:
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
                with self.log_path.open("a", encoding="utf-8") as handle:
                    handle.write(line + "\n")

    def register_client(self, token: str, key) -> None:
        self.clients[token] = key
        self.last_client_key = key

    def client_for(self, token: str):
        return self.clients.get(token) or self.last_client_key


class MockMileNetHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "MileNetMock/0.1"

    @property
    def state(self) -> MockState:
        return self.server.state  # type: ignore[attr-defined]

    def log_message(self, fmt, *args):
        return

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def do_PUT(self):
        self._handle("PUT")

    def do_DELETE(self):
        self._handle("DELETE")

    # ------------------------------------------------------------------
    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0") or "0")
        return self.rfile.read(length) if length else b""

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _send_plain_json(self, obj) -> None:
        body = json.dumps(obj, separators=(",", ":")).encode("utf-8")
        self._send(200, body, "text/plain; charset=UTF-8")

    def _send_encrypted(self, obj, client_key) -> None:
        if client_key is None:
            self._send(401, b"no client key", "text/plain; charset=UTF-8")
            return
        body = encrypt_payload(client_key, obj)
        self._send(200, body, "text/plain; charset=UTF-8")

    # ------------------------------------------------------------------
    def _handle(self, method: str) -> None:
        path = urlsplit(self.path).path
        body = self._read_body()
        self.state.log(f"{method} {path} body={len(body)}")

        if path == "/services/v1/Security/PublicKey":
            self._send(200, self.state.public_pem, "text/plain; charset=UTF-8")
            return

        if path == "/services/v1/PlayerProfile/Steam/Login":
            self._handle_login(body)
            return

        auth = self.headers.get("Authorization", "")
        client_key = self.state.client_for(auth)

        try:
            request_obj = decrypt_payload(self.state.private_key, body) if body else None
        except Exception as error:
            self.state.log(f"  decrypt error: {error}")
            self._send(400, b"bad request", "text/plain; charset=UTF-8")
            return

        if isinstance(request_obj, dict):
            self.state.log(f"  keys={sorted(request_obj.keys())}")

        if path.startswith("/services/v1/PlayerProfile/UpdateSession"):
            self._send_plain_json({})
            return

        if path.startswith("/services/v1/PlayerProfile/User/GetPlatformIds"):
            self._send_encrypted([], client_key)
            return

        if path.startswith("/services/v1/GameSessions/Regions"):
            self._send_encrypted(REGIONS, client_key)
            return

        if path.startswith("/services/v1/GameSessions/Create"):
            self.state.log("  Create non implémenté (morceau 6B)")
            self._send_encrypted({}, client_key)
            return

        if path.startswith("/services/v1/GameSessions/ReserveSpot"):
            self.state.log("  ReserveSpot non implémenté (morceau 6B)")
            self._send_encrypted({}, client_key)
            return

        if path.startswith("/services/v1/Storage"):
            if "/Catalog/" in path or path.endswith("/Notifications"):
                self._send_encrypted([], client_key)
            else:
                self._send_encrypted({}, client_key)
            return

        if path.startswith("/services/v1/Notifications"):
            self._send_encrypted([], client_key)
            return

        if path.startswith("/services/v1/Statistics") or path.startswith("/services/v1/Analytics"):
            self._send_encrypted({}, client_key)
            return

        # Endpoint inconnu : réponse neutre pour ne pas bloquer le client.
        self._send_encrypted({}, client_key)

    def _handle_login(self, body: bytes) -> None:
        if not body:
            self._send(400, b"empty login", "text/plain; charset=UTF-8")
            return

        try:
            request_obj = decrypt_payload(self.state.private_key, body)
        except Exception as error:
            self.state.log(f"  login decrypt error: {error}")
            self._send(400, b"bad login", "text/plain; charset=UTF-8")
            return

        if not isinstance(request_obj, dict):
            self._send(400, b"bad login json", "text/plain; charset=UTF-8")
            return

        self.state.log(f"  login keys={sorted(request_obj.keys())}")
        encryption_key = request_obj.get("EncryptionKey")
        if not encryption_key:
            self._send(400, b"missing EncryptionKey", "text/plain; charset=UTF-8")
            return

        try:
            client_key = load_client_public_key(str(encryption_key))
        except Exception as error:
            self.state.log(f"  client key error: {error}")
            self._send(400, b"bad EncryptionKey", "text/plain; charset=UTF-8")
            return

        token = secrets.token_hex(16)
        userid = secrets.token_hex(12)
        self.state.register_client(token, client_key)

        response = {"token": token, "userid": userid}
        self._send(200, encrypt_payload(client_key, response), "text/plain; charset=UTF-8")


class MockMileNetServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, state: MockState, certfile: Path, keyfile: Path):
        super().__init__(address, MockMileNetHandler)
        self.state = state
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(certfile), str(keyfile))
        self.socket = context.wrap_socket(self.socket, server_side=True)


def create_server(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    cert_dir: str | Path = "work/mock_tls",
    log_path: str | Path | None = "work/mock_milenet.log",
) -> MockMileNetServer:
    _require_crypto()
    cert_dir = Path(cert_dir)
    private_key, public_pem = load_or_create_server_keypair(cert_dir)
    certfile, keyfile = load_or_create_tls_cert(cert_dir)
    state = MockState(
        private_key=private_key,
        public_pem=public_pem,
        log_path=Path(log_path) if log_path else None,
    )
    return MockMileNetServer((host, port), state, certfile, keyfile)


def run_mock(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    cert_dir: str | Path = "work/mock_tls",
    log_path: str | Path | None = "work/mock_milenet.log",
) -> int:
    _require_crypto()
    server = create_server(host, port, cert_dir, log_path)
    actual_host, actual_port = server.server_address[:2]
    print(f"Mock MileNet en écoute sur https://{actual_host}:{actual_port}")
    print(f"Clé publique servie sur /services/v1/Security/PublicKey")
    print("Configure le client avec : [MileNetOnline] LiveBaseUrl=localhost:%d" % actual_port)
    print("Ctrl+C pour arrêter.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt du mock.")
    finally:
        server.server_close()
    return 0
