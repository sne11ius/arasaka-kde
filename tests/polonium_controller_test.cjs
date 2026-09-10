// Real adapted controller/driver/engine code; fake only the KWin boundary.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {test} = require('node:test');
const source = fs.readFileSync(process.argv[2], 'utf8');

function fixture() {
    const context = vm.createContext({});
    vm.runInContext(source.replace(/export \{[^}]+\};\s*$/, ''), context);
    const c = vm.runInContext(`
        consoleObj = {debug() {}, error() {}, warn() {}, log() {}};
        configObj = {defaultEngine: 0, btreeSettings: {swapInsertSide: true}};
        policyObj = {tiles(w) {return !w.quake;}};
        controllerObj = Object.create(Controller.prototype);
        Object.assign(controllerObj, {
            eventQueue: new Queue(), postEventQueue: new Queue(), processingEvents: false,
            drivers: new Map(), windowHandlers: new Map(), previousDisplays: new Map(),
            dbusHandler: null, eventTimer: {start() {}},
            workspace: {screens: [{name: 'left'}, {name: 'right'}],
                desktops: [{id: 'desktop'}], activities: ['activity'],
                currentActivity: 'activity', windows: []}
        });
        Display.setWorkspace(controllerObj.workspace);
        controllerObj;
    `, context);
    const Display = vm.runInContext('Display', context);
    const display = output => new Display(c.workspace.desktops[0], 'activity', output);
    c.updateDrivers();
    c.workspace.rootTile = () => null;
    c.processEvents(); // Finish initial discovery before testing later transitions.
    return {c, display};
}

test('a stale display cannot reach KWin or block rebuilding a live display', () => {
    const {c, display} = fixture();
    const live = display(c.workspace.screens[0]);
    const retired = display({}); // A destroyed QObject wrapper is still an object.
    let built = 0;
    const requested = [];
    c.getDriver(live).buildLayout = () => built++;
    c.workspace.rootTile = output => {
        requested.push(output);
        return {};
    };
    c.handleEvent = () => [retired, live];
    c.queueEvent({t: 'rebuildDisplays'});
    c.processEvents();
    assert.equal(built, 1);
    assert.deepEqual(requested, [c.workspace.screens[0]], 'only current output objects may reach KWin');
});

test('a rebuild exception does not prevent the next real tiling event', () => {
    const {c, display} = fixture();
    const live = display(c.workspace.screens[0]);
    let built = 0;
    c.getDriver(live).buildLayout = () => built++;
    c.workspace.rootTile = () => {throw new TypeError('KWin output conversion failed');};
    c.queueEvent({t: 'rebuildDisplays'});
    try {c.processEvents();} catch (_) {} // Recovery must work even when a batch throws.
    c.workspace.rootTile = () => ({});
    c.queueEvent({t: 'rebuildDisplays'});
    c.processEvents();
    assert.equal(built, 1, 'the next event must rebuild the layout');
});

test('an error on one output still allows the other output to rebuild', () => {
    const {c, display} = fixture();
    let built = 0;
    c.getDriver(display(c.workspace.screens[1])).buildLayout = () => built++;
    c.workspace.rootTile = output => {
        if (output === c.workspace.screens[0]) throw new TypeError('KWin output conversion failed');
        return {};
    };
    c.queueEvent({t: 'rebuildDisplays'});
    try {c.processEvents();} catch (_) {}
    assert.equal(built, 1, 'a failing output must not abort the remaining layouts');
});

test('an exception escaping post-event handling releases the event gate', () => {
    const {c, display} = fixture();
    const w = {resourceClass: 'fixture', set fullScreen(_) {throw new Error('window disappeared');}};
    c.workspace.windows.push(w);
    c.queuePostEvent({t: 'setWindowProperties', window: w, fullscreen: false});
    assert.throws(() => c.processEvents(), /window disappeared/);
    let built = 0;
    c.getDriver(display(c.workspace.screens[0])).buildLayout = () => built++;
    c.workspace.rootTile = () => ({});
    let timerStarts = 0;
    c.eventTimer.start = () => timerStarts++;
    c.queueEvent({t: 'rebuildDisplays'});
    assert.equal(timerStarts, 1);
    c.processEvents();
    assert.equal(built, 1);
});

