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
import re
import secrets
import socket
import ssl
import sys
import threading
import time
import uuid
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
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.x509.oid import NameOID

    HAVE_CRYPTO = True
except ImportError:
    HAVE_CRYPTO = False

from .network import local_ip

OAEP_SHA1 = None
if HAVE_CRYPTO:
    OAEP_SHA1 = padding.OAEP(
        mgf=padding.MGF1(algorithm=hashes.SHA1()),
        algorithm=hashes.SHA1(),
        label=None,
    )

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8443
# Une seule région pour éviter 6 x 10 s de timeout ICMP dans les tests.
REGIONS = ["eu-central-1"]

# Paire de handshake UE4 observée dans race_session.pcap.
# Le client envoie 01 00...04, le serveur répond par le challenge,
# le client renvoie le challenge, le serveur répond par la réponse.
HANDSHAKE_CHALLENGE = bytes.fromhex(
    "bdfd35ff3cdbd4e48e749656b47ecf4133eaf6ff5a7e6b5804"
)
HANDSHAKE_RESPONSE = bytes.fromhex(
    "030000fe3edbd4e48e749656b47ecf4133eaf6ff5a7e6b5804"
)


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


def realign(datagram: bytes, skip: int = 2) -> bytes:
    """Retire les bits de tête UE4 et le bit de terminaison."""
    n = len(datagram) - 1
    bits = [(x >> i) & 1 for x in datagram for i in range(8)][skip:]
    out = bytearray()
    for i in range(n):
        if (i + 1) * 8 > len(bits):
            break
        value = 0
        for j in range(8):
            value |= bits[i * 8 + j] << j
        out.append(value)
    return bytes(out)


