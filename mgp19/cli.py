"""Interface en ligne de commande du socle mgp19."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import launcher, network
from .config import ConfigManager, Profile
from .paths import find_install, is_game_running

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROFILES_DIR = PROJECT_ROOT / "profiles"


def _load_profiles() -> dict[str, Profile]:
    profiles: dict[str, Profile] = {}
    if not PROFILES_DIR.exists():
        return profiles
    for path in sorted(PROFILES_DIR.glob("*.json")):
        profile = Profile.load(path)
        profiles[profile.name] = profile
    return profiles


def _install(args):
    install = find_install(args.game_path)
    if install is None:
        print(
            "Jeu introuvable. Utilise --game-path pour indiquer le dossier d'installation.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return install


def cmd_doctor(args) -> int:
    install = _install(args)
    print("MotoGP 19 — diagnostic")
    print(f"  racine        : {install.root}")
    print(f"  exe           : {install.exe}")
    print(f"  shipping exe  : {install.shipping_exe}")
    print(f"  config        : {install.config_dir}")
    print(f"  logs          : {install.logs_dir}")
    print(f"  sauvegardes   : {install.backup_dir}")
    print(f"  jeu lancé     : {'oui' if is_game_running() else 'non'}")

    missing = install.missing()
    if missing:
        print("  manquant      : " + ", ".join(missing))
    else:
        print("  état          : installation complète")

    profiles = _load_profiles()
    print(f"  profils       : {', '.join(profiles) if profiles else 'aucun'}")
    return 0


def cmd_profiles(args) -> int:
    profiles = _load_profiles()
    if not profiles:
        print("Aucun profil.")
        return 0
    for profile in profiles.values():
        print(profile.name)
        if profile.description:
            print(f"  {profile.description}")
        targets = ", ".join(profile.targets) or "-"
        print(f"  cibles: {targets} | opérations: {len(profile.operations)}")
    return 0


def cmd_apply(args) -> int:
    install = _install(args)
    profiles = _load_profiles()
    profile = profiles.get(args.profile)
    if profile is None:
        print(f"Profil inconnu : {args.profile}", file=sys.stderr)
        print("Disponibles : " + ", ".join(profiles), file=sys.stderr)
        return 2

    manager = ConfigManager(install.config_dir)
    try:
        results = manager.apply_profile(profile, dry_run=not args.yes)
    except (FileNotFoundError, RuntimeError) as error:
        print(f"Erreur : {error}", file=sys.stderr)
        return 2

    for result in results:
        if result.written:
            state = "écrit"
        elif result.changed:
            state = "à écrire"
        else:
            state = "inchangé"
        print(f"{result.target}: {state}")
        if result.diff:
            print(result.diff, end="")

    if not args.yes and any(result.changed for result in results):
        print("\nMode aperçu. Relance avec --yes pour appliquer.")
    return 0


def cmd_restore(args) -> int:
    install = _install(args)
    manager = ConfigManager(install.config_dir)
    targets = args.targets or ["Engine.ini"]

    for target in targets:
        try:
            result = manager.restore(target, dry_run=not args.yes)
        except (FileNotFoundError, RuntimeError) as error:
            print(f"Erreur : {error}", file=sys.stderr)
            return 2
        print(f"{target}: {'restauré' if result.written else 'à restaurer'}")
        if result.diff:
            print(result.diff, end="")

    if not args.yes:
        print("\nMode aperçu. Relance avec --yes pour restaurer.")
    return 0


def cmd_status(args) -> int:
    install = _install(args)
    manager = ConfigManager(install.config_dir)
    info = manager.status(args.target)

    print(f"cible        : {info['target']}")
    print(f"chemin       : {info['path']}")
    print(f"existe       : {'oui' if info['exists'] else 'non'}")
    print(f"sauvegarde   : {info['original_backup'] or 'aucune'}")
    print(f"modifié      : {'oui' if info['modified'] else 'non'}")
    if info["snapshots"]:
        print("snapshots    :")
        for snapshot in info["snapshots"]:
            print(f"  {snapshot}")
    return 0


def cmd_net(args) -> int:
    info = network.diagnostics(port=args.port, include_public=args.public)

    print("Réseau MotoGP 19")
    print(f"  machine       : {info['hostname']}")
    print(f"  IP locale     : {info['local_ip']}")
    if info["public_ip"]:
        print(f"  IP publique   : {info['public_ip']}")
    elif args.public:
        print("  IP publique   : indisponible")
    print(f"  endpoint      : {info['endpoint']}")
    print(f"  UDP {info['port']:<9} : {'occupé' if info['udp_bound'] else 'libre'}")

    for listener in info["listeners"]:
        process = listener["process"] or "?"
        print(f"    pid {listener['pid']:<6} {process} {listener['address']}:{listener['port']}")

    print(f"  pare-feu      : {'règle présente' if info['firewall_exists'] else 'règle absente'}")
    print(f"  règle         : {info['firewall_rule']}")
    if not info["firewall_exists"]:
        print("  -> python -m mgp19 firewall --yes   (terminal administrateur)")
    return 0


def cmd_firewall(args) -> int:
    port_end = network.DEFAULT_PORT_END if args.range else None
    result = network.ensure_firewall_rule(
        port=args.port,
        port_end=port_end,
        dry_run=not args.yes,
    )

    print(f"règle      : {result.name}")
    print(f"existe     : {'oui' if result.exists else 'non'}")
    print(f"admin      : {'oui' if result.is_admin else 'non'}")

    if result.added:
        print("ajoutée    : oui")
    elif result.exists:
        print("ajout      : inutile")
    elif result.needs_admin:
        print("ajout      : refusé (terminal administrateur requis)")
    elif not args.yes:
        print("ajout      : aperçu")

    if not result.exists and not result.added:
        print("commande   :")
        print(f"  {result.command_text}")
        if not result.is_admin:
            print("  -> relance dans un terminal administrateur avec --yes")

    if result.output:
        print(result.output)
    return 0


def _print_plan(install, plan, *, yes: bool) -> bool:
    steam_exe = launcher.find_steam_exe()
    if steam_exe is None:
        print("steam.exe introuvable. Steam est-il installé ?", file=sys.stderr)
        return False

    command = launcher.steam_command(steam_exe, plan)
    print("Plan de lancement")
    print(f"  mode          : {plan.mode}")
    print(f"  profil        : {plan.profile}")

    if plan.mode == "host":
        print(f"  map           : {plan.map_url}")
        print(f"  port          : {plan.port}")
        endpoint = network.format_endpoint(network.local_ip(), plan.port)
        print(f"  endpoint      : {endpoint}")
    else:
        print(f"  endpoint      : {plan.endpoint}")

    print(f"  restauration  : {'oui' if plan.restore_after else 'non'}")
    print(f"  commande      : {launcher.command_text(command)}")

    if not yes:
        print("\nMode aperçu. Relance avec --yes pour lancer.")
    return True


def _print_session(info: launcher.SessionInfo) -> None:
    print(f"\nSession       : {info.directory}")
    print(f"Jeu démarré   : {'oui' if info.game_started else 'non'}")
    print(f"Jeu terminé   : {'oui' if info.game_exited else 'non'}")
    print(f"Durée         : {info.duration_s} s")
    for note in info.notes:
        print(f"  - {note}")


def cmd_host(args) -> int:
    install = _install(args)
    profiles = _load_profiles()
    profile = profiles.get(args.profile)
    if profile is None:
        print(f"Profil inconnu : {args.profile}", file=sys.stderr)
        return 2

    map_url = args.map or launcher.default_map(args.track)
    if "?" not in map_url:
        map_url += "?listen"

    plan = launcher.LaunchPlan(
        mode="host",
        map_url=map_url,
        port=args.port,
        profile=args.profile,
        restore_after=not args.no_restore,
        extra_args=args.extra_arg,
    )

    if not _print_plan(install, plan, yes=args.yes):
        return 2
    if not args.yes:
        return 0

    try:
        info = launcher.run_session(install, plan, profile, start_timeout=args.timeout)
    except RuntimeError as error:
        print(f"Erreur : {error}", file=sys.stderr)
        return 2

    _print_session(info)
    return 0


def cmd_join(args) -> int:
    install = _install(args)
    profiles = _load_profiles()
    profile = profiles.get(args.profile)
    if profile is None:
        print(f"Profil inconnu : {args.profile}", file=sys.stderr)
        return 2

    try:
        host, port = network.parse_endpoint(args.endpoint, default_port=args.port)
    except ValueError as error:
        print(f"Endpoint invalide : {error}", file=sys.stderr)
        return 2

    plan = launcher.LaunchPlan(
        mode="join",
        endpoint=network.format_endpoint(host, port),
        port=port,
        profile=args.profile,
        restore_after=not args.no_restore,
        extra_args=args.extra_arg,
    )

    if not _print_plan(install, plan, yes=args.yes):
        return 2
    if not args.yes:
        return 0

    try:
        info = launcher.run_session(install, plan, profile, start_timeout=args.timeout)
    except RuntimeError as error:
        print(f"Erreur : {error}", file=sys.stderr)
        return 2

    _print_session(info)
    return 0


def cmd_sessions(args) -> int:
    sessions = launcher.list_sessions()
    if not sessions:
        print("Aucune session enregistrée.")
        return 0

    for data in sessions:
        print(
            f"{data.get('id', '?'):<24} {data.get('mode', '?'):<5} "
            f"{data.get('started_at', '?')} "
            f"active={data.get('active')} duration={data.get('duration_s')}"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mgp19",
        description="Outils MotoGP 19 Community Host",
    )
    parser.add_argument(
        "--game-path",
        help="dossier d'installation du jeu (sinon détection Steam)",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="diagnostic de l'installation")
    doctor.set_defaults(func=cmd_doctor)

    profiles = sub.add_parser("profiles", help="lister les profils")
    profiles.set_defaults(func=cmd_profiles)

    apply = sub.add_parser("apply", help="appliquer un profil de config")
    apply.add_argument("profile")
    apply.add_argument(
        "--yes",
        action="store_true",
        help="écrire réellement (sinon simple aperçu)",
    )
    apply.set_defaults(func=cmd_apply)

    restore = sub.add_parser("restore", help="restaurer la config d'origine")
    restore.add_argument("targets", nargs="*")
    restore.add_argument(
        "--yes",
        action="store_true",
        help="écrire réellement (sinon simple aperçu)",
    )
    restore.set_defaults(func=cmd_restore)

    status = sub.add_parser("status", help="état de la config")
    status.add_argument("--target", default="Engine.ini")
    status.set_defaults(func=cmd_status)

    net = sub.add_parser("net", help="diagnostic réseau")
    net.add_argument("--port", type=int, default=network.DEFAULT_PORT)
    net.add_argument(
        "--public",
        action="store_true",
        help="récupérer aussi l'IP publique (service externe)",
    )
    net.set_defaults(func=cmd_net)

    firewall = sub.add_parser("firewall", help="vérifier / ajouter la règle pare-feu")
    firewall.add_argument("--port", type=int, default=network.DEFAULT_PORT)
    firewall.add_argument(
        "--range",
        action="store_true",
        help="ouvrir la plage 7777-8077 au lieu d'un seul port",
    )
    firewall.add_argument(
        "--yes",
        action="store_true",
        help="ajouter réellement la règle (admin requis)",
    )
    firewall.set_defaults(func=cmd_firewall)

    host = sub.add_parser("host", help="héberger une course locale")
    host.add_argument("--track", default=launcher.DEFAULT_TRACK)
    host.add_argument(
        "--map",
        help="chemin complet de la map (prioritaire sur --track)",
    )
    host.add_argument("--port", type=int, default=network.DEFAULT_PORT)
    host.add_argument("--profile", default="direct-connect")
    host.add_argument(
        "--no-restore",
        action="store_true",
        help="ne pas restaurer la config après la session",
    )
    host.add_argument(
        "--extra-arg",
        action="append",
        default=[],
        metavar="ARG",
        help="argument supplémentaire passé au jeu",
    )
    host.add_argument("--timeout", type=float, default=120.0)
    host.add_argument(
        "--yes",
        action="store_true",
        help="lancer réellement (sinon simple aperçu)",
    )
    host.set_defaults(func=cmd_host)

    join = sub.add_parser("join", help="rejoindre une course par IP")
    join.add_argument("endpoint")
    join.add_argument("--port", type=int, default=network.DEFAULT_PORT)
    join.add_argument("--profile", default="direct-connect")
    join.add_argument(
        "--no-restore",
        action="store_true",
        help="ne pas restaurer la config après la session",
    )
    join.add_argument(
        "--extra-arg",
        action="append",
        default=[],
        metavar="ARG",
        help="argument supplémentaire passé au jeu",
    )
    join.add_argument("--timeout", type=float, default=120.0)
    join.add_argument(
        "--yes",
        action="store_true",
        help="lancer réellement (sinon simple aperçu)",
    )
    join.set_defaults(func=cmd_join)

    sessions = sub.add_parser("sessions", help="lister les sessions enregistrées")
    sessions.set_defaults(func=cmd_sessions)

    return parser


def _configure_stdio() -> None:
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            ctypes.windll.kernel32.SetConsoleCP(65001)
        except (AttributeError, OSError):
            pass
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))
