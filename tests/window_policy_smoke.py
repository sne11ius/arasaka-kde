"""Opt-in real KWin/Polonium regression test, entirely in a disposable session.

Usage: python3 tests/window_policy_smoke.py /absolute/path/to/polonium/package
The unmodified upstream package is the RED baseline.
"""
import json
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]


def wait_for(fn, description, timeout=12):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = fn()
        if result:
            return result
        time.sleep(0.1)
    raise AssertionError(f"Timed out: {description}")


def child(run):
    assert Path(os.environ["HOME"]) == run / "home"
    assert os.environ["XDG_RUNTIME_DIR"] == str(run / "runtime")
    assert os.environ["DBUS_SESSION_BUS_ADDRESS"].startswith("unix:path=" + str(run))
    env = dict(os.environ, WAYLAND_DISPLAY="policy-test", QT_QPA_PLATFORM="wayland")

    def dbus(*args):
        return subprocess.check_output(["qdbus6", "org.kde.KWin", *args], text=True).strip()

    serial = 0

    def evaluate(code):
        nonlocal serial
        serial += 1
        marker = f"POLICY_PROBE_{serial}:"
        script = run / f"probe-{serial}.js"
        script.write_text(f'print({json.dumps(marker)} + JSON.stringify((function() {{ {code} }})()));')
        ident = dbus("/Scripting", "org.kde.kwin.Scripting.loadScript", str(script), "policy-probe")
        try:
            dbus(f"/Scripting/Script{ident}", "org.kde.kwin.Script.run")
            def result():
                for line in (run / "kwin.log").read_text(errors="replace").splitlines():
                    if marker in line:
                        return [json.loads(line.split(marker, 1)[1])]
            return wait_for(result, "KWin script reply")[0]
        finally:
            dbus("/Scripting", "org.kde.kwin.Scripting.unloadScript", "policy-probe")

    def windows():
        return evaluate("""
            return workspace.windowList().filter(w => w.normalWindow || w.dialog).map(w => ({
                id: String(w.internalId), app: String(w.resourceClass), caption: w.caption,
                pid: w.pid, tile: w.tile !== null, minimized: w.minimized,
                output: w.output.name,
                above: w.keepAbove, noBorder: w.noBorder, move: w.move, resize: w.resize,
                maximized: w.maximizeMode, fullScreen: w.fullScreen,
                tileFrame: w.tile ? w.tile.absoluteGeometry : null,
                frame: w.frameGeometry, client: w.clientGeometry
            }));
        """)

    def window(caption):
        return next((w for w in windows() if w["caption"] == caption), None)

    def action(caption, code):
        return evaluate(f"const w = workspace.windowList().find(w => w.caption === {json.dumps(caption)}); "
                        f"if (!w) throw Error('missing fixture'); {code}; return true;")

    clients = []
    try:
        plugin = json.loads((run / "package-metadata.json").read_text())["KPlugin"]["Id"]
        wait_for(lambda: dbus("/Scripting", "org.kde.kwin.Scripting.isScriptLoaded", plugin) == "true",
                 "Polonium loaded")
        if plugin == "arasaka-polonium":
            manifest = json.loads((run / "data/kwin/scripts" / plugin / "runtime.json").read_text())
            report = json.loads(dbus("/ArasakaWindowPolicy", "org.arasaka.WindowPolicy1.report"))
            assert report["version"] == manifest["version"], report
            assert report["nativeRevision"] == manifest["nativeRevision"], report
        probe_id = dbus("/Scripting", "org.kde.kwin.Scripting.loadDeclarativeScript", str(run / "drag-probe.qml"))
        dbus(f"/Scripting/Script{probe_id}", "org.kde.kwin.Script.run")
        clients.append(subprocess.Popen([str(run / "window-fixture"), str(ROOT / "tests/window_policy_windows.qml")],
                                        env=env, stdout=open(run / "windows.log", "w"), stderr=subprocess.STDOUT))
        wait_for(lambda: all(window(name) for name in ("Policy SSD", "Policy CSD", "Policy Dialog")),
                 "three fixture windows")
        failures = []

        def check(name, fn):
            try:
                fn()
                print("PASS", name, flush=True)
            except AssertionError as error:
                failures.append(name)
                print("FAIL", name, str(error), flush=True)

        def tiled_dialog():
            wait_for(lambda: window("Policy Dialog")["tile"], "dialog tiles", 3)
            dialog = window("Policy Dialog")
            frame, tile = dialog["frame"], dialog["tileFrame"]
            assert frame["x"] >= tile["x"] and frame["y"] >= tile["y"], dialog
            assert frame["x"] + frame["width"] <= tile["x"] + tile["width"] + 1, dialog
            assert frame["y"] + frame["height"] <= tile["y"] + tile["height"] + 1, dialog
        check("dialogs participate in automatic tiling", tiled_dialog)

        def decorations():
            ssd, csd = window("Policy SSD"), window("Policy CSD")
            assert ssd["client"]["y"] > ssd["frame"]["y"], ssd
            assert csd["client"] == csd["frame"], csd
        check("SSD retains controls and CSD has no extra frame", decorations)

        def maximize():
            action("Policy SSD", "w.setMaximize(true, true)")
            wait_for(lambda: window("Policy SSD")["tile"] and window("Policy SSD")["maximized"] == 0,
                     "maximize rejected and tile retained", 3)
        check("maximize cannot escape tiling", maximize)
        action("Policy SSD", "w.setMaximize(false, false)")

        def movement():
            outputs = evaluate("return workspace.screens.map(s => s.name);")
            before = window("Policy SSD")["output"]
            target = next(i for i, name in enumerate(outputs) if name != before)
            assert dbus("/PolicyDragProbe", "org.arasaka.TestDrag.begin", "Policy SSD") == "true"
            time.sleep(0.2)
            assert window("Policy SSD")["move"], "a move must remain interactive for cross-display dragging"
            assert dbus("/PolicyDragProbe", "org.arasaka.TestDrag.step", "Policy SSD", str(target)) == "true"
            time.sleep(0.2)
            assert dbus("/PolicyDragProbe", "org.arasaka.TestDrag.end", "Policy SSD", "false") == "true"
            wait_for(lambda: window("Policy SSD")["output"] == outputs[target] and window("Policy SSD")["tile"],
                     "cross-display drop tiles on destination", 3)
            assert all(window(name)["tile"] for name in ("Policy CSD", "Policy Dialog"))
            # A same-output drop also returns to the tree, rather than floating.
            assert dbus("/PolicyDragProbe", "org.arasaka.TestDrag.begin", "Policy SSD") == "true"
            time.sleep(0.1)
            dbus("/PolicyDragProbe", "org.arasaka.TestDrag.step", "Policy SSD", str(target))
            dbus("/PolicyDragProbe", "org.arasaka.TestDrag.end", "Policy SSD", "false")
            wait_for(lambda: window("Policy SSD")["tile"], "same-output drop retiles")
            # Cancelling a cross-display drag returns to its original output.
            assert dbus("/PolicyDragProbe", "org.arasaka.TestDrag.begin", "Policy SSD") == "true"
            time.sleep(0.1)
            dbus("/PolicyDragProbe", "org.arasaka.TestDrag.step", "Policy SSD", str(outputs.index(before)))
            dbus("/PolicyDragProbe", "org.arasaka.TestDrag.end", "Policy SSD", "true")
            wait_for(lambda: window("Policy SSD")["tile"] and window("Policy SSD")["output"] == outputs[target],
                     "cancelled drag retiles original output")
        check("dragging transfers between displays and retiles on drop or cancel", movement)

        def resizing():
            before = window("Policy CSD")["frame"]
            action("Policy CSD", "workspace.activeWindow = w; workspace.slotWindowResize()")
            wait_for(lambda: not window("Policy CSD")["resize"], "interactive resize cancelled", 3)
            assert window("Policy CSD")["frame"] == before
        check("interactive resizing cannot detach a tile", resizing)

        def fullscreen():
            action("Policy CSD", "w.fullScreen = true")
            wait_for(lambda: not window("Policy CSD")["fullScreen"] and window("Policy CSD")["tile"],
                     "fullscreen cannot bypass forced tiling", 3)
        check("fullscreen cannot escape the layout", fullscreen)

        def detach():
            action("Policy SSD", "w.tile = null")
            wait_for(lambda: window("Policy SSD")["tile"], "detached window reclaimed", 3)
        check("manual untiling is repaired", detach)

        def restore():
            action("Policy CSD", "w.minimized = true")
            wait_for(lambda: window("Policy CSD")["minimized"], "minimize")
            action("Policy CSD", "w.minimized = false")
            wait_for(lambda: window("Policy CSD")["tile"], "restored window tiles")
        check("minimize and restore retile", restore)

        def restore_after_reload():
            action("Policy CSD", "w.minimized = true")
            dbus("/Scripting", "org.kde.kwin.Scripting.unloadScript", plugin)
            dbus("/Scripting", "org.kde.kwin.Scripting.start")
            time.sleep(0.2)
            action("Policy CSD", "w.minimized = false")
            wait_for(lambda: window("Policy CSD")["tile"], "initially minimized window retiles on restore", 3)
        check("windows minimized at reload retile on restore", restore_after_reload)

        def all_activities():
            action("Policy CSD", "w.activities = []")
            time.sleep(0.2)
            wait_for(lambda: window("Policy CSD")["tile"], "all-activities window remains tiled", 3)
        check("windows on all activities are enrolled", all_activities)

        def authentication_prompt():
            prompt = subprocess.Popen(["pinentry-qt"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                      stderr=open(run / "pinentry.log", "w"), env=env, text=True)
            clients.append(prompt)
            prompt.stdin.write("SETTITLE Disposable Policy Confirmation\nSETDESC Window policy test; no credentials.\nCONFIRM --one-button\n")
            prompt.stdin.flush()
            def auth_window():
                return next((w for w in windows() if w["pid"] == prompt.pid), None)
            wait_for(auth_window, "real pinentry confirmation")
            wait_for(lambda: auth_window()["tile"], "fixed-size pinentry tiles", 3)
            prompt.terminate()
            prompt.wait(timeout=5)
        check("real authentication prompt is tiled", authentication_prompt)

        def quake():
            terminal = subprocess.Popen(["konsole", "--separate", "--hide-menubar", "-e", "sleep", "90"],
                                        env=env, stdout=open(run / "konsole.log", "w"), stderr=subprocess.STDOUT)
            clients.append(terminal)
            def terminal_window():
                return next((w for w in windows() if w["pid"] == terminal.pid), None)
            wait_for(terminal_window, "disposable Konsole")
            wait_for(lambda: terminal_window()["tile"], "ordinary Konsole tiles")
            (run / "quake.pid").write_text(str(window("Policy SSD")["pid"]) + "\n")
            time.sleep(0.2)
            assert window("Policy SSD")["tile"], "a non-Konsole PID must never gain the exception"
            (run / "quake.pid").write_text(str(terminal.pid) + "\n")
            wait_for(lambda: not terminal_window()["tile"], "PID-scoped Quake exception", 3)
            evaluate(f"const w = workspace.windowList().find(w => w.pid === {terminal.pid}); "
                     "w.noBorder = true; w.keepAbove = true; w.keepBelow = false; "
                     "w.frameGeometry = {x: 0, y: 0, width: 1280, height: 680}; return true;")
            time.sleep(0.3)
            current = terminal_window()
            assert current["above"] and current["noBorder"] and not current["tile"], current
            # Reload with existing windows: no layout, border, or PID state may
            # accidentally enlist the Quake, or leave ordinary windows floating.
            dbus("/Scripting", "org.kde.kwin.Scripting.unloadScript", plugin)
            dbus("/Scripting", "org.kde.kwin.Scripting.start")
            time.sleep(0.3)
            current = terminal_window()
            assert current["above"] and current["noBorder"] and not current["tile"], current
            assert all(window(name)["tile"] for name in ("Policy SSD", "Policy CSD", "Policy Dialog"))
            # Removing the identity must retile the same Konsole without restarting it.
            (run / "quake.pid").unlink()
            wait_for(lambda: terminal_window()["tile"], "revoked exception retiles", 3)
        check("only the validated Quake process floats, including late registration", quake)

        if plugin == "arasaka-polonium":
            def update_runtime():
                installed = run / "data/kwin/scripts" / plugin
                version = json.loads((installed / "runtime.json").read_text())["version"]
                shutil.copytree(installed / "contents/runtime" / version,
                                installed / "contents/runtime/reload-check")
                subprocess.run(["kwriteconfig6", "--file", "kwinrc", "--group", "Script-" + plugin,
                                "--key", "RuntimeVersion", "reload-check"], check=True)
                dbus("/Scripting", "org.kde.kwin.Scripting.unloadScript", plugin)
                dbus("/Scripting", "org.kde.kwin.Scripting.start")
                def updated():
                    response = subprocess.run(["qdbus6", "org.kde.KWin", "/ArasakaWindowPolicy",
                                               "org.arasaka.WindowPolicy1.report"], text=True, capture_output=True)
                    return response.returncode == 0 and json.loads(response.stdout)["version"] == "reload-check"
                wait_for(updated, "updated runtime loads without re-registering protected native module", 3)
                action("Policy SSD", "w.minimized = true")
                action("Policy SSD", "w.minimized = false")
                wait_for(lambda: window("Policy SSD")["tile"], "updated tiler handles window events")
            check("in-session runtime update reuses the native module", update_runtime)

            def no_stale_callbacks():
                errors = [line for line in (run / "kwin.log").read_text().splitlines()
                          if "TypeError:" in line or "ReferenceError:" in line]
                assert not errors, errors[:3]
            check("unloaded policy disconnects its window callbacks", no_stale_callbacks)

        (run / "result.json").write_text(json.dumps({"failures": failures}))
        return bool(failures)
    finally:
        for client in clients:
            client.terminate()
        for client in clients:
            try:
                client.wait(timeout=5)
            except subprocess.TimeoutExpired:
                client.kill()


def main():
    if sys.argv[1] == "--child":
        return child(Path(sys.argv[2]))
    if sys.argv[1] == "--session":
        run = Path(sys.argv[2])
        subprocess.Popen(["/usr/lib/x86_64-linux-gnu/libexec/kactivitymanagerd"],
                         env=dict(os.environ, QT_QPA_PLATFORM="offscreen"))
        def activity_ready():
            result = subprocess.run(["qdbus6", "org.kde.ActivityManager", "/ActivityManager/Activities",
                                     "org.kde.ActivityManager.Activities.CurrentActivity"],
                                    text=True, capture_output=True)
            return result.returncode == 0 and len(result.stdout.strip()) == 36
        wait_for(activity_ready, "private activity manager")
        os.execvp("kwin_wayland", ["kwin_wayland", "--virtual", "--output-count", "2", "--width", "1280", "--height", "900", "--scale", "1",
            "--socket", "policy-test", "--no-lockscreen", "--exit-with-session",
            f"/usr/bin/python3 {Path(__file__).resolve()} --child {run}"])
    package = Path(sys.argv[1]).resolve()
    assert (package / "metadata.json").is_file()
    plugin = json.loads((package / "metadata.json").read_text())["KPlugin"]["Id"]
    run = Path(tempfile.mkdtemp(prefix="window-policy-", dir="/tmp/opencode"))
    for name in ("home", "config", "data/kwin/scripts", "runtime", "state", "cache", "config-dirs"):
        (run / name).mkdir(parents=True, exist_ok=True)
    (run / "runtime").chmod(0o700)
    flags = shlex.split(subprocess.check_output(["pkg-config", "--cflags", "--libs", "Qt6Quick"], text=True))
    subprocess.run(["c++", "-std=c++17", str(ROOT / "tests/window_policy_windows.cpp"),
                    "-o", str(run / "window-fixture"), *flags], check=True)
    subprocess.run(["cmake", "-S", str(ROOT / "tests/window_drag_probe"), "-B", str(run / "drag-probe" )],
                   check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["cmake", "--build", str(run / "drag-probe"), "--parallel", "2"],
                   check=True, stdout=subprocess.DEVNULL)
    (run / "drag-probe.qml").write_text('import QtQuick\nimport "drag-probe" as Probe\nProbe.DragProbe {}\n')
    shutil.copytree(package, run / "data/kwin/scripts" / plugin)
    shutil.copy2(package / "metadata.json", run / "package-metadata.json")
    version = json.loads((package / "runtime.json").read_text())["version"] if (package / "runtime.json").exists() else ""
    (run / "config/kwinrc").write_text(
        f"[Plugins]\n{plugin}Enabled=true\n[Script-{plugin}]\nDefaultEngine=0\nRuntimeVersion={version}\n"
        "BTreeSwapInsertSide=true\nBorders=4\nWindowDragPolicy=2\n"
        f"QuakePidFile={run}/quake.pid\n[Desktops]\nNumber=1\nRows=1\n"
    )
    (run / "config/kwinrulesrc").write_text(
        "[General]\ncount=1\nrules=arasaka-frame\n[arasaka-frame]\n"
        "noborder=false\nnoborderrule=3\ntypes=1\nwmclass=.*\nwmclassmatch=3\n"
    )
    (run / "session.conf").write_text(f'''<busconfig><type>session</type>
        <listen>unix:tmpdir={run}/runtime</listen><auth>EXTERNAL</auth>
        <policy context="default"><allow send_destination="*"/>
        <allow receive_sender="*"/><allow own="*"/></policy></busconfig>''')
    env = dict(PATH="/usr/bin:/bin", LANG="C.UTF-8", HOME=str(run / "home"),
               XDG_CONFIG_HOME=str(run / "config"), XDG_CONFIG_DIRS=str(run / "config-dirs"),
               XDG_DATA_HOME=str(run / "data"), XDG_DATA_DIRS="/usr/share",
               XDG_STATE_HOME=str(run / "state"), XDG_CACHE_HOME=str(run / "cache"),
               XDG_RUNTIME_DIR=str(run / "runtime"), KWIN_COMPOSE="Q", QT_QUICK_BACKEND="software",
               LIBGL_ALWAYS_SOFTWARE="1", DBUS_SYSTEM_BUS_ADDRESS="unix:path=/nonexistent-policy-system-bus")
    if plugin == "arasaka-polonium":
        subprocess.run([sys.executable, "-c",
            f"import runpy; runpy.run_path({str(ROOT / 'bin/apply-window-policy')!r})['configure']({version!r})"],
            check=True, env=dict(env, DBUS_SESSION_BUS_ADDRESS="unix:path=/nonexistent-policy-session-bus"))
    print(f"ARTIFACTS={run}", flush=True)
    with (run / "kwin.log").open("w") as log:
        result = subprocess.run(["dbus-run-session", "--config-file", str(run / "session.conf"), "--",
            "/usr/bin/python3", str(Path(__file__).resolve()), "--session", str(run)],
            env=env, cwd=run / "home", stdout=log, stderr=subprocess.STDOUT, timeout=100)
    if (run / "result.json").exists():
        print((run / "result.json").read_text())
        return bool(json.loads((run / "result.json").read_text())["failures"])
    print(f"Harness did not finish ({result.returncode}); inspect {run}/kwin.log")
    return 1


if __name__ == "__main__":
    sys.exit(main())
