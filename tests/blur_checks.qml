import QtQuick
import QtTest
import "__PLUGIN_URL__" as Native

Item {
    width: 1024
    height: 576

    Native.ShaderEngine {
        id: engine
        anchors.fill: parent
        running: true
        targetFps: 30
        // Test-controlled uniforms only; no CursorTracker is instantiated.
        mouseEnabled: true
        shaderCode: __SHADER_CODE__
        iChannel0: __EDGE_URL__
        iChannel0Enabled: true
        imageChannels: [0, -1, -1, -1]
    }

    TestCase {
        name: "HeartfeltBlur"
        when: windowShown

        function test_edge() {
            var frame = engine.iFrame
            tryVerify(() => engine.iFrame > frame + 5, 10000)
            compare(engine.compileLog, "")
            verify(waitForRendering(engine, 5000))
            var image = grabImage(engine)
            image.save(__SCREENSHOT__ + "-edge.png")
            var y = Math.floor(image.height / 2)
            var step = Math.max(1, Math.round(image.width / 128))
            var maxSlope = 0, maxJump = 0, previous = 0
            var low = -1, high = -1
            for (var x = Math.floor(image.width / 4); x < 3 * image.width / 4 - step; x += step) {
                var value = image.pixel(x, y).r
                var slope = image.pixel(x + step, y).r - value
                maxSlope = Math.max(maxSlope, slope)
                maxJump = Math.max(maxJump, Math.abs(slope - previous))
                previous = slope
                if (low < 0 && value >= 0.1) low = x
                if (high < 0 && value >= 0.9) high = x
            }
            var width = (high - low) / image.width
            console.log("Edge slope jump:", maxJump / maxSlope, "10-90% width:", width)
            verify(maxSlope > 0.01 && low >= 0 && high > low, "Must render a blurred black-to-white edge")
            verify(maxJump / maxSlope < 0.3, "Fog must not have coarse linear-interpolation slope breaks")
            verify(width < 0.195 && width > 0.09, "Reduce blur modestly, without removing the fog")
        }

        function test_animation_times_data() {
            return [12, 31.416, 94.248, 157.08, 3600].map(time => ({tag: String(time), time: time}))
        }

        function test_animation_times(data) {
            engine.iChannel0 = __TEXTURE_URL__
            engine.iMouse = Qt.vector4d(data.time, 1, 0, 0)
            var frame = engine.iFrame
            tryVerify(() => engine.iFrame > frame + 3, 10000)
            verify(waitForRendering(engine, 5000))
            var image = grabImage(engine)
            image.save(__SCREENSHOT__ + "-" + data.tag + ".png")
            compare(engine.compileLog, "")
            compare(engine.hasError, false)
            compare(image.pixel(Math.floor(image.width / 2), Math.floor(image.height / 2)).a, 1)
        }

        function cleanup() {
            engine.iChannel0 = __EDGE_URL__
            engine.iMouse = Qt.vector4d(0, 0, 0, 0)
        }
    }
}
