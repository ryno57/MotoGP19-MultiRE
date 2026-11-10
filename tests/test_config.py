import tempfile
import unittest
from pathlib import Path

from mgp19.config import ConfigManager, IniDocument, Operation, Profile


class IniDocumentTests(unittest.TestCase):
    def test_set_preserves_comments_and_other_sections(self):
        text = (
            "; commentaire\r\n"
            "[A]\r\n"
            "foo=1\r\n"
            "\r\n"
            "[B]\r\n"
            "bar=2\r\n"
        )
        document = IniDocument(text)
        document.set("A", "foo", "3")
        document.set("A", "new", "x")
        output = document.to_text()

        self.assertIn("; commentaire\r\n", output)
        self.assertIn("foo=3\r\n", output)
        self.assertIn("new=x\r\n", output)
        self.assertIn("[B]\r\nbar=2\r\n", output)

    def test_append_and_clear_array(self):
        document = IniDocument("[S]\nvalue=1\n")
        document.clear_array("S", "arr")
        document.append("S", "arr", "(x=1)")
        output = document.to_text()

        self.assertIn("!arr=ClearArray\n", output)
        self.assertIn("+arr=(x=1)\n", output)

    def test_remove(self):
        document = IniDocument("[S]\nvalue=1\nother=2\n")
        document.remove("S", "value")
        output = document.to_text()

        self.assertNotIn("value=1", output)
        self.assertIn("other=2", output)

    def test_creates_missing_section(self):
        document = IniDocument("[A]\nx=1\n")
        document.set("B", "y", "2")
        output = document.to_text()

        self.assertIn("[B]\ny=2\n", output)

    def test_duplicate_keys_collapse(self):
        document = IniDocument("[S]\nvalue=1\nvalue=2\n")
        document.set("S", "value", "3")
        output = document.to_text()

        self.assertEqual(output.count("value="), 1)
        self.assertIn("value=3", output)

    def test_key_matching_is_case_insensitive(self):
        document = IniDocument("[S]\nFoo=1\n")
        document.set("s", "foo", "2")
        output = document.to_text()

        self.assertIn("foo=2", output)
        self.assertNotIn("Foo=1", output)


class ConfigManagerTests(unittest.TestCase):
    def _profile(self):
        return Profile(
            name="test",
            description="",
            targets=("Engine.ini",),
            operations=(Operation(section="A", key="x", mode="set", value="2"),),
        )

    def test_apply_and_restore(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp)
            target = config_dir / "Engine.ini"
            target.write_text("[A]\nx=1\n", encoding="utf-8")

            manager = ConfigManager(config_dir, check_running=False)
            result = manager.apply_profile(self._profile(), dry_run=False)[0]

            self.assertTrue(result.written)
            self.assertIn("x=2", target.read_text(encoding="utf-8"))
            self.assertTrue(manager.original_backup("Engine.ini").exists())

            manager.restore("Engine.ini", dry_run=False)
            self.assertIn("x=1", target.read_text(encoding="utf-8"))

    def test_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp)
            target = config_dir / "Engine.ini"
            target.write_text("[A]\nx=1\n", encoding="utf-8")

            manager = ConfigManager(config_dir, check_running=False)
            result = manager.apply_profile(self._profile(), dry_run=True)[0]

            self.assertTrue(result.changed)
            self.assertFalse(result.written)
            self.assertIn("x=1", target.read_text(encoding="utf-8"))

    def test_apply_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp)
            target = config_dir / "Engine.ini"
            target.write_text("[A]\nx=1\n", encoding="utf-8")

            manager = ConfigManager(config_dir, check_running=False)
            manager.apply_profile(self._profile(), dry_run=False)
            second = manager.apply_profile(self._profile(), dry_run=False)[0]

            self.assertFalse(second.changed)
            self.assertFalse(second.written)


if __name__ == "__main__":
    unittest.main()
