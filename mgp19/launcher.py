"""Lancement du jeu via Steam, modes host / join, sessions et logs.

Le launcher ne modifie que la config utilisateur. Il applique un profil avant
le lancement, attend la fin du jeu, puis restaure la config d'origine.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import network
from .config import ConfigManager, Profile
from .paths import APP_ID, GameInstall, is_game_running, steam_roots

DEFAULT_TRACK = "mugello"
DEFAULT_PORT = network.DEFAULT_PORT
DEFAULT_MAP_TEMPLATE = "/Game/maps/Tracks/{track}/{track}"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SESSIONS_DIR = PROJECT_ROOT / "sessions"


def find_steam_exe() -> Path | None:
    for root in steam_roots():
        candidate = root / "steam.exe"
        if candidate.exists():
            return candidate
    return None


def default_map(track: str) -> str:
    return DEFAULT_MAP_TEMPLATE.format(track=track)


def command_text(command: list[str]) -> str:
    return subprocess.list2cmdline(command)


@dataclass
class LaunchPlan:
    mode: str
    map_url: str | None = None
    endpoint: str | None = None
    port: int = DEFAULT_PORT
    profile: str = "direct-connect"
    restore_after: bool = True
    extra_args: list[str] = field(default_factory=list)
    nosteam: bool = True
    log: bool = True

    def game_args(self) -> list[str]:
        if self.mode == "host":
            if not self.map_url:
                raise ValueError("map_url manquant pour le mode host")
            args = [self.map_url, f"-port={self.port}"]
        elif self.mode == "join":
            if not self.endpoint:
                raise ValueError("endpoint manquant pour le mode join")
            args = [self.endpoint]
        else:
            raise ValueError(f"mode inconnu : {self.mode}")

        if self.nosteam:
            args.append("-nosteam")
        if self.log:
            args.append("-log")
        args.extend(self.extra_args)
        return args


def steam_command(steam_exe: Path, plan: LaunchPlan) -> list[str]:
    return [str(steam_exe), "-applaunch", APP_ID, *plan.game_args()]


@dataclass
class SessionInfo:
    id: str
    directory: Path
    plan: LaunchPlan
    steam_command: list[str]
    started_at: str
    targets: list[str] = field(default_factory=list)
    ended_at: str | None = None
    game_started: bool = False
    game_exited: bool = False
    duration_s: float | None = None
    active: bool = True
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "directory": str(self.directory),
            "mode": self.plan.mode,
            "map_url": self.plan.map_url,
            "endpoint": self.plan.endpoint,
            "port": self.plan.port,
            "profile": self.plan.profile,
            "targets": self.targets,
            "restore_after": self.plan.restore_after,
            "extra_args": self.plan.extra_args,
            "steam_command": self.steam_command,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "game_started": self.game_started,
            "game_exited": self.game_exited,
            "duration_s": self.duration_s,
            "active": self.active,
            "notes": self.notes,
        }


class SessionRecorder:
    def __init__(self, info: SessionInfo):
        self.info = info

    def write(self) -> None:
        self.info.directory.mkdir(parents=True, exist_ok=True)
        (self.info.directory / "session.json").write_text(
            json.dumps(self.info.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def note(self, text: str) -> None:
        self.info.notes.append(text)
        self.write()

    def write_text(self, name: str, text: str) -> None:
        (self.info.directory / name).write_text(text, encoding="utf-8")

    def write_json(self, name: str, data: dict) -> None:
        (self.info.directory / name).write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def attach_environment(self, install: GameInstall) -> None:
        self.info.directory.mkdir(parents=True, exist_ok=True)
        config = install.config_dir / "Engine.ini"
        if config.exists():
            shutil.copy2(config, self.info.directory / "Engine.before.ini")
        self.write_json("net.before.json", network.diagnostics(port=self.info.plan.port))
        self.write_text("steam-command.txt", command_text(self.info.steam_command))
        self.write()

    def collect(self, install: GameInstall) -> None:
        _copy_tree(install.logs_dir, self.info.directory / "logs")
        _copy_tree(install.saved_dir / "Crashes", self.info.directory / "crashes")
        _copy_tree(
            install.saved_dir / "Config" / "CrashReportClient",
            self.info.directory / "crash-report",
        )

        config = install.config_dir / "Engine.ini"
        if config.exists():
            shutil.copy2(config, self.info.directory / "Engine.after.ini")

        self.write_json("net.after.json", network.diagnostics(port=self.info.plan.port))
        self.write_text("processes.txt", _tasklist())
        self.write()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _copy_tree(source: Path, destination: Path) -> None:
    if not source.exists():
        return
    for item in source.rglob("*"):
        if not item.is_file():
            continue
        relative = item.relative_to(source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)


def _tasklist() -> str:
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq motogp19-Win64-Shipping.exe"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return (result.stdout + result.stderr).strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _wait_for_start(timeout: float, interval: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if is_game_running():
            return True
        time.sleep(interval)
    return False


def _wait_for_exit(interval: float) -> None:
    while is_game_running():
        time.sleep(interval)


def recover_previous_sessions(
    manager: ConfigManager,
    sessions_dir: Path = SESSIONS_DIR,
) -> list[str]:
    """Restaure la config d'une session précédente restée active."""
    if not sessions_dir.exists():
        return []

    recovered: list[str] = []
    for session_file in sorted(sessions_dir.glob("*/session.json"), reverse=True):
        try:
            data = json.loads(session_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        if not data.get("active") or not data.get("restore_after", True):
            continue

        try:
            manager.restore("Engine.ini", dry_run=False)
            recovered.append(str(session_file))
            data.setdefault("notes", []).append(
                "Restauration de récupération au démarrage suivant."
            )
        except (FileNotFoundError, RuntimeError) as error:
            data.setdefault("notes", []).append(
                f"Restauration de récupération impossible : {error}"
            )

        data["active"] = False
        try:
            session_file.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            pass

    return recovered


def run_session(
    install: GameInstall,
    plan: LaunchPlan,
    profile: Profile | None,
    *,
    start_timeout: float = 120.0,
    poll_interval: float = 2.0,
) -> SessionInfo:
    if is_game_running():
        raise RuntimeError("Le jeu est déjà lancé. Ferme-le avant de relancer.")

    steam_exe = find_steam_exe()
    if steam_exe is None:
        raise RuntimeError("steam.exe introuvable. Steam est-il installé ?")

    command = steam_command(steam_exe, plan)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    session_id = f"{stamp}-{plan.mode}"
    directory = SESSIONS_DIR / session_id

    info = SessionInfo(
        id=session_id,
        directory=directory,
        plan=plan,
        steam_command=command,
        started_at=_now(),
        targets=list(profile.targets) if profile else [],
    )
    recorder = SessionRecorder(info)
    manager = ConfigManager(install.config_dir)

    recovered = recover_previous_sessions(manager)
    for path in recovered:
        info.notes.append(f"Session précédente récupérée : {path}")

    started_monotonic = time.monotonic()
    try:
        if profile and profile.targets:
            results = manager.apply_profile(profile, dry_run=False)
            for result in results:
                if result.written:
                    info.notes.append(f"Profil appliqué : {result.target}")

        recorder.attach_environment(install)
        subprocess.Popen(command, cwd=str(install.root))

        info.game_started = _wait_for_start(start_timeout, poll_interval)
        if not info.game_started:
            info.notes.append(
                f"Le jeu n'a pas démarré dans le délai de {start_timeout:.0f} s."
            )
        else:
            recorder.write()
            _wait_for_exit(poll_interval)
            info.game_exited = True
    finally:
        if plan.restore_after:
            try:
                if manager.original_backup("Engine.ini").exists():
                    manager.restore("Engine.ini", dry_run=False)
                    info.notes.append("Config restaurée après la session.")
            except (FileNotFoundError, RuntimeError) as error:
                info.notes.append(f"Restauration impossible : {error}")

        info.ended_at = _now()
        info.duration_s = round(time.monotonic() - started_monotonic, 1)
        info.active = False
        try:
            recorder.collect(install)
        except OSError as error:
            info.notes.append(f"Collecte des logs partielle : {error}")
        recorder.write()

    return info


def list_sessions(sessions_dir: Path = SESSIONS_DIR) -> list[dict]:
    sessions: list[dict] = []
    if not sessions_dir.exists():
        return sessions
    for session_file in sorted(sessions_dir.glob("*/session.json"), reverse=True):
        try:
            data = json.loads(session_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        sessions.append(data)
    return sessions
