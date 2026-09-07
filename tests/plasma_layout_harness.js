#!/usr/bin/env node

const fs = require("fs");
const vm = require("vm");

const options = JSON.parse(process.argv[3] || "{}");
const launcherType = "com.arasaka.launcher";
let nextId = 1;
let primaryConnector = options.primaryConnector || "DP-1";
const events = [];
const panelModel = [];
const children = new Map();
const owners = new Map();

function configurable(model) {
    model.currentConfigGroup = [];
    model.config = model.config || {};
    model.writeConfig = function(key, value) {
        this.config[this.currentConfigGroup.join("/") + "/" + key] = value;
    };
    model.readConfig = function(key, fallback) {
        const configKey = this.currentConfigGroup.join("/") + "/" + key;
        return Object.prototype.hasOwnProperty.call(this.config, configKey)
            ? this.config[configKey]
            : fallback;
    };
    model.reloadConfig = function() {};
    if (model.type === launcherType) {
        model.reloadConfig = function() {
            if (this.config["General/ready"] && !options.staleReady) {
                this.config["General/readyToken"] = this.config["General/requestToken"];
            }
        };
    }
    return model;
}

function makeContainment(spec) {
    const containment = configurable({
        id: nextId++, screen: spec.screen, config: {...spec.config},
        wallpaperPlugin: spec.wallpaperPlugin || "org.kde.image", removed: false
    });
    children.set(containment, []);
    Object.defineProperty(containment, "widgetIds", {
        get: function() { return children.get(this).map(widget => widget.id); }
    });
    containment.widgetById = function(id) {
        return children.get(this).find(widget => widget.id === id);
    };
    containment.widgets = function(type) {
        return children.get(this).filter(widget => !type || widget.type === type);
    };
    containment.addWidget = function(value) {
        if (typeof value === "string") {
            if (value === launcherType && options.addFailure) {
                if (options.addFailure === "throw") {
                    throw new Error("Could not create widget");
                }
                // Plasma may return an Error value rather than throwing it.
                return options.addFailure === "error" ? new Error("Could not create widget") : undefined;
            }
            const widget = configurable({id: nextId++, type: value,
                config: value === launcherType ? {"General/ready": !options.notReady} : {}});
            widget.remove = function() {
                const owner = owners.get(this);
                children.set(owner, children.get(owner).filter(item => item.id !== this.id));
                events.push({action: "removeWidget", id: this.id});
            };
            children.get(this).push(widget);
            owners.set(widget, this);
            events.push({action: "addWidget", id: widget.id, type: value, desktop: this.id});
            return widget;
        }
        if (!owners.has(value)) {
            return new Error("addWidget requires a name of a widget or a widget object");
        }
        if (options.moveFailure) {
            return options.moveFailure === "error" ? new Error("Cannot move widget") : value;
        }
        const oldOwner = owners.get(value);
        children.set(oldOwner, children.get(oldOwner).filter(widget => widget.id !== value.id));
        children.get(this).push(value);
        owners.set(value, this);
        events.push({action: "moveWidget", id: value.id, desktop: this.id});
        return value;
    };
    containment.remove = function() {
        this.removed = true;
        children.set(this, []);
        events.push({action: "removeContainment", id: this.id});
    };
    for (const specWidget of spec.widgets || []) {
        // Seed persisted widgets independently of injected runtime failures.
        const failure = options.addFailure;
        delete options.addFailure;
        const widget = containment.addWidget(specWidget.type);
        options.addFailure = failure;
        widget.config = {...widget.config, ...specWidget.config};
    }
    return containment;
}

const desktopModel = (options.desktops || [{screen: 0}, {screen: 1}]).map(spec => {
    return makeContainment({
        ...spec,
        config: {"/activityId": spec.activity || "current", ...spec.config}
    });
});
for (const managed of [false, undefined, "false", true, "true"]) {
    panelModel.push(makeContainment({
        screen: 0,
        config: managed === undefined ? {} : {"Arasaka/Managed": managed},
        widgets: [{type: "example.user.widget", config: {"General/value": "keep"}}]
    }));
}

global.Panel = function() {
    const panel = makeContainment({screen: 0});
    panelModel.push(panel);
    events.push({action: "createPanel", id: panel.id});
    return panel;
};
global.panels = function() { return panelModel.filter(panel => !panel.removed); };
global.desktops = function() { return desktopModel; };
global.currentActivity = function() { return options.currentActivity ?? "current"; };
global.screenForConnector = function(connector) {
    const connectors = options.connectors || {"DP-1": 0, "eDP-1": 1};
    return Object.prototype.hasOwnProperty.call(connectors, connector) ? connectors[connector] : -1;
};
global.knownWidgetTypes = options.unavailable ? [] : [launcherType];

const template = fs.readFileSync(process.argv[2], "utf8");
function snapshot() {
    function serialize(containment) {
        return {
            id: containment.id, screen: containment.screen,
            config: {...containment.config}, wallpaperPlugin: containment.wallpaperPlugin,
            widgets: containment.widgetIds.map(id => {
                const widget = containment.widgetById(id);
                return {id: widget.id, type: widget.type, config: {...widget.config}};
            })
        };
    }
    return {desktops: desktopModel.map(serialize), panels: panels().map(serialize)};
}

function run() {
    events.length = 0;
    const source = template
        .replaceAll("__PRIMARY_CONNECTOR__", primaryConnector)
        .replaceAll("__INTERNAL_CONNECTOR__", "eDP-1")
        .replaceAll("__HOME__", "/tmp/test-home")
        .replaceAll("__LAUNCHER_SESSION__", "test-bus/:1.42")
        .replaceAll("__HIDE_DESKTOP_ICONS__", options.hideDesktopIcons ? "true" : "false")
        .replace("__COLORIZER_SETTINGS__", "{}");
    let error = null;
    try {
        vm.runInThisContext(source, {filename: process.argv[2]});
    } catch (exception) {
        error = exception.message;
    }
    return {...snapshot(), error, events: events.slice()};
}

const initial = snapshot();
const first = run();
// Emulate applet-owned state written after initialization, before reconciliation.
for (const desktop of desktopModel) {
    for (const widget of desktop.widgets(launcherType)) {
        widget.config["General/persistedState"] = "keep-native-applet-ids-and-settings";
        if (options.becomesReady) {
            widget.config["General/ready"] = true;
        }
    }
}
if (options.movePrimary) {
    primaryConnector = "eDP-1";
}
if (options.disconnectOldPrimary) {
    desktopModel[0].screen = -1;
}
const beforeSecond = snapshot();
const second = run();
process.stdout.write(JSON.stringify({initial, first, beforeSecond, second}) + "\n");
