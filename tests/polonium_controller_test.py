"""Run controller regressions against our adaptation of the pinned upstream code."""
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
from arasaka_polonium import adapt


def main():
    archive = subprocess.check_output([str(ROOT / "bin/fetch-components"), "polonium"], text=True).strip()
    with tempfile.TemporaryDirectory(prefix="polonium-controller-") as directory:
        package = Path(directory) / "pkg"
        with zipfile.ZipFile(archive) as upstream:
            upstream.extractall(directory)
        adapt(package)
        return subprocess.run(["node", str(ROOT / "tests/polonium_controller_test.cjs"),
                               str(package / "contents/code/main.mjs")]).returncode


if __name__ == "__main__":
    sys.exit(main())