def extract_strings(data: bytes, minlen: int = 4) -> list[str]:
    """Extrait les chaînes ASCII visibles pour tous les décalages de bits 0-7."""
    found: list[str] = []
    for shift in range(8):
        bits = [(x >> i) & 1 for x in data for i in range(8)][shift:]
        buffer = bytearray()
        for i in range(0, len(bits) - 7, 8):
            value = 0
            for j in range(8):
                value |= bits[i + j] << j
            buffer.append(value)
        for match in re.findall(rb"[ -~]{%d,}" % minlen, bytes(buffer)):
            text = match.decode("ascii", "replace")
            if text not in found:
                found.append(text)
    return found


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
    game_ip: str = "127.0.0.1"
    game_port: int = 7777
    log_path: Path | None = None
    clients: dict[str, object] = field(default_factory=dict)
    last_client_key: object | None = None
    userid: str | None = None
    game_session_id: str | None = None
    fleet_id: str | None = None
    fleet_arn: str | None = None
    player_sessions: dict[str, dict] = field(default_factory=dict)
    udp_keys: list[tuple[bytes, bytes]] = field(default_factory=list)
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
            self._handle_create(request_obj, client_key)
            return

        if path.startswith("/services/v1/GameSessions/ReserveSpot"):
            self._handle_reserve(request_obj, client_key)
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

    def _handle_create(self, request_obj, client_key) -> None:
        max_players = 12
        if isinstance(request_obj, dict):
            try:
                max_players = int(request_obj.get("MaxPlayers", 12))
            except (TypeError, ValueError):
                max_players = 12

        fleet_id = f"fleet-{uuid.uuid4()}"
        fleet_arn = (
            f"arn:aws:gamelift:eu-central-1:000000000000:fleet/{fleet_id}"
        )
        gsess = f"gsess-{secrets.token_hex(24)}"
        game_session_id = (
            f"arn:aws:gamelift:eu-central-1::gamesession/{fleet_id}/{gsess}"
        )

        self.state.game_session_id = game_session_id
        self.state.fleet_id = fleet_id
        self.state.fleet_arn = fleet_arn

        response = {
            "gameSessionId": game_session_id,
            "fleetId": fleet_id,
            "fleetArn": fleet_arn,
            "creationTime": {"$date": int(time.time() * 1000)},
            "status": "ACTIVE",
            "ipAddress": self.state.game_ip,
            "dnsName": f"ec2-{self.state.game_ip.replace('.', '-')}.compute.amazonaws.com",
            "port": self.state.game_port,
            "currentPlayerSessionCount": 0,
            "maximumPlayerSessionCount": max_players,
            "gameProperties": [],
            "playerSessionCreationPolicy": "ACCEPT_ALL",
        }
        self.state.log(
            f"  Create -> {game_session_id} ip={self.state.game_ip}:{self.state.game_port}"
        )
        self._send_encrypted(response, client_key)

    def _handle_reserve(self, request_obj, client_key) -> None:
        game_session_id = None
        if isinstance(request_obj, dict):
            game_session_id = request_obj.get("GameSessionId")
        game_session_id = game_session_id or self.state.game_session_id
        if not game_session_id:
            self.state.log("  ReserveSpot sans GameSessionId")
            self._send_encrypted({}, client_key)
            return

        player_session_id = f"psess-{uuid.uuid4()}"
        aes_key = os.urandom(32)
        nonce = os.urandom(12)
        self.state.player_sessions[player_session_id] = {
            "key": aes_key,
            "nonce": nonce,
            "game_session_id": game_session_id,
        }
        self.state.udp_keys.append((aes_key, nonce))

        player_data = json.dumps(
            {
                "EncryptionKey": base64.b64encode(aes_key).decode("ascii"),
                "EncryptionNonce": base64.b64encode(nonce).decode("ascii"),
                "Environment": "Steam",
                "IsTrustedPlatform": False,
                "Platform": "Steam",
                "IsDevLocation": False,
            },
            separators=(",", ":"),
        )

        response = {
            "playerSessionId": player_session_id,
            "playerId": self.state.userid or ("0" * 24),
            "gameSessionId": game_session_id,
            "fleetId": self.state.fleet_id or "fleet-unknown",
            "fleetArn": self.state.fleet_arn
            or "arn:aws:gamelift:eu-central-1:000000000000:fleet/fleet-unknown",
            "creationTime": {"$date": int(time.time() * 1000)},
            "status": "RESERVED",
            "ipAddress": self.state.game_ip,
            "dnsName": f"ec2-{self.state.game_ip.replace('.', '-')}.compute.amazonaws.com",
            "port": self.state.game_port,
            "playerData": player_data,
        }
        self.state.log(
            f"  ReserveSpot -> {player_session_id} "
            f"ip={self.state.game_ip}:{self.state.game_port}"
        )
        self._send_encrypted(response, client_key)

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
        self.state.userid = userid
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