test('topology discovered during driver lookup still rebuilds every new driver', () => {
    const {c} = fixture();
    c.workspace.screens = [c.workspace.screens[0]];
    c.updateDrivers();
    c.processEvents();
    const w = {internalId: 'all-desktops', caption: 'all-desktops', resourceClass: 'fixture',
        onAllDesktops: true, desktops: [], activities: ['activity'],
        output: c.workspace.screens[0], minSize: {width: 10, height: 10}};
    c.workspace.windows.push(w);
    c.windowHandlers.set(w, {window: w});
    c.queueEvent({t: 'windowActivated', window: w});
    c.workspace.desktops.push({id: 'second'});
    c.queueEvent({t: 'updateDrivers'});
    const requested = [];
    c.workspace.rootTile = (output, desktop) => {requested.push(desktop.id); return null;};
    c.processEvents();
    assert.deepEqual(requested.sort(), ['desktop', 'second']);
});

test('retired drivers disconnect tile callbacks across repeated hotplug', () => {
    const {c} = fixture();
    function signal() {
        const callbacks = new Set();
        return {connect(fn) {callbacks.add(fn);}, disconnect(fn) {callbacks.delete(fn);},
            emit() {for (const fn of callbacks) fn();}};
    }
    const roots = new Map();
    c.workspace.rootTile = output => {
        if (!roots.has(output)) roots.set(output, {tiles: [], layoutDirection: 1,
            relativeGeometryChanged: signal(), childTilesChanged: signal()});
        return roots.get(output);
    };
    c.queueEvent({t: 'rebuildDisplays'});
    c.processEvents();
    const survivingRoot = roots.get(c.workspace.screens[0]);
    for (let i = 0; i < 5; i++) {
        c.workspace.screens.push({name: 'hotplug'});
        c.queueEvent({t: 'updateDrivers'});
        c.processEvents();
        c.workspace.screens.pop();
        c.queueEvent({t: 'updateDrivers'});
        c.processEvents();
    }
    survivingRoot.childTilesChanged.emit();
    assert.equal(c.eventQueue.size, 1, 'one tile change must trigger only the current driver callback');
});

test('output recreation rebuilds membership from live windows without empty branches', () => {
    const {c, display} = fixture();
    const [left, right] = c.workspace.screens;
    function window(id, output, extra = {}) {
        const w = {internalId: id, caption: id, minSize: {width: 10, height: 10},
            desktops: c.workspace.desktops, activities: ['activity'], output,
            minimized: false, move: false, tile: null, ...extra};
        c.workspace.windows.push(w);
        c.windowHandlers.set(w, {window: w});
        c.previousDisplays.set(w, [display(output)]);
        const driver = c.getDriver(display(output));
        if (w.minimized || w.quake) driver.addWindowUntiled(w);
        else driver.addWindow(w);
        return w;
    }
    const one = window('one', left);
    const two = window('two', right);
    window('minimized', left, {minimized: true});
    window('quake', left, {quake: true});
    // Remove right, move its window to left, then recreate the same connector.
    c.workspace.screens = [left];
    two.output = left;
    c.updateDrivers();
    function layoutIds(output) {
        const root = c.getDriver(display(output)).tilingEngine.buildLayout();
        const ids = tile => [...tile.windows.map(w => w.id), ...tile.children.flatMap(ids)];
        return Array.from(ids(root)).sort();
    }
    assert.deepEqual(layoutIds(left), ['one', 'two']);
    assert.equal(c.drivers.size, 1, 'removed output drivers must be retired');
    const replacement = {name: 'right'};
    c.workspace.screens = [left, replacement];
    two.output = replacement;
    c.updateDrivers();
    assert.deepEqual(layoutIds(left), ['one']);
    assert.deepEqual(layoutIds(replacement), ['two']);
    assert.equal(c.getDriver(display(left)).tilingEngine.buildLayout().children.length, 0);
    // Some reconnects replace an output with no intervening one-output snapshot.
    const next = {name: 'right'};
    c.workspace.screens = [left, next];
    two.output = next;
    c.updateDrivers();
    assert.deepEqual(layoutIds(next), ['two']);
    assert.equal(c.previousDisplays.get(two)[0].output, next);
    assert.equal(one.output, left);
});
