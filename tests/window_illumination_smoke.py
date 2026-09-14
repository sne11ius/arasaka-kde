"""Run the real window-count model inside a disposable two-output Wayland session.

Usage: python3 tests/window_illumination_smoke.py build/rain-host-tests/window_count_test [--per-output-desktops]
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


def main():
    if sys.argv[1] == "--session":
        subprocess.Popen(["/usr/lib/x86_64-linux-gnu/libexec/kactivitymanagerd"],
                         env=dict(os.environ, QT_QPA_PLATFORM="offscreen"))
        for _ in range(100):
            ready = subprocess.run(["qdbus6", "org.kde.ActivityManager", "/ActivityManager/Activities",
                                    "org.kde.ActivityManager.Activities.CurrentActivity"],
                                   text=True, capture_output=True)
            if ready.returncode == 0 and len(ready.stdout.strip()) == 36:
                break
            time.sleep(.1)
        else:
            raise RuntimeError("Private activity manager did not start")
        os.execvp("kwin_wayland", ["kwin_wayland", "--virtual", "--output-count", "2",
            "--width", "1280", "--height", "900", "--scale", "1", "--socket", "illumination-test",
            "--no-lockscreen", "--exit-with-session", sys.argv[2]])

    binary = Path(sys.argv[1]).resolve()
    if not binary.is_file():
        raise ValueError(f"Build the full wallpaper-host tests first: {binary}")
    run = Path(tempfile.mkdtemp(prefix="window-illumination-", dir="/tmp/opencode"))
    for name in ("home", "config", "data", "runtime", "state", "cache", "config-dirs"):
        (run / name).mkdir()
    (run / "runtime").chmod(0o700)
    per_output = "--per-output-desktops" in sys.argv[2:]
    (run / "config/kwinrc").write_text("[Desktops]\nNumber=2\nRows=1\n"
        f"[Windows]\nPerOutputVirtualDesktops={'true' if per_output else 'false'}\n")
    (run / "session.conf").write_text(f'''<busconfig><type>session</type>
        <listen>unix:tmpdir={run}/runtime</listen><auth>EXTERNAL</auth>
        <policy context="default"><allow send_destination="*"/>
        <allow receive_sender="*"/><allow own="*"/></policy></busconfig>''')
    env = dict(PATH="/usr/bin:/bin", LANG="C.UTF-8", HOME=str(run / "home"),
               XDG_CONFIG_HOME=str(run / "config"), XDG_CONFIG_DIRS=str(run / "config-dirs"),
               XDG_DATA_HOME=str(run / "data"), XDG_DATA_DIRS="/usr/share",
               XDG_STATE_HOME=str(run / "state"), XDG_CACHE_HOME=str(run / "cache"),
               XDG_RUNTIME_DIR=str(run / "runtime"), KWIN_COMPOSE="Q", QT_QUICK_BACKEND="software",
               QT_QPA_PLATFORM="wayland", WAYLAND_DISPLAY="illumination-test",
               LIBGL_ALWAYS_SOFTWARE="1", ARASAKA_WINDOW_COUNT_TEST="1",
               ARASAKA_PER_OUTPUT_DESKTOPS="1" if per_output else "0",
               KWIN_WAYLAND_NO_PERMISSION_CHECKS="1",
               DBUS_SYSTEM_BUS_ADDRESS="unix:path=/nonexistent-illumination-system-bus")
    log_path = run / "kwin.log"
    print(f"ARTIFACTS={run}", flush=True)
    with log_path.open("w") as log:
        result = subprocess.run(["dbus-run-session", "--config-file", str(run / "session.conf"), "--",
            sys.executable, str(Path(__file__).resolve()), "--session", str(binary)],
            env=env, cwd=run / "home", stdout=log, stderr=subprocess.STDOUT, timeout=90)
    text = log_path.read_text()
    for line in text.splitlines():
        if line.startswith(("PASS", "FAIL", "Totals:")):
            print(line)
    # KWin's exit code alone does not report the exit-with-session client's assertions.
    return 0 if "Totals: 5 passed, 0 failed" in text and result.returncode == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
