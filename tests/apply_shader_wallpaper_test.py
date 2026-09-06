import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tarfile
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = "online.knowmad.shaderwallpaper"
SHADER = "Heartfelt_No_Heart.frag"
HEADER = "// Heartfelt - by Martijn Steinrucken aka BigWings - 2017\n"
LICENSE = "// License Creative Commons Attribution-NonCommercial-ShareAlike 3.0 Unported License.\n"

# Only the external Plasma API is simulated; the actual wallpaper JavaScript runs.
PLASMA = r"""
const fs = require('fs');
const vm = require('vm');
const state = JSON.parse(fs.readFileSync(process.env.DESKTOP_STATE, 'utf8'));
const context = {
    desktops: () => state.map(d => ({
        id: d.id, screen: d.screen,
        get wallpaperPlugin() { return d.wallpaperPlugin; },
        set wallpaperPlugin(value) {
            if (process.env.CHECK_PRIVACY && (d.config.audioEnabled || d.config.mouseEnabled || d.config.playlistEnabled)) {
                throw Error('capture/playlist enabled when loading wallpaper');
            }
            d.wallpaperPlugin = value;
        },
        currentConfigGroup: [],
        writeConfig(key, value) {
            if (JSON.stringify(this.currentConfigGroup) !==
                JSON.stringify(['Wallpaper', 'online.knowmad.shaderwallpaper', 'General'])) {
                throw Error('unexpected configuration group');
            }
            if (key !== process.env.REJECT_SETTING) d.config[key] = value;
        },
        readConfig(key, fallback) {
            if (!(key in d.config)) return fallback;
            // Plasma's KConfig readEntry converts to the fallback's type.
            return fallback === undefined || typeof fallback === 'string' ? String(d.config[key]) : d.config[key];
        }
    })),
    screenForConnector: connector => connector === 'HDMI-A-1' ? 1 : -1,
    print: value => console.log(value)
};
try { vm.runInNewContext(process.argv[1], context); }
catch (error) { console.log('Error: ' + error.message); }
fs.writeFileSync(process.env.DESKTOP_STATE, JSON.stringify(state));
"""


class ApplyShaderWallpaperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="shader-wallpaper-test-", dir="/tmp/opencode")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.repo = self.base / "repo"
        self.home = self.base / "home"
        self.data = self.home / 'data "quoted" \\ space#%?'
        self.config = self.home / "config"
        self.state = self.home / "state"
        self.package = self.data / "plasma/wallpapers" / PLUGIN
        self.artwork = self.data / "wallpapers/Arasaka"
        self.backups = self.state / "arasaka-kde/backups"
        self.tools = self.base / "tools"
        for directory in (self.repo / "bin", self.repo / "lib", self.repo / "plasma",
                          self.repo / "assets/wallpapers/shaders", self.home,
                          self.config, self.tools, self.base / "tmp"):
            directory.mkdir(parents=True, exist_ok=True)
        for relative in ("bin/fetch-components", "lib/common.sh", "lib/arasaka_topology.py",
                         "assets/wallpapers/mikoshi-16x9.svg", "assets/wallpapers/mikoshi-16x10.svg",
                         "bin/apply-shader-wallpaper", "plasma/shader-wallpaper.js"):
            if (ROOT / relative).exists():
                shutil.copy2(ROOT / relative, self.repo / relative)
        # A tiny real CMake build models upstream's embedded native plugin output.
        source = self.base / "upstream"
        ui = source / "package/contents/ui"
        (ui / "Shaders").mkdir(parents=True)
        (ui / "shaderwallpaper").mkdir()
        (source / "package/contents/config").mkdir()
        (source / "package/metadata.json").write_text(json.dumps({
            "KPackageStructure": "Plasma/Wallpaper", "KPlugin": {"Id": PLUGIN}}))
        (source / "package/contents/config/main.xml").write_text("<kcfg/>\n")
        (ui / "main.qml").write_text('import "shaderwallpaper" as ShaderPlugin\n')
        (ui / "Shaders/Heartfelt.frag").write_text(HEADER + LICENSE + "\n#define HAS_HEART\nvoid mainImage() {}\n")
        self.stock_entry = {"id": "stock-heartfelt", "name": "Heartfelt", "shaderPath": "Shaders/Heartfelt.frag",
                            "author": "BigWings", "category": "Nature", "source": "local", "sourceId": "",
                            "description": "Stock fixture", "tags": [], "thumbnailPath": "", "favorite": False,
                            "needsTextures": True, "needsAudio": False, "hasBuffers": False, "likes": 0, "views": 0}
        (ui / "shader_index.json").write_text(json.dumps({"categories": ["Fixture"], "shaders": [self.stock_entry]}))
        (source / "LICENSE").write_text("Upstream license fixture\n")
        (source / "plugin.c").write_text("int plugin_fixture(void) { return 1; }\n")
        (source / "qmldir").write_text(
            "module online.knowmad.shaderwallpaper\nplugin shaderwallpaperplugin\n"
            "PluginStatus 1.0 PluginStatus.qml\n")
        (source / "PluginStatus.qml").write_text("import QtQuick\nQtObject { readonly property bool installed: true }\n")
        (source / "CMakeLists.txt").write_text(textwrap.dedent('''\
            cmake_minimum_required(VERSION 3.22)
            project(shader_fixture LANGUAGES C)
            add_library(shaderwallpaperplugin MODULE plugin.c)
            set(out "${CMAKE_SOURCE_DIR}/package/contents/ui/shaderwallpaper")
            set_target_properties(shaderwallpaperplugin PROPERTIES LIBRARY_OUTPUT_DIRECTORY "${out}")
            add_custom_command(TARGET shaderwallpaperplugin POST_BUILD
                COMMAND ${CMAKE_COMMAND} -E copy "${CMAKE_SOURCE_DIR}/qmldir" "${out}/qmldir"
                COMMAND ${CMAKE_COMMAND} -E copy "${CMAKE_SOURCE_DIR}/PluginStatus.qml" "${out}/PluginStatus.qml")
            install(CODE "message(FATAL_ERROR \\"cmake install must never run\\")")
            '''))
        patch = self.repo / "assets/wallpapers/shaders/heartfelt-no-heart.patch"
        patch.write_text("--- a/Heartfelt_No_Heart.frag\n+++ b/Heartfelt_No_Heart.frag\n"
                         "@@ -1,5 +1,5 @@\n " + HEADER + " " + LICENSE + " \n"
                         "-#define HAS_HEART\n+// Arasaka adaptation; source: upstream Heartfelt.frag\n"
                         " void mainImage() {}\n")
        archive = self.base / "shader.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(source, arcname="kde-shader-wallpaper-pinned")
        manifest = self.base / "components.tsv"
        manifest.write_text("name\tversion\turl\tsha256\tfilename\nshader-wallpaper\tfixture\t"
                            f"{archive.as_uri()}\t{hashlib.sha256(archive.read_bytes()).hexdigest()}\tshader.tar.gz\n")
        self.tokyo = self.base / "Tokyo.glsl"
        self.tokyo_code = ("// Created by Reinder Nijhoff 2014\n"
                           "// Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License.\n"
                           "void mainImage(out vec4 color, in vec2 pixel) { color = vec4(1.); }\n")
        self.tokyo.write_bytes(b"\xef\xbb\xbf" + self.tokyo_code.encode())
        self.dusti = self.base / "Dusti.json"
        self.dusti_code = ("// Dusti fixture; credits Xor, FabriceNeyret2, gopher and catnip.\n"
                           "void mainImage(out vec4 O, vec2 I) {\n    O = vec4(7,4,3,0);\n}\n")
        self.dusti_adapted = ("// Dusti fixture; credits Xor, FabriceNeyret2, gopher and catnip.\n"
                              "void mainImage(out vec4 O, vec2 I) {\n    O = vec4(7,4,3,0);\n    O.a = 1.0;\n}\n")
        (self.repo / "assets/wallpapers/shaders/dusti.patch").write_text(
            "--- a/Dusti.frag\n+++ b/Dusti.frag\n@@ -1,4 +1,5 @@\n"
            " // Dusti fixture; credits Xor, FabriceNeyret2, gopher and catnip.\n"
            " void mainImage(out vec4 O, vec2 I) {\n     O = vec4(7,4,3,0);\n+    O.a = 1.0;\n }\n")
        self.dusti_document = {"Shader": {
            "ver": "0.1", "info": {"id": "tcXXDB", "name": "Dusti [237 Chars]", "username": "HellMood",
                "description": "Depth and desert colors", "tags": ["golf"], "date": "1741283910",
                "flags": 0, "hasliked": 0, "likes": 29, "published": 3, "usePreview": 0, "viewed": 541},
            "renderpass": [{"name": "Image", "type": "image", "inputs": [], "description": "",
                            "outputs": [{"channel": 0, "id": 37}], "code": self.dusti_code}],
        }}
        self.dusti.write_text(json.dumps(self.dusti_document))
        with manifest.open("a") as stream:
            for component, path in (("shader-tokyo", self.tokyo), ("shader-dusti", self.dusti)):
                stream.write(f"{component}\tfixture\t{path.as_uri()}\t"
                             f"{hashlib.sha256(path.read_bytes()).hexdigest()}\t{path.name}\n")
        self.env = dict(os.environ, HOME=str(self.home), XDG_DATA_HOME=str(self.data),
                        XDG_CONFIG_HOME=str(self.config), XDG_STATE_HOME=str(self.state),
                        XDG_CACHE_HOME=str(self.home / "cache"), TMPDIR=str(self.base / "tmp"),
                        ARASAKA_COMPONENT_MANIFEST=str(manifest), ARASAKA_TEST_ALLOW_FILE="1",
                        PATH=f"{self.tools}:{os.environ['PATH']}",
                        REAL_CMAKE=shutil.which("cmake"), TOOL_LOG=str(self.base / "tools.jsonl"),
                        DESKTOP_STATE=str(self.base / "desktops.json"), PYTHONDONTWRITEBYTECODE="1")
        for name in ("FAIL_BUILD", "OMIT_PLUGIN", "BAD_DBUS", "REJECT_SETTING", "CHECK_PRIVACY", "ARASAKA_SHADER_BUILD_JOBS"):
            self.env.pop(name, None)
        self.desktops = [
            {"id": 12, "screen": 0, "wallpaperPlugin": "org.kde.image", "config": {"targetFps": 60}},
            {"id": 27, "screen": 1, "wallpaperPlugin": "org.kde.image", "config": {"playlistEnabled": True}},
        ]
        Path(self.env["DESKTOP_STATE"]).write_text(json.dumps(self.desktops))
        self.tool("cmake", '''
            if '--install' in sys.argv:
                sys.exit('forbidden cmake install')
            if '--build' in sys.argv and os.environ.get('FAIL_BUILD'):
                sys.exit('fixture build failure')
            result = subprocess.run([os.environ['REAL_CMAKE'], *sys.argv[1:]])
            if result.returncode == 0 and '--build' in sys.argv and os.environ.get('OMIT_PLUGIN'):
                cache = pathlib.Path(sys.argv[2]) / 'CMakeCache.txt'
                for line in cache.read_text().splitlines():
                    if line.startswith('CMAKE_HOME_DIRECTORY:INTERNAL='):
                        source = pathlib.Path(line.split('=', 1)[1])
                        (source / 'package/contents/ui/shaderwallpaper/libshaderwallpaperplugin.so').unlink()
            sys.exit(result.returncode)
            ''')
        self.tool("kscreen-doctor", '''
            assert sys.argv[1:] == ['--json'], 'display reconfiguration is forbidden'
            print(json.dumps({'outputs': [
                {'id': 1, 'name': 'eDP-1', 'connected': True, 'enabled': True, 'priority': 1},
                {'id': 2, 'name': 'HDMI-A-1', 'connected': True, 'enabled': True, 'priority': 2}
            ]}))
            ''')
        self.tool("qdbus6", f'''
            assert sys.argv[1:4] == ['org.kde.plasmashell', '/PlasmaShell', 'org.kde.PlasmaShell.evaluateScript']
            assert len(sys.argv) == 5
            if os.environ.get('BAD_DBUS'):
                print(os.environ['BAD_DBUS'])
            else:
                sys.exit(subprocess.run(['node', '-e', {PLASMA!r}, sys.argv[4]]).returncode)
            ''')

    def tool(self, name, code):
        path = self.tools / name
        path.write_text("#!/usr/bin/env python3\nimport json, os, pathlib, subprocess, sys\n"
                        "with open(os.environ['TOOL_LOG'], 'a') as log:\n"
                        "    log.write(json.dumps([pathlib.Path(sys.argv[0]).name, *sys.argv[1:]]) + '\\n')\n"
                        + textwrap.dedent(code))
        path.chmod(0o755)

    def run_installer(self, *args, **env):
        return subprocess.run(["python3", str(self.repo / "bin/apply-shader-wallpaper"), *args],
                              env=dict(self.env, **env), text=True, capture_output=True)

    def calls(self):
        log = Path(self.env["TOOL_LOG"])
        return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

    def seed_previous_install(self):
        self.package.mkdir(parents=True)
        (self.package / "previous.txt").write_text("previous package\n")
        (self.artwork / "shaders").mkdir(parents=True)
        for name in ("mikoshi-16x9.png", "mikoshi-16x10.png", f"shaders/{SHADER}"):
            (self.artwork / name).write_text(f"previous {name}\n")
        (self.artwork / "unrelated.txt").write_text("keep\n")
        (self.config / "plasma-org.kde.plasma.desktop-appletsrc").write_text("previous plasma config\n")
        runtime = self.home / ".local/libexec/arasaka-kde"
        runtime.mkdir(parents=True)
        (runtime / "layout.js").write_text("previous runtime layout\n")

    def assert_previous_unchanged(self):
        self.assertEqual((self.package / "previous.txt").read_text(), "previous package\n")
        self.assertEqual((self.artwork / "mikoshi-16x9.png").read_text(), "previous mikoshi-16x9.png\n")
        self.assertEqual((self.config / "plasma-org.kde.plasma.desktop-appletsrc").read_text(), "previous plasma config\n")
        self.assertFalse(any(call[0] == "qdbus6" for call in self.calls()))

    def test_install_only_deploys_self_contained_package_and_patched_shader_without_session_calls(self):
        result = self.run_installer("--install-only")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        ui = self.package / "contents/ui"
        self.assertTrue((ui / "shaderwallpaper/libshaderwallpaperplugin.so").read_bytes().startswith(b"\x7fELF"))
        self.assertIn("installed: true", (ui / "shaderwallpaper/PluginStatus.qml").read_text())
        self.assertIn("#define HAS_HEART", (ui / "Shaders/Heartfelt.frag").read_text())
        adapted = (self.artwork / "shaders" / SHADER).read_text()
        self.assertTrue(adapted.startswith(HEADER + LICENSE))
        self.assertNotIn("#define HAS_HEART", adapted)
        self.assertIn("Arasaka adaptation", adapted)
        for name, size in (("mikoshi-16x9.png", (1920, 1080)), ("mikoshi-16x10.png", (1600, 1000))):
            self.assertEqual(struct.unpack(">II", (self.artwork / name).read_bytes()[16:24]), size)
        self.assertEqual({call[0] for call in self.calls()}, {"cmake"})
        builds = [call for call in self.calls() if "--build" in call]
        self.assertEqual(builds[0][-2:], ["--parallel", "4"])
        self.assertFalse((self.home / ".local/lib/qml").exists())
        self.assertFalse(list(self.repo.rglob("*.png")))

    def test_default_activation_configures_both_desktops_with_escaped_absolute_urls_and_backups(self):
        self.seed_previous_install()
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        desktops = json.loads(Path(self.env["DESKTOP_STATE"]).read_text())
        expected = {
            "selectedShaderPath": (self.artwork / "shaders" / SHADER).as_uri(),
            "selectedShaderCode": "", "running": True, "shaderSpeed": 0.75,
            "targetFps": 30, "resolutionScale": 1, "pauseMode": 0, "checkActiveScreen": True,
            "mouseEnabled": False, "audioEnabled": False, "windowsEnabled": False,
            "iChannel0Enabled": True, "imageChannel0": 0, "playlistEnabled": False,
            "commonCode": "", "useBufferA": False, "useBufferB": False,
            "useBufferC": False, "useBufferD": False,
            "iChannel1Enabled": False, "iChannel2Enabled": False, "iChannel3Enabled": False,
            "imageChannel1": -1, "imageChannel2": -1, "imageChannel3": -1,
        }
        for desktop, image in zip(desktops, ("mikoshi-16x10.png", "mikoshi-16x9.png")):
            self.assertEqual(desktop["wallpaperPlugin"], PLUGIN)
            for key, value in dict(expected, iChannel0=(self.artwork / image).as_uri()).items():
                self.assertEqual(desktop["config"][key], value, key)
        backups = list(self.backups.glob("shader-wallpaper-*"))
        self.assertEqual(len(backups), 1)
        backup = backups[0]
        self.assertEqual(backup.stat().st_mode & 0o777, 0o700)
        for relative, text in (("package/previous.txt", "previous package\n"),
                               ("artwork/mikoshi-16x9.png", "previous mikoshi-16x9.png\n"),
                               (f"artwork/shaders/{SHADER}", f"previous shaders/{SHADER}\n"),
                               ("plasma-org.kde.plasma.desktop-appletsrc", "previous plasma config\n"),
                               ("runtime/layout.js", "previous runtime layout\n")):
            self.assertEqual((backup / relative).read_text(), text)
        self.assertEqual((self.artwork / "unrelated.txt").read_text(), "keep\n")
        self.assertEqual((self.home / ".local/libexec/arasaka-kde/layout.js").read_text(), "previous runtime layout\n")
        self.assertEqual([call[1:] for call in self.calls() if call[0] == "kscreen-doctor"], [["--json"]])
        self.assertEqual(sum(call[0] == "qdbus6" for call in self.calls()), 1)

    def test_failed_build_preserves_previous_package_artwork_and_config(self):
        self.seed_previous_install()
        result = self.run_installer(FAIL_BUILD="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("build", result.stderr.lower())
        self.assert_previous_unchanged()
        self.assertFalse(self.backups.exists())

    def test_missing_native_plugin_is_rejected_before_replacement(self):
        self.seed_previous_install()
        result = self.run_installer(OMIT_PLUGIN="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("libshaderwallpaperplugin.so", result.stderr)
        self.assert_previous_unchanged()

    def test_patch_failure_preserves_previous_installation(self):
        self.seed_previous_install()
        (self.repo / "assets/wallpapers/shaders/heartfelt-no-heart.patch").write_text("not a patch\n")
        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("patch", result.stderr.lower())
        self.assert_previous_unchanged()

    def test_symlinked_package_artwork_config_and_runtime_sources_are_refused(self):
        self.seed_previous_install()
        for target in (self.package, self.artwork / "mikoshi-16x9.png",
                       self.config / "plasma-org.kde.plasma.desktop-appletsrc",
                       self.home / ".local/libexec/arasaka-kde/layout.js"):
            with self.subTest(target=target):
                original = target.with_name(target.name + ".real")
                target.rename(original)
                target.symlink_to(original, target_is_directory=original.is_dir())
                result = self.run_installer("--install-only")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("symlink", result.stderr.lower())
                self.assertTrue(target.is_symlink())
                target.unlink()
                original.rename(target)
        self.assert_previous_unchanged()

    def test_symlinked_destination_parent_is_refused(self):
        self.data.mkdir(parents=True)
        elsewhere = self.base / "elsewhere"
        elsewhere.mkdir()
        (self.data / "plasma").symlink_to(elsewhere, target_is_directory=True)
        result = self.run_installer("--install-only")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("symlink", result.stderr.lower())
        self.assertEqual(list(elsewhere.iterdir()), [])

    def test_install_only_still_backs_up_but_leaves_desktop_state_untouched(self):
        self.seed_previous_install()
        result = self.run_installer("--install-only", ARASAKA_SHADER_BUILD_JOBS="2")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertTrue(list(self.backups.glob("shader-wallpaper-*/package/previous.txt")))
        self.assertEqual(json.loads(Path(self.env["DESKTOP_STATE"]).read_text()), self.desktops)
        self.assertEqual({call[0] for call in self.calls()}, {"cmake"})
        self.assertEqual([call for call in self.calls() if "--build" in call][0][-2:], ["--parallel", "2"])

    def test_unverified_dbus_output_is_failure_and_requests_explicit_restart(self):
        result = self.run_installer(BAD_DBUS="Error: wallpaper plugin unavailable")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("restart", result.stderr.lower())
        self.assertIn("backup", result.stderr.lower())

    def test_readback_mismatch_is_not_reported_as_success(self):
        result = self.run_installer(REJECT_SETTING="targetFps")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("targetFps", result.stderr)

    def test_empty_desktop_report_is_not_accepted_as_activation(self):
        result = self.run_installer(BAD_DBUS='ARASAKA_SHADER_WALLPAPER={"status":"ok","desktops":[]}')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("verification", result.stderr.lower())

    def test_capture_and_playlist_are_disabled_before_loading_wallpaper(self):
        for desktop in self.desktops:
            desktop["config"].update(audioEnabled=True, mouseEnabled=True, playlistEnabled=True)
        Path(self.env["DESKTOP_STATE"]).write_text(json.dumps(self.desktops))
        result = self.run_installer(CHECK_PRIVACY="1")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_structured_report_cannot_hide_wrong_privacy_settings(self):
        desktops = []
        for desktop, image in zip(self.desktops, ("mikoshi-16x10.png", "mikoshi-16x9.png")):
            desktops.append(dict(desktop, wallpaperPlugin=PLUGIN, config={
                "selectedShaderPath": (self.artwork / "shaders" / SHADER).as_uri(),
                "iChannel0": (self.artwork / image).as_uri(), "targetFps": 30, "audioEnabled": True,
            }))
        report = {"status": "ok", "primaryScreen": 1, "desktops": desktops}
        result = self.run_installer(BAD_DBUS="ARASAKA_SHADER_WALLPAPER=" + json.dumps(report))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("verification", result.stderr.lower())

    def test_malformed_structured_report_keeps_backup_and_restart_guidance(self):
        result = self.run_installer(BAD_DBUS="ARASAKA_SHADER_WALLPAPER=null")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("verification", result.stderr.lower())
        self.assertIn("restart", result.stderr.lower())
        self.assertIn("backup", result.stderr.lower())

    def test_selectable_imports_apply_compatibility_and_disable_texture_routing_without_activation(self):
        result = self.run_installer("--install-only")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        for name, expected in (("Tokyo", self.tokyo_code), ("Dusti", self.dusti_adapted)):
            path = self.package / "contents/ui/Shaders" / f"{name}.frag"
            self.assertTrue(path.is_file(), f"missing selectable shader: {name}")
            code = path.read_text()
            self.assertNotIn("\ufeff", code)
            self.assertTrue(code.endswith(expected), f"unexpected installed shader adaptation: {name}")
            self.assertIn("// @channels none,none,none,none", "\n".join(code.splitlines()[:60]))
            self.assertIn("https://www.shadertoy.com/view/", code)
        self.assertEqual(json.loads(Path(self.env["DESKTOP_STATE"]).read_text()), self.desktops)
        self.assertFalse(any(call[0] == "qdbus6" for call in self.calls()))

    def test_missing_dusti_patch_fails_preflight_without_build_or_replacement(self):
        self.seed_previous_install()
        (self.repo / "assets/wallpapers/shaders/dusti.patch").unlink()
        result = self.run_installer("--install-only")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("dusti.patch", result.stderr)
        self.assertEqual(self.calls(), [])
        self.assert_previous_unchanged()
        self.assertFalse(self.backups.exists())

    def test_failed_dusti_patch_preserves_previous_installation(self):
        self.seed_previous_install()
        (self.repo / "assets/wallpapers/shaders/dusti.patch").write_text("invalid patch\n")
        result = self.run_installer("--install-only")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("patch", result.stderr.lower())
        self.assert_previous_unchanged()
        self.assertFalse(self.backups.exists())

    def test_gallery_adds_credited_imports_and_external_no_heart_without_losing_stock_entries(self):
        result = self.run_installer("--install-only")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        index = json.loads((self.package / "contents/ui/shader_index.json").read_text())
        self.assertEqual(index["categories"], ["Fixture"])
        self.assertIn(self.stock_entry, index["shaders"])
        self.assertEqual(len(index["shaders"]), 4)
        entries = {entry["name"]: entry for entry in index["shaders"]}
        for name, source_id, author, license_name, path, textures in (
                ("Tokyo", "Xtf3zn", "Reinder Nijhoff", "CC BY-NC-SA 4.0", "Shaders/Tokyo.frag", False),
                ("Dusti [237 Chars]", "tcXXDB", "HellMood", "CC BY-NC-SA 3.0", "Shaders/Dusti.frag", False),
                ("Heartfelt No Heart", "ltffzl", "Martijn Steinrucken", "CC BY-NC-SA 3.0",
                 (self.artwork / "shaders" / SHADER).as_uri(), True)):
            entry = entries[name]
            self.assertEqual(entry["shaderPath"], path)
            self.assertEqual(entry["source"], "shadertoy")
            self.assertEqual(entry["sourceId"], source_id)
            self.assertIn(author, entry["author"])
            self.assertIn(license_name, entry["description"])
            self.assertEqual(entry["needsTextures"], textures)
            self.assertIs(entry["needsAudio"], False)
            self.assertIs(entry["hasBuffers"], False)
        self.assertEqual(len({entry["id"] for entry in index["shaders"]}), 4)

    def test_import_checksum_failure_preserves_previous_installation(self):
        self.seed_previous_install()
        self.tokyo.write_text("corrupted download\n")
        result = self.run_installer("--install-only")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SHA-256 verification failed", result.stderr)
        self.assert_previous_unchanged()
        self.assertFalse(self.backups.exists())

    def test_dusti_with_unexpected_inputs_is_rejected_before_replacement(self):
        self.seed_previous_install()
        old_hash = hashlib.sha256(self.dusti.read_bytes()).hexdigest()
        self.dusti_document["Shader"]["renderpass"][0]["inputs"] = [{"channel": 0, "ctype": "texture", "src": "/texture.png"}]
        self.dusti.write_text(json.dumps(self.dusti_document))
        manifest = self.base / "components.tsv"
        manifest.write_text(manifest.read_text().replace(old_hash, hashlib.sha256(self.dusti.read_bytes()).hexdigest()))
        result = self.run_installer("--install-only")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Dusti", result.stderr)
        self.assert_previous_unchanged()

    def test_one_existing_desktop_can_activate_no_heart(self):
        Path(self.env["DESKTOP_STATE"]).write_text(json.dumps([self.desktops[1]]))
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        desktops = json.loads(Path(self.env["DESKTOP_STATE"]).read_text())
        self.assertEqual(len(desktops), 1)
        self.assertEqual(desktops[0]["config"]["selectedShaderPath"], (self.artwork / "shaders" / SHADER).as_uri())

    def test_three_existing_desktops_can_activate_no_heart(self):
        third = {"id": 42, "screen": 2, "wallpaperPlugin": "org.kde.image", "config": {}}
        Path(self.env["DESKTOP_STATE"]).write_text(json.dumps([*self.desktops, third]))
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        desktops = json.loads(Path(self.env["DESKTOP_STATE"]).read_text())
        self.assertEqual(len(desktops), 3)
        for desktop in desktops:
            self.assertEqual(desktop["config"]["selectedShaderPath"], (self.artwork / "shaders" / SHADER).as_uri())

    def test_invalid_existing_screen_is_rejected_without_config_writes(self):
        self.desktops[0]["screen"] = "invalid"
        Path(self.env["DESKTOP_STATE"]).write_text(json.dumps(self.desktops))
        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads(Path(self.env["DESKTOP_STATE"]).read_text()), self.desktops)

    def test_parked_desktop_is_untouched_while_connected_primary_is_configured(self):
        self.desktops[0]["screen"] = -1
        Path(self.env["DESKTOP_STATE"]).write_text(json.dumps(self.desktops))
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        desktops = json.loads(Path(self.env["DESKTOP_STATE"]).read_text())
        self.assertEqual(desktops[0], self.desktops[0])
        self.assertEqual(desktops[1]["config"]["selectedShaderPath"], (self.artwork / "shaders" / SHADER).as_uri())

    def test_only_parked_desktops_is_not_success(self):
        for desktop in self.desktops:
            desktop["screen"] = -1
        Path(self.env["DESKTOP_STATE"]).write_text(json.dumps(self.desktops))
        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads(Path(self.env["DESKTOP_STATE"]).read_text()), self.desktops)

    def test_install_only_retains_selected_import_bundle_resources_and_unindexed_files(self):
        self.seed_previous_install()
        ui = self.package / "contents/ui"
        files = {
            "Shaders/Imported/My Shader.frag": b"// user's selected shader\n",
            "Shaders/Imported/My Shader_bufferA.frag": b"// user's buffer\n",
            "Shaders/Imported/textures/noise.bin": b"\x00\xff\x01",
            "Shaders/Custom Bundle/main.frag": b"// bundled main\n",
            "Shaders/Custom Bundle/manifest.json": b'{"name":"Custom Bundle"}\n',
            "Shaders/Custom Bundle/resources/image.bin": b"\x02\xff\x00",
            "Shaders/unindexed.frag": b"// not yet scanned\n",
            "Shaders6/local.frag": b"// secondary shader directory\n",
        }
        for relative, contents in files.items():
            path = ui / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(contents)
        selected = (ui / "Shaders/Imported/My Shader.frag").as_uri()
        saved_entry = dict(self.stock_entry, id="user-import-id", name="My Shader", shaderPath=selected,
                           favorite=True, source="imported", category="Personal", hasBuffers=True)
        saved_index = {"categories": ["Personal"], "shaders": [saved_entry]}
        (ui / "shader_index.json").write_text(json.dumps(saved_index))
        config = self.config / "plasma-org.kde.plasma.desktop-appletsrc"
        config_text = f"[Containments][12][Wallpaper][{PLUGIN}][General]\nselectedShaderPath={selected}\n"
        config.write_text(config_text)
        self.desktops[0].update(wallpaperPlugin=PLUGIN, config={"selectedShaderPath": selected})
        Path(self.env["DESKTOP_STATE"]).write_text(json.dumps(self.desktops))
        for _ in range(2):
            result = self.run_installer("--install-only")
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            for relative, contents in files.items():
                self.assertTrue((ui / relative).is_file(), f"lost user file: {relative}")
                self.assertEqual((ui / relative).read_bytes(), contents)
            index = json.loads((ui / "shader_index.json").read_text())
            self.assertEqual(index["shaders"].count(saved_entry), 1)
            self.assertEqual(len(index["shaders"]), 5)
            self.assertIn("Personal", index["categories"])
            self.assertEqual(config.read_text(), config_text)
            self.assertEqual(json.loads(Path(self.env["DESKTOP_STATE"]).read_text()), self.desktops)
        backup = next(self.backups.glob("shader-wallpaper-*/package/contents/ui/"))
        self.assertEqual((backup / "Shaders/Imported/My Shader.frag").read_bytes(), files["Shaders/Imported/My Shader.frag"])
        self.assertFalse(any(call[0] == "qdbus6" for call in self.calls()))

    def test_gallery_favorites_and_ids_survive_path_normalization_without_restoring_stale_managed_code(self):
        self.seed_previous_install()
        ui = self.package / "contents/ui"
        (ui / "Shaders").mkdir(parents=True)
        (ui / "Shaders/Heartfelt.frag").write_text(HEADER + LICENSE + "\n#define HAS_HEART\nvoid mainImage() {}\n")
        for name in ("Tokyo", "Dusti"):
            (ui / "Shaders" / f"{name}.frag").write_text(f"stale {name} shader\n")
        paths = [(ui / "Shaders/Heartfelt.frag").as_uri(), (ui / "Shaders/Tokyo.frag").as_uri(),
                 "Shaders/Dusti.frag", str(self.artwork / "shaders" / SHADER)]
        entries = [dict(self.stock_entry, id=f"saved-{number}", shaderPath=path, favorite=True,
                        description="stale metadata", thumbnailPath=f"file:///saved-thumb-{number}.png")
                   for number, path in enumerate(paths)]
        (ui / "shader_index.json").write_text(json.dumps({"categories": [], "shaders": entries}))
        result = self.run_installer("--install-only")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        index = json.loads((ui / "shader_index.json").read_text())
        self.assertEqual(len(index["shaders"]), 4)
        by_name = {entry["name"]: entry for entry in index["shaders"]}
        for number, name in enumerate(("Heartfelt", "Tokyo", "Dusti [237 Chars]", "Heartfelt No Heart")):
            self.assertTrue(by_name[name]["favorite"], name)
            self.assertEqual(by_name[name]["id"], f"saved-{number}")
            self.assertEqual(by_name[name]["thumbnailPath"], f"file:///saved-thumb-{number}.png")
            self.assertNotEqual(by_name[name]["description"], "stale metadata")
        self.assertTrue((ui / "Shaders/Tokyo.frag").read_text().endswith(self.tokyo_code))
        self.assertTrue((ui / "Shaders/Dusti.frag").read_text().endswith(self.dusti_adapted))
        self.assertTrue((self.artwork / "shaders" / SHADER).read_text().startswith(HEADER + LICENSE))

    def test_conflicting_bundled_shader_is_refused_without_losing_user_edits(self):
        self.seed_previous_install()
        shader = self.package / "contents/ui/Shaders/Heartfelt.frag"
        shader.parent.mkdir(parents=True)
        shader.write_text("user-edited bundled shader\n")
        result = self.run_installer("--install-only")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("collision", result.stderr.lower())
        self.assertEqual(shader.read_text(), "user-edited bundled shader\n")
        self.assert_previous_unchanged()
        self.assertFalse(self.backups.exists())

    def test_custom_directory_colliding_with_managed_shader_is_not_removed(self):
        self.seed_previous_install()
        resource = self.package / "contents/ui/Shaders/Tokyo.frag/resource.bin"
        resource.parent.mkdir(parents=True)
        resource.write_bytes(b"user resource")
        result = self.run_installer("--install-only")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("collision", result.stderr.lower())
        self.assertEqual(resource.read_bytes(), b"user resource")
        self.assert_previous_unchanged()

    def test_imported_gallery_id_collision_is_refused_before_replacement(self):
        self.seed_previous_install()
        ui = self.package / "contents/ui"
        shader = ui / "Shaders/Imported/custom.frag"
        shader.parent.mkdir(parents=True)
        shader.write_text("custom shader\n")
        entry = dict(self.stock_entry, shaderPath="Shaders/Imported/custom.frag")
        (ui / "shader_index.json").write_text(json.dumps({"categories": [], "shaders": [entry]}))
        result = self.run_installer("--install-only")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("collision", result.stderr.lower())
        self.assertEqual(shader.read_text(), "custom shader\n")
        self.assert_previous_unchanged()


if __name__ == "__main__":
    unittest.main()
