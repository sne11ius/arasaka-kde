// Wallpaper-only application: do not create desktops, panels, or change display topology.
var dataHome = __DATA_HOME_JSON__;
var primaryConnector = __PRIMARY_CONNECTOR_JSON__;
var ensureOnly = "__ENSURE_ONLY__" === "true";
var shaderPhase = "__SHADER_PHASE__";
if (shaderPhase !== "prepare" && shaderPhase !== "activate") {
    throw new Error("Expected an explicit shader activation phase");
}
var expectedConnectors = __ENABLED_CONNECTORS_JSON__;
var plugin = "online.knowmad.shaderwallpaper";
var primaryScreen = screenForConnector(primaryConnector);
// Plasma retains disconnected/inactive containments with screen -1.
var targets = desktops().filter(function (desktop) { return desktop.screen !== -1; });
if (primaryScreen < 0 || targets.length === 0 ||
        targets.some(function (desktop) { return !Number.isInteger(desktop.screen) || desktop.screen < 0; }) ||
        !targets.some(function (desktop) { return desktop.screen === primaryScreen; })) {
    throw new Error("Expected existing desktops with valid screens, including primary connector " + primaryConnector);
}
expectedConnectors.forEach(function (connector) {
    var screen = screenForConnector(connector);
    if (!Number.isInteger(screen) || screen < 0 ||
            !targets.some(function (desktop) { return desktop.screen === screen; })) {
        throw new Error("Expected existing desktop for enabled connector " + connector);
    }
});

function fileUrl(path) {
    return "file://" + path.split("/").map(function (part) {
        return encodeURIComponent(part).replace(/[!'()*]/g, function (character) {
            return "%" + character.charCodeAt(0).toString(16).toUpperCase();
        });
    }).join("/");
}

var report = {status: shaderPhase === "prepare" ? "prepared" : "ok", primaryScreen: primaryScreen, desktops: []};
targets.forEach(function (desktop) {
    desktop.currentConfigGroup = ["Wallpaper", plugin, "General"];
    var pendingKey = "arasakaRainPending";
    var pending = desktop.readConfig(pendingKey, false);
    if (ensureOnly && desktop.wallpaperPlugin === plugin && !pending) {
        report.desktops.push({id: desktop.id, screen: desktop.screen, wallpaperPlugin: desktop.wallpaperPlugin, preserved: true});
        return;
    }
    var image = desktop.screen === primaryScreen ? "mikoshi-16x9.png" : "mikoshi-16x10.png";
    var settings = {
        selectedShaderPath: fileUrl(dataHome + "/wallpapers/Arasaka/shaders/Interactive_Rain.frag"),
        selectedShaderCode: "",
        running: true,
        shaderSpeed: 0.75,
        targetFps: 30,
        resolutionScale: 1,
        pauseMode: 0,
        checkActiveScreen: true,
        excludeWindows: [],
        mouseEnabled: false,
        audioEnabled: false,
        windowsEnabled: false,
        playlistEnabled: false,
        enableShaderTweaks: false,
        commonCode: "",
        useBufferA: false,
        useBufferB: false,
        useBufferC: false,
        useBufferD: false,
        iChannel0Enabled: true,
        iChannel0: fileUrl(dataHome + "/wallpapers/Arasaka/" + image),
        imageChannel0: 0,
        iChannel1Enabled: false,
        iChannel2Enabled: false,
        iChannel3Enabled: false,
        imageChannel1: -1,
        imageChannel2: -1,
        imageChannel3: -1
    };
    function readSettings() {
        var actual = {};
        Object.keys(settings).forEach(function (key) {
            // KConfig uses the fallback's type; a differing fallback also detects missing writes.
            var fallback = typeof settings[key] === "boolean" ? !settings[key] :
                typeof settings[key] === "number" ? settings[key] + 1 : "__ARASAKA_MISSING__";
            actual[key] = desktop.readConfig(key, fallback);
            if (Array.isArray(settings[key]) && actual[key] === "") {
                actual[key] = [];
            }
            if (JSON.stringify(actual[key]) !== JSON.stringify(settings[key])) {
                throw new Error("Wallpaper configuration mismatch on desktop " + desktop.id + ": " + key);
            }
        });
        return actual;
    }
    var actual;
    if (shaderPhase === "prepare" && (!ensureOnly || !pending)) {
        // writeConfig can reach the OLD wallpaper until the wrapper is destroyed.
        ["mouseEnabled", "audioEnabled", "windowsEnabled", "playlistEnabled"].forEach(function (key) {
            desktop.writeConfig(key, false);
        });
        Object.keys(settings).forEach(function (key) {
            desktop.writeConfig(key, settings[key]);
        });
        actual = readSettings();
        desktop.writeConfig(pendingKey, true);
        if (desktop.readConfig(pendingKey, false) !== true) {
            throw new Error("Could not mark rain initialization pending on desktop " + desktop.id);
        }
    } else {
        if (!pending) {
            throw new Error("Wallpaper was not prepared on desktop " + desktop.id);
        }
        try {
            actual = readSettings();
        } catch (error) {
            // A pending marker is not permission to overwrite later user changes.
            if (!ensureOnly) throw error;
            desktop.writeConfig(pendingKey, false);
            if (desktop.readConfig(pendingKey, true) !== false) {
                throw new Error("Could not cancel pending rain initialization on desktop " + desktop.id);
            }
            report.desktops.push({id: desktop.id, screen: desktop.screen, wallpaperPlugin: desktop.wallpaperPlugin, preserved: true});
            return;
        }
    }
    if (shaderPhase === "prepare") {
        // Plasma commits this cached setter only at evaluation/wrapper cleanup.
        if (desktop.wallpaperPlugin !== plugin) desktop.wallpaperPlugin = plugin;
    } else {
        // This fresh wrapper reads the committed selection; never assign it here.
        if (desktop.wallpaperPlugin !== plugin) {
            throw new Error("Wallpaper plugin mismatch on desktop " + desktop.id);
        }
        settings.mouseEnabled = true;
        desktop.writeConfig("mouseEnabled", true);
        actual = readSettings();
        desktop.writeConfig(pendingKey, false);
        if (desktop.readConfig(pendingKey, true) !== false) {
            throw new Error("Could not clear pending rain initialization on desktop " + desktop.id);
        }
    }
    report.desktops.push({id: desktop.id, screen: desktop.screen, wallpaperPlugin: desktop.wallpaperPlugin, config: actual});
});
print("ARASAKA_SHADER_WALLPAPER=" + JSON.stringify(report));