class UdpProbe(threading.Thread):
    """Écoute le port de jeu et journalise les paquets du client."""

    def __init__(
        self,
        host: str,
        port: int,
        state: MockState,
        log_path: str | Path | None = "work/mock_udp.jsonl",
        max_packets: int = 500,
    ):
        super().__init__(daemon=True)
        self.state = state
        self.log_path = Path(log_path) if log_path else None
        self.max_packets = max_packets
        self.running = True
        self.count = 0
        self.pending: dict[tuple[str, int], str] = {}
        self.lock = threading.Lock()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((host, port))
        self.sock.settimeout(1.0)

    def run(self) -> None:
        while self.running:
            try:
                data, addr = self.sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            self._handle_packet(data, addr)
            self.count += 1
            if self.count >= self.max_packets:
                self.running = False

    def _handle_packet(self, data: bytes, addr) -> None:
        key = (addr[0], addr[1])
        handshake = None

        if len(data) == 25 and data[:1] == b"\x01":
            self.sock.sendto(HANDSHAKE_CHALLENGE, addr)
            self.pending[key] = "challenge"
            handshake = "challenge_sent"
        elif (
            len(data) == 25
            and data == HANDSHAKE_CHALLENGE
            and self.pending.get(key) == "challenge"
        ):
            self.sock.sendto(HANDSHAKE_RESPONSE, addr)
            self.pending[key] = "response"
            handshake = "response_sent"
        elif len(data) == 61:
            handshake = "hello"

        strings = extract_strings(data, 4)
        record = {
            "time": round(time.time(), 3),
            "src": f"{addr[0]}:{addr[1]}",
            "len": len(data),
            "hex": data.hex(),
            "strings": strings,
            "handshake": handshake,
        }

        clear = self._try_decrypt(data)
        if clear:
            record["decrypted_hex"] = clear.hex()
            record["decrypted_strings"] = extract_strings(clear, 4)

        self._write(record)

        if handshake:
            self.state.log(f"  HANDSHAKE {handshake} {addr[0]}:{addr[1]}")

        markers = ("psess-", "EncryptionToken", "/Game/maps/", "MILENET")
        for text in strings + record.get("decrypted_strings", []):
            if any(marker in text for marker in markers):
                self.state.log(f"  UDP {addr[0]}:{addr[1]} {text[:220]}")

    def _try_decrypt(self, data: bytes) -> bytes | None:
        if len(data) < 30:
            return None
        aligned = realign(data, 2)
        if len(aligned) < 28:
            return None
        nonce, tag, ciphertext = aligned[:12], aligned[12:28], aligned[28:]
        for key, _ in list(self.state.udp_keys):
            try:
                return AESGCM(key).decrypt(nonce, ciphertext + tag, None)
            except Exception:
                continue
        return None

    def _write(self, record: dict) -> None:
        if not self.log_path:
            return
        with self.lock:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def stop(self) -> None:
        self.running = False
        try:
            self.sock.close()
        except OSError:
            pass


def create_server(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    cert_dir: str | Path = "work/mock_tls",
    log_path: str | Path | None = "work/mock_milenet.log",
    game_ip: str | None = None,
    game_port: int = 7777,
) -> MockMileNetServer:
    _require_crypto()
    cert_dir = Path(cert_dir)
    private_key, public_pem = load_or_create_server_keypair(cert_dir)
    certfile, keyfile = load_or_create_tls_cert(cert_dir)
    state = MockState(
        private_key=private_key,
        public_pem=public_pem,
        game_ip=game_ip or local_ip(),
        game_port=game_port,
        log_path=Path(log_path) if log_path else None,
    )
    return MockMileNetServer((host, port), state, certfile, keyfile)


def run_mock(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    cert_dir: str | Path = "work/mock_tls",
    log_path: str | Path | None = "work/mock_milenet.log",
    game_ip: str | None = None,
    game_port: int = 7777,
    udp: bool = True,
    udp_log: str | Path | None = "work/mock_udp.jsonl",
) -> int:
    _require_crypto()
    server = create_server(
        host,
        port,
        cert_dir,
        log_path,
        game_ip=game_ip,
        game_port=game_port,
    )
    actual_host, actual_port = server.server_address[:2]
    print(f"Mock MileNet en écoute sur https://{actual_host}:{actual_port}")
    print("Clé publique servie sur /services/v1/Security/PublicKey")
    print(f"Endpoint de jeu renvoyé : {server.state.game_ip}:{server.state.game_port}")
    print(f"Configure le client avec : [MileNetOnline] LiveBaseUrl=localhost:{actual_port}")

    probe = None
    if udp:
        try:
            probe = UdpProbe(
                "0.0.0.0",
                server.state.game_port,
                server.state,
                log_path=udp_log,
            )
            probe.start()
            print(f"Écoute UDP sur 0.0.0.0:{server.state.game_port} (log: {udp_log})")
        except OSError as error:
            print(f"UDP {server.state.game_port} indisponible : {error}")

    print("Ctrl+C pour arrêter.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt du mock.")
    finally:
        if probe is not None:
            probe.stop()
        server.server_close()
    return 0
