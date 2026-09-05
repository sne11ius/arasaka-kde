#!/usr/bin/env node

const fs = require("fs");
const vm = require("vm");

let nextId = 1;
const panelModel = [];

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
    return model;
}

const desktopModel = [configurable({screen: 0, config: {}})];

function makePanel(managed, role) {
    const panel = configurable({id: nextId++, widgets: [], removed: false});
    panel.addWidget = function(plugin) {
        const widget = configurable({plugin: plugin});
        this.widgets.push(widget);
        return widget;
    };
    panel.remove = function() {
        this.removed = true;
    };
    if (managed !== undefined) {
        panel.config["Arasaka/Managed"] = managed;
    }
    if (role) {
        panel.config["Arasaka/Role"] = role;
    }
    panelModel.push(panel);
    return panel;
}

function Panel() {
    return makePanel(undefined, undefined);
}

global.Panel = Panel;
global.panels = function() {
    return panelModel.filter(function(panel) { return !panel.removed; });
};
global.desktops = function() { return desktopModel; };
global.screenForConnector = function(connector) {
    return connector === "DP-1" ? 0 : connector === "eDP-1" ? 1 : -1;
};

const userPanel = makePanel(false, "user-panel");
userPanel.addWidget("example.user.widget");
makePanel(true, "obsolete-arasaka-panel");

let source = fs.readFileSync(process.argv[2], "utf8");
source = source
    .replaceAll("__PRIMARY_CONNECTOR__", "DP-1")
    .replaceAll("__INTERNAL_CONNECTOR__", "eDP-1")
    .replaceAll("__HOME__", "/tmp/test-home")
    .replace("__COLORIZER_SETTINGS__", "{}")
    .replace("__MIGRATE_ALL__", "true");

function snapshot() {
    return {
        desktopCount: desktopModel.length,
        panels: panels().map(function(panel) {
            return {
                id: panel.id,
                location: panel.location || null,
                managed: panel.config["Arasaka/Managed"] === true,
                role: panel.config["Arasaka/Role"] || null,
                screen: panel.screen,
                widgets: panel.widgets.map(function(widget) { return widget.plugin; })
            };
        })
    };
}

vm.runInThisContext(source, {filename: process.argv[2]});
const first = snapshot();
vm.runInThisContext(source, {filename: process.argv[2]});
const second = snapshot();
process.stdout.write(JSON.stringify({first: first, second: second}) + "\n");
