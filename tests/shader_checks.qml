import QtQuick
import QtTest
import "__PLUGIN_URL__" as Native

Item {
    width: 960
    height: 540

    Native.ShaderEngine {
        id: engine
        anchors.fill: parent
        running: true
        targetFps: 30
        speed: 4
        iChannel0: __TEXTURE_URL__
        iChannel0Enabled: true
        imageChannels: [0, -1, -1, -1]
    }

    TestCase {
        name: "ShaderRendering"
        when: windowShown

        function test_render() {
            tryVerify(() => engine.iFrame > 2, 10000)
            engine.compileShader("void mainImage(out vec4 c, in vec2 p) { invalidIdentifier; }")
            tryVerify(() => engine.compileLog.length > 0, 5000)
            verify(engine.loadShader(__SHADER_URL__))
            tryCompare(engine, "compileLog", "", 10000)
            compare(engine.hasError, false)
            tryVerify(() => engine.iTime > 12, 15000)
            verify(waitForRendering(engine, 5000))
            var first = grabImage(engine)
            var frame = engine.iFrame
            tryVerify(() => engine.iFrame > frame + 12, 10000)
            verify(waitForRendering(engine, 5000))
            var second = grabImage(engine)
            second.save(__SCREENSHOT__)
            verify(!second.equals(first), "The shader must produce changing pixels")
            var lit = 0
            for (var y = 20; y < second.height; y += 40) {
                for (var x = 20; x < second.width; x += 40) {
                    var pixel = second.pixel(x, y)
                    if (pixel.r + pixel.g + pixel.b > 0.015) lit++
                    verify(pixel.a > 0.99, "Wallpaper pixels must be opaque")
                }
            }
            verify(lit > 20, "The shader must render visible content, not black")
            compare(engine.compileLog, "")
            compare(engine.hasError, false)
            console.log("Rendered frames:", engine.iFrame, "time:", engine.iTime, "lit samples:", lit)
        }
    }
}
