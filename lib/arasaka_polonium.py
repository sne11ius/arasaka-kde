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
    # Output QObjects can be destroyed while a rebuild is queued (especially
    # across suspend/resume). A non-null JS wrapper is not proof of validity.
    # Never pass retired objects to KWin, and never leave the event gate latched
    # if a native call or an individual output's layout rebuild throws.
    method("  processEvents() {", "  // returns a list of displays", """  processEvents() {
    this.processingEvents = true;
    try {
      const queue = simplifyEvents(this.eventQueue);
      this.eventQueue = new Queue();
      const rebuildDisplays = new Map();
      while (!queue.isEmpty) {
        const ev = queue.pop();
        if (ev === undefined) break;
        for (const display of this.handleEvent(ev)) {
          if (this.isCurrentDisplay(display)) rebuildDisplays.set(display.toSymbol(), display);
        }
      }
      // getDriver can discover topology while handling another event. Keep its
      // rebuild obligation even when the caller ignores updateDrivers' return.
      for (const display of this.dirtyDisplays ?? []) {
        if (this.isCurrentDisplay(display)) rebuildDisplays.set(display.toSymbol(), display);
      }
      this.dirtyDisplays = [];
      for (const display of rebuildDisplays.values()) {
        if (!this.isCurrentDisplay(display) || display.activity !== this.workspace.currentActivity) continue;
        try {
          const driver = this.getDriver(display);
          if (!driver) continue;
          const rootTile = this.workspace.rootTile(display.output, display.desktop);
          if (!rootTile) continue;
          rootTile.padding = 8;
          driver.buildLayout(rootTile, display);
        } catch (error) {
          console().error("display rebuild failed", error.message);
        }
      }
      const postQueue = simplifyPostEvents(this.postEventQueue);
      this.postEventQueue = new Queue();
      while (!postQueue.isEmpty) {
        const ev = postQueue.pop();
        if (ev === undefined) break;
        this.handlePostEvent(ev);
      }
    } finally {
      this.processingEvents = false;
    }
  }
""")
    method("  updateDrivers() {\n    const ret = [];", "  displaysToRebuild() {", """  isCurrentDisplay(display) {
    return display && this.workspace.screens.includes(display.output)
      && this.workspace.desktops.includes(display.desktop)
      && this.workspace.activities.includes(display.activity);
  }
  updateDrivers() {
    const displays = [...Display.generate(this.workspace.desktops, this.workspace.activities, this.workspace.screens)];
    const previous = this.knownDisplays ?? [];
    if (previous.length === displays.length && displays.every(d => previous.some(p => d.equals(p)))) return [];
    this.knownDisplays = displays;
    this.dirtyDisplays = displays;
    if (!this.processingEvents) this.eventTimer.start();
    // Connector names may be reused with entirely new QObjects/root tiles.
    // Reconstruct membership from live windows, not the retired layout trees.
    for (const driver of this.drivers.values()) disconnectPolicySignals(driver);
    this.drivers.clear();
    for (const display of displays) {
      this.drivers.set(display.toSymbol(), new Driver(config().defaultEngine));
    }
    this.previousDisplays.clear();
    for (const window of Array.from(this.windowHandlers.keys())) {
      if (!this.windowExists(window)) {
        this.windowHandlers.delete(window);
        continue;
      }
      const current = [...Display.generateWindow(window)].filter(d => this.isCurrentDisplay(d));
      this.previousDisplays.set(window, current);
      for (const display of current) {
        const driver = this.drivers.get(display.toSymbol());
        if (policy().tiles(window) && !window.minimized && !window.move) driver.addWindow(window);
        else driver.addWindowUntiled(window);
      }
    }
    return displays;
  }
""")
    replace("  getDriver(display) {\n    let id;",
            "  getDriver(display) {\n"
            "    if (typeof display === 'object' && !this.isCurrentDisplay(display)) return undefined;\n"
            "    let id;")
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
    # Retiring a driver also retires its callbacks on surviving output tiles.
    for callback in ("updateTileSizesCallback", "updateTileCountCallback"):
        code = replace_once(code, f"this.{callback}.bind(this, display)\n        );",
                            f"this.{callback}.bind(this, display), this\n        );")
    code = """const signalConnections = new Set();
function connectPolicySignal(signal, callback, owner) {
  signal.connect(callback);
  signalConnections.add([signal, callback, owner]);
}
function disconnectPolicySignals(owner) {
  // Qt 6.10's JS Set iterator skips entries when the current one is deleted.
  // Iterate a snapshot so teardown disconnects every callback, including reloads.
  for (const connection of Array.from(signalConnections)) {
    const [signal, callback, connectionOwner] = connection;
    if (owner !== undefined && connectionOwner !== owner) continue;
    try { signal.disconnect(callback); } catch (_) {} // closed windows/tiles
    signalConnections.delete(connection);
  }
}
function reconcileForcedPolicy() {
  for (const handler of controller().windowHandlers.values()) handler.updateForcedState();
}
function stop() {
  disconnectPolicySignals();
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
