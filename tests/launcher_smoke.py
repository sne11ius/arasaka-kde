#!/usr/bin/env python3
"""Opt-in real Plasma/QML integration test; never changes the live layout."""

import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix="arasaka-launcher-") as temporary:
        base = Path(temporary)
        package = base / "package"
        shutil.copytree(ROOT / "plasma/applets/com.arasaka.launcher", package)
        main_qml = package / "contents/ui/main.qml"
        source = main_qml.read_text()
        if "--trace" in sys.argv:
            source = source.replace("function close() {", "function close() { console.log('CLOSE', new Error().stack);")
        # Plasma requires ContainmentItem directly at the package root. Inject a
        # test-only Loader rather than subclassing it and losing AppletContext.
        source = source.rstrip()[:-1] + '''
    Loader {
        source: "%s"
        onLoaded: item.host = root
    }
}
''' % (ROOT / "tests/launcher_checks.qml").as_uri()
        main_qml.write_text(source)
        env = dict(os.environ)
        for key, directory in (("XDG_CONFIG_HOME", "config"),
                               ("XDG_CACHE_HOME", "cache"),
                               ("XDG_DATA_HOME", "data")):
            (base / directory).mkdir()
            env[key] = str(base / directory)
        applications = base / "data/applications"
        applications.mkdir()
        for name in ("Alpha", "Beta"):
            (applications / f"arasaka-search-{name.lower()}.desktop").write_text(
                "[Desktop Entry]\nType=Application\n"
                f"Name=ArasakaSearchFixture {name}\n"
                f"Exec=/usr/bin/touch {base / name}\n"
                "Icon=application-x-executable\nCategories=Utility;\n"
            )
        (applications / "arasaka-cancelled.desktop").write_text(
            "[Desktop Entry]\nType=Application\nName=ArasakaCancelledFixture\n"
            f"Exec=/usr/bin/touch {base / 'Cancelled'}\n"
            "Icon=application-x-executable\nCategories=Utility;\n"
        )
        for number in range(8):
            (applications / f"arasaka-scroll-{number}.desktop").write_text(
                "[Desktop Entry]\nType=Application\n"
                f"Name=ArasakaScrollFixture {number}\n"
                f"Exec=/usr/bin/touch {base / f'Scroll{number}'}\n"
                "Icon=application-x-executable\nCategories=Utility;\n"
            )
        subprocess.run(["kbuildsycoca6", "--noincremental"], env=env,
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        # Klipper requires a real window system and crashes with Qt's offscreen plugin.
        env.setdefault("QT_QPA_PLATFORM", "wayland")
        bus_config = base / "bus.conf"
        bus_config.write_text('''<busconfig>
  <type>session</type><listen>unix:tmpdir=/tmp</listen>
  <policy context="default">
    <allow send_destination="*"/><allow receive_sender="*"/><allow own="*"/>
  </policy>
</busconfig>''')
        command = ["plasmawindowed", str(package)]
        if "--gdb" in sys.argv:
            command = ["gdb", "--batch", "-ex", "run", "-ex", "bt", "--args"] + command
        log = base / "test.log"
        with log.open("w") as output_file:
            process = subprocess.Popen(
                ["dbus-run-session", "--config-file", str(bus_config), "--",
                 *command], env=env,
                stdout=output_file, stderr=subprocess.STDOUT, start_new_session=True,
            )
            try:
                deadline = time.monotonic() + 45
                while process.poll() is None and time.monotonic() < deadline:
                    if "ARASAKA_TEST_FINISHED" in log.read_text():
                        break
                    time.sleep(0.1)
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=5)
        output = log.read_text()
        if (base / "Cancelled").exists():
            raise SystemExit("FAIL: pending search launched an application after dismissal")
        if "ARASAKA_TEST_FINISHED" not in output or "ARASAKA_TEST_FAILURES 0" not in output:
            print(output)
            raise SystemExit("FAIL: native launcher integration")
        selection = re.search(r"ARASAKA_SCROLL_SELECTION ArasakaScrollFixture ([0-7])", output)
        if not selection:
            raise SystemExit("FAIL: missing keyboard scroll selection")
        for name in ("Alpha", "Beta", "Scroll6", f"Scroll{selection[1]}"):
            if not (base / name).exists():
                print(output)
                raise SystemExit(f"FAIL: application search did not launch {name}")
        if "--trace" in sys.argv or "--gdb" in sys.argv:
            print(output)
        print("Native launcher integration: PASS (Wayland, isolated settings and session bus)")


if __name__ == "__main__":
    main()
