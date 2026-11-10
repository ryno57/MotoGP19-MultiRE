"""Diagnostics réseau et pare-feu Windows pour l'hébergement local.

Aucun paquet n'est envoyé pour déterminer l'IP locale : on utilise un socket
UDP non connecté. Les fonctions qui modifient le système (pare-feu) sont
explicites et ne s'exécutent que si l'appelant le demande.
"""

from __future__ import annotations

import ipaddress
import json
import os
import socket
import subprocess
from dataclasses import dataclass

DEFAULT_PORT = 7777
DEFAULT_PORT_END = 8077
FIREWALL_RULE_PREFIX = "MotoGP19 Community Host"


def local_ip() -> str:
    """Retourne l'IP locale utilisée pour sortir sur le réseau."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"
    finally:
        sock.close()


def public_ip(timeout: float = 4.0) -> str | None:
    """Récupère l'IP publique via un service externe. Optionnel."""
    try:
        import urllib.request

        with urllib.request.urlopen("https://api.ipify.org", timeout=timeout) as response:
            value = response.read().decode("ascii", "replace").strip()
        return value or None
    except Exception:
        return None


def is_private_ip(value: str) -> bool:
    try:
        return ipaddress.ip_address(value).is_private
    except ValueError:
        return False


def format_endpoint(host: str, port: int) -> str:
    if ":" in host and not host.startswith("["):
        return f"[{host}]:{port}"
    return f"{host}:{port}"


def parse_endpoint(value: str, default_port: int = DEFAULT_PORT) -> tuple[str, int]:
    text = value.strip()
    if not text:
        raise ValueError("endpoint vide")

    if text.startswith("["):
        end = text.find("]")
        if end == -1:
            raise ValueError("crochet IPv6 non fermé")
        host = text[1:end]
        rest = text[end + 1:]
        if rest and not rest.startswith(":"):
            raise ValueError("format attendu : [ipv6]:port")
        port_text = rest[1:] if rest.startswith(":") else ""
    elif text.count(":") == 1:
        host, port_text = text.split(":", 1)
    elif text.count(":") == 0:
        host, port_text = text, ""
    else:
        # IPv6 sans crochets : on ne peut pas distinguer le port.
        host, port_text = text, ""

    if not host:
        raise ValueError("hôte vide")

    if port_text:
        try:
            port = int(port_text)
        except ValueError as error:
            raise ValueError(f"port invalide : {port_text}") from error
    else:
        port = default_port

    if not 1 <= port <= 65535:
        raise ValueError(f"port hors plage : {port}")

    return host, port


def port_free(port: int, host: str = "0.0.0.0") -> bool:
    """Teste si on peut binder un port UDP localement."""
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_DGRAM)
    try:
        sock.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def udp_listeners(port: int) -> list[dict]:
    """Liste les processus qui écoutent sur un port UDP (Windows)."""
    if os.name != "nt":
        return []

    script = """
$items = Get-NetUDPEndpoint -LocalPort {port} -ErrorAction SilentlyContinue | ForEach-Object {{
  $proc = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue
  [pscustomobject]@{{ pid = [int]$_.OwningProcess; address = [string]$_.LocalAddress; port = [int]$_.LocalPort; process = [string]$proc.ProcessName }}
}}
if ($items) {{ $items | ConvertTo-Json -Compress }} else {{ '[]' }}
""".format(port=int(port)).strip()

    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return []

    output = result.stdout.strip()
    if not output:
        return []

    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return []

    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return []

    listeners: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        listeners.append(
            {
                "pid": int(item.get("pid", 0)),
                "address": str(item.get("address", "")),
                "port": int(item.get("port", port)),
                "process": str(item.get("process", "")),
            }
        )
    return listeners


def firewall_rule_name(port: int = DEFAULT_PORT, port_end: int | None = None) -> str:
    if port_end and port_end != port:
        return f"{FIREWALL_RULE_PREFIX} (UDP {port}-{port_end})"
    return f"{FIREWALL_RULE_PREFIX} (UDP {port})"


def firewall_rule_exists(name: str) -> bool:
    if os.name != "nt":
        return False
    try:
        result = subprocess.run(
            ["netsh", "advfirewall", "firewall", "show", "rule", f"name={name}"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def is_admin() -> bool:
    if os.name != "nt":
        return False
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


@dataclass
class FirewallResult:
    name: str
    exists: bool
    added: bool
    needs_admin: bool
    is_admin: bool
    command_text: str
    output: str = ""


def ensure_firewall_rule(
    port: int = DEFAULT_PORT,
    port_end: int | None = None,
    *,
    dry_run: bool = True,
) -> FirewallResult:
    name = firewall_rule_name(port, port_end)
    exists = firewall_rule_exists(name)
    port_spec = f"{port}-{port_end}" if port_end and port_end != port else str(port)

    command = [
        "netsh",
        "advfirewall",
        "firewall",
        "add",
        "rule",
        f"name={name}",
        "dir=in",
        "action=allow",
        "protocol=UDP",
        f"localport={port_spec}",
        "profile=any",
    ]
    command_text = " ".join(f'"{part}"' if " " in part else part for part in command)
    admin = is_admin()

    if exists:
        return FirewallResult(name, True, False, False, admin, command_text)

    if dry_run:
        return FirewallResult(name, False, False, False, admin, command_text)

    if not admin:
        return FirewallResult(name, False, False, True, False, command_text)

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return FirewallResult(
            name,
            False,
            False,
            False,
            True,
            command_text,
            output=str(error),
        )

    return FirewallResult(
        name,
        False,
        result.returncode == 0,
        False,
        True,
        command_text,
        output=(result.stdout + result.stderr).strip(),
    )


def diagnostics(port: int = DEFAULT_PORT, *, include_public: bool = False) -> dict:
    host = local_ip()
    listeners = udp_listeners(port)
    rule = firewall_rule_name(port)
    return {
        "hostname": socket.gethostname(),
        "local_ip": host,
        "private_ip": is_private_ip(host),
        "public_ip": public_ip() if include_public else None,
        "port": port,
        "endpoint": format_endpoint(host, port),
        "listeners": listeners,
        "udp_bound": bool(listeners),
        "port_free": port_free(port) if not listeners else False,
        "firewall_rule": rule,
        "firewall_exists": firewall_rule_exists(rule),
    }
