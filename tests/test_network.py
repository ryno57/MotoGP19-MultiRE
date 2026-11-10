import socket
import unittest

from mgp19 import network


class EndpointTests(unittest.TestCase):
    def test_parse_ipv4_with_port(self):
        self.assertEqual(network.parse_endpoint("192.168.0.42:7777"), ("192.168.0.42", 7777))

    def test_parse_default_port(self):
        self.assertEqual(network.parse_endpoint("192.168.0.42"), ("192.168.0.42", 7777))

    def test_parse_ipv6_with_port(self):
        self.assertEqual(network.parse_endpoint("[::1]:7777"), ("::1", 7777))

    def test_parse_ipv6_without_port(self):
        self.assertEqual(network.parse_endpoint("[::1]"), ("::1", 7777))

    def test_parse_invalid_port(self):
        with self.assertRaises(ValueError):
            network.parse_endpoint("192.168.0.42:70000")

    def test_parse_empty(self):
        with self.assertRaises(ValueError):
            network.parse_endpoint("   ")

    def test_format_ipv4(self):
        self.assertEqual(network.format_endpoint("192.168.0.42", 7777), "192.168.0.42:7777")

    def test_format_ipv6(self):
        self.assertEqual(network.format_endpoint("::1", 7777), "[::1]:7777")


class NetworkHelpersTests(unittest.TestCase):
    def test_local_ip_shape(self):
        value = network.local_ip()
        parts = value.split(".")
        self.assertEqual(len(parts), 4)
        for part in parts:
            self.assertTrue(0 <= int(part) <= 255)

    def test_port_free_detects_bound_port(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        try:
            self.assertFalse(network.port_free(port, host="127.0.0.1"))
        finally:
            sock.close()
        self.assertTrue(network.port_free(port, host="127.0.0.1"))

    def test_firewall_rule_name(self):
        self.assertEqual(
            network.firewall_rule_name(7777),
            "MotoGP19 Community Host (UDP 7777)",
        )
        self.assertEqual(
            network.firewall_rule_name(7777, 8077),
            "MotoGP19 Community Host (UDP 7777-8077)",
        )

    def test_is_private_ip(self):
        self.assertTrue(network.is_private_ip("192.168.0.11"))
        self.assertTrue(network.is_private_ip("10.0.0.1"))
        self.assertFalse(network.is_private_ip("8.8.8.8"))
        self.assertFalse(network.is_private_ip("not-an-ip"))


if __name__ == "__main__":
    unittest.main()
