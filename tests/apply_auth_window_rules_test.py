import configparser
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("kwriteconfig6") and shutil.which("kreadconfig6"),
                     "requires KDE KConfig tools")
class ApplyAuthWindowRulesTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="arasaka-auth-rules-test-")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.config = self.home / "config"
        self.config.mkdir()
        tools = self.home / "tools"
        tools.mkdir()
        # Only the live compositor boundary is stubbed; KConfig reads/writes are real.
        qdbus = tools / "qdbus6"
        qdbus.write_text(
            '#!/bin/sh\n'
            '[ "${KWIN_UNAVAILABLE:-0}" = 0 ] || exit 1\n'
            'case "$*" in\n'
            '  "org.kde.KWin /KWin org.freedesktop.DBus.Peer.Ping") ;;\n'
            '  "org.kde.KWin /KWin org.kde.KWin.reconfigure") ;;\n'
            '  *) exit 2 ;;\n'
            'esac\n'
        )
        qdbus.chmod(0o755)
        self.env = {
            "HOME": str(self.home), "XDG_CONFIG_HOME": str(self.config),
            "XDG_STATE_HOME": str(self.home / "state"),
            "XDG_CACHE_HOME": str(self.home / "cache"),
            "PATH": str(tools) + os.pathsep + os.environ["PATH"],
            "DBUS_SESSION_BUS_ADDRESS": "unix:path=/nonexistent-test-bus",
        }

    def apply(self):
        result = subprocess.run(
            ["bash", str(ROOT / "bin/apply-auth-window-rules")], env=self.env,
            capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def read_config(self, name):
        config = configparser.ConfigParser(interpolation=None)
        config.optionxform = str
        config.read(self.config / name)
        return config

    def test_prompts_are_forced_above_without_matching_other_apps(self):
        self.apply()
        config = self.read_config("kwinrulesrc")
        rule = config["arasaka-auth-prompts"]
        self.assertEqual(config["General"]["rules"], "arasaka-auth-prompts")
        self.assertEqual(config["General"]["count"], "1")
        self.assertEqual(rule["wmclassmatch"], "3")
        self.assertEqual(rule["wmclasscomplete"], "false")
        self.assertEqual(rule["types"], "33")  # Normal or dialog, not panels/popups.
        self.assertEqual(rule["above"], "true")
        self.assertEqual(rule["aboverule"], "2")
        self.assertEqual(rule["below"], "false")
        self.assertEqual(rule["belowrule"], "2")
        for app_id in ("pinentry-qt", "org.gnupg.pinentry-qt", "ksshaskpass", "org.kde.ksshaskpass"):
            with self.subTest(app_id=app_id):
                self.assertRegex(app_id, rule["wmclass"])
        for app_id in ("konsole", "org.kde.konsole", "firefox", "pinentry-qt-editor", "not-ksshaskpass"):
            with self.subTest(app_id=app_id):
                self.assertNotRegex(app_id, rule["wmclass"])
        ignored = self.read_config("kwinrc")["Script-polonium"]["IgnoreWindowClasses"].split(",")
        self.assertEqual({item.strip() for item in ignored}, {
            "krunner", "yakuake", "kded", "polkit", "plasmashell", "xwaylandvideobridge",
            "pinentry-qt", "org.gnupg.pinentry-qt", "ksshaskpass", "org.kde.ksshaskpass",
        })

    def test_reapply_preserves_existing_rules_settings_and_original_backup(self):
        original_rules = (
            "[General]\ncount=2\nrules=personal,arasaka-frame\n"
            "[personal]\nDescription=My rule\nabove=false\naboverule=2\nwmclass=firefox\n"
            "[arasaka-frame]\nnoborder=false\nnoborderrule=2\n"
        )
        original_kwin = (
            "[Windows]\nFocusStealingPreventionLevel=3\n"
            "[Script-polonium]\nIgnoreWindowClasses=custom-app, ksshaskpass\nDefaultEngine=2\n"
            "[Plugins]\npoloniumEnabled=true\n"
        )
        (self.config / "kwinrulesrc").write_text(original_rules)
        (self.config / "kwinrc").write_text(original_kwin)
        self.apply()
        first_rules = (self.config / "kwinrulesrc").read_bytes()
        first_kwin = (self.config / "kwinrc").read_bytes()
        self.apply()
        self.assertEqual((self.config / "kwinrulesrc").read_bytes(), first_rules)
        self.assertEqual((self.config / "kwinrc").read_bytes(), first_kwin)
        rules = self.read_config("kwinrulesrc")
        self.assertEqual(rules["General"]["rules"], "arasaka-auth-prompts,personal,arasaka-frame")
        self.assertEqual(rules["General"]["count"], "3")
        self.assertEqual(dict(rules["personal"]), {
            "Description": "My rule", "above": "false", "aboverule": "2", "wmclass": "firefox",
        })
        self.assertEqual(dict(rules["arasaka-frame"]), {"noborder": "false", "noborderrule": "2"})
        kwin = self.read_config("kwinrc")
        self.assertEqual(dict(kwin["Windows"]), {"FocusStealingPreventionLevel": "3"})
        self.assertEqual(dict(kwin["Plugins"]), {"poloniumEnabled": "true"})
        self.assertEqual(kwin["Script-polonium"]["DefaultEngine"], "2")
        ignored = [item.strip() for item in kwin["Script-polonium"]["IgnoreWindowClasses"].split(",")]
        self.assertIn("custom-app", ignored)
        self.assertEqual(ignored.count("ksshaskpass"), 1)
        backups = list((self.home / "state/arasaka-kde/backups").glob("auth-window-rules-*"))
        self.assertTrue(any((backup / "kwinrulesrc").read_text() == original_rules
                            and (backup / "kwinrc").read_text() == original_kwin for backup in backups))

    def test_preserves_raw_regex_tiling_exclusions(self):
        (self.config / "kwinrc").write_text(
            "[Script-polonium]\nRawRegex=true\nIgnoreWindowClasses=^custom-(one|two)$\n"
        )
        self.apply()
        self.apply()
        group = self.read_config("kwinrc")["Script-polonium"]
        self.assertEqual(group["RawRegex"], "true")
        for app_id in ("custom-one", "custom-two", "pinentry-qt", "org.gnupg.pinentry-qt", "org.kde.ksshaskpass"):
            self.assertIsNotNone(re.search(group["IgnoreWindowClasses"], app_id))
        self.assertIsNone(re.search(group["IgnoreWindowClasses"], "custom-three"))

    def test_full_apply_preserves_custom_tiling_exclusions(self):
        (self.config / "kwinrc").write_text(
            "[Script-polonium]\nRawRegex=true\nIgnoreWindowClasses=^custom-(one|two)$\n"
        )
        # Exercise the full installer's tiling/auth policy without installing a theme.
        section = "\n".join(
            line for line in (ROOT / "bin/apply-live").read_text().splitlines()
            if line.startswith("kwriteconfig6 --file kwinrc --group Script-polonium ")
            or line == '"$repo_root/bin/apply-auth-window-rules"'
        )
        result = subprocess.run(
            ["bash", "-eu", "-c", section], env=dict(self.env, repo_root=str(ROOT)),
            capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        ignored = self.read_config("kwinrc")["Script-polonium"]["IgnoreWindowClasses"]
        self.assertRegex("custom-one", ignored)
        self.assertRegex("org.gnupg.pinentry-qt", ignored)

    def test_unavailable_session_leaves_configuration_untouched(self):
        original = "[General]\nrules=personal\n"
        (self.config / "kwinrulesrc").write_text(original)
        self.env["KWIN_UNAVAILABLE"] = "1"
        result = subprocess.run(
            ["bash", str(ROOT / "bin/apply-auth-window-rules")], env=self.env,
            capture_output=True, text=True, timeout=15,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("KWin session is unavailable", result.stderr)
        self.assertEqual((self.config / "kwinrulesrc").read_text(), original)
        self.assertFalse((self.config / "kwinrc").exists())


if __name__ == "__main__":
    unittest.main()
