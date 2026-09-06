#!/usr/bin/env python3

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


class SystemdUnitsTest(unittest.TestCase):
    def test_units_use_portable_home_paths(self):
        service = (
            REPO_ROOT / "systemd" / "arasaka-display-reconcile.service"
        ).read_text(encoding="utf-8")
        path_unit = (
            REPO_ROOT / "systemd" / "arasaka-display-reconcile.path"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "ExecStart=%h/.local/libexec/arasaka-kde/reconcile-displays", service
        )
        self.assertIn("PathChanged=%h/.config/kwinoutputconfig.json", path_unit)
        self.assertNotIn(str(REPO_ROOT), service + path_unit)
        self.assertNotIn("/home/cwichering", service + path_unit)

    def test_reconciler_runs_from_deployed_libexec_layout(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "home"
            libexec = home / ".local" / "libexec" / "arasaka-kde"
            libexec.mkdir(parents=True)
            shutil.copy2(REPO_ROOT / "bin" / "reconcile-displays", libexec)
            shutil.copy2(REPO_ROOT / "lib" / "arasaka_topology.py", libexec)

            environment = os.environ.copy()
            environment["HOME"] = str(home)
            environment.pop("XDG_STATE_HOME", None)
            completed = subprocess.run(
                [
                    str(libexec / "reconcile-displays"),
                    "--dry-run",
                    "--json",
                    str(
                        REPO_ROOT
                        / "tests"
                        / "fixtures"
                        / "topology"
                        / "external-only.json"
                    ),
                ],
                check=True,
                capture_output=True,
                env=environment,
                text=True,
            )
            self.assertIn('"primary":"HDMI-A-1"', completed.stdout)


if __name__ == "__main__":
    unittest.main()
