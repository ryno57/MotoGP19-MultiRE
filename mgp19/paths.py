"""Détection de l'installation MotoGP 19 et des chemins utilisateur.

Aucune dépendance externe : uniquement la bibliothèque standard.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

APP_ID = "984780"
GAME_DIR_RE = re.compile(r"^MotoGP.{0,2}19$", re.IGNORECASE)
PATH_RE = re.compile(r'"path"\s+"([^"]+)"')
INSTALLDIR_RE = re.compile(r'"installdir"\s+"([^"]+)"')


def local_appdata() -> Path:
    value = os.environ.get("LOCALAPPDATA")
    if value:
        return Path(value)
    return Path.home() / "AppData" / "Local"


def _decode_vdf_path(raw: str) -> Path:
    # Les chemins VDF échappent les antislashs : C:\\Program Files\\Steam
    return Path(raw.replace("\\\\", "\\"))


def registry_steam_roots() -> list[Path]:
    roots: list[Path] = []
    try:
        import winreg
    except ImportError:
        return roots

    candidates = [
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "InstallPath"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath"),
    ]
    for hive, key, name in candidates:
        try:
            with winreg.OpenKey(hive, key) as handle:
                value, _ = winreg.QueryValueEx(handle, name)
                if value:
                    roots.append(Path(value))
        except OSError:
            continue
    return roots


def steam_roots() -> list[Path]:
    candidates = registry_steam_roots() + [
        Path(r"C:\Program Files (x86)\Steam"),
        Path(r"C:\Program Files\Steam"),
    ]
    seen: set[str] = set()
    result: list[Path] = []
    for path in candidates:
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        key = str(resolved).casefold()
        if key not in seen and resolved.exists():
            seen.add(key)
            result.append(resolved)
    return result


def library_folders(steam_root: Path) -> list[Path]:
    libraries = [steam_root]
    vdf = steam_root / "steamapps" / "libraryfolders.vdf"
    if vdf.exists():
        text = vdf.read_text(encoding="utf-8", errors="replace")
        for raw in PATH_RE.findall(text):
            path = _decode_vdf_path(raw)
            if path.exists():
                libraries.append(path)

    seen: set[str] = set()
    result: list[Path] = []
    for library in libraries:
        try:
            key = str(library.resolve()).casefold()
        except OSError:
            key = str(library).casefold()
        if key not in seen:
            seen.add(key)
            result.append(library)
    return result


def find_install(game_path: str | Path | None = None) -> "GameInstall | None":
    if game_path:
        root = Path(game_path)
        return GameInstall(root) if root.exists() else None

    for steam_root in steam_roots():
        for library in library_folders(steam_root):
            common = library / "steamapps" / "common"
            manifest = library / "steamapps" / f"appmanifest_{APP_ID}.acf"
            if manifest.exists():
                text = manifest.read_text(encoding="utf-8", errors="replace")
                match = INSTALLDIR_RE.search(text)
                if match:
                    root = common / match.group(1)
                    if root.exists():
                        return GameInstall(root)
            if common.exists():
                for child in common.iterdir():
                    if child.is_dir() and GAME_DIR_RE.match(child.name):
                        return GameInstall(child)
    return None


@dataclass(frozen=True)
class GameInstall:
    root: Path

    @property
    def exe(self) -> Path:
        return self.root / "motogp19.exe"

    @property
    def shipping_exe(self) -> Path:
        return self.root / "motogp19" / "Binaries" / "Win64" / "motogp19-Win64-Shipping.exe"

    @property
    def content_dir(self) -> Path:
        return self.root / "motogp19" / "Content"

    @property
    def user_dir(self) -> Path:
        return local_appdata() / "motogp19"

    @property
    def saved_dir(self) -> Path:
        return self.user_dir / "Saved"

    @property
    def config_dir(self) -> Path:
        return self.saved_dir / "Config" / "WindowsNoEditor"

    @property
    def logs_dir(self) -> Path:
        return self.saved_dir / "Logs"

    @property
    def savegames_dir(self) -> Path:
        return self.saved_dir / "SaveGames"

    @property
    def backup_dir(self) -> Path:
        return self.config_dir / "_mgp19_backups"

    def missing(self) -> list[str]:
        checks = {
            "dossier du jeu": self.root,
            "motogp19.exe": self.exe,
            "motogp19-Win64-Shipping.exe": self.shipping_exe,
            "dossier de config": self.config_dir,
        }
        return [label for label, path in checks.items() if not path.exists()]

    def as_dict(self) -> dict[str, str]:
        return {
            "root": str(self.root),
            "exe": str(self.exe),
            "shipping_exe": str(self.shipping_exe),
            "config_dir": str(self.config_dir),
            "logs_dir": str(self.logs_dir),
            "savegames_dir": str(self.savegames_dir),
            "backup_dir": str(self.backup_dir),
        }


def is_game_running() -> bool:
    if os.name != "nt":
        return False
    for name in ("motogp19-Win64-Shipping.exe", "motogp19.exe"):
        try:
            result = subprocess.run(
                ["tasklist", "/NH", "/FI", f"IMAGENAME eq {name}"],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if name.casefold() in result.stdout.casefold():
            return True
    return False
