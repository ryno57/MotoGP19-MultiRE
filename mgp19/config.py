"""Gestion des fichiers .ini UE4, profils et sauvegardes.

Le but est de modifier uniquement la config utilisateur, sans jamais toucher
aux paks ni aux exécutables du jeu. Chaque application de profil crée une
sauvegarde de l'original, ce qui permet un retour arrière propre.
"""

from __future__ import annotations

import difflib
import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .paths import is_game_running

SECTION_RE = re.compile(r"^\s*\[(.+?)\]\s*$")
ENTRY_RE = re.compile(r"^([+\-!.]?)([^=]+)=(.*)$")

VALID_MODES = {"set", "append", "clear_array", "remove"}


def _split_ending(line: str) -> tuple[str, str]:
    body = line.rstrip("\r\n")
    return body, line[len(body):]


def _detect_newline(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


class IniDocument:
    """Document .ini UE4 minimal, avec préservation des commentaires."""

    def __init__(self, text: str):
        self.newline = _detect_newline(text)
        self.lines = text.splitlines(keepends=True)

    def to_text(self) -> str:
        return "".join(self.lines)

    def _section_span(self, section: str) -> tuple[int, int] | None:
        starts: list[int] = []
        for index, line in enumerate(self.lines):
            match = SECTION_RE.match(line.rstrip("\r\n"))
            if match and match.group(1).strip().casefold() == section.strip().casefold():
                starts.append(index)
        if not starts:
            return None

        start = starts[-1]
        end = len(self.lines)
        for index in range(start + 1, len(self.lines)):
            if SECTION_RE.match(self.lines[index].rstrip("\r\n")):
                end = index
                break
        return start, end

    def _key_indices(self, section: str, key: str) -> list[int]:
        span = self._section_span(section)
        if not span:
            return []

        start, end = span
        result: list[int] = []
        for index in range(start + 1, end):
            body, _ = _split_ending(self.lines[index])
            match = ENTRY_RE.match(body)
            if match and match.group(2).strip().casefold() == key.strip().casefold():
                result.append(index)
        return result

    def _ensure_section(self, section: str) -> tuple[int, int]:
        span = self._section_span(section)
        if span:
            return span

        if self.lines and not self.lines[-1].endswith(("\n", "\r")):
            self.lines[-1] += self.newline
        if self.lines and self.lines[-1].strip():
            self.lines.append(self.newline)
        self.lines.append(f"[{section}]{self.newline}")
        return len(self.lines) - 1, len(self.lines)

    def _insert_at_section_end(self, section: str, text: str) -> None:
        start, end = self._ensure_section(section)
        if end > start + 1 and not self.lines[end - 1].endswith(("\n", "\r")):
            self.lines[end - 1] += self.newline
        self.lines.insert(end, text + self.newline)

    def set(self, section: str, key: str, value: str) -> bool:
        indices = self._key_indices(section, key)
        new_line = f"{key}={value}"

        if not indices:
            self._insert_at_section_end(section, new_line)
            return True

        first = indices[0]
        _, ending = _split_ending(self.lines[first])
        replacement = new_line + (ending or self.newline)
        changed = self.lines[first] != replacement
        self.lines[first] = replacement

        for index in reversed(indices[1:]):
            del self.lines[index]
            changed = True
        return changed

    def append(self, section: str, key: str, value: str) -> bool:
        self._insert_at_section_end(section, f"+{key}={value}")
        return True

    def clear_array(self, section: str, key: str) -> bool:
        self._insert_at_section_end(section, f"!{key}=ClearArray")
        return True

    def remove(self, section: str, key: str) -> bool:
        indices = self._key_indices(section, key)
        for index in reversed(indices):
            del self.lines[index]
        return bool(indices)

    def apply(self, operation: "Operation") -> bool:
        if operation.mode == "set":
            return self.set(operation.section, operation.key, operation.value or "")
        if operation.mode == "append":
            return self.append(operation.section, operation.key, operation.value or "")
        if operation.mode == "clear_array":
            return self.clear_array(operation.section, operation.key)
        if operation.mode == "remove":
            return self.remove(operation.section, operation.key)
        raise ValueError(f"mode inconnu : {operation.mode}")


@dataclass(frozen=True)
class Operation:
    section: str
    key: str
    mode: str
    value: str | None = None
    target: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "Operation":
        section = str(data["section"])
        key = str(data["key"])
        mode = str(data["mode"])
        value = data.get("value")
        target = data.get("target")

        if mode not in VALID_MODES:
            raise ValueError(f"mode inconnu : {mode}")
        if mode in {"set", "append"} and value is None:
            raise ValueError(f"valeur manquante pour {section}/{key}")

        return cls(
            section=section,
            key=key,
            mode=mode,
            value=None if value is None else str(value),
            target=None if target is None else str(target),
        )


@dataclass(frozen=True)
class Profile:
    name: str
    description: str
    targets: tuple[str, ...]
    operations: tuple[Operation, ...]
    path: Path | None = None

    @classmethod
    def load(cls, path: str | Path) -> "Profile":
        path = Path(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            name=str(data["name"]),
            description=str(data.get("description", "")),
            targets=tuple(str(target) for target in data.get("targets", [])),
            operations=tuple(Operation.from_dict(op) for op in data.get("operations", [])),
            path=path,
        )

    def operations_for(self, target: str) -> list[Operation]:
        return [op for op in self.operations if op.target in (None, target)]


@dataclass
class ApplyResult:
    target: str
    changed: bool
    written: bool
    diff: str
    backup: Path | None = None


class ConfigManager:
    def __init__(self, config_dir: str | Path, *, check_running: bool = True):
        self.config_dir = Path(config_dir)
        self.backup_dir = self.config_dir / "_mgp19_backups"
        self.check_running = check_running

    def target_path(self, target: str) -> Path:
        return self.config_dir / target

    def original_backup(self, target: str) -> Path:
        return self.backup_dir / f"{target}.original.mgp19bak"

    def snapshots(self, target: str) -> list[Path]:
        if not self.backup_dir.exists():
            return []
        return sorted(self.backup_dir.glob(f"{target}.*.mgp19bak"))

    def ensure_original(self, target: str) -> Path:
        source = self.target_path(target)
        if not source.exists():
            raise FileNotFoundError(source)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        destination = self.original_backup(target)
        if not destination.exists():
            shutil.copy2(source, destination)
        return destination

    def snapshot(self, target: str) -> Path:
        source = self.target_path(target)
        if not source.exists():
            raise FileNotFoundError(source)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        destination = self.backup_dir / f"{target}.{stamp}.mgp19bak"
        shutil.copy2(source, destination)
        return destination

    def apply_profile(
        self,
        profile: Profile,
        *,
        dry_run: bool = True,
        targets: Iterable[str] | None = None,
    ) -> list[ApplyResult]:
        selected = list(targets) if targets else list(profile.targets)
        if not selected:
            return []
        if not dry_run and self.check_running and is_game_running():
            raise RuntimeError(
                "Le jeu est en cours d'exécution. Ferme-le avant d'appliquer un profil."
            )

        results: list[ApplyResult] = []
        for target in selected:
            path = self.target_path(target)
            if not path.exists():
                raise FileNotFoundError(path)

            encoding, bom = _read_encoding(path)
            old_text = path.read_text(encoding=encoding)
            if bom:
                old_text = old_text.lstrip("\ufeff")

            document = IniDocument(old_text)
            for operation in profile.operations_for(target):
                document.apply(operation)
            new_text = document.to_text()

            changed = new_text != old_text
            diff = "".join(
                difflib.unified_diff(
                    old_text.splitlines(keepends=True),
                    new_text.splitlines(keepends=True),
                    fromfile=f"a/{target}",
                    tofile=f"b/{target}",
                )
            )

            backup = None
            written = False
            if changed and not dry_run:
                backup = self.ensure_original(target)
                self.snapshot(target)
                _atomic_write(path, new_text, bom=bom)
                written = True

            results.append(
                ApplyResult(
                    target=target,
                    changed=changed,
                    written=written,
                    diff=diff,
                    backup=backup,
                )
            )
        return results

    def restore(self, target: str, *, dry_run: bool = True) -> ApplyResult:
        original = self.original_backup(target)
        path = self.target_path(target)
        if not original.exists():
            raise FileNotFoundError(f"Aucune sauvegarde originale pour {target}")

        old_text = path.read_text(encoding="utf-8-sig") if path.exists() else ""
        new_text = original.read_text(encoding="utf-8-sig")
        diff = "".join(
            difflib.unified_diff(
                old_text.splitlines(keepends=True),
                new_text.splitlines(keepends=True),
                fromfile=f"a/{target}",
                tofile=f"b/{target}",
            )
        )

        written = False
        if not dry_run:
            if self.check_running and is_game_running():
                raise RuntimeError(
                    "Le jeu est en cours d'exécution. Ferme-le avant de restaurer."
                )
            if path.exists():
                self.snapshot(target)
            shutil.copy2(original, path)
            written = True

        return ApplyResult(
            target=target,
            changed=diff != "",
            written=written,
            diff=diff,
        )

    def status(self, target: str = "Engine.ini") -> dict:
        path = self.target_path(target)
        original = self.original_backup(target)
        current = path.read_text(encoding="utf-8-sig") if path.exists() else None
        base = original.read_text(encoding="utf-8-sig") if original.exists() else None
        return {
            "target": target,
            "path": str(path),
            "exists": path.exists(),
            "original_backup": str(original) if original.exists() else None,
            "snapshots": [str(snapshot) for snapshot in self.snapshots(target)],
            "modified": current is not None and base is not None and current != base,
        }


def _read_encoding(path: Path) -> tuple[str, bool]:
    raw = path.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    return ("utf-8-sig" if bom else "utf-8"), bom


def _atomic_write(path: Path, text: str, *, bom: bool) -> None:
    data = text.encode("utf-8")
    if bom:
        data = b"\xef\xbb\xbf" + data
    temporary = path.with_name(path.name + ".mgp19tmp")
    temporary.write_bytes(data)
    os.replace(temporary, path)
