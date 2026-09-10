import json
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = "com.arasaka.launcher"
TOOLS = "bash python3 dirname mkdir flock jq sha256sum cut sleep node".split()

# Only session-facing commands are faked; deployment and reconciliation are real.
SESSION_TOOL = r'''#!/usr/bin/env python3
import json, os, pathlib, subprocess, sys, time
tool = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
root = pathlib.Path(os.environ["TEST_SESSION"])
with (root / "calls").open("a") as stream:
    stream.write(json.dumps([tool, *args]) + "\n")
if tool == "kpackagetool6":
    assert args[:3] == ["--type", "Plasma/Applet", "--show"]
    assert pathlib.Path(args[3]).is_absolute()
    sys.exit(int(os.environ.get("PACKAGE_FAIL", "0")))
if tool == "systemctl":
    unit = args[-1]
    if "show" in args:
        print("loaded" if os.environ.get("WATCHER", "active") != "missing" else "not-found")
    elif "is-active" in args:
        sys.exit(0 if os.environ.get("WATCHER", "active") == "active" else 3)
    elif "stop" in args:
        if os.environ.get("STOP_FAIL"):
            sys.exit(1)
        (root / (unit + ".stopped")).touch()
    elif "start" in args:
        if os.environ.get("START_FAIL"):
            sys.exit(1)
        (root / (unit + ".stopped")).unlink(missing_ok=True)
    else:
        sys.exit(92)
elif tool == "kscreen-doctor":
    assert args == ["--json"]
    if os.environ.get("STALL_AFTER_FIRST_ATTEMPT") and (root / "attempts").exists():
        time.sleep(30)
    print(json.dumps({"outputs": [{"name": "eDP-1", "connected": True,
        "enabled": True, "priority": 1}]}))
elif tool == "qdbus6":
    if "org.freedesktop.DBus.Peer.Ping" in args:
        sys.exit(int(os.environ.get("PING_FAIL", "0")))
    elif "org.freedesktop.DBus.GetNameOwner" in args:
        print(os.environ.get("SHELL_OWNER", ":1.42"))
    elif "org.freedesktop.DBus.GetId" in args:
        print(os.environ.get("BUS_ID", "test-bus-1"))
    elif "org.kde.PlasmaShell.evaluateScript" in args:
        if "arasaka-launcher-status" in args[-1]:
            ready = (root / "ready").exists() and not os.environ.get("NEVER_READY")
            config = {"Managed": True, "ready": bool(ready),
                "readyToken": os.environ.get("READY_TOKEN",
                    os.environ.get("BUS_ID", "test-bus-1") + "/" + os.environ.get("SHELL_OWNER", ":1.42"))}
            harness = "const config = " + json.dumps(config) + ";\n"
            harness += "const host = {type: 'com.arasaka.launcher', readConfig: (key, fallback) => config[key] ?? fallback};\n"
            harness += "function desktops() { return [{widgetIds: " + ("[1]" if ready or os.environ.get("HOST") else "[]") + ", widgetById: () => host}]; }\n"
            harness += "function panels() { return " + ("[]" if ready else "[host, host]") + "; }\nconst print = console.log;\n"
            result = subprocess.run(["node", "-e", harness + args[-1]], text=True, capture_output=True)
            sys.stdout.write(result.stdout)
            sys.stderr.write(result.stderr)
            sys.exit(result.returncode)
        else:
            count_file = root / "attempts"
            count = int(count_file.read_text()) + 1 if count_file.exists() else 1
            count_file.write_text(str(count))
            if count <= int(os.environ.get("NOT_READY_COUNT", "0")):
                print("Error: launcher is not ready yet", file=sys.stderr)
                sys.exit(1)
            if os.environ.get("LAYOUT_FAIL"):
                print("Error: broken layout", file=sys.stderr)
                sys.exit(1)
            (root / "ready").touch()
            if os.environ.get("DESKTOP_STATE"):
                sys.path.insert(0, os.environ["TEST_MODULES"])
                from apply_shader_wallpaper_test import PLASMA
                sys.exit(subprocess.run(["node", "-e", PLASMA, args[-1]]).returncode)
    else:
        sys.exit(93)
'''


class ApplyLauncherTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="arasaka-launcher-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.home = self.root / "home"
        self.data = self.home / "data"
        self.config = self.home / "config"
        self.state = self.home / "state"
        self.runtime = self.home / ".local/libexec/arasaka-kde"
        self.package = self.data / "plasma/plasmoids" / PLUGIN
        self.session = self.root / "session"
        self.tools = self.root / "tools"
        for directory in (self.config, self.session, self.tools, self.repo / "bin"):
            directory.mkdir(parents=True)
        for name in TOOLS:
            executable = shutil.which(name)
            self.assertIsNotNone(executable, name)
            (self.tools / name).symlink_to(executable)
        for name in ("kpackagetool6", "qdbus6", "systemctl", "kscreen-doctor"):
            self.write(self.tools / name, SESSION_TOOL, 0o755)
        for name in ("apply-launcher", "reconcile-displays", "apply-live"):
            source = ROOT / "bin" / name
            if source.exists():
                shutil.copy2(source, self.repo / "bin" / name)
        self.write(self.repo / "lib/arasaka_topology.py", (ROOT / "lib/arasaka_topology.py").read_text())
        self.write(self.repo / "plasma/layout.js",
                   'var launcherSession = "__LAUNCHER_SESSION__";\n'
                   'var hideDesktopIcons = __HIDE_DESKTOP_ICONS__;\n')
        self.write(self.repo / "plasma/shader-wallpaper.js", (ROOT / "plasma/shader-wallpaper.js").read_text())
        self.write(self.repo / "plasma/wallpaper-defaults.json", (ROOT / "plasma/wallpaper-defaults.json").read_text())
        self.write(self.repo / "theme/panel-colorizer/Arasaka.json", '{"fixture": true}\n')
        self.source_package = self.repo / "plasma/applets" / PLUGIN
        self.write(self.source_package / "metadata.json", json.dumps({
            "KPackageStructure": "Plasma/Applet", "KPlugin": {"Id": PLUGIN}}))
        self.write(self.source_package / "contents/ui/main.qml", "// fixture QML\n")
        self.write(self.source_package / "contents/config/main.xml",
                   '<kcfg><group name="General"><entry name="ready" type="Bool">'
                   '<default>false</default></entry></group></kcfg>\n')
        self.write(self.config / "plasma-org.kde.plasma.desktop-appletsrc", "original panels\n")
        self.write(self.config / "plasmashellrc", "original shell\n")
        self.env = {
            "HOME": str(self.home), "XDG_DATA_HOME": str(self.data),
            "XDG_CONFIG_HOME": str(self.config), "XDG_STATE_HOME": str(self.state),
            "XDG_CACHE_HOME": str(self.home / "cache"),
            "XDG_RUNTIME_DIR": str(self.session), "PATH": str(self.tools),
            "TEST_SESSION": str(self.session), "DBUS_SESSION_BUS_ADDRESS": "unix:path=/nonexistent-test-bus",
        }

    def write(self, path, text, mode=0o644):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        path.chmod(mode)

    def run_installer(self, *args, clock_step=None, **env):
        script = self.repo / "bin/apply-launcher"
        self.assertTrue(script.exists(), "scoped launcher installer is missing")
        command = [str(script), *args]
        if clock_step is not None:
            # Only the installer's clock advances; child commands and their timeouts remain real.
            command = [str(self.tools / "python3"), "-c", '''
import runpy, subprocess, sys, time
from types import SimpleNamespace
from unittest.mock import Mock, patch
step = float(sys.argv[1])
sys.argv = sys.argv[2:]
clock = Mock(return_value=0)
subprocess_time = SimpleNamespace(**vars(time))
def advance(seconds):
    clock.return_value += step
# Popen.wait() may sleep after a child closes its pipes but before it exits.
# That cleanup must use real time rather than consume the installer's deadline.
with patch("subprocess.time", subprocess_time), patch("time.monotonic", clock), patch("time.sleep", advance):
    runpy.run_path(sys.argv[0], run_name="__main__")
''', str(clock_step), *command]
        return subprocess.run(command, env={**self.env, **env},
                              text=True, capture_output=True, timeout=20)

    def calls(self):
        path = self.session / "calls"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def backups(self):
        return list((self.state / "arasaka-kde/backups").glob("launcher-*"))

    def test_installs_exact_package_and_runtime_with_private_unique_backups(self):
        self.write(self.package / "old.qml", "previous package\n")
        self.write(self.runtime / "layout.js", "previous layout\n")
        self.write(self.runtime / "unrelated", "keep me\n")
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        backup, = self.backups()
        self.assertIn(str(backup), result.stdout)
        self.assertEqual((backup / "plasma-org.kde.plasma.desktop-appletsrc").read_text(), "original panels\n")
        self.assertEqual((backup / "plasmashellrc").read_text(), "original shell\n")
        self.assertEqual((backup / "package/old.qml").read_text(), "previous package\n")
        self.assertEqual((backup / "runtime/layout.js").read_text(), "previous layout\n")
        for path in [backup, *backup.rglob("*")]:
            self.assertEqual(stat.S_IMODE(path.stat().st_mode) & 0o077, 0, str(path))
        self.assertFalse((self.package / "old.qml").exists())
        self.assertEqual((self.package / "contents/ui/main.qml").read_bytes(),
                         (self.source_package / "contents/ui/main.qml").read_bytes())
        for source, target in (("bin/reconcile-displays", "reconcile-displays"),
                               ("lib/arasaka_topology.py", "arasaka_topology.py"),
                               ("plasma/layout.js", "layout.js"),
                               ("plasma/shader-wallpaper.js", "shader-wallpaper.js"),
                               ("theme/panel-colorizer/Arasaka.json", "Arasaka.json")):
            self.assertTrue((self.runtime / target).is_file(), target)
            self.assertEqual((self.repo / source).read_bytes(), (self.runtime / target).read_bytes())
        self.assertEqual((self.runtime / "unrelated").read_text(), "keep me\n")
        self.assertFalse((self.data / "wallpapers").exists())
        self.assertEqual((self.config / "plasmashellrc").read_text(), "original shell\n")
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.backups()), 2)
        self.assertEqual((self.session / "attempts").read_text(), "2", "must force unchanged topology")

    def test_preflight_failures_do_not_write_user_state(self):
        for variable in ("PACKAGE_FAIL", "PING_FAIL"):
            with self.subTest(variable=variable):
                result = self.run_installer(**{variable: "1"})
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.state.exists())
                self.assertFalse(self.data.exists())
                self.assertFalse(self.runtime.exists())
                self.assertFalse(any("stop" in call for call in self.calls()))

    def test_missing_command_fails_before_session_or_state_changes(self):
        (self.tools / "kscreen-doctor").unlink()
        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("kscreen-doctor", result.stderr)
        self.assertFalse(self.state.exists())
        self.assertEqual(self.calls(), [])

    def test_unreadable_input_or_backup_source_is_rejected_before_writes(self):
        for path in (self.source_package / "contents/ui/main.qml", self.config / "plasmashellrc"):
            with self.subTest(path=path):
                path.chmod(0)
                result = self.run_installer()
                path.chmod(0o644)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(str(path), result.stderr)
                self.assertFalse(self.state.exists())

    def test_symlinked_runtime_is_not_overwritten(self):
        outside = self.home / "other-runtime"
        self.write(outside / "layout.js", "untouched\n")
        self.runtime.parent.mkdir(parents=True)
        self.runtime.symlink_to(outside, target_is_directory=True)
        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((outside / "layout.js").read_text(), "untouched\n")
        self.assertFalse(self.state.exists())

    def test_install_only_stages_without_layout_and_restores_active_watcher(self):
        result = self.run_installer("--install-only")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.runtime / "layout.js").exists())
        self.assertFalse((self.session / "attempts").exists())
        self.assertFalse((self.state / "arasaka-kde/topology").exists())
        self.assertFalse((self.session / "arasaka-display-reconcile.path.stopped").exists())
        calls = self.calls()
        validate = next(i for i, call in enumerate(calls) if call[0] == "kpackagetool6")
        ping = next(i for i, call in enumerate(calls) if "org.freedesktop.DBus.Peer.Ping" in call)
        stop = next(i for i, call in enumerate(calls) if "stop" in call)
        self.assertLess(validate, stop)
        self.assertLess(ping, stop)
        self.assertTrue(any("stop" in c and c[-1] == "arasaka-display-reconcile.service" for c in calls))
        self.assertTrue(any("start" in c and c[-1] == "arasaka-display-reconcile.path" for c in calls))
        self.assertFalse(any("enable" in c or "disable" in c for c in calls))

    def test_inactive_or_missing_watcher_is_not_enabled(self):
        for state in ("inactive", "missing"):
            result = self.run_installer(WATCHER=state)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(any("start" in c or "enable" in c for c in self.calls()))

    def test_pre_rain_launcher_publication_keeps_watcher_layout_working(self):
        artwork = self.data / "wallpapers/Arasaka"
        old_assets = [artwork / "shaders/Heartfelt_No_Heart.frag",
                      artwork / "mikoshi-16x9.png", artwork / "mikoshi-16x10.png",
                      self.data / "plasma/wallpapers/online.knowmad.shaderwallpaper/contents/ui/shaderwallpaper/libshaderwallpaperplugin.so"]
        for asset in old_assets:
            self.write(asset, "preceding installed asset\n")
        initial = [{"id": 12, "screen": 0, "wallpaperPlugin": "online.knowmad.shaderwallpaper",
                    "config": {"selectedShaderPath": "file:///custom.frag", "targetFps": 17, "mouseEnabled": False}},
                   {"id": 27, "screen": 0, "wallpaperPlugin": "org.kde.image", "config": {"keep": True}}]
        desktop_state = self.session / "desktops.json"
        environment = {**self.env, "DESKTOP_STATE": str(desktop_state),
                       "TEST_MODULES": str(ROOT / "tests"), "PYTHONDONTWRITEBYTECODE": "1", "CHECK_PRIVACY": "1"}
        command = [str(self.runtime / "reconcile-displays"), "--hide-desktop-icons", "--ensure-shader-wallpaper"]
        for args in (("--install-only",), ()):
            with self.subTest(args=args):
                self.write(desktop_state, json.dumps(initial))
                result = self.run_installer(*args)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse((self.session / "arasaka-display-reconcile.path.stopped").exists())
                before = len(self.calls())
                result = subprocess.run(command, env=environment, text=True, capture_output=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("deferred", result.stderr)
                evaluations = [c[-1] for c in self.calls()[before:] if "org.kde.PlasmaShell.evaluateScript" in c]
                self.assertEqual(len(evaluations), 1, "layout must run, even when new wallpaper cannot be initialized")
                self.assertIn("var hideDesktopIcons = true;", evaluations[0])
                self.assertNotIn("ARASAKA_SHADER_WALLPAPER=", evaluations[0])
                self.assertEqual(json.loads(desktop_state.read_text()), initial)
                self.assertTrue((self.state / "arasaka-kde/topology").is_file())
                for asset in old_assets:
                    self.assertEqual(asset.read_text(), "preceding installed asset\n")
                self.assertFalse((artwork / "shaders/Interactive_Rain.frag").exists())
        # Readiness is evaluated anew even with the already-recorded topology signature.
        self.write(artwork / "shaders/Interactive_Rain.frag", "new staged asset\n")
        result = subprocess.run(command, env=environment, text=True, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        desktops = json.loads(desktop_state.read_text())
        self.assertEqual(desktops[0], initial[0])
        self.assertEqual(desktops[1]["wallpaperPlugin"], "online.knowmad.shaderwallpaper")
        self.assertTrue(desktops[1]["config"]["mouseEnabled"])
        self.assertFalse(desktops[1]["config"]["arasakaRainPending"])

    def test_apply_live_build_failure_does_not_break_published_runtime(self):
        # Execute the real publication prefix and shader-build call, excluding unrelated rice.
        source = (self.repo / "bin/apply-live").read_text()
        prefix = source.split("install_upstream_visuals() {", 1)[0]
        shader_call = next(line for line in source.splitlines() if line == '"$repo_root/bin/apply-shader-wallpaper"')
        self.write(self.repo / "bin/apply-live-wallpaper-test", prefix + shader_call + "\n", 0o755)
        self.write(self.repo / "bin/apply-shader-wallpaper",
                   '#!/usr/bin/env bash\nprintf "fixture native build failed\\n" >&2\nexit 42\n', 0o755)
        result = subprocess.run([str(self.repo / "bin/apply-live-wallpaper-test")],
                                env=self.env, text=True, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 42, result.stderr)
        self.assertFalse((self.session / "arasaka-display-reconcile.path.stopped").exists())
        result = subprocess.run([str(self.runtime / "reconcile-displays"), "--hide-desktop-icons", "--ensure-shader-wallpaper"],
                                env=self.env, text=True, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("deferred", result.stderr)
        self.assertEqual((self.session / "attempts").read_text(), "1")
        self.assertEqual((self.config / "plasmashellrc").read_text(), "original shell\n")

    def test_install_only_backs_up_and_stages_package_including_config_schema(self):
        self.write(self.package / "contents/config/main.xml", "previous schema\n")
        self.write(self.runtime / "layout.js", "previous layout\n")
        result = self.run_installer("--install-only")
        self.assertEqual(result.returncode, 0, result.stderr)
        backup, = self.backups()
        self.assertEqual((backup / "package/contents/config/main.xml").read_text(), "previous schema\n")
        self.assertEqual((backup / "runtime/layout.js").read_text(), "previous layout\n")
        self.assertEqual((backup / "plasmashellrc").read_text(), "original shell\n")
        schema = self.package / "contents/config/main.xml"
        self.assertEqual(schema.read_bytes(), (self.source_package / "contents/config/main.xml").read_bytes())
        installed = schema.stat()
        result = self.run_installer("--install-only")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.backups()), 2)
        self.assertEqual(schema.stat().st_ino, installed.st_ino)
        self.assertEqual(schema.stat().st_ctime_ns, installed.st_ctime_ns)
        self.assertFalse((self.session / "attempts").exists())
        self.assertEqual((self.config / "plasmashellrc").read_text(), "original shell\n")

    def test_initial_not_ready_is_retried_until_converged(self):
        result = self.run_installer(NOT_READY_COUNT="2")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.session / "attempts").read_text(), "3")

    def test_layout_failure_is_bounded_visible_and_restores_watcher(self):
        result = self.run_installer(LAYOUT_FAIL="1", clock_step=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("broken layout", result.stderr)
        self.assertEqual((self.session / "attempts").read_text(), "1", "must stop at the deadline")
        self.assertTrue(self.backups())
        self.assertFalse((self.session / "arasaka-display-reconcile.path.stopped").exists())

    def test_success_without_ready_host_is_not_reported_as_convergence(self):
        result = self.run_installer(NEVER_READY="1", clock_step=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ready", result.stderr.lower())
        self.assertNotIn("Launcher ready;", result.stdout)

    def test_saved_ready_with_stale_acknowledgement_is_not_convergence(self):
        shutil.copytree(self.source_package, self.package)
        (self.session / "ready").touch()
        for token in ("test-bus-1/:1.41", "old-bus/:1.42", ""):
            with self.subTest(token=token):
                result = self.run_installer(READY_TOKEN=token, clock_step=10)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn("not ready", result.stderr)
                self.assertNotIn("Launcher ready;", result.stdout)

    def test_existing_host_with_current_acknowledgement_converges_without_wallpapers(self):
        shutil.copytree(self.source_package, self.package)
        (self.session / "ready").touch()
        result = self.run_installer(BUS_ID="new-bus", SHELL_OWNER=":1.99",
                                    READY_TOKEN="new-bus/:1.99")
        self.assertEqual(result.returncode, 0, result.stderr)
        layouts = [c[-1] for c in self.calls() if "org.kde.PlasmaShell.evaluateScript" in c
                   and "arasaka-launcher-status" not in c[-1]]
        self.assertEqual(len(layouts), 1)
        self.assertIn('"new-bus/:1.99"', layouts[0])
        self.assertIn('var hideDesktopIcons = false;', layouts[0])

    def test_apply_live_explicitly_reconciles_wallpapers_after_launcher(self):
        # Run the layout-application section without executing unrelated theme installers.
        script = (self.repo / "bin/apply-live").read_text()
        section = script.split('"$repo_root/bin/apply-window-effects"\n', 1)[1].split('path_disabled=false', 1)[0]
        self.write(self.repo / "bin/apply-launcher",
                   '#!/usr/bin/env bash\nprintf "launcher\\n" >>"$TEST_SESSION/order"\n', 0o755)
        self.write(self.runtime / "reconcile-displays",
                   '#!/usr/bin/env bash\nprintf "reconcile %s\\n" "$*" >>"$TEST_SESSION/order"\n', 0o755)
        result = subprocess.run([str(self.tools / "bash"), "-c",
                                 'set -eu; repo_root=$1; systemctl() { :; };\n' + section,
                                 "apply-live-test", str(self.repo)],
                                env=self.env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.session / "order").read_text(),
                         "launcher\nreconcile --force --hide-desktop-icons --ensure-shader-wallpaper\n")

    def test_final_timeout_does_not_hide_observed_readiness_failure(self):
        result = self.run_installer(NEVER_READY="1", STALL_AFTER_FIRST_ATTEMPT="1", clock_step=9.99)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("timed out", result.stderr)
        self.assertIn("not ready", result.stderr)
        self.assertNotIn("Launcher ready;", result.stdout)
        self.assertFalse((self.session / "arasaka-display-reconcile.path.stopped").exists())

    def test_watcher_stop_failure_prevents_installation(self):
        result = self.run_installer(STOP_FAIL="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.package.exists())
        self.assertFalse(self.runtime.exists())

    def test_watcher_resume_failure_is_reported(self):
        result = self.run_installer(START_FAIL="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("arasaka-display-reconcile.path", result.stderr)

    def test_changed_loaded_package_requires_explicit_shell_restart(self):
        self.write(self.package / "contents/ui/main.qml", "previous loaded QML\n")
        result = self.run_installer(HOST="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("restart", result.stderr.lower())
        self.assertIn("watcher", result.stderr.lower())
        self.assertFalse((self.session / "attempts").exists())
        self.assertTrue((self.session / "arasaka-display-reconcile.path.stopped").exists())
        self.assertEqual((self.package / "contents/ui/main.qml").read_text(), "// fixture QML\n")
        result = self.run_installer(HOST="1", WATCHER="inactive")
        self.assertNotEqual(result.returncode, 0, "same-session rerun must not accept cached QML")
        self.assertFalse((self.session / "attempts").exists())
        result = self.run_installer(HOST="1", WATCHER="inactive", SHELL_OWNER=":1.99")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.session / "arasaka-display-reconcile.path.stopped").exists())
        self.assertFalse(any("restart" in c for c in self.calls()))

    def test_apply_live_aborts_before_unrelated_work_when_staging_fails(self):
        # Execute the broad entry point, but stop at its real launcher preflight.
        result = subprocess.run([str(self.repo / "bin/apply-live")],
                                env={**self.env, "PACKAGE_FAIL": "1"},
                                text=True, capture_output=True, timeout=20)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(any(c[0] == "kpackagetool6" for c in self.calls()), result.stderr)
        self.assertFalse(self.data.exists())
        self.assertFalse(self.state.exists())

    def test_new_login_can_resume_even_if_shell_connection_name_is_reused(self):
        self.write(self.package / "contents/ui/main.qml", "previous loaded QML\n")
        result = self.run_installer(HOST="1")
        self.assertNotEqual(result.returncode, 0)
        result = self.run_installer(HOST="1", WATCHER="inactive", BUS_ID="test-bus-2")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.session / "arasaka-display-reconcile.path.stopped").exists())


if __name__ == "__main__":
    unittest.main()
