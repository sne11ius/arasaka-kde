var primaryConnector = "__PRIMARY_CONNECTOR__";
var internalConnector = "__INTERNAL_CONNECTOR__";
var home = "__HOME__";
var primaryScreen = screenForConnector(primaryConnector);
var internalScreen = internalConnector ? screenForConnector(internalConnector) : -1;

if (primaryScreen < 0 || (internalConnector && internalScreen < 0)) {
    throw new Error("Arasaka display connectors are not available in Plasma yet");
}

var colorizerSettings = __COLORIZER_SETTINGS__;

function config(widget, group, values) {
    widget.currentConfigGroup = [group];
    Object.keys(values).forEach(function(key) {
        widget.writeConfig(key, values[key]);
    });
    widget.reloadConfig();
}

function addColorizer(panel) {
    var widget = panel.addWidget("luisbocanegra.panel.colorizer");
    config(widget, "General", {
        hideWidget: true,
        globalSettings: JSON.stringify(colorizerSettings),
        forceForegroundColor: JSON.stringify({widgets: [], reloadInterval: 250})
    });
}

function addMonitor(panel, plugin, title, face) {
    var widget = panel.addWidget(plugin);
    config(widget, "Appearance", {title: title, chartFace: face});
    return widget;
}

function markPanel(panel, role) {
    panel.currentConfigGroup = ["Arasaka"];
    panel.writeConfig("Managed", true);
    panel.writeConfig("Role", role);
}

function createCommandStrip(screen) {
    var panel = new Panel;
    panel.screen = screen;
    panel.location = "top";
    panel.lengthMode = "fill";
    panel.hiding = "none";
    panel.height = 44;
    panel.floating = false;
    markPanel(panel, "command-strip");

    var launcher = panel.addWidget("org.kde.plasma.kickoff");
    config(launcher, "General", {
        icon: home + "/.local/share/icons/arasaka-launcher.svg",
        favorites: "applications:org.kde.dolphin.desktop,applications:firefox.desktop,applications:org.kde.konsole.desktop,applications:systemsettings.desktop"
    });

    var title = panel.addWidget("com.github.antroids.application-title-bar");
    config(title, "Appearance", {
        widgetElements: "windowIcon,windowTitle",
        windowTitleFontSize: 11,
        windowTitleFontBold: true,
        windowTitleMaximumWidth: 640,
        windowTitleUndefined: "ARASAKA // SECURE OPERATIONS",
        widgetToolTipMode: 0
    });

    panel.addWidget("org.kde.plasma.marginsseparator");
    var leftSpacer = panel.addWidget("org.kde.plasma.panelspacer");
    config(leftSpacer, "General", {expanding: true});
    panel.addWidget("org.kde.plasma.mediacontroller");
    var rightSpacer = panel.addWidget("org.kde.plasma.panelspacer");
    config(rightSpacer, "General", {expanding: true});
    addMonitor(panel, "org.kde.plasma.systemmonitor.cpu", "CPU", "org.kde.ksysguard.textonly");
    addMonitor(panel, "org.kde.plasma.systemmonitor.memory", "MEM", "org.kde.ksysguard.textonly");
    addMonitor(panel, "org.kde.plasma.systemmonitor.net", "NET", "org.kde.ksysguard.textonly");
    panel.addWidget("org.kde.plasma.marginsseparator");
    panel.addWidget("org.kde.plasma.systemtray");
    addColorizer(panel);
}

function createTelemetryRail(screen) {
    var panel = new Panel;
    panel.screen = screen;
    panel.location = "right";
    panel.lengthMode = "fill";
    panel.hiding = "none";
    panel.height = 54;
    panel.floating = false;
    markPanel(panel, "telemetry-rail");

    addMonitor(panel, "org.kde.plasma.systemmonitor.cpu", "CPU", "org.kde.ksysguard.colorgrid");
    addMonitor(panel, "org.kde.plasma.systemmonitor.memory", "RAM", "org.kde.ksysguard.horizontalbars");
    addMonitor(panel, "org.kde.plasma.systemmonitor.net", "NET", "org.kde.ksysguard.linechart");
    panel.addWidget("org.kde.plasma.mediacontroller");
    panel.addWidget("org.kde.plasma.battery");
    var curve = panel.addWidget("luisbocanegra.audio.visualizer");
    config(curve, "General", {
        active: true,
        barCount: 22,
        barWidth: 3,
        barGap: 2,
        roundedBars: false,
        fillPanel: true,
        expanding: true,
        minimumLength: 180,
        hideWhenIdle: false,
        barColors: JSON.stringify({colors: [{color: "#e60012", position: 0}, {color: "#e8e9ea", position: 1}]})
    });
    addColorizer(panel);
}

var previousPanels = panels().filter(function(panel) {
    panel.currentConfigGroup = ["Arasaka"];
    return String(panel.readConfig("Managed", "false")) === "true";
});
previousPanels.forEach(function(panel) { panel.remove(); });
createCommandStrip(primaryScreen);
if (internalScreen >= 0 && internalScreen !== primaryScreen) {
    createTelemetryRail(internalScreen);
}

desktops().forEach(function(desktop) {
    desktop.currentConfigGroup = ["General"];
    desktop.writeConfig("filterMode", 1);
    desktop.writeConfig("filterPattern", "__ARASAKA_DESKTOP_ITEMS_HIDDEN__");

    var video = desktop.screen === primaryScreen ? "mikoshi-16x9.mp4" : "mikoshi-16x10.mp4";
    desktop.wallpaperPlugin = "luisbocanegra.smart.video.wallpaper.reborn";
    desktop.currentConfigGroup = ["Wallpaper", "luisbocanegra.smart.video.wallpaper.reborn", "General"];
    desktop.writeConfig("VideoUrls", JSON.stringify([{
        filename: "file://" + home + "/.local/share/wallpapers/Arasaka/" + video,
        enabled: true,
        duration: 0,
        customDuration: 0,
        playbackRate: 0,
        alternativePlaybackRate: 0,
        loop: true
    }]));
    desktop.writeConfig("BackgroundColor", "#07090c");
    desktop.writeConfig("FillMode", 2);
    desktop.writeConfig("PauseMode", 0);
    desktop.writeConfig("MuteMode", 5);
    desktop.writeConfig("Volume", 0);
    desktop.writeConfig("BatteryPausesVideo", true);
    desktop.writeConfig("PauseBatteryLevel", 20);
    desktop.writeConfig("CrossfadeEnabled", true);
    desktop.writeConfig("CrossfadeDuration", 1000);
    desktop.reloadConfig();
});
