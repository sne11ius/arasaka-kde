import difflib
import hashlib
import json
import os
import runpy
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
RAIN = "Interactive_Rain.frag"
PENDING = "arasakaRainPending"
RAIN_SOURCES = ("dropletsimulation.h", "dropletsimulation.cpp", "rainfieldrenderer.h",
                "rainfieldrenderer.cpp", "raininput.h", "raininput.cpp")
HEADER = "// Heartfelt - by Martijn Steinrucken aka BigWings - 2017\n"
LICENSE = "// License Creative Commons Attribution-NonCommercial-ShareAlike 3.0 Unported License.\n"

# Only the external Plasma API is simulated; the actual wallpaper JavaScript runs.
PLASMA = r"""
const fs = require('fs');
const vm = require('vm');
const state = JSON.parse(fs.readFileSync(process.env.DESKTOP_STATE, 'utf8'));
const mutations = [];
const wrappers = [];
const context = {
    desktops: () => state.map(d => {
        let selectedPlugin = d.wallpaperPlugin;
        wrappers.push(() => {
            if (selectedPlugin === d.wallpaperPlugin) return;
            mutations.push({id: d.id, operation: 'wallpaperCommit', value: selectedPlugin, config: {...d.config}});
            if (process.env.CHECK_PRIVACY && (d.config.audioEnabled || d.config.mouseEnabled ||
                    d.config.windowsEnabled || d.config.playlistEnabled)) {
                throw Error('capture/playlist enabled when committing wallpaper');
            }
            if (!process.env.REJECT_PLUGIN_COMMIT) d.wallpaperPlugin = selectedPlugin;
        });
        return {
        id: d.id, screen: d.screen,
        get wallpaperPlugin() { return selectedPlugin; },
        set wallpaperPlugin(value) {
            mutations.push({id: d.id, operation: 'wallpaperPlugin', value, config: {...d.config}});
            selectedPlugin = value;
        },
        configGroup: [],
        get currentConfigGroup() { return this.configGroup; },
        set currentConfigGroup(value) {
            this.configGroup = value;
        },
        writeConfig(key, value) {
            mutations.push({id: d.id, operation: 'writeConfig', key, value, activePlugin: d.wallpaperPlugin});
            if (JSON.stringify(this.currentConfigGroup) !==
                JSON.stringify(['Wallpaper', 'online.knowmad.shaderwallpaper', 'General'])) {
                throw Error('unexpected configuration group');
            }
            if (key !== process.env.REJECT_SETTING && !(process.env.REJECT_MOUSE_ENABLE &&
                    key === 'mouseEnabled' && value === true)) d.config[key] = value;
        },
        readConfig(key, fallback) {
            if (!(key in d.config)) return fallback;
            // Plasma's KConfig readEntry converts to the fallback's type.
            return fallback === undefined || typeof fallback === 'string' ? String(d.config[key]) : d.config[key];
        }
    }; }),
    screenForConnector: connector => ({'eDP-1': 0, 'HDMI-A-1': 1, 'DP-1': 2}[connector] ?? -1),
    print: value => console.log(value)
};
let failure;
const output = [];
context.print = value => output.push(value);
try { vm.runInNewContext(process.argv[1], context); }
catch (error) { failure = error; }
// Plasma applies cached wallpaper assignments at wrapper destruction, even on error.
try { wrappers.forEach(commit => commit()); }
catch (error) { failure = error; }
console.log(failure ? 'Error: ' + failure.message : output.join('\n'));
fs.writeFileSync(process.env.DESKTOP_STATE, JSON.stringify(state));
if (process.env.MUTATION_LOG) fs.writeFileSync(process.env.MUTATION_LOG, JSON.stringify(mutations));
"""


class ShaderWallpaperScriptTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="shader-script-test-", dir="/tmp/opencode")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.data = self.base / 'data "quoted" \\ space#%?'
        self.desktops = [
            {"id": 12, "screen": 0, "wallpaperPlugin": PLUGIN, "config": {
                "selectedShaderPath": "file:///custom.frag", "selectedShaderCode": "custom shader code",
                "targetFps": 144, "shaderSpeed": 1.5, "running": False, "audioEnabled": True,
                "mouseEnabled": True, "windowsEnabled": True, "playlistEnabled": True,
                "commonCode": "custom common code", "useBufferA": True, "customSetting": [1, "keep"],
            }},
            {"id": 27, "screen": 1, "wallpaperPlugin": "org.kde.image", "config": {
                "audioEnabled": True, "mouseEnabled": True, "windowsEnabled": True, "playlistEnabled": True,
            }},
            {"id": 42, "screen": 2, "wallpaperPlugin": "org.kde.image", "config": {}},
        ]

    def run_template(self, desktops, ensure_only=True, connectors=("eDP-1", "HDMI-A-1", "DP-1"), phase=None, defaults=None, **env):
        script = (ROOT / "plasma/shader-wallpaper.js").read_text()
        defaults = defaults or json.loads((ROOT / "plasma/wallpaper-defaults.json").read_text())
        script = script.replace("__WALLPAPER_DEFAULTS_JSON__", json.dumps(defaults))
        for key, value in {"DATA_HOME": str(self.data), "PRIMARY_CONNECTOR": "HDMI-A-1",
                           "ENABLED_CONNECTORS": connectors}.items():
            script = script.replace(f"__{key}_JSON__", json.dumps(value))
        if ensure_only is not None:
            script = script.replace("__ENSURE_ONLY__", json.dumps(ensure_only))
        state = self.base / "desktops.json"
        mutations = self.base / "mutations.json"
        state.write_text(json.dumps(desktops))
        environment = dict(os.environ, DESKTOP_STATE=str(state), MUTATION_LOG=str(mutations))
        for name in ("CHECK_PRIVACY", "REJECT_SETTING", "REJECT_MOUSE_ENABLE", "REJECT_PLUGIN_COMMIT"):
            environment.pop(name, None)
        events = []
        for current_phase in ((phase,) if phase else ("prepare", "activate")):
            result = subprocess.run(["node", "-e", PLASMA, script.replace("__SHADER_PHASE__", current_phase)],
                                    env=dict(environment, **env), text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            events += [dict(event, phase=current_phase) for event in json.loads(mutations.read_text())]
            if result.stdout.startswith("Error:"):
                break
        return result.stdout.strip(), json.loads(state.read_text()), events

    def test_ensure_initializes_three_active_screens_but_preserves_custom_shader_and_parked_desktop(self):
        parked = {"id": 99, "screen": -1, "wallpaperPlugin": "org.kde.image", "config": {"keep": True}}
        output, desktops, mutations = self.run_template([*self.desktops, parked], CHECK_PRIVACY="1")
        self.assertTrue(output.startswith("ARASAKA_SHADER_WALLPAPER="), output)
        self.assertEqual(desktops[0], self.desktops[0])
        self.assertEqual(desktops[3], parked)
        self.assertEqual({mutation["id"] for mutation in mutations}, {27, 42})
        report = json.loads(output.removeprefix("ARASAKA_SHADER_WALLPAPER="))
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["primaryScreen"], 1)
        self.assertEqual(report["desktops"][0], {
            "id": 12, "screen": 0, "wallpaperPlugin": PLUGIN, "preserved": True,
        })
        self.assertEqual(len(report["desktops"]), 3)
        for desktop, image, entry in zip(desktops[1:3], ("mikoshi-16x9.png", "mikoshi-16x10.png"),
                                         report["desktops"][1:]):
            self.assertEqual(desktop["wallpaperPlugin"], PLUGIN)
            for key, value in {
                "selectedShaderPath": (self.data / "wallpapers/Arasaka/shaders" / RAIN).as_uri(),
                "selectedShaderCode": "", "running": True, "shaderSpeed": 0.75, "targetFps": 30,
                "iChannel0": (self.data / "wallpapers/Arasaka" / image).as_uri(),
                "mouseEnabled": True, "audioEnabled": False, "windowsEnabled": False, "playlistEnabled": False,
            }.items():
                self.assertEqual(desktop["config"][key], value, key)
                self.assertEqual(entry["config"][key], value, key)

    def test_ensure_is_idempotent_with_an_all_preserved_report_and_no_writes(self):
        output, desktops, _ = self.run_template(self.desktops)
        self.assertTrue(output.startswith("ARASAKA_SHADER_WALLPAPER="), output)
        output, repeated, mutations = self.run_template(desktops)
        self.assertEqual(mutations, [])
        self.assertEqual(repeated, desktops)
        self.assertEqual(json.loads(output.removeprefix("ARASAKA_SHADER_WALLPAPER=")), {
            "status": "ok", "primaryScreen": 1, "desktops": [
                {"id": 12, "screen": 0, "wallpaperPlugin": PLUGIN, "preserved": True},
                {"id": 27, "screen": 1, "wallpaperPlugin": PLUGIN, "preserved": True},
                {"id": 42, "screen": 2, "wallpaperPlugin": PLUGIN, "preserved": True},
            ],
        })

    def test_login_defaults_match_activated_desktop_effect_and_interaction(self):
        output, desktops, _ = self.run_template(self.desktops, ensure_only=False)
        self.assertTrue(output.startswith("ARASAKA_SHADER_WALLPAPER="), output)
        login = runpy.run_path(str(ROOT / "bin/apply-plm"))["SHADER"]
        desktop = desktops[1]["config"]
        for key, value in login.items():
            if key == "pauseMode":
                self.assertEqual(value, "3")
                self.assertEqual(desktop[key], 0)
            elif key in ("selectedShaderPath", "iChannel0"):
                self.assertEqual(Path(value).name, Path(desktop[key]).name)
            else:
                actual = desktop.get(key, False if key == "watchSourceFile" else None)
                if isinstance(actual, bool):
                    actual = str(actual).lower()
                elif isinstance(actual, list):
                    actual = ",".join(actual)
                self.assertEqual(value, str(actual), key)

    def test_shared_profile_changes_reach_every_activated_desktop(self):
        defaults = json.loads((ROOT / "plasma/wallpaper-defaults.json").read_text())
        defaults.update(targetFps=45, shaderSpeed=.5, mouseEnabled=False, iChannel0="new-artwork.png")
        output, desktops, _ = self.run_template(self.desktops, ensure_only=False, defaults=defaults)
        self.assertTrue(output.startswith("ARASAKA_SHADER_WALLPAPER="), output)
        for desktop in desktops:
            self.assertEqual(desktop["config"]["mouseEnabled"], False)
            self.assertEqual(desktop["config"]["targetFps"], 45)
            self.assertEqual(desktop["config"]["shaderSpeed"], .5)
            self.assertEqual(desktop["config"]["iChannel0"], (self.data / "wallpapers/Arasaka/new-artwork.png").as_uri())

    def test_missing_secondary_coverage_fails_before_any_writes_in_both_modes(self):
        for ensure_only in (True, False):
            for connector in ("DP-1", "unmapped"):
                with self.subTest(ensure_only=ensure_only, connector=connector):
                    parked = dict(self.desktops[2], screen=-1)
                    initial = [*self.desktops[:2], parked]
                    output, desktops, mutations = self.run_template(
                        initial, ensure_only=ensure_only, connectors=("eDP-1", "HDMI-A-1", connector))
                    self.assertTrue(output.startswith("Error:"), output)
                    self.assertIn(connector, output)
                    self.assertEqual(mutations, [])
                    self.assertEqual(desktops, initial)

    def test_explicit_and_unrendered_modes_reset_existing_shader_settings(self):
        for ensure_only in (False, None):
            with self.subTest(ensure_only=ensure_only):
                output, desktops, mutations = self.run_template(self.desktops, ensure_only=ensure_only, CHECK_PRIVACY="1")
                self.assertTrue(output.startswith("ARASAKA_SHADER_WALLPAPER="), output)
                self.assertEqual({mutation["id"] for mutation in mutations}, {12, 27, 42})
                self.assertEqual(desktops[0]["config"]["selectedShaderPath"],
                                 (self.data / "wallpapers/Arasaka/shaders" / RAIN).as_uri())
                self.assertEqual(desktops[0]["config"]["selectedShaderCode"], "")
                self.assertEqual(desktops[0]["config"]["targetFps"], 30)
                for desktop in desktops:
                    self.assertIs(desktop["config"]["mouseEnabled"], True)
                    self.assertIs(desktop["config"][PENDING], False)
                    events = [event for event in mutations if event["id"] == desktop["id"]]
                    enables = [event for event in events if event.get("key") == "mouseEnabled" and event["value"] is True]
                    self.assertEqual(len(enables), 1)
                    self.assertEqual(enables[0]["phase"], "activate")
                    self.assertEqual(enables[0]["activePlugin"], PLUGIN)
                    for event in events:
                        if event["operation"] == "wallpaperCommit":
                            self.assertEqual(event["phase"], "prepare")
                            self.assertEqual(event["config"]["selectedShaderPath"],
                                             (self.data / "wallpapers/Arasaka/shaders" / RAIN).as_uri())
                            self.assertEqual(event["config"]["selectedShaderCode"], "")
                            self.assertIs(event["config"]["mouseEnabled"], False)

    def test_prepare_commits_with_mouse_off_and_interruption_resumes_only_pending_targets(self):
        output, prepared, events = self.run_template(self.desktops, phase="prepare", CHECK_PRIVACY="1")
        self.assertTrue(output.startswith("ARASAKA_SHADER_WALLPAPER="), output)
        self.assertEqual(json.loads(output.removeprefix("ARASAKA_SHADER_WALLPAPER="))["status"], "prepared")
        self.assertEqual(prepared[0], self.desktops[0])
        self.assertEqual(sum(event["operation"] == "wallpaperCommit" for event in events), 2)
        for desktop in prepared[1:]:
            self.assertEqual(desktop["wallpaperPlugin"], PLUGIN)
            self.assertIs(desktop["config"]["mouseEnabled"], False)
            self.assertIs(desktop["config"][PENDING], True)
        output, resumed, events = self.run_template(prepared, CHECK_PRIVACY="1")
        self.assertTrue(output.startswith("ARASAKA_SHADER_WALLPAPER="), output)
        self.assertEqual(resumed[0], self.desktops[0])
        self.assertFalse(any(event["operation"] == "wallpaperPlugin" for event in events))
        for desktop in resumed[1:]:
            self.assertIs(desktop["config"]["mouseEnabled"], True)
            self.assertIs(desktop["config"][PENDING], False)

    def test_fresh_evaluation_rejects_uncommitted_plugin_without_optin_and_retries(self):
        output, failed, events = self.run_template(self.desktops, REJECT_PLUGIN_COMMIT="1", CHECK_PRIVACY="1")
        self.assertTrue(output.startswith("Error:"), output)
        self.assertIn("plugin mismatch", output)
        self.assertEqual(failed[1]["wallpaperPlugin"], "org.kde.image")
        self.assertIs(failed[1]["config"][PENDING], True)
        self.assertFalse(any(event.get("key") == "mouseEnabled" and event["value"] is True for event in events))
        output, resumed, _ = self.run_template(failed, CHECK_PRIVACY="1")
        self.assertTrue(output.startswith("ARASAKA_SHADER_WALLPAPER="), output)
        self.assertIs(resumed[1]["config"]["mouseEnabled"], True)

    def test_pending_custom_changes_are_preserved_in_both_phases_and_on_retry(self):
        for key, value in (("selectedShaderPath", "file:///user-selected.frag"),
                           ("selectedShaderCode", "user edited inline shader"),
                           ("targetFps", 17), ("audioEnabled", True), ("useBufferA", True)):
            for ensure_only in (True, False):
                with self.subTest(key=key, ensure_only=ensure_only):
                    output, prepared, _ = self.run_template(self.desktops, phase="prepare", ensure_only=ensure_only)
                    self.assertTrue(output.startswith("ARASAKA_SHADER_WALLPAPER="), output)
                    prepared[1]["config"][key] = value
                    cancelled = dict(prepared[1], config=dict(prepared[1]["config"], **{PENDING: False}))
                    output, result, events = self.run_template(prepared, phase="activate", ensure_only=ensure_only)
                    self.assertEqual(result[1], cancelled if ensure_only else prepared[1])
                    self.assertTrue(all(event.get("key") == PENDING and event["value"] is False
                                        for event in events if event["id"] == 27))
                    if not ensure_only:
                        self.assertTrue(output.startswith("Error:"), output)
                    output, retried, events = self.run_template(result)
                    self.assertEqual(retried[1], cancelled)
                    self.assertTrue(all(event.get("key") == PENDING and event["value"] is False
                                        for event in events if event["id"] == 27))

    def test_activation_rechecks_coverage_before_any_optin(self):
        output, prepared, _ = self.run_template(self.desktops, phase="prepare")
        self.assertTrue(output.startswith("ARASAKA_SHADER_WALLPAPER="), output)
        prepared[2]["screen"] = -1
        output, result, events = self.run_template(prepared, phase="activate")
        self.assertTrue(output.startswith("Error:"), output)
        self.assertIn("DP-1", output)
        self.assertEqual(result, prepared)
        self.assertEqual(events, [])

    def test_changed_selection_cancels_pending_optin_even_if_user_returns_to_rain(self):
        output, prepared, _ = self.run_template(self.desktops, phase="prepare")
        self.assertTrue(output.startswith("ARASAKA_SHADER_WALLPAPER="), output)
        rain_path = prepared[1]["config"]["selectedShaderPath"]
        prepared[1]["config"]["selectedShaderPath"] = "file:///chosen-in-gallery.frag"
        output, changed, _ = self.run_template(prepared)
        self.assertTrue(output.startswith("ARASAKA_SHADER_WALLPAPER="), output)
        self.assertEqual(changed[1]["config"]["selectedShaderPath"], "file:///chosen-in-gallery.frag")
        changed[1]["config"]["selectedShaderPath"] = rain_path
        output, returned, events = self.run_template(changed)
        self.assertTrue(output.startswith("ARASAKA_SHADER_WALLPAPER="), output)
        self.assertIs(returned[1]["config"]["mouseEnabled"], False)
        self.assertFalse(any(event["id"] == 27 for event in events))

    def test_activate_never_initializes_an_unprepared_desktop(self):
        output, result, events = self.run_template(self.desktops, phase="activate")
        self.assertTrue(output.startswith("Error:"), output)
        self.assertEqual(result, self.desktops)
        self.assertEqual(events, [])

    def test_failed_hover_enable_is_verified_and_initialization_remains_retryable(self):
        desktops = self.desktops
        for _ in range(2):
            output, desktops, _ = self.run_template(desktops, REJECT_MOUSE_ENABLE="1", CHECK_PRIVACY="1")
            self.assertTrue(output.startswith("Error:"), output)
            self.assertIn("desktop 27: mouseEnabled", output)
            self.assertEqual(desktops[1]["wallpaperPlugin"], PLUGIN)
            self.assertIs(desktops[1]["config"]["mouseEnabled"], False)
            self.assertIs(desktops[1]["config"][PENDING], True)
        output, desktops, _ = self.run_template(desktops, CHECK_PRIVACY="1")
        self.assertTrue(output.startswith("ARASAKA_SHADER_WALLPAPER="), output)
        self.assertIs(desktops[1]["config"]["mouseEnabled"], True)

    def test_ensure_keeps_readback_checks_for_initialized_desktops(self):
        desktops = self.desktops
        for _ in range(2):
            output, desktops, _ = self.run_template(desktops, REJECT_SETTING="targetFps")
            self.assertTrue(output.startswith("Error:"), output)
            self.assertIn("desktop 27: targetFps", output)
            self.assertEqual(desktops[1]["wallpaperPlugin"], "org.kde.image")
        output, desktops, _ = self.run_template(desktops)
        self.assertTrue(output.startswith("ARASAKA_SHADER_WALLPAPER="), output)
        self.assertEqual(desktops[1]["config"]["targetFps"], 30)
        self.assertEqual(desktops[1]["wallpaperPlugin"], PLUGIN)


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
                          self.repo / "assets/wallpapers/shaders", self.repo / "native/rain", self.home,
                          self.config, self.tools, self.base / "tmp"):
            directory.mkdir(parents=True, exist_ok=True)
        for relative in ("bin/fetch-components", "lib/common.sh", "lib/arasaka_topology.py",
                         "assets/wallpapers/mikoshi-16x9.svg", "assets/wallpapers/mikoshi-16x10.svg",
                         "bin/apply-shader-wallpaper", "bin/reconcile-displays", "plasma/shader-wallpaper.js", "plasma/wallpaper-defaults.json"):
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
        for name in RAIN_SOURCES:
            (self.repo / "native/rain" / name).write_text(f"// required native source: {name}\n")
        # Only the patched CMake project validates copied inputs and emits this artifact.
        host_checks = ["set(rain_marker \"\")"]
        for name in RAIN_SOURCES:
            host_checks += [f'file(READ "${{CMAKE_SOURCE_DIR}}/src/rain/{name}" rain_source)',
                            f'if(NOT rain_source STREQUAL "// required native source: {name}\\n")',
                            f'    message(FATAL_ERROR "incorrect native source: {name}")',
                            'endif()', 'string(APPEND rain_marker "${rain_source}")']
        host_checks += ['file(WRITE "${CMAKE_SOURCE_DIR}/package/rain-extension.txt" "${rain_marker}")']
        (self.repo / "assets/wallpapers/shaders/interactive-rain-host.patch").write_text(
            "--- a/CMakeLists.txt\n+++ b/CMakeLists.txt\n"
            f"@@ -1,4 +1,{4 + len(host_checks)} @@\n"
            " cmake_minimum_required(VERSION 3.22)\n project(shader_fixture LANGUAGES C)\n" +
            "".join("+" + line + "\n" for line in host_checks) +
            " add_library(shaderwallpaperplugin MODULE plugin.c)\n"
            ' set(out "${CMAKE_SOURCE_DIR}/package/contents/ui/shaderwallpaper")\n')
        patch = self.repo / "assets/wallpapers/shaders/heartfelt-no-heart.patch"
        patch.write_text("--- a/Heartfelt_No_Heart.frag\n+++ b/Heartfelt_No_Heart.frag\n"
                         "@@ -1,5 +1,5 @@\n " + HEADER + " " + LICENSE + " \n"
                          "-#define HAS_HEART\n+// Arasaka adaptation; source: upstream Heartfelt.frag\n"
                         " void mainImage() {}\n")
        self.noheart_code = HEADER + LICENSE + "\n// Arasaka adaptation; source: upstream Heartfelt.frag\nvoid mainImage() {}\n"
        self.rain_code = self.noheart_code.replace("void mainImage() {}\n",
            "// @channels tex0,none,none,none\n// @arasaka-effect rain-v1\n"
            "uniform sampler2D iRainField;\nvoid mainImage() {}\n")
        self.rain_patch = self.repo / "assets/wallpapers/shaders/interactive-rain.patch"
        self.rain_patch.write_text("--- a/Interactive_Rain.frag\n+++ b/Interactive_Rain.frag\n"
            "@@ -4,2 +4,5 @@\n // Arasaka adaptation; source: upstream Heartfelt.frag\n"
            "+// @channels tex0,none,none,none\n+// @arasaka-effect rain-v1\n"
            "+uniform sampler2D iRainField;\n void mainImage() {}\n")
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
        for name in ("FAIL_BUILD", "OMIT_PLUGIN", "BAD_DBUS", "REJECT_SETTING", "CHECK_PRIVACY",
                     "REJECT_MOUSE_ENABLE", "REJECT_PLUGIN_COMMIT", "FAIL_ACTIVATE", "ARASAKA_SHADER_BUILD_JOBS"):
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
            if os.environ.get('FAIL_ACTIVATE') and 'var shaderPhase = "activate";' in sys.argv[4]:
                sys.exit('fixture interruption after prepare')
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
        for name in ("mikoshi-16x9.png", "mikoshi-16x10.png", f"shaders/{SHADER}", f"shaders/{RAIN}"):
            (self.artwork / name).write_text(f"previous {name}\n")
        (self.artwork / "unrelated.txt").write_text("keep\n")
        (self.config / "plasma-org.kde.plasma.desktop-appletsrc").write_text("previous plasma config\n")
        runtime = self.home / ".local/libexec/arasaka-kde"
        runtime.mkdir(parents=True)
        (runtime / "layout.js").write_text("previous runtime layout\n")

    def assert_previous_unchanged(self):
        self.assertEqual((self.package / "previous.txt").read_text(), "previous package\n")
        self.assertEqual((self.artwork / "mikoshi-16x9.png").read_text(), "previous mikoshi-16x9.png\n")
        for name in (SHADER, RAIN):
            self.assertEqual((self.artwork / "shaders" / name).read_text(), f"previous shaders/{name}\n")
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
        self.assertEqual(adapted, self.noheart_code)
        self.assertTrue((self.package / "rain-extension.txt").is_file(), "host integration was not configured")
        self.assertTrue((self.artwork / "shaders" / RAIN).is_file(), "Interactive Rain was not installed")
        self.assertEqual((self.artwork / "shaders" / RAIN).read_text(), self.rain_code)
        self.assertEqual((self.package / "rain-extension.txt").read_text(),
                         "".join(f"// required native source: {name}\n" for name in RAIN_SOURCES))
        for name, size in (("mikoshi-16x9.png", (1920, 1080)), ("mikoshi-16x10.png", (1600, 1000))):
            self.assertEqual(struct.unpack(">II", (self.artwork / name).read_bytes()[16:24]), size)
        self.assertEqual({call[0] for call in self.calls()}, {"cmake"})
        builds = [call for call in self.calls() if "--build" in call]
        self.assertEqual(builds[0][-2:], ["--parallel", "4"])
        self.assertFalse((self.home / ".local/lib/qml").exists())
        self.assertFalse(list(self.repo.rglob("*.png")))

    def test_default_activation_configures_both_desktops_with_escaped_absolute_urls_and_backups(self):
        self.seed_previous_install()
        self.desktops[0].update(wallpaperPlugin=PLUGIN, config={
            "selectedShaderPath": "file:///custom.frag", "selectedShaderCode": "custom", "targetFps": 144,
        })
        Path(self.env["DESKTOP_STATE"]).write_text(json.dumps(self.desktops))
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        desktops = json.loads(Path(self.env["DESKTOP_STATE"]).read_text())
        expected = {
            "selectedShaderPath": (self.artwork / "shaders" / RAIN).as_uri(),
            "selectedShaderCode": "", "running": True, "shaderSpeed": 0.75,
            "targetFps": 30, "resolutionScale": 1, "pauseMode": 0, "checkActiveScreen": True,
            "mouseEnabled": True, "audioEnabled": False, "windowsEnabled": False,
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
                               (f"artwork/shaders/{RAIN}", f"previous shaders/{RAIN}\n"),
                               ("plasma-org.kde.plasma.desktop-appletsrc", "previous plasma config\n"),
                               ("runtime/layout.js", "previous runtime layout\n")):
            self.assertEqual((backup / relative).read_text(), text)
        self.assertEqual((self.artwork / "unrelated.txt").read_text(), "keep\n")
        self.assertEqual((self.home / ".local/libexec/arasaka-kde/layout.js").read_text(), "previous runtime layout\n")
        self.assertEqual([call[1:] for call in self.calls() if call[0] == "kscreen-doctor"], [["--json"]])
        calls = [call for call in self.calls() if call[0] == "qdbus6"]
        self.assertEqual(len(calls), 2)
        self.assertIn('var shaderPhase = "prepare";', calls[0][-1])
        self.assertIn('var shaderPhase = "activate";', calls[1][-1])

    def test_activation_interruption_leaves_committed_pending_rain_with_mouse_off(self):
        result = self.run_installer(FAIL_ACTIVATE="1", CHECK_PRIVACY="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("interruption after prepare", result.stderr)
        for desktop in json.loads(Path(self.env["DESKTOP_STATE"]).read_text()):
            self.assertEqual(desktop["wallpaperPlugin"], PLUGIN)
            self.assertIs(desktop["config"]["mouseEnabled"], False)
            self.assertIs(desktop["config"][PENDING], True)
        result = self.run_installer(CHECK_PRIVACY="1")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        for desktop in json.loads(Path(self.env["DESKTOP_STATE"]).read_text()):
            self.assertIs(desktop["config"]["mouseEnabled"], True)
            self.assertIs(desktop["config"][PENDING], False)

    def test_installer_does_not_trust_cached_plugin_report_when_commit_is_ignored(self):
        result = self.run_installer(REJECT_PLUGIN_COMMIT="1", CHECK_PRIVACY="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("plugin mismatch", result.stderr)
        for desktop in json.loads(Path(self.env["DESKTOP_STATE"]).read_text()):
            self.assertIs(desktop["config"]["mouseEnabled"], False)
            self.assertIs(desktop["config"][PENDING], True)

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
                       self.artwork / "shaders" / RAIN,
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

    def test_refresh_updates_existing_desktops_and_the_published_hotplug_profile(self):
        profile = self.repo / "plasma/wallpaper-defaults.json"
        defaults = json.loads(profile.read_text())
        defaults.update(targetFps=45, shaderSpeed=.5)
        profile.write_text(json.dumps(defaults))
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        for desktop in json.loads(Path(self.env["DESKTOP_STATE"]).read_text()):
            self.assertEqual(desktop["config"]["targetFps"], 45)
            self.assertEqual(desktop["config"]["shaderSpeed"], .5)
        runtime = self.home / ".local/libexec/arasaka-kde"
        self.assertTrue((runtime / "wallpaper-defaults.json").is_file(), "background refresh must publish hotplug defaults")
        self.assertTrue((runtime / "reconcile-displays").is_file())
        script = (runtime / "shader-wallpaper.js").read_text()
        values = {"WALLPAPER_DEFAULTS": json.loads((runtime / "wallpaper-defaults.json").read_text()),
                  "DATA_HOME": str(self.data), "PRIMARY_CONNECTOR": "HDMI-A-1", "ENABLED_CONNECTORS": ["HDMI-A-1"]}
        for key, value in values.items():
            script = script.replace(f"__{key}_JSON__", json.dumps(value))
        script = script.replace("__ENSURE_ONLY__", "true")
        Path(self.env["DESKTOP_STATE"]).write_text(json.dumps([
            {"id": 77, "screen": 1, "wallpaperPlugin": "org.kde.image", "config": {}}]))
        for phase in ("prepare", "activate"):
            result = subprocess.run(["node", "-e", PLASMA, script.replace("__SHADER_PHASE__", phase)],
                                    env=self.env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(result.stdout.startswith("ARASAKA_SHADER_WALLPAPER="), result.stdout)
        config = json.loads(Path(self.env["DESKTOP_STATE"]).read_text())[0]["config"]
        self.assertEqual(config["targetFps"], 45)
        self.assertEqual(config["shaderSpeed"], .5)
        self.assertTrue(config["mouseEnabled"])

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
                "selectedShaderPath": (self.artwork / "shaders" / RAIN).as_uri(),
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

    def test_missing_rain_inputs_fail_preflight_in_user_and_stage_modes(self):
        self.seed_previous_install()
        inputs = [self.repo / "native/rain" / name for name in RAIN_SOURCES]
        inputs += [self.rain_patch, self.rain_patch.with_name("interactive-rain-host.patch")]
        destination = self.base / "system-stage"
        for path in inputs:
            contents = path.read_bytes()
            path.unlink()
            try:
                for args in (("--install-only",), ("--stage-only", str(destination))):
                    with self.subTest(path=path.name, args=args):
                        result = self.run_installer(*args)
                        self.assertNotEqual(result.returncode, 0, result.stdout)
                        self.assertIn(path.name, result.stderr)
                        self.assertEqual(self.calls(), [])
                        self.assert_previous_unchanged()
                        self.assertFalse(self.backups.exists())
                        self.assertFalse(destination.exists())
            finally:
                path.write_bytes(contents)

    def test_symlinked_rain_inputs_and_source_parent_are_rejected_in_both_modes(self):
        self.seed_previous_install()
        inputs = [self.repo / "native/rain" / name for name in RAIN_SOURCES]
        inputs += [self.repo / "native/rain", self.rain_patch,
                   self.rain_patch.with_name("interactive-rain-host.patch")]
        for path in inputs:
            original = path.with_name(path.name + ".real")
            path.rename(original)
            path.symlink_to(original, target_is_directory=original.is_dir())
            try:
                for args in (("--install-only",), ("--stage-only", str(self.base / "system-stage"))):
                    with self.subTest(path=path.name, args=args):
                        result = self.run_installer(*args)
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn("symlink", result.stderr.lower())
                        self.assertEqual(self.calls(), [])
                        self.assert_previous_unchanged()
            finally:
                path.unlink()
                original.rename(path)

    def test_failed_host_patch_prevents_configure_build_and_replacement(self):
        self.seed_previous_install()
        patch = self.rain_patch.with_name("interactive-rain-host.patch")
        # Only a fuzzy application could ignore this mismatched context line.
        patch.write_text(patch.read_text().replace("cmake_minimum_required(VERSION 3.22)",
                                                  "cmake_minimum_required(VERSION 9.99)"))
        result = self.run_installer("--install-only")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("patch", result.stderr.lower())
        self.assertEqual(self.calls(), [])
        self.assert_previous_unchanged()
        self.assertFalse(self.backups.exists())

    def test_failed_rain_shader_patch_preserves_previous_assets_and_config(self):
        self.seed_previous_install()
        self.rain_patch.write_text(self.rain_patch.read_text().replace(
            "// Arasaka adaptation; source: upstream Heartfelt.frag", "// wrong adaptation step"))
        result = self.run_installer("--install-only")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("patch", result.stderr.lower())
        self.assert_previous_unchanged()
        self.assertFalse(self.backups.exists())

    def test_rain_shader_validation_rejects_missing_interface_and_lost_license(self):
        self.seed_previous_install()
        original = self.rain_patch.read_text()
        for before, after in (("// @arasaka-effect rain-v1", "// @arasaka-effect rain-v1 extra"),
                              ("uniform sampler2D iRainField;", "// uniform sampler2D iRainField;"),
                              ("void mainImage() {}", "void missingEntry() {}"),
                              (LICENSE.rstrip(), "// lost license")):
            with self.subTest(before=before):
                # Generate a valid patch with the wrong output, so validation must catch it.
                bad_code = self.rain_code.replace(before, after)
                self.rain_patch.write_text("".join(difflib.unified_diff(
                    self.noheart_code.splitlines(keepends=True), bad_code.splitlines(keepends=True),
                    fromfile="a/Interactive_Rain.frag", tofile="b/Interactive_Rain.frag")))
                result = self.run_installer("--install-only")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("shader", result.stderr.lower())
                self.assert_previous_unchanged()
                self.assertFalse(self.backups.exists())
        self.rain_patch.write_text(original)

    def test_stage_only_exports_extended_plugin_and_both_shaders_with_system_urls(self):
        self.seed_previous_install()
        destination = self.base / "system-stage"
        # Only the six explicit files belong in the build inputs.
        (self.repo / "native/rain/ignored.cpp").symlink_to(self.base / "missing.cpp")
        result = self.run_installer("--stage-only", str(destination))
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        package = destination / "usr/share/plasma/wallpapers" / PLUGIN
        artwork = destination / "usr/share/wallpapers/Arasaka"
        self.assertTrue((package / "contents/ui/shaderwallpaper/libshaderwallpaperplugin.so").read_bytes().startswith(b"\x7fELF"))
        self.assertTrue((package / "rain-extension.txt").is_file(), "host integration was not staged")
        self.assertEqual((package / "rain-extension.txt").read_text(),
                         "".join(f"// required native source: {name}\n" for name in RAIN_SOURCES))
        self.assertEqual((artwork / "shaders" / SHADER).read_text(), self.noheart_code)
        self.assertEqual((artwork / "shaders" / RAIN).read_text(), self.rain_code)
        index = json.loads((package / "contents/ui/shader_index.json").read_text())
        entries = {entry["id"]: entry for entry in index["shaders"]}
        self.assertEqual(len(entries), 5)
        self.assertEqual(entries["arasaka-interactive-rain"]["shaderPath"],
                         "file:///usr/share/wallpapers/Arasaka/shaders/Interactive_Rain.frag")
        self.assertEqual(entries["arasaka-heartfelt-no-heart"]["shaderPath"],
                         "file:///usr/share/wallpapers/Arasaka/shaders/Heartfelt_No_Heart.frag")
        self.assertNotIn(str(self.home), json.dumps(index))
        self.assertNotIn(str(destination), json.dumps(index))
        for path in destination.rglob("*"):
            self.assertFalse(path.is_symlink())
            self.assertEqual(path.stat().st_mode & 0o777, 0o755 if path.is_dir() else 0o644)
        self.assertEqual({call[0] for call in self.calls()}, {"cmake"})
        configure = next(call for call in self.calls() if "-S" in call)
        self.assertIn("-DBUILD_TESTING=OFF", configure)
        self.assertIn("-DCMAKE_SKIP_RPATH=ON", configure)
        self.assert_previous_unchanged()
        self.assertFalse(self.backups.exists())
        self.assertEqual(json.loads(Path(self.env["DESKTOP_STATE"]).read_text()), self.desktops)

    def test_gallery_adds_credited_imports_and_external_no_heart_without_losing_stock_entries(self):
        result = self.run_installer("--install-only")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        index = json.loads((self.package / "contents/ui/shader_index.json").read_text())
        self.assertEqual(index["categories"], ["Fixture"])
        self.assertIn(self.stock_entry, index["shaders"])
        self.assertEqual(len(index["shaders"]), 5)
        entries = {entry["name"]: entry for entry in index["shaders"]}
        for name, source_id, author, license_name, path, textures in (
                ("Tokyo", "Xtf3zn", "Reinder Nijhoff", "CC BY-NC-SA 4.0", "Shaders/Tokyo.frag", False),
                ("Dusti [237 Chars]", "tcXXDB", "HellMood", "CC BY-NC-SA 3.0", "Shaders/Dusti.frag", False),
                ("Heartfelt No Heart", "ltffzl", "Martijn Steinrucken", "CC BY-NC-SA 3.0",
                 (self.artwork / "shaders" / SHADER).as_uri(), True),
                ("Interactive Rain", "ltffzl", "Martijn Steinrucken", "CC BY-NC-SA 3.0",
                 (self.artwork / "shaders" / RAIN).as_uri(), True)):
            entry = entries[name]
            self.assertEqual(entry["shaderPath"], path)
            self.assertEqual(entry["source"], "shadertoy")
            self.assertEqual(entry["sourceId"], source_id)
            self.assertIn(author, entry["author"])
            self.assertIn(license_name, entry["description"])
            self.assertEqual(entry["needsTextures"], textures)
            self.assertIs(entry["needsAudio"], False)
            self.assertIs(entry["hasBuffers"], False)
        self.assertEqual(entries["Interactive Rain"]["id"], "arasaka-interactive-rain")
        self.assertEqual(len({entry["id"] for entry in index["shaders"]}), 5)

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

    def test_one_existing_desktop_can_activate_interactive_rain(self):
        self.tool("kscreen-doctor", '''
            assert sys.argv[1:] == ['--json'], 'display reconfiguration is forbidden'
            print(json.dumps({'outputs': [
                {'id': 2, 'name': 'HDMI-A-1', 'connected': True, 'enabled': True, 'priority': 1}
            ]}))
            ''')
        Path(self.env["DESKTOP_STATE"]).write_text(json.dumps([self.desktops[1]]))
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        desktops = json.loads(Path(self.env["DESKTOP_STATE"]).read_text())
        self.assertEqual(len(desktops), 1)
        self.assertEqual(desktops[0]["config"]["selectedShaderPath"], (self.artwork / "shaders" / RAIN).as_uri())

    def test_missing_enabled_secondary_desktop_fails_without_config_writes(self):
        initial = [self.desktops[1]]
        Path(self.env["DESKTOP_STATE"]).write_text(json.dumps(initial))
        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("eDP-1", result.stderr)
        self.assertEqual(json.loads(Path(self.env["DESKTOP_STATE"]).read_text()), initial)

    def test_three_existing_desktops_can_activate_interactive_rain(self):
        third = {"id": 42, "screen": 2, "wallpaperPlugin": "org.kde.image", "config": {}}
        Path(self.env["DESKTOP_STATE"]).write_text(json.dumps([*self.desktops, third]))
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        desktops = json.loads(Path(self.env["DESKTOP_STATE"]).read_text())
        self.assertEqual(len(desktops), 3)
        for desktop in desktops:
            self.assertEqual(desktop["config"]["selectedShaderPath"], (self.artwork / "shaders" / RAIN).as_uri())

    def test_invalid_existing_screen_is_rejected_without_config_writes(self):
        self.desktops[0]["screen"] = "invalid"
        Path(self.env["DESKTOP_STATE"]).write_text(json.dumps(self.desktops))
        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads(Path(self.env["DESKTOP_STATE"]).read_text()), self.desktops)

    def test_parked_desktop_is_untouched_while_connected_primary_is_configured(self):
        parked = {"id": 99, "screen": -1, "wallpaperPlugin": "org.kde.image", "config": {"keep": True}}
        Path(self.env["DESKTOP_STATE"]).write_text(json.dumps([*self.desktops, parked]))
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        desktops = json.loads(Path(self.env["DESKTOP_STATE"]).read_text())
        self.assertEqual(desktops[2], parked)
        self.assertEqual(desktops[1]["config"]["selectedShaderPath"], (self.artwork / "shaders" / RAIN).as_uri())

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
            self.assertEqual(len(index["shaders"]), 6)
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
                 "Shaders/Dusti.frag", str(self.artwork / "shaders" / SHADER),
                 str(self.artwork / "shaders" / RAIN)]
        entries = [dict(self.stock_entry, id=f"saved-{number}", shaderPath=path, favorite=True,
                        description="stale metadata", thumbnailPath=f"file:///saved-thumb-{number}.png")
                   for number, path in enumerate(paths)]
        (ui / "shader_index.json").write_text(json.dumps({"categories": [], "shaders": entries}))
        result = self.run_installer("--install-only")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        index = json.loads((ui / "shader_index.json").read_text())
        self.assertEqual(len(index["shaders"]), 5)
        by_name = {entry["name"]: entry for entry in index["shaders"]}
        for number, name in enumerate(("Heartfelt", "Tokyo", "Dusti [237 Chars]", "Heartfelt No Heart", "Interactive Rain")):
            self.assertTrue(by_name[name]["favorite"], name)
            self.assertEqual(by_name[name]["id"], f"saved-{number}")
            self.assertEqual(by_name[name]["thumbnailPath"], f"file:///saved-thumb-{number}.png")
            self.assertNotEqual(by_name[name]["description"], "stale metadata")
        self.assertTrue((ui / "Shaders/Tokyo.frag").read_text().endswith(self.tokyo_code))
        self.assertTrue((ui / "Shaders/Dusti.frag").read_text().endswith(self.dusti_adapted))
        self.assertTrue((self.artwork / "shaders" / SHADER).read_text().startswith(HEADER + LICENSE))
        self.assertEqual((self.artwork / "shaders" / RAIN).read_text(), self.rain_code)
        # Reinstall the just-installed gallery, not only a hand-authored legacy index.
        (self.artwork / "shaders" / RAIN).write_text("obsolete managed rain\n")
        result = self.run_installer("--install-only")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(json.loads((ui / "shader_index.json").read_text()), index)
        self.assertEqual((self.artwork / "shaders" / RAIN).read_text(), self.rain_code)
        self.assertEqual((self.artwork / "shaders" / SHADER).read_text(), self.noheart_code)

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
