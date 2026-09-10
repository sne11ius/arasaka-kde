import QtQuick
import QtTest
import "__PLUGIN_URL__" as Native

Item {
    id: root
    width: 960
    height: 540

    function i18n(text) { return text }

    QtObject {
        id: config
        signal valueChanged()
        property string selectedShaderPath: ""
        property string selectedShaderCode: __SHADER_CODE__
        property bool running: true
        property bool mouseEnabled: true
        property bool rainLockScreenHost: true // Saved values must not grant a host role.
        property bool experimentalScreenUniforms: false
        property int pauseMode: 3
        property bool playlistEnabled: false
        property var playlistShaders: []
        property bool iChannel0Enabled: true
        property url iChannel0: __TEXTURE_URL__
        property int targetFps: 30
    }

    Native.ShaderEngine {
        id: engine
        anchors.fill: parent
        running: true
        targetFps: 30
        speed: 4
        mouseEnabled: true
        iChannel0: __TEXTURE_URL__
        iChannel0Enabled: true
        imageChannels: [0, -1, -1, -1]
    }

    TestCase {
        name: "InteractiveRain"
        when: windowShown

        Component {
            id: invalidRain
            Native.ShaderEngine {
                width: 100
                height: 100
                running: false
                shaderCode: "// @arasaka-effect rain-v1\nvoid mainImage(out vec4 c, in vec2 p) { badColdShader; }"
            }
        }

        function test_coldFailureIsNotSuccess() {
            var rejected = createTemporaryObject(invalidRain, root)
            verify(rejected !== null)
            tryVerify(() => rejected.compileLog.length > 0, 5000, "Fallback must not hide a failed initial rain selection")
            wait(100)
            verify(rejected.compileLog.length > 0)
            compare(rejected.rainActive, false)
        }

        function visibleImage(image) {
            var lit = 0
            for (var y = 10; y < image.height; y += 30) {
                for (var x = 10; x < image.width; x += 30) {
                    var p = image.pixel(x, y)
                    compare(p.a, 1, "Rain output must be opaque")
                    if (p.r + p.g + p.b > 0.015) lit++
                }
            }
            verify(lit > 30, "Rain must render artwork, not black")
        }

        function test_lifecycle() {
            tryVerify(() => engine.iFrame > 2, 10000)
            compare(engine.rainActive, false, "Only committed marked shaders enable native rain")
            engine.shaderCode = __SHADER_CODE__
            tryCompare(engine, "rainActive", true, 10000)
            compare(engine.compileLog, "")
            tryVerify(() => engine.iTime > 12, 15000)
            var first = grabImage(engine)
            var frame = engine.iFrame
            tryVerify(() => engine.iFrame > frame + 12, 10000)
            var second = grabImage(engine)
            verify(!first.equals(second), "Rain must animate")
            visibleImage(second)
            second.save(__SCREENSHOT__)

            engine.running = false
            wait(150)
            var paused = grabImage(engine)
            frame = engine.iFrame
            wait(250)
            // grabImage and property changes provoke incidental redraws while paused.
            engine.screenIndex = 2
            wait(100)
            verify(paused.equals(grabImage(engine)), "Paused history and physics must freeze")
            compare(engine.iFrame, frame)

            engine.shaderSource = "file:///nonexistent/arasaka-rain-missing.frag"
            verify(engine.hasError)
            engine.screenIndex = 3
            wait(100)
            verify(engine.hasError, "A failed file selection must not recompile old code and clear its error")
            compare(engine.rainActive, true)
            verify(paused.equals(grabImage(engine)), "A failed file selection must not reset existing rain")
            engine.shaderSource = ""

            engine.shaderCode = "// @arasaka-effect rain-v1\nvoid mainImage(out vec4 c, in vec2 p) { broken; }"
            tryVerify(() => engine.compileLog.length > 0, 5000)
            compare(engine.rainActive, true)
            verify(paused.equals(grabImage(engine)), "Compile failure must preserve sim, field and image")
            engine.shaderCode = "void mainImage(out vec4 c, in vec2 p) { brokenAgain; }"
            wait(100)
            compare(engine.rainActive, true, "Failed switch away retains committed rain")
            verify(paused.equals(grabImage(engine)))

            engine.resolutionScale = 0.5
            wait(150)
            visibleImage(grabImage(engine))
            root.width = 800
            root.height = 600
            wait(150)
            var resized = grabImage(engine)
            visibleImage(resized)
            wait(150)
            verify(resized.equals(grabImage(engine)), "Resize clears trails once, not on every redraw")
            engine.running = true
            frame = engine.iFrame
            tryVerify(() => engine.iFrame > frame + 5, 10000)
            verify(!resized.equals(grabImage(engine)))

            // A substring or a sampler declaration is not the explicit mode marker.
            engine.shaderCode = "// @arasaka-effect rain-v1 extra\nuniform sampler2D iRainField;\nvoid mainImage(out vec4 c, in vec2 p) { c = vec4(.2,.3,.4,1); }"
            tryCompare(engine, "rainActive", false, 5000)
            tryCompare(engine, "compileLog", "", 5000)
            visibleImage(grabImage(engine))
            engine.shaderCode = __SHADER_CODE__
            tryCompare(engine, "rainActive", true, 5000)
            engine.resetTime()
            verify(engine.iTime < 1, "Reset restarts rain time explicitly")
            console.log("Rain lifecycle: committed, animated, frozen, retained on failure, resized, switched, reset")
        }

        function test_stockInputDisabledInRealHostQml() {
            failOnWarning(/.*(rainLockScreenHost|non-existent property).*/)
            config.selectedShaderCode = __SHADER_CODE__
            config.mouseEnabled = true
            var component = Qt.createComponent(__SYSTEM_URL__)
            compare(component.status, Component.Ready, component.errorString())
            var system = createTemporaryObject(component, root, {wallpaperConfig: config})
            verify(system !== null)
            function setHost(lock, login) {
                system.inputHost = { window: system.Window.window, lockScreenMode: lock, loginScreenMode: login }
            }
            var hostEngine = null, tracker = null, area = null
            for (var i = 0; i < system.data.length; ++i) {
                var object = system.data[i]
                if (typeof object.rainActive !== "undefined") hostEngine = object
                if (typeof object.updateClick === "function") tracker = object
                if (typeof object.propagateComposedEvents !== "undefined") area = object
            }
            verify(hostEngine !== null && tracker !== null && area !== null)
            var restrictedLeak = false
            function checkRestricted() {
                if (system.restrictedMode && (tracker.enabled || area.enabled || area.hoverEnabled))
                    restrictedLeak = true
            }
            tracker.enabledChanged.connect(checkRestricted)
            area.enabledChanged.connect(checkRestricted)
            area.hoverEnabledChanged.connect(checkRestricted)
            compare(hostEngine.mouseEnabled, false, "Unclassified hosts must reject mouse permission")
            compare(tracker.enabled, false)
            compare(area.enabled, false)
            setHost(false, false)
            tryCompare(hostEngine, "rainActive", true, 10000)
            compare(tracker.enabled, false, "Rain must disable global cursor polling")
            compare(area.enabled, false, "Rain must disable stock MouseArea forwarding, not just its timer")
            compare(area.hoverEnabled, false)
            compare(hostEngine.mouseEnabled, true)
            if (__LOCK_HOST_SUPPORTED__)
                compare(hostEngine.rainLockScreenHost, false)
            else
                compare(typeof hostEngine.rainLockScreenHost, "undefined", "Compatibility check must load the previous module")
            setHost(true, false)
            compare(hostEngine.mouseEnabled, __LOCK_HOST_SUPPORTED__, "Only capable committed Rain may observe lockscreen hover")
            if (__LOCK_HOST_SUPPORTED__)
                compare(hostEngine.rainLockScreenHost, true)
            config.mouseEnabled = false
            compare(hostEngine.mouseEnabled, false)
            config.mouseEnabled = true
            compare(hostEngine.mouseEnabled, __LOCK_HOST_SUPPORTED__)
            // Both greeters use the same committed native Rain interaction.
            setHost(true, true)
            compare(hostEngine.mouseEnabled, __LOCK_HOST_SUPPORTED__)
            if (__LOCK_HOST_SUPPORTED__)
                compare(hostEngine.rainLockScreenHost, true)
            setHost(false, true)
            compare(hostEngine.mouseEnabled, __LOCK_HOST_SUPPORTED__)
            setHost(false, false)
            compare(hostEngine.mouseEnabled, true)
            setHost(true, false)
            config.selectedShaderCode = "void mainImage(out vec4 c, in vec2 p) { c = vec4(.2,.3,.4,1); }"
            tryCompare(hostEngine, "rainActive", false, 5000)
            compare(hostEngine.mouseEnabled, false, "Ordinary lockscreen shaders cannot use the Rain exception")
            compare(tracker.enabled, false)
            compare(area.enabled, false)
            compare(area.hoverEnabled, false)
            verify(!restrictedLeak, "Generic input must stay off throughout restricted role/selection transitions")
            setHost(false, false)
            compare(tracker.enabled, true, "Ordinary shader cursor behavior must return")
            compare(area.enabled, true)
            compare(hostEngine.mouseEnabled, true)
        }
    }
}
