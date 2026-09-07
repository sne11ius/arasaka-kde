var primaryConnector = "__PRIMARY_CONNECTOR__";
var primaryScreen = screenForConnector(primaryConnector);
var launcherPlugin = "com.arasaka.launcher";
var launcherSession = "__LAUNCHER_SESSION__";

if (primaryScreen < 0) {
    throw new Error("Arasaka primary display connector is not available in Plasma yet");
}

// Plasma exposes the installed plugin list as knownWidgetTypes.
var availableWidgetTypes = knownWidgetTypes;
if (availableWidgetTypes.indexOf(launcherPlugin) < 0) {
    throw new Error("Arasaka launcher package is not available in Plasma yet");
}

var existingDesktops = desktops();
var activity = currentActivity();
var primaryDesktop = existingDesktops.filter(function(desktop) {
    desktop.currentConfigGroup = [];
    return desktop.screen === primaryScreen && desktop.readConfig("activityId", "") === activity;
})[0];

var managedHosts = [];
existingDesktops.forEach(function(desktop) {
    desktop.widgetIds.forEach(function(id) {
        var widget = desktop.widgetById(id);
        if (widget && widget.type === launcherPlugin) {
            widget.currentConfigGroup = ["Arasaka"];
            if (String(widget.readConfig("Managed", "false")) === "true") {
                managedHosts.push({desktop: desktop, widget: widget});
            }
        }
    });
});

var existingHost = managedHosts.filter(function(host) {
    return primaryDesktop && host.desktop.id === primaryDesktop.id;
})[0] || managedHosts[0];
var launcher;
if (existingHost) {
    launcher = existingHost.widget;
    // Plasma 6.7's addWidget(existing) mis-migrates CustomEmbedded config trees.
    // Keep ownership stable; popup placement follows the configured primary output.
} else {
    // Retarget an existing host even while Plasma's desktop/activity mapping settles.
    if (!primaryDesktop) {
        throw new Error("Arasaka primary desktop is not available in the current activity yet");
    }
    launcher = primaryDesktop.addWidget(launcherPlugin);
}

// addWidget can return an Error value rather than throwing.
var owner = existingHost ? existingHost.desktop : primaryDesktop;
if (!launcher || launcher.type !== launcherPlugin || !launcher.id || !owner.widgetById(launcher.id)) {
    throw new Error("Arasaka launcher could not be placed on the primary desktop; keeping existing panels");
}
if (!existingHost) {
    launcher.currentConfigGroup = ["Arasaka"];
    launcher.writeConfig("Managed", true);
    launcher.reloadConfig();
}

launcher.currentConfigGroup = ["General"];
launcher.writeConfig("primaryConnector", primaryConnector);
launcher.writeConfig("requestToken", launcherSession);
launcher.reloadConfig();
if (String(launcher.readConfig("ready", "false")) !== "true" || launcher.readConfig("readyToken", "") !== launcherSession) {
    throw new Error("Arasaka launcher is still loading; keeping existing panels");
}

managedHosts.forEach(function(host) {
    if (host.widget.id !== launcher.id) {
        host.widget.remove();
    }
});
panels().forEach(function(panel) {
    panel.currentConfigGroup = ["Arasaka"];
    if (String(panel.readConfig("Managed", "false")) === "true") {
        panel.remove();
    }
});

if ("__HIDE_DESKTOP_ICONS__" === "true") desktops().forEach(function(desktop) {
    desktop.currentConfigGroup = ["General"];
    desktop.writeConfig("filterMode", 1);
    desktop.writeConfig("filterPattern", "__ARASAKA_DESKTOP_ITEMS_HIDDEN__");
    desktop.reloadConfig();
});
