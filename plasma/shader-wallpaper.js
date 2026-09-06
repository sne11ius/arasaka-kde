// Wallpaper-only application: do not create desktops, panels, or change display topology.
var dataHome = __DATA_HOME_JSON__;
var primaryConnector = __PRIMARY_CONNECTOR_JSON__;
var plugin = "online.knowmad.shaderwallpaper";
var primaryScreen = screenForConnector(primaryConnector);
// Plasma retains disconnected/inactive containments with screen -1.
var targets = desktops().filter(function (desktop) { return desktop.screen !== -1; });
if (primaryScreen < 0 || targets.length === 0 ||
        targets.some(function (desktop) { return !Number.isInteger(desktop.screen) || desktop.screen < 0; }) ||
        !targets.some(function (desktop) { return desktop.screen === primaryScreen; })) {
    throw new Error("Expected existing desktops with valid screens, including primary connector " + primaryConnector);
}

function fileUrl(path) {
    return "file://" + path.split("/").map(function (part) {
        return encodeURIComponent(part).replace(/[!'()*]/g, function (character) {
            return "%" + character.charCodeAt(0).toString(16).toUpperCase();
        });
    }).join("/");
}

var report = {status: "ok", primaryScreen: primaryScreen, desktops: []};
targets.forEach(function (desktop) {
    var image = desktop.screen === primaryScreen ? "mikoshi-16x9.png" : "mikoshi-16x10.png";
    var settings = {
        selectedShaderPath: fileUrl(dataHome + "/wallpapers/Arasaka/shaders/Heartfelt_No_Heart.frag"),
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
    desktop.currentConfigGroup = ["Wallpaper", plugin, "General"];
    // Persist capture/playlist opt-outs before a previously used plugin is loaded.
    ["mouseEnabled", "audioEnabled", "windowsEnabled", "playlistEnabled"].forEach(function (key) {
        desktop.writeConfig(key, false);
    });
    Object.keys(settings).forEach(function (key) {
        desktop.writeConfig(key, settings[key]);
    });
    desktop.wallpaperPlugin = plugin;
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
    if (desktop.wallpaperPlugin !== plugin) {
        throw new Error("Wallpaper plugin mismatch on desktop " + desktop.id);
    }
    report.desktops.push({id: desktop.id, screen: desktop.screen, wallpaperPlugin: desktop.wallpaperPlugin, config: actual});
});
print("ARASAKA_SHADER_WALLPAPER=" + JSON.stringify(report));
