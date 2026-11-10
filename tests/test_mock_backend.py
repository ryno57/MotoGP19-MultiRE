import base64
import http.client
import json
import socket
import ssl
import tempfile
import threading
import time
import unittest
from pathlib import Path

try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    from mgp19 import mock_backend

    HAVE_CRYPTO = True
except ImportError:
    HAVE_CRYPTO = False


def client_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=1024)
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_key, public_pem


@unittest.skipUnless(HAVE_CRYPTO, "cryptography manquant")
class CryptoRoundTripTests(unittest.TestCase):
    def test_request_and_response_roundtrip(self):
        server_private, server_public_pem = mock_backend.load_or_create_server_keypair(
            Path(tempfile.mkdtemp())
        )
        client_private, client_public_pem = client_keypair()
        client_public = serialization.load_pem_public_key(client_public_pem)

        request = {"createNew": False, "buildId": 4909173}
        body = mock_backend.encrypt_payload(
            serialization.load_pem_public_key(server_public_pem), request
        )
        self.assertEqual(mock_backend.decrypt_payload(server_private, body), request)

        response = {"token": "a" * 32, "userid": "b" * 24}
        response_body = mock_backend.encrypt_payload(client_public, response)
        self.assertEqual(
            mock_backend.decrypt_payload(client_private, response_body), response
        )


@unittest.skipUnless(HAVE_CRYPTO, "cryptography manquant")
class MockServerTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.server = mock_backend.create_server(
            host="127.0.0.1",
            port=0,
            cert_dir=Path(self.tempdir.name) / "certs",
            log_path=None,
            game_ip="127.0.0.1",
            game_port=7777,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.tempdir.cleanup()

    def _connection(self):
        return http.client.HTTPSConnection(
            "127.0.0.1",
            self.port,
            context=ssl._create_unverified_context(),
            timeout=10,
        )

    def test_public_key_and_login(self):
        connection = self._connection()
        connection.request("GET", "/services/v1/Security/PublicKey")
        response = connection.getresponse()
        server_public_pem = response.read()
        self.assertEqual(response.status, 200)
        server_public = serialization.load_pem_public_key(server_public_pem)

        client_private, client_public_pem = client_keypair()
        login = {
            "createNew": False,
            "buildId": 4909173,
            "branch": "public",
            "EncryptionKey": client_public_pem.decode("utf-8"),
            "AuthToken": "test-ticket",
        }
        body = mock_backend.encrypt_payload(server_public, login)
        connection.request(
            "POST",
            "/services/v1/PlayerProfile/Steam/Login",
            body=body,
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        encrypted = response.read()
        self.assertEqual(response.status, 200)

        payload = mock_backend.decrypt_payload(client_private, encrypted)
        self.assertRegex(payload["token"], r"^[0-9a-f]{32}$")
        self.assertRegex(payload["userid"], r"^[0-9a-f]{24}$")

        get_ids = mock_backend.encrypt_payload(server_public, ["abc"])
        connection.request(
            "POST",
            "/services/v1/PlayerProfile/User/GetPlatformIds/",
            body=get_ids,
            headers={
                "Content-Type": "application/json",
                "Authorization": payload["token"],
            },
        )
        response = connection.getresponse()
        encrypted = response.read()
        self.assertEqual(response.status, 200)
        self.assertEqual(
            mock_backend.decrypt_payload(client_private, encrypted), []
        )

        connection.close()

    def test_create_and_reserve(self):
        connection = self._connection()
        connection.request("GET", "/services/v1/Security/PublicKey")
        response = connection.getresponse()
        server_public = serialization.load_pem_public_key(response.read())

        client_private, client_public_pem = client_keypair()
        login = {
            "createNew": False,
            "buildId": 4909173,
            "branch": "public",
            "EncryptionKey": client_public_pem.decode("utf-8"),
            "AuthToken": "test-ticket",
        }
        login_body = mock_backend.encrypt_payload(server_public, login)
        connection.request(
            "POST",
            "/services/v1/PlayerProfile/Steam/Login",
            body=login_body,
            headers={"Content-Type": "application/json"},
        )
        login_payload = mock_backend.decrypt_payload(
            client_private, connection.getresponse().read()
        )
        token = login_payload["token"]

        create = {
            "Latencies": {"eu-central-1": 99999},
            "MaxPlayers": 12,
            "Alias": "MGP19-Test",
            "Properties": {"PlatformSessionId": "123456"},
        }
        create_body = mock_backend.encrypt_payload(server_public, create)
        connection.request(
            "POST",
            "/services/v1/GameSessions/Create/",
            body=create_body,
            headers={
                "Content-Type": "application/json",
                "Authorization": token,
            },
        )
        create_response = mock_backend.decrypt_payload(
            client_private, connection.getresponse().read()
        )
        self.assertIn("gameSessionId", create_response)
        self.assertEqual(create_response["ipAddress"], "127.0.0.1")
        self.assertEqual(create_response["port"], 7777)

        reserve = {"GameSessionId": create_response["gameSessionId"]}
        reserve_body = mock_backend.encrypt_payload(server_public, reserve)
        connection.request(
            "POST",
            "/services/v1/GameSessions/ReserveSpot/",
            body=reserve_body,
            headers={
                "Content-Type": "application/json",
                "Authorization": token,
            },
        )
        reserve_response = mock_backend.decrypt_payload(
            client_private, connection.getresponse().read()
        )
        self.assertTrue(reserve_response["playerSessionId"].startswith("psess-"))
        self.assertEqual(reserve_response["ipAddress"], "127.0.0.1")
        self.assertEqual(reserve_response["port"], 7777)

        player_data = json.loads(reserve_response["playerData"])
        self.assertEqual(len(base64.b64decode(player_data["EncryptionKey"])), 32)
        self.assertEqual(len(base64.b64decode(player_data["EncryptionNonce"])), 12)
        connection.close()

    def test_udp_handshake(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = mock_backend.MockState(
                private_key=None,
                public_pem=b"",
                game_ip="127.0.0.1",
                log_path=None,
            )
            log_path = Path(tmp) / "udp.jsonl"
            probe = mock_backend.UdpProbe(
                "127.0.0.1", 0, state, log_path=log_path
            )
            port = probe.sock.getsockname()[1]
            probe.start()

            client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            client.settimeout(3)
            try:
                client.sendto(
                    b"\x01" + b"\x00" * 23 + b"\x04",
                    ("127.0.0.1", port),
                )
                challenge, _ = client.recvfrom(2048)
                self.assertEqual(challenge, mock_backend.HANDSHAKE_CHALLENGE)

                client.sendto(challenge, ("127.0.0.1", port))
                response, _ = client.recvfrom(2048)
                self.assertEqual(response, mock_backend.HANDSHAKE_RESPONSE)

                hello = b"x" * 10 + b"psess-test-1234" + b"y" * 36
                self.assertEqual(len(hello), 61)
                client.sendto(hello, ("127.0.0.1", port))
                time.sleep(0.5)
            finally:
                client.close()
                probe.stop()
                probe.join(timeout=2)

            records = [
                json.loads(line)
                for line in log_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            handshakes = [record.get("handshake") for record in records]
            self.assertIn("challenge_sent", handshakes)
            self.assertIn("response_sent", handshakes)
            self.assertIn("hello", handshakes)


if __name__ == "__main__":
    unittest.main()
