#!/usr/bin/env python3

import json
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LAYOUT = REPO_ROOT / "plasma" / "layout.js"
HARNESS = Path(__file__).with_name("plasma_layout_harness.js")


class PlasmaLayoutTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        completed = subprocess.run(
            ["node", str(HARNESS), str(LAYOUT)],
            check=True,
            capture_output=True,
            text=True,
        )
        cls.model = json.loads(completed.stdout)
        cls.source = LAYOUT.read_text(encoding="utf-8")

    def test_first_and_later_runs_remove_only_managed_panels(self):
        for run in ("first", "second"):
            panels = self.model[run]["panels"]
            user_panels = [panel for panel in panels if panel["role"] == "user-panel"]
            self.assertEqual(1, len(user_panels), f"{run} run must preserve user panels")
            self.assertEqual(1, user_panels[0]["id"])
            self.assertNotIn(
                "obsolete-arasaka-panel", [panel["role"] for panel in panels]
            )

    def test_panel_roles_converge_without_task_dock(self):
        expected_roles = {
            "command-strip": (0, "top"),
            "telemetry-rail": (1, "right"),
        }
        for run in ("first", "second"):
            managed = {
                panel["role"]: panel
                for panel in self.model[run]["panels"]
                if panel["managed"]
            }
            self.assertEqual(set(expected_roles), set(managed))
            for role, (screen, location) in expected_roles.items():
                self.assertEqual(screen, managed[role]["screen"])
                self.assertEqual(location, managed[role]["location"])
            self.assertIn(
                "com.github.antroids.application-title-bar",
                managed["command-strip"]["widgets"],
            )
            self.assertIn(
                "luisbocanegra.audio.visualizer",
                managed["telemetry-rail"]["widgets"],
            )
            self.assertNotIn(
                "org.kde.plasma.icontasks", managed["telemetry-rail"]["widgets"]
            )
            self.assertNotIn(
                "org.kde.plasma.systemtray", managed["telemetry-rail"]["widgets"]
            )
            self.assertFalse(
                any(
                    "org.kde.plasma.icontasks" in panel["widgets"]
                    for panel in managed.values()
                )
            )
            tray_count = sum(
                panel["widgets"].count("org.kde.plasma.systemtray")
                for panel in managed.values()
            )
            self.assertEqual(1, tray_count)

    def test_layout_policy_has_no_destructive_migration_or_pager(self):
        self.assertNotIn("__MIGRATE_ALL__", self.source)
        self.assertNotIn("migrateAllPanels", self.source)
        self.assertNotIn("org.kde.plasma.pager", self.source)
        self.assertEqual(1, self.model["first"]["desktopCount"])
        self.assertEqual(1, self.model["second"]["desktopCount"])

        apply_source = (REPO_ROOT / "bin" / "apply-live").read_text(encoding="utf-8")
        self.assertIn("--group Desktops --key Number 1", apply_source)


if __name__ == "__main__":
    unittest.main()
