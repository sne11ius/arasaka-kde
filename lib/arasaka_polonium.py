"""Scoped adaptation of the SHA-256-pinned Polonium 1.2.1 package.

All replacements must match once. Unknown upstream inputs fail before deployment.
The upstream layout engine stays intact; the native helper owns process identity
and cancellation of KWin operations that are unavailable to JavaScript.
"""
from pathlib import Path
import re


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"Polonium source mismatch: {old[:80]!r}")
    return text.replace(old, new, 1)


def adapt(package):
    package = Path(package)
    path = package / "contents/code/main.mjs"
    code = path.read_text()

    def replace(old, new):
        nonlocal code
        code = replace_once(code, old, new)

    def method(start, end, body):
        nonlocal code
        begin = code.index(start)
        finish = code.index(end, begin)
        code = code[:begin] + body + code[finish:]

    # An empty activity list means all activities, not no eligible displays.
    replace("      for (const activity of window.activities) {",
            "      for (const activity of (window.activities.length ? window.activities : this.workspace.activities)) {")
    replace("!kwinWindow.activities.includes(display.activity)",
            "(kwinWindow.activities.length > 0 && !kwinWindow.activities.includes(display.activity))")

    method("  startTiled() {", "  updateWindow() {", """  startTiled() {
    return policy().tiles(this.window) && !this.window.minimized;
  }
  updateForcedState() {
    if (this.window.move) return; // Hold enforcement until the cross-display drop.
    this.wantsTiled = policy().tiles(this.window);
    const wanted = this.wantsTiled && !this.window.minimized;
    const tiled = controller().isWindowTiled(this.window);
    if (wanted !== tiled) {
      controller().queueEvent({t: wanted ? "tileWindow" : "untileWindow", window: this.window});
    } else if (wanted) {
      controller().queueEvent({t: "rebuildDisplays"});
    }
  }
""")
    method("  updateWindow() {", "  fullscreenChanged() {", """  updateWindow() {
    if (this.window.move) return;
    controller().queueEvent({t: "updateWindow", window: this.window});
  }
""")
    method("  fullscreenChanged() {", "  minimizedChanged() {", """  fullscreenChanged() {
    this.updateForcedState();
  }
""")
    method("  minimizedChanged() {", "  maximizedChanged(state) {", """  minimizedChanged() {
    // Intent is policy-owned even if this window was minimized at startup.
    this.updateForcedState();
  }
""")
    method("  maximizedChanged(state) {", "  canBeTiled() {", """  maximizedChanged(state) {
    // The native helper rejects maximization. Keep the window in the tree.
    this.maximized = false;
    this.updateForcedState();
  }
  interactiveMoveResizeStarted() {
    if (!this.window.move || !policy().tiles(this.window)) return;
    this.dragging = true;
    this.wantsTiled = true;
    controller().queueEvent({t: "untileWindow", window: this.window});
  }
  interactiveMoveResizeStepped() {}
  interactiveMoveResizeFinished() {
    if (this.dragging) {
      this.dragging = false;
      // Transfer the registered display before adding the window to its new tree.
      controller().queueEvent({t: "updateWindow", window: this.window});
      if (policy().tiles(this.window) && !this.window.minimized)
        controller().queueEvent({t: "tileWindow", window: this.window});
    }
    this.updateForcedState();
  }
  tileChanged(tile) {
    // Also repair a manual untile or native quick-tile action.
    this.updateForcedState();
  }
""")
    replace('  evUntileWindow(window) {\n    console().log("untiling window", window.resourceClass);\n'
            '    const ret = [];\n    for (const display of Display.generateWindow(window)) {',
            '  evUntileWindow(window) {\n    console().log("untiling window", window.resourceClass);\n'
            '    const ret = [];\n    for (const display of (this.previousDisplays.get(window) ?? [...Display.generateWindow(window)])) {')
    replace("      driver.removeWindow(window);\n      ret.push(oldDisplay);",
            "      if (driver.hasWindow(window)) driver.removeWindow(window);\n      ret.push(oldDisplay);")
    replace("    for (const [kwinWindow, _ew] of this.windowMap) {",
            "    for (const [kwinWindow, _ew] of this.windowMap) {\n      if (kwinWindow.move) continue;")
    # Membership must be current while several events are handled in one batch,
    # not only after buildLayout. Otherwise a quick cross-display drop can add
    # a window twice or mistake a freshly registered floating window for tiled.
    replace("    this.initializeWindow(kwinWindow);\n  }\n  tileWindow(kwinWindow) {",
            "    this.initializeWindow(kwinWindow);\n    this.untiledWindows.add(kwinWindow);\n  }\n  tileWindow(kwinWindow) {")
    replace("  tileWindow(kwinWindow) {\n    const window = this.windowMap.get(kwinWindow);",
            "  tileWindow(kwinWindow) {\n    if (this.isWindowTiled(kwinWindow)) return;\n"
            "    this.untiledWindows.delete(kwinWindow);\n    const window = this.windowMap.get(kwinWindow);")
    replace("  untileWindow(kwinWindow) {\n    const window = this.windowMap.get(kwinWindow);",
            "  untileWindow(kwinWindow) {\n    if (!this.isWindowTiled(kwinWindow)) return;\n"
            "    this.untiledWindows.add(kwinWindow);\n    const window = this.windowMap.get(kwinWindow);")
    replace("return !(this.window.fullScreen || this.window.minimized || this.maximized);",
            "return policy().tiles(this.window) && !this.window.minimized;")
    replace("if (config().ignoreWindowClasses.test(window.resourceClass) || config().ignoreWindowCaptions.test(window.caption)) {",
            "if (window.popupWindow || !(window.normalWindow || window.dialog)) {")
    method("  toggleActiveTiling() {", "  setEngineType(engineType) {", """  toggleActiveTiling() {
    // Forced tiling cannot be toggled off. The legacy Quake launcher's toggle
    // is harmless: PID discovery already excludes that one window.
  }
""")
    replace("  evChangeEngine(display, engineType, engineSettings, noDBusUpdate) {",
            "  evChangeEngine(display, engineType, engineSettings, noDBusUpdate) {\n"
            "    if (engineType !== 0) return []; // Only the managed binary tree.\n"
            "    engineSettings = config().btreeSettings;\n")
    method("  toggleSettingsMenu() {", "  cycleEngine() {", """  toggleSettingsMenu() {
    // This managed policy has no per-output floating/unbalanced layout menu.
  }
""")
    replace("        driver.buildLayout(rootTile, display);",
            "        rootTile.padding = 8;\n        driver.buildLayout(rootTile, display);")
    replace("        if (kwinWindow.tile !== kwinTile) kwinTile.manage(kwinWindow);",
            "        if (kwinWindow.tile !== kwinTile && !kwinTile.manage(kwinWindow)) {\n"
            '          console().error("KWin refused tile membership for", kwinWindow.resourceClass);\n'
            "          continue;\n        }")
    method("function setTiledProps(window) {", "// src/controller/index.ts", """function setTiledProps(window) {
  window.keepBelow = false;
  window.noBorder = false;
  window.setMaximize(false, false);
}
function setUntiledProps(window) {
  window.keepBelow = false;
  if (policy().isQuake(window)) {
    window.noBorder = true;
    window.keepAbove = true;
  }
}

""")
    replace("var controllerObj;", "var policyObj;\nfunction policy() { return policyObj; }\nvar controllerObj;")
    replace("  configObj = new Config(qmlApi.kwin);", """  policyObj = qmlObjects.policy;
  configObj = new Config(qmlApi.kwin);
  configObj.defaultEngine = 0;
  configObj.btreeSettings = {swapInsertSide: true, rotateLayout: false, insertionStyle: 0, insertInActive: false};
""")
    replace("  controllerObj = new Controller(qmlApi, qmlObjects);", """  controllerObj = new Controller(qmlApi, qmlObjects);
  policy().changed.connect(reconcileForcedPolicy);
  // Script reloads must enroll existing windows, including the live Quake.
  for (const window of qmlApi.workspace.windows) controllerObj.workspaceHandler.windowAdded(window);
""")
    # Bound JS signal callbacks otherwise survive their QML root. Disconnect
    # them explicitly before loading a different content-addressed module.
    connections = code.count(".connect(")
    code, count = re.subn(r"([\w.()]+)\.connect\(([\s\S]*?)\);", r"connectPolicySignal(\1, \2);", code)
    if count != connections:
        raise ValueError("Unrecognized Polonium signal subscription")
    code = """const signalConnections = [];
function connectPolicySignal(signal, callback) {
  signal.connect(callback);
  signalConnections.push([signal, callback]);
}
function reconcileForcedPolicy() {
  for (const handler of controller().windowHandlers.values()) handler.updateForcedState();
}
function stop() {
  for (const [signal, callback] of signalConnections.splice(0)) {
    try { signal.disconnect(callback); } catch (_) {} // closed windows/tiles
  }
  controller().eventTimer.stop();
}
""" + code
    code = replace_once(code, "export {\n  main\n};", "export {\n  main, stop\n};")
    path.write_text(code)
    qml_path = package / "contents/ui/main.qml"
    qml = qml_path.read_text()
    qml = replace_once(qml, "import org.kde.kwin;", 'import org.kde.kwin;\nimport "policy" as Arasaka;')
    qml = replace_once(qml, "    id: root;", """    id: root;
    Component.onDestruction: Polonium.stop()
    Arasaka.WindowPolicy {
        id: windowPolicy
        pidFile: KWin.readConfig("QuakePidFile", "/tmp/konsole-quake.pid")
    }
""")
    qml = replace_once(qml, '"root": root,', '"root": root,\n            "policy": windowPolicy,')
    qml = replace_once(qml, "        Polonium.main(api, qmlObjects);",
                       "        Polonium.main(api, qmlObjects);\n"
                       '        windowPolicy.ready(KWin.readConfig("RuntimeVersion", ""));')
    qml_path.write_text(qml)
