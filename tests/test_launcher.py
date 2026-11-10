import json
import tempfile
import unittest
from pathlib import Path

from mgp19 import launcher
from mgp19.config import ConfigManager


class LaunchPlanTests(unittest.TestCase):
    def test_default_map(self):
        self.assertEqual(
            launcher.default_map("mugello"),
            "/Game/maps/Tracks/mugello/mugello",
        )

    def test_host_args(self):
        plan = launcher.LaunchPlan(
            mode="host",
            map_url="/Game/maps/Tracks/mugello/mugello?listen",
            port=7777,
        )
        args = plan.game_args()
        self.assertEqual(args[0], "/Game/maps/Tracks/mugello/mugello?listen")
        self.assertIn("-port=7777", args)
        self.assertIn("-nosteam", args)
        self.assertIn("-log", args)

    def test_join_args(self):
        plan = launcher.LaunchPlan(mode="join", endpoint="192.168.0.42:7777")
        args = plan.game_args()
        self.assertEqual(args[0], "192.168.0.42:7777")
        self.assertIn("-nosteam", args)

    def test_join_without_endpoint_fails(self):
        plan = launcher.LaunchPlan(mode="join")
        with self.assertRaises(ValueError):
            plan.game_args()

    def test_steam_command(self):
        plan = launcher.LaunchPlan(mode="join", endpoint="192.168.0.42:7777")
        command = launcher.steam_command(Path("C:/Steam/steam.exe"), plan)
        self.assertEqual(command[0], "C:\\Steam\\steam.exe")
        self.assertEqual(command[1:3], ["-applaunch", "984780"])
        self.assertEqual(command[3], "192.168.0.42:7777")


class SessionTests(unittest.TestCase):
    def test_recorder_writes_session_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            plan = launcher.LaunchPlan(mode="join", endpoint="192.168.0.42:7777")
            info = launcher.SessionInfo(
                id="test",
                directory=directory,
                plan=plan,
                steam_command=["steam.exe", "-applaunch", "984780"],
                started_at="2026-11-10T19:00:00",
            )
            recorder = launcher.SessionRecorder(info)
            recorder.write()
            recorder.note("note de test")

            data = json.loads((directory / "session.json").read_text(encoding="utf-8"))
            self.assertEqual(data["id"], "test")
            self.assertEqual(data["mode"], "join")
            self.assertIn("note de test", data["notes"])

    def test_recover_previous_sessions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_dir = root / "config"
            config_dir.mkdir()
            target = config_dir / "Engine.ini"
            target.write_text("[A]\nx=1\n", encoding="utf-8")

            manager = ConfigManager(config_dir, check_running=False)
            manager.ensure_original("Engine.ini")
            target.write_text("[A]\nx=2\n", encoding="utf-8")

            sessions_dir = root / "sessions"
            session_dir = sessions_dir / "20261110-190000-join"
            session_dir.mkdir(parents=True)
            (session_dir / "session.json").write_text(
                json.dumps({"id": "x", "active": True, "restore_after": True, "notes": []}),
                encoding="utf-8",
            )

            recovered = launcher.recover_previous_sessions(manager, sessions_dir)

            self.assertEqual(len(recovered), 1)
            self.assertIn("x=1", target.read_text(encoding="utf-8"))
            data = json.loads((session_dir / "session.json").read_text(encoding="utf-8"))
            self.assertFalse(data["active"])

    def test_list_sessions(self):
        with tempfile.TemporaryDirectory() as tmp:
            sessions_dir = Path(tmp)
            session_dir = sessions_dir / "a"
            session_dir.mkdir()
            (session_dir / "session.json").write_text(
                json.dumps({"id": "a", "mode": "host"}),
                encoding="utf-8",
            )
            self.assertEqual(len(launcher.list_sessions(sessions_dir)), 1)


if __name__ == "__main__":
    unittest.main()
