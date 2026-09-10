import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = "online.knowmad.shaderwallpaper"
GROUP = ["Greeter", "Wallpaper", PLUGIN, "General"]


@unittest.skipUnless(all(shutil.which(tool) for tool in ("kreadconfig6", "kwriteconfig6", "ldd", "c++"))
                     and os.geteuid() != 0, "requires desktop user, KConfig tools and C++ compiler")
class ApplyLockscreenTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="arasaka-lockscreen-test-")
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        self.config = self.home / "config"
        self.config.mkdir()
        self.data = self.home / "data with spaces"
        self.package = self.data / "plasma/wallpapers" / PLUGIN
        self.native = self.package / "contents/ui/shaderwallpaper"
        self.native.mkdir(parents=True)
        self.types = self.native / "shaderwallpaperplugin.qmltypes"
        self.types.write_text('import QtQuick.tooling 1.2\nModule { Component { name: "ShaderEngine"\n'
                              'Property { name: "rainLockScreenHost"; type: "bool"; '
                              'read: "rainLockScreenHost"; write: "setRainLockScreenHost"; '
                              'notify: "rainLockScreenHostChanged" } '
                              'Property { name: "rainGreeterInteractionVersion"; type: "int"; '
                              'read: "rainGreeterInteractionVersion"; isReadonly: true } } }\n')
        # Only installed assets are fixtures; dependency resolution and KConfig are real.
        subprocess.run(["c++", "-shared", "-fPIC", "-x", "c++", "-", "-o",
                        str(self.native / "libshaderwallpaperplugin.so")],
                       input='#include <stdio.h>\nextern "C" void dependency() { puts("fixture"); }\n',
                       text=True, capture_output=True, check=True)
        (self.native / "qmldir").write_text("module online.knowmad.shaderwallpaper\n")
        (self.native / "PluginStatus.qml").write_text("pragma Singleton\nQtObject { property bool installed: true }\n")
        for name in ("main.qml", "ShaderSystem.qml"):
            (self.native.parent / name).write_text("import QtQuick\nItem {}\n")
        (self.package / "metadata.json").write_text(json.dumps({
            "KPlugin": {"Id": PLUGIN}, "KPackageStructure": "Plasma/Wallpaper"}))
        self.artwork = self.data / "wallpapers/Arasaka"
        (self.artwork / "shaders").mkdir(parents=True)
        self.shader = self.artwork / "shaders/Interactive_Rain.frag"
        self.shader.write_text("// @arasaka-effect rain-v1\nvoid mainImage(out vec4 c, in vec2 p) { c = vec4(1); }\n")
        (self.artwork / "shaders/Heartfelt_No_Heart.frag").write_text("// preceding installed shader\n")
        (self.artwork / "mikoshi-16x9.png").write_bytes(b"fixture artwork")
        self.expected = {
            "selectedShaderPath": self.shader.as_uri(), "selectedShaderCode": "", "commonCode": "",
            "running": "true", "shaderSpeed": "0.75", "targetFps": "30", "resolutionScale": "1",
            "pauseMode": "3", "checkActiveScreen": "true", "excludeWindows": "",
            "mouseEnabled": "true", "audioEnabled": "false", "windowsEnabled": "false",
            "playlistEnabled": "false", "enableShaderTweaks": "false", "watchSourceFile": "false",
            "useBufferA": "false", "useBufferB": "false", "useBufferC": "false", "useBufferD": "false",
            "iChannel0Enabled": "true", "iChannel0": (self.artwork / "mikoshi-16x9.png").as_uri(), "imageChannel0": "0",
            "iChannel1Enabled": "false", "iChannel2Enabled": "false", "iChannel3Enabled": "false",
            "imageChannel1": "-1", "imageChannel2": "-1", "imageChannel3": "-1",
        }
        schema = self.package / "contents/config/main.xml"
        schema.parent.mkdir()
        schema.write_text('<kcfg><group name="General">' + ''.join(
            f'<entry name="{key}" type="String"/>' for key in self.expected) + '</group></kcfg>')
        shell = self.data / "plasma/shells/org.kde.plasma.desktop"
        (shell / "contents/lockscreen").mkdir(parents=True)
        (shell / "metadata.json").write_text("{}")
        (shell / "contents/lockscreen/config.xml").write_text(
            '<kcfg><group name="General"><entry name="alwaysShowClock" type="Bool"/></group></kcfg>')
        self.original = ("[Daemon]\nAutolock=true\nTimeout=7\nLockOnResume=true\nCustomPolicy=keep\n\n"
                         "[Greeter]\nWallpaperPlugin=org.kde.image\nUnknownGreeter=keep\n\n"
                         "[Greeter][LnF][General]\nalwaysShowClock=true\nUnknownTheme=keep\n\n"
                         f"[Greeter][Wallpaper][{PLUGIN}][General]\nmouseEnabled=false\nCustomShader=keep\n\n"
                         "[Greeter][Wallpaper][org.kde.image][General]\nImage=file:///keep.png\n\n"
                         "[UnknownGroup]\nUntouched=keep\n")
        self.target = self.config / "kscreenlockerrc"
        self.target.write_text(self.original)
        self.other_files = ("plasmashellrc", "plasma-org.kde.plasma.desktop-appletsrc", "kwinrc", "plasmaloginrc")
        for name in self.other_files:
            (self.config / name).write_text("[Untouched]\nValue=keep\n")
        tools = self.home / "tools"
        tools.mkdir()
        self.writes = self.home / "writes.jsonl"
        writer = tools / "kwriteconfig6"
        writer.write_text("#!/usr/bin/env python3\nimport json, os, sys\n"
                          "with open(os.environ['WRITE_LOG'], 'a') as log: log.write(json.dumps(sys.argv[1:]) + '\\n')\n"
                          f"os.execv({shutil.which('kwriteconfig6')!r}, ['kwriteconfig6', *sys.argv[1:]])\n")
        writer.chmod(0o755)
        self.env = dict(os.environ, HOME=str(self.home), XDG_DATA_HOME=str(self.data),
                        XDG_CONFIG_HOME=str(self.config), XDG_STATE_HOME=str(self.home / "state"),
                        XDG_CACHE_HOME=str(self.home / "cache"), XDG_DATA_DIRS=str(self.data),
                        PLASMA_DEFAULT_SHELL="org.kde.plasma.desktop", WRITE_LOG=str(self.writes),
                        PATH=str(tools) + os.pathsep + os.environ["PATH"],
                        DBUS_SESSION_BUS_ADDRESS="unix:path=/nonexistent-lockscreen-test-bus")

    def apply(self):
        return subprocess.run([str(ROOT / "bin/apply-lockscreen")], env=self.env,
                              capture_output=True, text=True, timeout=30)

    def read(self, groups, key):
        command = ["kreadconfig6", "--file", str(self.target)]
        for group in groups:
            command += ["--group", group]
        return subprocess.check_output([*command, "--key", key, "--default", "MISSING"],
                                       env=self.env, text=True).rstrip("\n")

    def test_rain_hover_appearance_preserves_policy_unknown_keys_and_private_backups(self):
        result = self.apply()
        self.assertEqual(result.returncode, 0, result.stderr)
        for key, value in self.expected.items():
            self.assertEqual(self.read(GROUP, key), value, key)
        self.assertEqual(self.read(["Greeter"], "WallpaperPlugin"), PLUGIN)
        self.assertEqual(self.read(["Greeter", "LnF", "General"], "alwaysShowClock"), "true")
        for group, key, value in [(["Daemon"], "Autolock", "true"), (["Daemon"], "Timeout", "7"),
                                  (["Daemon"], "LockOnResume", "true"), (["Daemon"], "CustomPolicy", "keep"),
                                  (["Greeter"], "UnknownGreeter", "keep"),
                                  (["Greeter", "LnF", "General"], "UnknownTheme", "keep"),
                                  (GROUP, "CustomShader", "keep"), (["UnknownGroup"], "Untouched", "keep"),
                                  (["Greeter", "Wallpaper", "org.kde.image", "General"], "Image", "file:///keep.png")]:
            self.assertEqual(self.read(group, key), value)
        for name in self.other_files:
            self.assertEqual((self.config / name).read_text(), "[Untouched]\nValue=keep\n")
        backups = list((self.home / "state/arasaka-kde/backups").glob("lockscreen-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(stat.S_IMODE(backups[0].stat().st_mode), 0o700)
        saved = backups[0] / "kscreenlockerrc"
        self.assertEqual(saved.read_text(), self.original)
        self.assertEqual(stat.S_IMODE(saved.stat().st_mode), 0o600)
        writes = [json.loads(line) for line in self.writes.read_text().splitlines()]
        self.assertEqual(writes[-1][-6:], ["--group", "Greeter", "--key", "WallpaperPlugin", "--", PLUGIN])
        self.assertEqual(len(writes), len(self.expected) + 1)
        applied = self.target.read_bytes()
        result = self.apply()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.target.read_bytes(), applied)
        self.assertEqual(saved.read_text(), self.original)

    def test_old_capability_missing_assets_and_inexact_marker_reject_before_writes(self):
        for kind in ("old-capability", "hover-only", "readonly-capability", "wrong-type", "missing-types", "missing-rain", "inexact-marker"):
            with self.subTest(kind=kind):
                types, shader = self.types.read_bytes(), self.shader.read_bytes()
                if kind == "old-capability":
                    self.types.write_text('Module { Component { name: "ShaderEngine" } }\n')
                elif kind == "hover-only":
                    self.types.write_bytes(types.replace(b"rainGreeterInteractionVersion", b"unrelatedVersion"))
                elif kind == "readonly-capability":
                    self.types.write_bytes(types.replace(b'write: "setRainLockScreenHost";', b'isReadonly: true;'))
                elif kind == "wrong-type":
                    self.types.write_bytes(types.replace(b'type: "bool"', b'type: "string"'))
                elif kind == "missing-types":
                    self.types.unlink()
                elif kind == "missing-rain":
                    self.shader.unlink()
                else:
                    self.shader.write_bytes(shader.replace(b"rain-v1\n", b"rain-v1 extra\n"))
                result = self.apply()
                self.types.write_bytes(types)
                self.shader.write_bytes(shader)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertRegex(result.stderr, "rainLockScreenHost|rainGreeterInteractionVersion|native.rain marker|missing or unreadable")
                self.assertEqual(self.target.read_text(), self.original)
                self.assertFalse(self.writes.exists())
                self.assertFalse((self.home / "state").exists())

    def test_login_background_uses_shared_settings_and_preserves_authentication_and_clock(self):
        self.target = self.config / "plasmalogin.conf"
        original = ("[Autologin]\nUser=\nSession=\nRelogin=false\n\n"
                    "[Greeter]\nShowClock=false\nPreselectedUser=keep\nPreselectedSession=plasma.desktop\n"
                    "WallpaperPluginId=org.kde.image\n")
        self.target.write_text(original)
        query = self.home / "tools/dpkg-query"
        query.write_text('#!/bin/sh\nprintf "6.7.4-0arasaka2"\n')
        query.chmod(0o755)
        # Redirect only host paths and the privilege identity; actual assets, KConfig
        # validation, backup and configuration writes run through the login branch.
        probe = '''import os, pathlib, runpy, sys
from unittest.mock import patch
main = runpy.run_path(sys.argv[1])["main"]
paths = (pathlib.Path(os.environ["XDG_DATA_HOME"]), pathlib.Path(os.environ["XDG_CONFIG_HOME"]),
         pathlib.Path(os.environ["XDG_CONFIG_HOME"]) / "plasmalogin.conf",
         pathlib.Path(os.environ["XDG_STATE_HOME"]) / "arasaka-kde/backups")
sys.argv = [sys.argv[1], "--login"]
with patch("os.geteuid", return_value=0), patch.dict(main.__globals__, host_paths=lambda login: paths):
    main()
'''
        for version in ("6.7.4-0arasaka1", "6.7.5-1"):
            query.write_text(f'#!/bin/sh\nprintf "{version}"\n')
            rejected = subprocess.run([sys.executable, "-c", probe, str(ROOT / "bin/apply-lockscreen")],
                                      env=self.env, capture_output=True, text=True, timeout=30)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("lacks the pointer bridge", rejected.stderr)
            self.assertEqual(self.target.read_text(), original)
            self.assertFalse(self.writes.exists())
        query.write_text('#!/bin/sh\nprintf "6.7.4-0arasaka2"\n')
        result = subprocess.run([sys.executable, "-c", probe, str(ROOT / "bin/apply-lockscreen")],
                                env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        for key, value in self.expected.items():
            self.assertEqual(self.read(GROUP, key), value, key)
        self.assertEqual(self.read(["Greeter"], "WallpaperPluginId"), PLUGIN)
        self.assertEqual(self.read(["Greeter"], "ShowClock"), "false")
        self.assertEqual(self.read(["Greeter"], "PreselectedUser"), "keep")
        self.assertEqual(self.read(["Greeter"], "PreselectedSession"), "plasma.desktop")
        self.assertEqual(self.read(["Autologin"], "User"), "")
        self.assertEqual(self.read(["Autologin"], "Relogin"), "false")
        backups = list((self.home / "state/arasaka-kde/backups").glob("login-wallpaper-*/plasmalogin.conf"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), original)


if __name__ == "__main__":
    unittest.main()
