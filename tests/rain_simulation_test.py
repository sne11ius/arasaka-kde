#!/usr/bin/env python3

import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RainSimulationTest(unittest.TestCase):
    def test_standalone_cpp_simulation(self):
        for tool in ("cmake", "ctest"):
            if not shutil.which(tool):
                self.skipTest(f"Rain physics tests require {tool}")
        compiler = shlex.split(os.environ.get("CXX", "c++"))
        if not compiler or not shutil.which(compiler[0]):
            self.skipTest("Rain physics tests require a C++20 compiler (set CXX)")
        if not (shutil.which("ninja") or shutil.which("make")):
            self.skipTest("Rain physics tests require Ninja or Make")

        with tempfile.TemporaryDirectory(prefix="arasaka-rain-physics-") as build:
            commands = [
                ["cmake", "-S", str(ROOT / "native/rain/tests"), "-B", build,
                 "-DCMAKE_BUILD_TYPE=Release", "-G",
                 "Ninja" if shutil.which("ninja") else "Unix Makefiles"],
                ["cmake", "--build", build, "--parallel", "2"],
                ["ctest", "--test-dir", build, "--output-on-failure"],
            ]
            for command in commands:
                completed = subprocess.run(command, capture_output=True, text=True, timeout=180)
                self.assertEqual(completed.returncode, 0,
                                 f"{' '.join(command)}\n{completed.stdout}\n{completed.stderr}")


if __name__ == "__main__":
    unittest.main()
