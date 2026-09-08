import configparser
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("kwriteconfig6"), "requires KDE KConfig tools")
class ApplyLiveTest(unittest.TestCase):
    def test_reapply_selects_right_first_balanced_tree_and_drag_to_float(self):
        with tempfile.TemporaryDirectory(prefix="arasaka-tiling-test-") as temp:
            home = Path(temp)
            config_dir = home / "config"
            config_dir.mkdir()
            config_path = config_dir / "kwinrc"
            config_path.write_text(
                "[Plugins]\nunrelatedEnabled=true\n"
                "[MouseBindings]\nCommandAllKey=Meta\n"
                "[Script-polonium]\nDefaultEngine=2\n"
                "BTreeInsertionStyle=1\nBTreeSwapInsertSide=false\n"
                "BTreeRotateLayout=true\nBTreeInsertInActive=true\n"
                "WindowDragPolicy=1\n"
            )
            tools = home / "tools"
            tools.mkdir()
            (tools / "kwriteconfig6").symlink_to(shutil.which("kwriteconfig6"))
            # Exercise only the tiling writes, never the full desktop installer.
            script = (ROOT / "bin/apply-live").read_text()
            section = "\n".join(
                line for line in script.splitlines()
                if line.startswith("kwriteconfig6 --file kwinrc --group Script-polonium ")
            )
            result = subprocess.run(
                [shutil.which("bash"), "-eu", "-c", section],
                env={"HOME": temp, "XDG_CONFIG_HOME": str(config_dir),
                     "XDG_CACHE_HOME": str(home / "cache"), "PATH": str(tools),
                     "DBUS_SESSION_BUS_ADDRESS": "unix:path=/nonexistent-test-bus"},
                text=True, capture_output=True, timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            config = configparser.ConfigParser()
            config.optionxform = str
            config.read(config_path)
            expected = {
                "DefaultEngine": "0", "BTreeInsertionStyle": "0",
                "BTreeSwapInsertSide": "true", "BTreeRotateLayout": "false",
                "BTreeInsertInActive": "false", "WindowDragPolicy": "2",
                "Borders": "4",
                "IgnoreWindowClasses": "krunner, yakuake, kded, polkit, plasmashell, xwaylandvideobridge",
            }
            for key, value in expected.items():
                with self.subTest(key=key):
                    self.assertEqual(config["Script-polonium"].get(key), value)
            self.assertEqual(dict(config["Plugins"]), {"unrelatedEnabled": "true"})
            self.assertEqual(dict(config["MouseBindings"]), {"CommandAllKey": "Meta"})


if __name__ == "__main__":
    unittest.main()
