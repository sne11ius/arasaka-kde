import configparser
import json
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
                "WindowDragPolicy=1\nIgnoreWindowClasses=custom-app\n"
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
                "IgnoreWindowClasses": "custom-app",
            }
            for key, value in expected.items():
                with self.subTest(key=key):
                    self.assertEqual(config["Script-polonium"].get(key), value)
            self.assertEqual(dict(config["Plugins"]), {"unrelatedEnabled": "true"})
            self.assertEqual(dict(config["MouseBindings"]), {"CommandAllKey": "Meta"})

    def test_reapply_disables_both_outlines_without_changing_other_decoration_settings(self):
        with tempfile.TemporaryDirectory(prefix="arasaka-outline-test-") as temp:
            home = Path(temp)
            config_path = home / "config/klassy/klassyrc"
            config_path.parent.mkdir(parents=True)
            config_path.write_text(
                "[WindowOutlineStyle]\nWindowOutlineStyleActive=WindowOutlineCustomColor\n"
                "WindowOutlineStyleInactive=WindowOutlineContrast\nWindowOutlineThickness=2\n"
                "[Windeco]\nWindowCornerRadius=3\n"
                "[TitleBarOpacity]\nActiveTitleBarOpacity=92\n"
            )
            tools = home / "tools"
            tools.mkdir()
            (tools / "kwriteconfig6").symlink_to(shutil.which("kwriteconfig6"))
            script = (ROOT / "bin/apply-live").read_text()
            section = "\n".join(
                line for line in script.splitlines()
                if line.startswith("kwriteconfig6 --file klassy/klassyrc --group WindowOutlineStyle ")
            )
            for _ in range(2):
                result = subprocess.run(
                    [shutil.which("bash"), "-eu", "-c", section],
                    env={"HOME": temp, "XDG_CONFIG_HOME": str(home / "config"),
                         "XDG_CACHE_HOME": str(home / "cache"), "PATH": str(tools),
                         "DBUS_SESSION_BUS_ADDRESS": "unix:path=/nonexistent-test-bus"},
                    text=True, capture_output=True, timeout=10,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
            config = configparser.ConfigParser()
            config.optionxform = str
            config.read(config_path)
            for state in ("Active", "Inactive"):
                with self.subTest(state=state):
                    self.assertEqual(config["WindowOutlineStyle"][f"WindowOutlineStyle{state}"],
                                     "WindowOutlineNone")
            self.assertEqual(config["WindowOutlineStyle"]["WindowOutlineThickness"], "2")
            self.assertEqual(dict(config["Windeco"]), {"WindowCornerRadius": "3"})
            self.assertEqual(dict(config["TitleBarOpacity"]), {"ActiveTitleBarOpacity": "92"})

    def test_generated_padding_script_updates_every_screen_to_eight(self):
        with tempfile.TemporaryDirectory(prefix="arasaka-padding-test-") as temp:
            padding_script = Path(temp) / "padding.js"
            script = (ROOT / "bin/apply-live").read_text()
            section = script.split("tile_padding_script=$(mktemp)\n", 1)[1].split("\nqdbus6 ", 1)[0]
            result = subprocess.run(
                [shutil.which("bash"), "-eu", "-c", section],
                env={"tile_padding_script": str(padding_script)},
                text=True, capture_output=True, timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            # Only KWin's external workspace API is simulated; execute the emitted JavaScript.
            result = subprocess.run(["node", "-e", """
                const fs = require('fs'), vm = require('vm');
                const screens = [{name: 'eDP-1'}, {name: 'DP-2'}, {name: 'HDMI-A-1'}];
                const managers = screens.map((screen, i) => ({rootTile: {padding: 4 + i * 2}}));
                const workspace = {screens, tilingForScreen: screen => managers[screens.indexOf(screen)]};
                const code = fs.readFileSync(process.argv[1], 'utf8');
                vm.runInNewContext(code, {workspace});
                vm.runInNewContext(code, {workspace});
                console.log(JSON.stringify(managers.map(manager => manager.rootTile.padding)));
            """, str(padding_script)], text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), [8, 8, 8])


if __name__ == "__main__":
    unittest.main()
