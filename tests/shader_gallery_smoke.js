#!/usr/bin/env node
// Exercise the installed gallery's actual selection function without changing Plasma.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const {fileURLToPath, pathToFileURL} = require("node:url");

const ui = path.resolve(process.argv[2], "contents/ui");
const external = path.resolve(process.argv[3]);
const config = fs.readFileSync(path.join(ui, "ConfigContent.qml"), "utf8");
const start = config.indexOf("    function _applyShaderFromPathImpl(");
assert(start >= 0, "Installed gallery must expose its shader selection function");
const end = config.indexOf("\n    }", start) + "\n    }".length;
const directive = {};
vm.runInNewContext(fs.readFileSync(path.join(ui, "ChannelDirective.js"), "utf8")
    .replace(/^\.pragma library\s*/m, ""), directive);
const context = {
    console,
    cfg_mouseEnabled: false,
    cfg_audioEnabled: false,
    ChannelDirective: directive,
    // Native I/O boundary: these three imports have no buffer files.
    ShaderLibrarySingleton: {
        toRelativeShaderPath: value => value,
        loadBufferCodes: () => ({}),
        loadShaderCode: value => fs.readFileSync(fileURLToPath(value), "utf8")
    }
};
context.configItem = context;
vm.createContext(context);
vm.runInContext(config.slice(start, end), context);
for (const file of [path.join(ui, "Shaders/Tokyo.frag"), path.join(ui, "Shaders/Dusti.frag"), external]) {
    context._applyShaderFromPathImpl(pathToFileURL(file).href, path.basename(file));
    assert.equal(context.cfg_mouseEnabled, false, "Gallery selection must retain disabled mouse capture");
    assert.equal(context.cfg_audioEnabled, false, "Gallery selection must retain disabled audio capture");
    const channels = [0, 1, 2, 3].map(i => context["cfg_imageChannel" + i]);
    assert.deepEqual(channels, file === external ? [0, -1, -1, -1] : [-1, -1, -1, -1]);
}
console.log("Gallery round-trip: Tokyo -> Dusti -> Heartfelt No Heart passed.");
