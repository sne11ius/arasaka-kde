#include "core/shaderengine.h"
#include <QDir>
#include <QFile>
#include <QKeyEvent>
#include <QMouseEvent>
#include <QOffscreenSurface>
#include <QOpenGLContext>
#include <QOpenGLExtraFunctions>
#include <QtTest>
#include <QTemporaryDir>
#include <cmath>
#include <functional>

namespace arasaka::rain {
struct DropletSimulationTestAccess {
    static double pendingSeconds(const DropletSimulation &simulation) { return simulation.pointerTime_; }
    static std::size_t pendingMotions(const DropletSimulation &simulation) { return simulation.pointerMotions_.size(); }
    static void placeProbe(DropletSimulation &simulation, double x) {
        simulation.drops_ = {{1, {x, 120}, {x, 120}, {}, 64}};
    }
};
}

// Count real Qt shader compiler failures without adding instrumentation to the host.
class CompileDiagnostics {
public:
    CompileDiagnostics() { failures = 0; previous = qInstallMessageHandler(handle); }
    ~CompileDiagnostics() { qInstallMessageHandler(previous); }
    static inline int failures = 0;
private:
    static inline QtMessageHandler previous = nullptr;
    static void handle(QtMsgType type, const QMessageLogContext &context, const QString &message) {
        if (type == QtWarningMsg && message.startsWith(QStringLiteral("QOpenGLShader::compile("))) ++failures;
        if (previous) previous(type, context, message);
    }
};

class RainHostTest : public QObject {
    Q_OBJECT
    QOpenGLContext context;
    QOffscreenSurface surface;
    const QString plain = QStringLiteral("void mainImage(out vec4 c, in vec2 p) { c = vec4(.2,.3,.4,1); }");
    QString rain() const { return QStringLiteral("// @arasaka-effect rain-v1\n") + plain; }

    QVector4D imagePixel(ShaderEngineRenderer &renderer) {
        renderer.initializeGL();
        if (!renderer.m_lowResFBO) {
            renderer.m_fboSize = renderer.m_lowResSize = QSize(8, 8);
            renderer.m_lowResFBO = std::make_unique<QOpenGLFramebufferObject>(
                QSize(8, 8), QOpenGLFramebufferObject::NoAttachment, GL_TEXTURE_2D, GL_RGBA32F);
        }
        auto *f = context.extraFunctions();
        f->glDisable(GL_BLEND);
        f->glDisable(GL_DEPTH_TEST);
        f->glDisable(GL_SCISSOR_TEST);
        f->glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
        for (int i = 0; i < 4; ++i) renderer.renderBuffer(i);
        renderer.renderMainPass();
        GLfloat pixel[4]{};
        f->glReadPixels(4, 4, 1, 1, GL_RGBA, GL_FLOAT, pixel);
        renderer.m_pingPong = !renderer.m_pingPong;
        return {pixel[0], pixel[1], pixel[2], pixel[3]};
    }

private Q_SLOTS:
    void initTestCase() {
        QSurfaceFormat format;
        format.setVersion(3, 3);
        format.setProfile(QSurfaceFormat::CoreProfile);
        context.setFormat(format);
        QVERIFY(context.create());
        surface.setFormat(context.format());
        surface.create();
        QVERIFY(context.makeCurrent(&surface));
    }

    void init() {
        QCoreApplication::processEvents();
        QVERIFY(context.makeCurrent(&surface));
    }

    void transactionRetainsProgramSimulationAndField() {
        ShaderEngine engine;
        engine.setRunning(false);
        engine.setSize({640, 480});
        engine.setShaderCode(rain());
        ShaderEngineRenderer renderer;
        renderer.synchronize(&engine);
        QCoreApplication::processEvents();
        QVERIFY(engine.rainActive());
        QVERIFY(engine.m_rainInput);
        auto *program = renderer.m_shaderProgram.get();
        auto *simulation = renderer.m_rainSimulation.get();
        auto texture = renderer.m_rainField->texture();
        const auto first = simulation->drops().front();
        engine.setShaderCode(QStringLiteral("// @arasaka-effect rain-v1\ninvalid"));
        renderer.synchronize(&engine);
        QCoreApplication::processEvents();
        QVERIFY(engine.rainActive());
        QVERIFY(!engine.compileLog().isEmpty());
        QCOMPARE(renderer.m_shaderProgram.get(), program);
        QCOMPARE(renderer.m_rainSimulation.get(), simulation);
        QCOMPARE(renderer.m_rainField->texture(), texture);
        QCOMPARE(simulation->drops().front().position, first.position);

        // An actual failed allocation precondition must not commit a linked rain candidate.
        engine.setSize({0, 0});
        engine.setShaderCode(rain() + QStringLiteral("\n// reload"));
        renderer.synchronize(&engine);
        QCoreApplication::processEvents();
        QVERIFY(engine.compileLog().contains(QStringLiteral("Rain resources")));
        QCOMPARE(renderer.m_shaderProgram.get(), program);
        QCOMPARE(renderer.m_rainSimulation.get(), simulation);
        QCOMPARE(renderer.m_rainField->texture(), texture);
        QVERIFY(engine.rainActive());
    }

    void staleSelectionAndRendererCallbacksAreRejected() {
        ShaderEngine engine;
        engine.setRunning(false);
        engine.setSize({320, 240});
        engine.setShaderCode(rain());
        auto old = std::make_unique<ShaderEngineRenderer>();
        old->synchronize(&engine);
        engine.setShaderCode(plain);
        QCoreApplication::processEvents();
        QVERIFY(!engine.rainActive()); // queued rain success belongs to an older selection
        ShaderEngineRenderer replacement;
        replacement.synchronize(&engine);
        old.reset();
        QCoreApplication::processEvents();
        QVERIFY(!engine.rainActive());
        engine.setShaderCode(rain());
        replacement.synchronize(&engine);
        QCoreApplication::processEvents();
        QVERIFY(engine.rainActive());
        // A dying, stale renderer must not clear the current renderer's input.
        auto stale = std::make_unique<ShaderEngineRenderer>();
        stale->m_engineForCallbacks = &engine;
        stale.reset();
        QCoreApplication::processEvents();
        QVERIFY(engine.rainActive());
        engine.setShaderCode(plain);
        replacement.synchronize(&engine);
        QCoreApplication::processEvents();
        QVERIFY(!engine.rainActive());
        QVERIFY(!engine.m_rainInput);
        QVERIFY(!replacement.m_rainSimulation && !replacement.m_rainField);
    }

    void resizeResolutionAndIndependentReset() {
        ShaderEngine first, second;
        first.setRunning(false);
        second.setRunning(false);
        first.setSize({640, 480});
        second.setSize({640, 480});
        first.setShaderCode(rain());
        second.setShaderCode(rain());
        ShaderEngineRenderer a, b;
        a.synchronize(&first);
        b.synchronize(&second);
        QVERIFY(a.m_rainSimulation.get() != b.m_rainSimulation.get());
        QVERIFY(a.m_rainField->texture() != b.m_rainField->texture());
        const auto original = a.m_rainSimulation->drops().front();
        auto texture = a.m_rainField->texture();
        first.setResolutionScale(.5);
        a.synchronize(&first);
        QCOMPARE(a.m_rainField->texture(), texture);
        QCOMPARE(a.m_rainSimulation->drops().front().position, original.position);
        first.setSize({1280, 960});
        a.synchronize(&first);
        const auto resized = a.m_rainSimulation->drops().front();
        QCOMPARE(resized.id, original.id);
        QCOMPARE(resized.volume, original.volume);
        QCOMPARE(resized.position.x, original.position.x * 2);
        QCOMPARE(resized.position.y, original.position.y * 2);
        QCOMPARE(b.m_rainSimulation->drops().front().position, original.position);
        first.resetTime();
        a.synchronize(&first);
        QCOMPARE(a.m_iTimeDelta, 0);
        QCOMPARE(a.m_rainSimulation->drops().size(), std::size_t(1024));
        QCOMPARE(b.m_rainSimulation->drops().front().position, original.position);
    }

    void pauseClearsDeltaAndInputEvenWithoutInterveningSync() {
        ShaderEngine engine;
        engine.setSize({320, 240});
        engine.setShaderCode(rain());
        engine.setMouseEnabled(true);
        ShaderEngineRenderer renderer;
        renderer.synchronize(&engine);
        QCoreApplication::processEvents();
        QVERIFY(engine.m_rainInput);
        const auto cancellation = engine.m_rainInput->invalidationSequence();
        engine.setRunning(false);
        engine.accumulateFrame();
        QCOMPARE(engine.lastTimeDelta(), 0);
        engine.setRunning(true);
        QVERIFY(engine.m_rainInput->invalidationSequence() > cancellation);
        renderer.synchronize(&engine);
        QVERIFY(renderer.m_iTimeDelta < .05);
        QVERIFY(!renderer.m_rainPointer.valid);
        const auto allowed = engine.m_rainInput->invalidationSequence();
        engine.setMouseEnabled(false);
        engine.setMouseEnabled(true);
        QVERIFY(engine.m_rainInput->invalidationSequence() > allowed);
    }

    void rejectedSelectionKeepsLiveInputs_data() {
        QTest::addColumn<bool>("missingFile");
        QTest::newRow("invalid-main") << false;
        QTest::newRow("missing-file") << true;
    }

    void lockHostHoverIsLocalPassiveAndCancelledOnModeChanges() {
        class Window : public QQuickWindow {
        public:
            int presses = 0, releases = 0, keys = 0;
            void mousePressEvent(QMouseEvent *event) override { ++presses; event->accept(); }
            void mouseReleaseEvent(QMouseEvent *event) override { ++releases; event->accept(); }
            void keyPressEvent(QKeyEvent *event) override { ++keys; event->accept(); }
        } window, other;
        window.resize(320, 240);
        ShaderEngine engine(window.contentItem());
        engine.setFlag(QQuickItem::ItemHasContents, false);
        engine.setSize({320, 240});
        engine.setMouseEnabled(true);
        QVERIFY2(engine.property("rainLockScreenHost").isValid(), "Native host must expose explicit lockscreen mode");
        QCOMPARE(engine.property("rainLockScreenHost").toBool(), false);
        QVERIFY(engine.setProperty("rainLockScreenHost", true));
        QVERIFY(!engine.m_rainInput); // Host permission alone cannot activate uncommitted Rain.
        engine.setShaderCode(rain());
        window.show();
        QVERIFY(QTest::qWaitForWindowExposed(&window));
        QVERIFY(context.makeCurrent(&surface));
        ShaderEngineRenderer renderer;
        renderer.synchronize(&engine);
        QCoreApplication::processEvents();
        QVERIFY(engine.rainActive() && engine.m_rainInput);
        auto &input = *engine.m_rainInput;
        QVERIFY(QMetaObject::invokeMethod(&input, "sessionLockChanged", Q_ARG(bool, true)));
        const auto move = [&](QQuickWindow &target, QPointF point, Qt::MouseButtons buttons = Qt::NoButton) {
            QMouseEvent event(QEvent::MouseMove, point, point, Qt::NoButton, buttons, Qt::NoModifier);
            QCoreApplication::sendEvent(&target, &event);
        };
        move(other, {30, 30});
        QVERIFY(!input.snapshot().valid);
        move(window, {30, 30});
        QVERIFY(input.snapshot().valid);
        QCOMPARE(input.snapshot().position, (arasaka::rain::Vec2{30, 30}));
        QKeyEvent key(QEvent::KeyPress, Qt::Key_A, Qt::NoModifier, QStringLiteral("a"));
        QCoreApplication::sendEvent(&window, &key);
        QCOMPARE(window.keys, 1);
        QVERIFY(input.snapshot().valid); // Keyboard events are not interpreted as pointer input.
        QMouseEvent press(QEvent::MouseButtonPress, {30, 30}, {30, 30}, Qt::LeftButton, Qt::LeftButton, Qt::NoModifier);
        QCoreApplication::sendEvent(&window, &press);
        QCOMPARE(window.presses, 1);
        QVERIFY(!input.snapshot().valid);
        move(window, {40, 30}, Qt::LeftButton);
        QVERIFY(!input.snapshot().valid);
        QMouseEvent release(QEvent::MouseButtonRelease, {40, 30}, {40, 30}, Qt::LeftButton, Qt::NoButton, Qt::NoModifier);
        QCoreApplication::sendEvent(&window, &release);
        QCOMPARE(window.releases, 1);
        QVERIFY(!input.snapshot().valid);
        move(window, {40, 30});
        QVERIFY(input.snapshot().valid);
        move(window, {-1, 30});
        QVERIFY(!input.snapshot().valid);
        for (auto type : {QEvent::Leave, QEvent::WindowDeactivate, QEvent::UngrabMouse, QEvent::TouchCancel}) {
            move(window, {40, 30});
            QVERIFY(input.snapshot().valid);
            QEvent cancel(type);
            QCoreApplication::sendEvent(&window, &cancel);
            QVERIFY(!input.snapshot().valid);
        }
        move(window, {40, 30});
        engine.setVisible(false);
        QVERIFY(!input.snapshot().valid);
        move(window, {40, 30});
        QVERIFY(!input.snapshot().valid);
        engine.setVisible(true);
        engine.setEnabled(false);
        move(window, {40, 30});
        QVERIFY(!input.snapshot().valid);
        engine.setEnabled(true);
        move(window, {40, 30});
        QVERIFY(input.snapshot().valid);

        const auto revision = input.invalidationSequence();
        QVERIFY(engine.setProperty("rainLockScreenHost", false));
        QVERIFY(!input.snapshot().valid);
        QVERIFY(input.invalidationSequence() > revision);
        move(window, {50, 30});
        QVERIFY(!input.snapshot().valid); // Locked desktop must still reject its own window.
        QVERIFY(engine.setProperty("rainLockScreenHost", true));
        QVERIFY(!input.snapshot().valid);
        move(window, {50, 30});
        QVERIFY(input.snapshot().valid);
        renderer.m_rainSimulation->advance(.01, {{40, 30}, true, 1, 0});
        renderer.m_rainSimulation->advance(.001, {{50, 30}, true, 2, .2});
        QVERIFY(arasaka::rain::DropletSimulationTestAccess::pendingMotions(*renderer.m_rainSimulation) > 0);
        QVERIFY(engine.setProperty("rainLockScreenHost", false));
        QVERIFY(engine.setProperty("rainLockScreenHost", true)); // No intervening render.
        renderer.synchronize(&engine);
        QVERIFY(!renderer.m_rainPointer.valid);
        QCOMPARE(arasaka::rain::DropletSimulationTestAccess::pendingMotions(*renderer.m_rainSimulation), std::size_t(0));
        for (const auto property : {"running", "mouseEnabled", "speed"}) {
            move(window, {60, 30});
            QVERIFY(input.snapshot().valid);
            QVERIFY(engine.setProperty(property, 0));
            move(window, {70, 30});
            QVERIFY(!input.snapshot().valid);
            QVERIFY(engine.setProperty(property, 1));
            QVERIFY(!input.snapshot().valid);
        }
        QVERIFY(engine.setProperty("rainLockScreenHost", false));
        QVERIFY(QMetaObject::invokeMethod(&input, "sessionLockChanged", Q_ARG(bool, false)));
        move(window, {70, 30});
        QVERIFY(input.snapshot().valid);
    }

    void sustainedPointerUsesActiveClock_data() {
        QTest::addColumn<double>("speed");
        QTest::addColumn<int>("frameMilliseconds");
        QTest::addColumn<int>("frames");
        QTest::addColumn<bool>("lockHost");
        QTest::newRow("managed-0.75") << .75 << 33 << 180 << false;
        QTest::newRow("locked-host-0.75") << .75 << 33 << 180 << true;
        QTest::newRow("slow-0.5") << .5 << 33 << 180 << false;
        QTest::newRow("fast-4") << 4. << 33 << 180 << false;
        QTest::newRow("wall-clamp") << .75 << 160 << 15 << false;
        QTest::newRow("physics-clamp") << 4. << 160 << 15 << false;
    }

    void sustainedPointerUsesActiveClock() {
        QFETCH(double, speed);
        QFETCH(int, frameMilliseconds);
        QFETCH(int, frames);
        QFETCH(bool, lockHost);
        using Access = arasaka::rain::DropletSimulationTestAccess;
        QQuickWindow window;
        window.resize(320, 240);
        ShaderEngine engine(window.contentItem());
        // Synchronize explicitly; the window is only the real passive-input event target.
        engine.setFlag(QQuickItem::ItemHasContents, false);
        engine.setSize({320, 240});
        engine.setSpeed(speed);
        if (lockHost) QVERIFY(engine.setProperty("rainLockScreenHost", true));
        engine.setMouseEnabled(true);
        engine.setShaderCode(rain());
        window.show();
        QVERIFY(QTest::qWaitForWindowExposed(&window));
        QVERIFY(context.makeCurrent(&surface));
        ShaderEngineRenderer renderer;
        renderer.synchronize(&engine);
        QCoreApplication::processEvents();
        QVERIFY(engine.m_rainInput);
        QVERIFY(QMetaObject::invokeMethod(engine.m_rainInput.get(), "sessionLockChanged", Q_ARG(bool, lockHost)));
        // No rainfall/collisions; a fresh probe detects discarded sweeps even if delay looks bounded.
        renderer.m_rainSimulation->reset(320, 240, 1, 0);
        const auto advance = [&] {
            renderer.synchronize(&engine);
            renderer.m_rainSimulation->advance(std::clamp(double(renderer.m_iTimeDelta), 0., .25), renderer.m_rainPointer);
        };
        arasaka::rain::PointerSnapshot previous, previousRaw;
        double maximumDelay = 0;
        for (int frame = 0; frame < frames; ++frame) {
            QTest::qSleep(frameMilliseconds);
            const QPointF point(160 + 80 * std::sin(frame * .08), 120);
            QMouseEvent move(QEvent::MouseMove, point, point, Qt::NoButton, Qt::NoButton, Qt::NoModifier);
            QCoreApplication::sendEvent(&window, &move);
            const auto raw = engine.m_rainInput->snapshot();
            QVERIFY(raw.valid);
            Access::placeProbe(*renderer.m_rainSimulation, point.x());
            advance();
            const auto mapped = renderer.m_rainPointer;
            QVERIFY(mapped.valid);
            QCOMPARE(mapped.sequence, raw.sequence);
            QCOMPARE(mapped.position, raw.position);
            if (frame) {
                QCOMPARE(mapped.sequence, previous.sequence + 1);
                QVERIFY(mapped.sampleSeconds > previous.sampleSeconds);
                QVERIFY2(std::abs(renderer.m_rainSimulation->drops().front().velocity.x) > 1e-6,
                         "Each accepted moving sample must exert force, not be periodically dropped to bound delay");
                if (frameMilliseconds == 33)
                    QVERIFY2(std::abs((mapped.sampleSeconds - previous.sampleSeconds)
                        - speed * (raw.sampleSeconds - previousRaw.sampleSeconds)) < .003,
                        "Source intervals must use playback speed, not receiving-frame duration");
            }
            previous = mapped;
            previousRaw = raw;
            const double delay = Access::pendingSeconds(*renderer.m_rainSimulation);
            maximumDelay = std::max(maximumDelay, delay);
            QVERIFY2(delay <= .25 + 2 * arasaka::rain::DropletSimulation::fixedStep,
                     "Sustained input delay must remain bounded by admitted frame time, not grow until queue overflow");
            QVERIFY(Access::pendingMotions(*renderer.m_rainSimulation) <= 3);
            advance(); // Held sequence must keep its original active timestamp.
            QCOMPARE(renderer.m_rainPointer.sequence, mapped.sequence);
            QCOMPARE(renderer.m_rainPointer.sampleSeconds, mapped.sampleSeconds);
        }
        qInfo() << "speed" << speed << "frame ms" << frameMilliseconds << "maximum pending seconds" << maximumDelay;
        for (int frame = 0; frame < 12; ++frame) {
            QTest::qSleep(33);
            advance();
        }
        QCOMPARE(Access::pendingMotions(*renderer.m_rainSimulation), std::size_t(0));

        const auto cancellation = engine.m_rainInput->invalidationSequence();
        engine.setSpeed(0);
        QMouseEvent frozenMove(QEvent::MouseMove, {20, 20}, {20, 20}, Qt::NoButton, Qt::NoButton, Qt::NoModifier);
        QCoreApplication::sendEvent(&window, &frozenMove);
        QVERIFY(!engine.m_rainInput->snapshot().valid);
        engine.setSpeed(speed); // Also cancel if no render occurs while speed is zero.
        QVERIFY(engine.m_rainInput->invalidationSequence() > cancellation);
        advance();
        QVERIFY(!renderer.m_rainPointer.valid);
        QCOMPARE(Access::pendingMotions(*renderer.m_rainSimulation), std::size_t(0));
        const auto changed = engine.m_rainInput->invalidationSequence();
        engine.setSpeed(speed * .8);
        QVERIFY(engine.m_rainInput->invalidationSequence() > changed);
    }

    void rejectedSelectionKeepsLiveInputs() {
        QFETCH(bool, missingFile);
        ShaderEngine engine;
        engine.setSize({640, 480});
        engine.setShaderCode(QStringLiteral(
            "void mainImage(out vec4 c, in vec2 p) { c = vec4("
            "texture(iChannel0, vec2(.5)).r, iWindowRects[0].x / 100.,"
            "iScreenOffset.x / 100. + iVirtualDesktopAnim, 1.); }"));
        engine.setUseBufferA(true);
        engine.setBufferACode(plain);
        engine.setImageChannels({20, -1, -1, -1});
        engine.setAudioEnabled(true);
        engine.setAudioData(QVariantList(4096, QVariant(.2f)));
        engine.setWindowsEnabled(true);
        engine.setWindowCount(1);
        engine.setWindowRects({20, 30, 40, 50});
        engine.setWindowVelocities({0, 0});
        engine.setScreenOffset({20, 0});
        ShaderEngineRenderer renderer;
        renderer.synchronize(&engine);
        QCoreApplication::processEvents();
        const auto initial = imagePixel(renderer);
        QVERIFY(std::abs(initial.x() - .2f) < .001f);
        QVERIFY(std::abs(initial.y() - .2f) < .001f);
        QVERIFY(std::abs(initial.z() - .2f) < .001f);
        auto *program = renderer.m_shaderProgram.get();
        auto *buffer = renderer.m_bufferPrograms[0].get();

        if (missingFile) {
            engine.setShaderSource(QUrl::fromLocalFile(qEnvironmentVariable("XDG_DATA_HOME") + QStringLiteral("/missing.frag")));
            QVERIFY(engine.hasError());
        } else {
            engine.setShaderCode(QStringLiteral("void mainImage(out vec4 c, in vec2 p) { invalidMain; }"));
        }
        engine.setUseBufferA(false);
        engine.setImageChannels({0, 1, 2, 3});
        engine.setBufferAChannels({10, 1, 2, 3});
        engine.setIChannel0Enabled(false);
        for (int sample : {60, 70}) {
            const auto time = renderer.m_iTime;
            QTest::qWait(2);
            engine.setAudioChannel(1);
            engine.setAudioData(QVariantList(4096, QVariant(float(sample) / 100)));
            engine.setWindowCount(2);
            engine.setWindowRects({sample, 30, 40, 50, 5, 6, 7, 8});
            engine.setScreenOffset({float(sample), 10});
            engine.setScreenIndex(2);
            engine.setScreenCount(3);
            engine.setVirtualDesktop(2);
            engine.setVirtualDesktopCount(4);
            engine.setVirtualDesktopAnim(.1);
            renderer.synchronize(&engine);
            QCoreApplication::processEvents();
            QCOMPARE(renderer.m_shaderProgram.get(), program);
            QCOMPARE(renderer.m_bufferPrograms[0].get(), buffer);
            QVERIFY(renderer.m_useBuffers[0]);
            QCOMPARE(renderer.m_imageChannelMapping[0], 20);
            QCOMPARE(renderer.m_bufferChannelMapping[0][0], -1);
            QVERIFY(renderer.m_channelEnabled[0]);
            QVERIFY(renderer.m_iTime > time);
            const auto pixel = imagePixel(renderer);
            qInfo() << "Retained live input sample" << sample << "pixel" << pixel;
            QVERIFY2(std::abs(pixel.x() - float(sample) / 100) < .001f, "Retained shader must consume fresh audio");
            QVERIFY2(std::abs(pixel.y() - float(sample) / 100) < .001f, "Retained shader must consume fresh window positions");
            QVERIFY2(std::abs(pixel.z() - (float(sample) / 100 + .1f)) < .001f, "Retained shader must consume fresh screen/desktop uniforms");
            QCOMPARE(renderer.m_audioChannel, 1);
            QCOMPARE(renderer.m_windowCount, 2);
            QCOMPARE(renderer.m_screenIndex, 2);
            QCOMPARE(renderer.m_screenCount, 3);
            QCOMPARE(renderer.m_virtualDesktop, 2);
            QCOMPARE(renderer.m_virtualDesktopCount, 4);
            if (missingFile) QVERIFY(engine.hasError());
            else QVERIFY(!engine.compileLog().isEmpty());
        }
        engine.setAudioEnabled(false);
        engine.setWindowsEnabled(false);
        engine.setWindowCount(0);
        renderer.synchronize(&engine);
        QVERIFY(!renderer.m_audioEnabled);
        QVERIFY(!renderer.m_windowsEnabled);
        QCOMPARE(renderer.m_windowCount, 0);
    }

    void commonChangeSurvivesRejectedMain_data() {
        QTest::addColumn<bool>("deferredBuffer");
        QTest::newRow("enabled-buffer") << false;
        QTest::newRow("re-enabled-buffer") << true;
    }

    void commonChangeSurvivesRejectedMain() {
        QFETCH(bool, deferredBuffer);
        ShaderEngine engine;
        engine.setRunning(false);
        engine.setSize({640, 480});
        const auto main = QStringLiteral("void mainImage(out vec4 c, in vec2 p) { c = vec4(texture(iChannel0, p/iResolution.xy).r, gain, 0., 1.); }");
        engine.setShaderCode(main);
        engine.setCommonCode(QStringLiteral("const float gain = .2;"));
        engine.setUseBufferA(true);
        engine.setBufferACode(QStringLiteral("void mainImage(out vec4 c, in vec2 p) { c = vec4(gain); }"));
        engine.setImageChannels({10, -1, -1, -1});
        ShaderEngineRenderer renderer;
        renderer.synchronize(&engine);
        QCoreApplication::processEvents();
        const auto initial = imagePixel(renderer);
        QVERIFY(std::abs(initial.x() - .2f) < .001f);
        QVERIFY(std::abs(initial.y() - .2f) < .001f);
        auto *buffer = renderer.m_bufferPrograms[0].get();
        engine.setCommonCode(QStringLiteral("const float gain = .8;"));
        engine.setShaderCode(QStringLiteral("void mainImage(out vec4 c, in vec2 p) { invalidMain; }"));
        for (int i = 0; i < 2; ++i) {
            renderer.synchronize(&engine);
            QCoreApplication::processEvents();
            QCOMPARE(renderer.m_bufferPrograms[0].get(), buffer);
            QVERIFY(!engine.compileLog().isEmpty());
            QCOMPARE(imagePixel(renderer), initial);
        }
        engine.setShaderCode(main); // Correct only main; Common and buffer source are unchanged.
        if (deferredBuffer) engine.setUseBufferA(false);
        renderer.synchronize(&engine);
        if (deferredBuffer) {
            QCOMPARE(renderer.m_bufferPrograms[0].get(), buffer);
            engine.setUseBufferA(true);
            renderer.synchronize(&engine);
        }
        QCoreApplication::processEvents();
        QCOMPARE(engine.compileLog(), QString());
        const auto recovered = imagePixel(renderer);
        qInfo() << "Recovered buffer/main Common gains:" << recovered.x() << recovered.y();
        QVERIFY2(std::abs(recovered.x() - .8f) < .001f, "Recovered buffer must use pending Common code, not stale gain .2");
        QVERIFY(std::abs(recovered.y() - .8f) < .001f);
    }

    void failedBufferCommonRetainsFeedbackAndAttemptsOnce_data() {
        QTest::addColumn<bool>("correctCommon");
        QTest::newRow("correct-buffer-source") << false;
        QTest::newRow("correct-common-source") << true;
    }

    void failedBufferCommonRetainsFeedbackAndAttemptsOnce() {
        QFETCH(bool, correctCommon);
        ShaderEngine engine;
        engine.setRunning(false);
        engine.setSize({640, 480});
        const auto main = QStringLiteral("void mainImage(out vec4 c, in vec2 p) { c = texture(iChannel0, p / iResolution.xy); }");
        const auto buffer = QStringLiteral("void mainImage(out vec4 c, in vec2 p) { c = vec4(texture(iChannel0, p / iResolution.xy).r + gain, 0., 0., 1.); }");
        engine.setShaderCode(main);
        engine.setCommonCode(QStringLiteral("const float gain = .2;"));
        engine.setUseBufferA(true);
        engine.setBufferACode(buffer);
        engine.setImageChannels({10, -1, -1, -1});
        engine.setBufferAChannels({10, -1, -1, -1});
        ShaderEngineRenderer renderer;
        renderer.synchronize(&engine);
        QCoreApplication::processEvents();
        for (float expected : {.2f, .4f, .6f})
            QVERIFY(std::abs(imagePixel(renderer).x() - expected) < .001f);
        auto *working = renderer.m_bufferPrograms[0].get();
        const auto front = renderer.m_bufferFBOs[0]->texture();
        const auto back = renderer.m_bufferFBOsBack[0]->texture();
        CompileDiagnostics diagnostics;
        engine.setCommonCode(QStringLiteral("const float renamedGain = .8;"));
        renderer.synchronize(&engine);
        QCoreApplication::processEvents();
        QCOMPARE(CompileDiagnostics::failures, 1);
        QVERIFY(engine.compileLog().contains(QStringLiteral("buffer A")));
        const auto failure = engine.compileLog();
        std::vector<float> retained;
        for (int frame = 0; frame < 3; ++frame) {
            if (frame == 1) engine.setShaderCode(main + QStringLiteral("\n// main-only edit"));
            renderer.synchronize(&engine);
            QCoreApplication::processEvents();
            QCOMPARE(renderer.m_bufferPrograms[0].get(), working);
            QCOMPARE(renderer.m_bufferFBOs[0]->texture(), front);
            QCOMPARE(renderer.m_bufferFBOsBack[0]->texture(), back);
            QCOMPARE(engine.compileLog(), failure);
            retained.push_back(imagePixel(renderer).x());
        }
        qInfo() << "Failed buffer compile count:" << CompileDiagnostics::failures
                << "retained feedback:" << retained[0] << retained[1] << retained[2];
        QCOMPARE(CompileDiagnostics::failures, 1);
        QVERIFY(std::abs(retained[0] - .8f) < .001f);
        QVERIFY(std::abs(retained[1] - 1.f) < .001f);
        QVERIFY(std::abs(retained[2] - 1.2f) < .001f);

        // Toggling use must neither retry the same rejected pair nor lose its diagnostic.
        engine.setUseBufferA(false);
        renderer.synchronize(&engine);
        engine.setUseBufferA(true);
        renderer.synchronize(&engine);
        QCoreApplication::processEvents();
        QCOMPARE(CompileDiagnostics::failures, 1);
        QCOMPARE(engine.compileLog(), failure);
        QVERIFY(std::abs(imagePixel(renderer).x() - 1.4f) < .001f);

        if (correctCommon) engine.setCommonCode(QStringLiteral("const float gain = .8;"));
        else engine.setBufferACode(QString(buffer).replace(QStringLiteral("gain"), QStringLiteral("renamedGain")));
        renderer.synchronize(&engine);
        QCoreApplication::processEvents();
        QCOMPARE(CompileDiagnostics::failures, 1);
        QCOMPARE(engine.compileLog(), QString());
        QVERIFY(renderer.m_bufferPrograms[0].get() != working);
        QVERIFY(renderer.m_bufferNeedsClear[0]);
        auto *corrected = renderer.m_bufferPrograms[0].get();
        for (float expected : {.8f, 1.6f, 2.4f}) {
            const auto actual = imagePixel(renderer).x();
            QVERIFY(std::abs(actual - expected) < .001f);
            renderer.synchronize(&engine);
            QCoreApplication::processEvents();
            QCOMPARE(renderer.m_bufferPrograms[0].get(), corrected);
            QVERIFY(!renderer.m_bufferNeedsClear[0]);
            QCOMPARE(engine.compileLog(), QString());
        }
    }

    void successfulPassCannotHideFailedBufferLog() {
        ShaderEngine engine;
        engine.setRunning(false);
        engine.setSize({640, 480});
        engine.setShaderCode(plain);
        engine.setCommonCode(QStringLiteral("const float gain = .2;"));
        engine.setUseBufferA(true);
        engine.setUseBufferB(true);
        engine.setBufferACode(QStringLiteral("void mainImage(out vec4 c, in vec2 p) { c = vec4(gain); }"));
        engine.setBufferBCode(plain);
        ShaderEngineRenderer renderer;
        renderer.synchronize(&engine);
        QCoreApplication::processEvents();
        QStringList published;
        connect(&engine, &ShaderEngine::compileLogChanged, this, [&]() { published.append(engine.compileLog()); });
        engine.setCommonCode(QStringLiteral("const float renamedGain = .8;"));
        renderer.synchronize(&engine); // main and B succeed, A fails
        QCoreApplication::processEvents();
        QVERIFY2(engine.compileLog().contains(QStringLiteral("buffer A")), "Successful Buffer B must not clear Buffer A's failure");
        const auto failure = engine.compileLog();
        engine.setShaderCode(plain + QStringLiteral("\n// main-only success"));
        renderer.synchronize(&engine);
        engine.setBufferBCode(plain + QStringLiteral("\n// buffer-only success"));
        renderer.synchronize(&engine);
        QCoreApplication::processEvents();
        QCOMPARE(engine.compileLog(), failure);
        QVERIFY(!published.contains(QString()));
        published.clear();
        engine.setBufferACode(plain);
        renderer.synchronize(&engine);
        QCoreApplication::processEvents();
        QCOMPARE(engine.compileLog(), QString());
        QCOMPARE(published, QStringList{QString()});
    }

    void successfulPackageRoundTripResetsFeedback_data() {
        QTest::addColumn<bool>("useRain");
        QTest::newRow("main-rain-main") << true;
        QTest::newRow("main-ordinary-main") << false;
    }

    void successfulPackageRoundTripResetsFeedback() {
        QFETCH(bool, useRain);
        QTemporaryDir shaders;
        QVERIFY(shaders.isValid());
        const auto main = QStringLiteral("void mainImage(out vec4 c, in vec2 p) { c = texture(iChannel0, p / iResolution.xy); }");
        const auto buffer = QStringLiteral("void mainImage(out vec4 c, in vec2 p) { c = vec4(texture(iChannel0, p / iResolution.xy).r + .2, 0., 0., 1.); }");
        const auto writeShader = [&](const QString &name, const QString &code) {
            QFile file(shaders.filePath(name));
            return file.open(QIODevice::WriteOnly) && file.write(code.toUtf8()) == code.toUtf8().size();
        };
        QVERIFY(writeShader("main.frag", main));
        QVERIFY(writeShader("main_bufferA.frag", buffer));
        QVERIFY(writeShader("other.frag", useRain ? rain() : plain));
        QVERIFY(writeShader("rejected.frag", QStringLiteral("// @arasaka-effect rain-v1\ninvalid")));
        ShaderEngine engine;
        engine.setRunning(false);
        engine.setSize({320, 240});
        engine.setShaderSource(QUrl::fromLocalFile(shaders.filePath("main.frag")));
        QVERIFY(engine.useBufferA());
        engine.setImageChannels({10, -1, -1, -1});
        engine.setBufferAChannels({10, -1, -1, -1});
        ShaderEngineRenderer renderer;
        renderer.synchronize(&engine);
        QCoreApplication::processEvents();
        for (float expected : {.2f, .4f, .6f})
            QVERIFY(std::abs(imagePixel(renderer).x() - expected) < .001f);
        auto *working = renderer.m_bufferPrograms[0].get();
        const auto front = renderer.m_bufferFBOs[0]->texture();
        const auto back = renderer.m_bufferFBOsBack[0]->texture();
        engine.setShaderSource(QUrl::fromLocalFile(shaders.filePath("rejected.frag")));
        for (float expected : {.8f, 1.f, 1.2f}) {
            renderer.synchronize(&engine);
            QCoreApplication::processEvents();
            QVERIFY(!engine.compileLog().isEmpty());
            QVERIFY(!renderer.m_bufferNeedsClear[0]);
            QVERIFY(std::abs(imagePixel(renderer).x() - expected) < .001f);
        }
        // Returning from a failed candidate is not a package commit boundary.
        engine.setShaderSource(QUrl::fromLocalFile(shaders.filePath("main.frag")));
        renderer.synchronize(&engine);
        QVERIFY(std::abs(imagePixel(renderer).x() - 1.4f) < .001f);
        // A successful hot edit within this same package retains feedback too.
        QVERIFY(writeShader("main.frag", main + QStringLiteral("\n// hot edit")));
        engine.reloadShaderFilesFromDisk();
        renderer.synchronize(&engine);
        QVERIFY(std::abs(imagePixel(renderer).x() - 1.6f) < .001f);

        engine.setShaderSource(QUrl::fromLocalFile(shaders.filePath("other.frag")));
        renderer.synchronize(&engine);
        QCoreApplication::processEvents();
        QCOMPARE(engine.rainActive(), useRain);
        QVERIFY(!renderer.m_useBuffers[0]);
        imagePixel(renderer);
        engine.setShaderSource(QUrl::fromLocalFile(shaders.filePath("main.frag")));
        renderer.synchronize(&engine);
        QCoreApplication::processEvents();
        QVERIFY(!engine.rainActive());
        // Same cached buffer program and surfaces; only successful package commitment resets state.
        QCOMPARE(renderer.m_bufferPrograms[0].get(), working);
        QCOMPARE(renderer.m_bufferFBOs[0]->texture(), front);
        QCOMPARE(renderer.m_bufferFBOsBack[0]->texture(), back);
        for (float expected : {.2f, .4f, .6f}) {
            const auto actual = imagePixel(renderer).x();
            qInfo() << "Round-trip feedback actual/expected:" << actual << expected;
            QVERIFY2(std::abs(actual - expected) < .001f, "Successful package round-trip must clear both feedback surfaces once");
            renderer.synchronize(&engine);
            QVERIFY(!renderer.m_bufferNeedsClear[0]);
        }
    }

    void incidentalRenderConsumesNoSecondDelta() {
        class InspectingRenderer : public ShaderEngineRenderer {
        public:
            std::function<void(ShaderEngineRenderer *)> inspect;
            void render() override {
                ShaderEngineRenderer::render();
                inspect(this);
            }
        };
        class Engine : public ShaderEngine {
        public:
            using ShaderEngine::ShaderEngine;
            std::function<void(ShaderEngineRenderer *)> inspect;
            Renderer *createRenderer() const override {
                auto *renderer = new InspectingRenderer;
                renderer->inspect = inspect;
                return renderer;
            }
        };
        int checked = 0;
        bool stable = true;
        {
            QQuickWindow window;
            window.resize(320, 240);
            Engine engine(window.contentItem());
            engine.setSize({320, 240});
            engine.setShaderCode(rain());
            engine.inspect = [&](ShaderEngineRenderer *renderer) {
                const auto before = renderer->m_rainSimulation->drops();
                const auto texture = renderer->m_rainField->texture();
                stable = stable && renderer->m_iTimeDelta == 0;
                // Qt already supplied a real output FBO. Redraw without synchronize().
                renderer->ShaderEngineRenderer::render();
                const auto &after = renderer->m_rainSimulation->drops();
                stable = stable && renderer->m_rainField->texture() == texture && before.size() == after.size();
                for (std::size_t i = 0; i < std::min(before.size(), after.size()); ++i)
                    stable = stable && before[i].position == after[i].position
                        && before[i].previousPosition == after[i].previousPosition;
                ++checked;
            };
            window.show();
            QVERIFY(QTest::qWaitForWindowExposed(&window));
            QTRY_VERIFY(checked >= 3);
            QVERIFY(stable);
        }
        QVERIFY(context.makeCurrent(&surface));
    }
};

int main(int argc, char **argv)
{
    QTemporaryDir sandbox;
    if (!sandbox.isValid()) return 1;
    qputenv("XDG_DATA_HOME", (sandbox.path() + QStringLiteral("/data")).toUtf8());
    qputenv("XDG_CONFIG_HOME", (sandbox.path() + QStringLiteral("/config")).toUtf8());
    qputenv("XDG_CACHE_HOME", (sandbox.path() + QStringLiteral("/cache")).toUtf8());
    const auto library = sandbox.path() + QStringLiteral("/data/plasma/wallpapers/online.knowmad.shaderwallpaper/contents/ui/Shaders");
    if (!QDir().mkpath(library)) return 1;
    QFile seed(library + QStringLiteral("/Default.frag"));
    if (!seed.open(QIODevice::WriteOnly) || seed.write("void mainImage(out vec4 c, in vec2 p) { c = vec4(1.); }\n") < 0) return 1;
    seed.close();
    qputenv("QSG_RENDER_LOOP", "basic");
    QQuickWindow::setGraphicsApi(QSGRendererInterface::OpenGL);
    QGuiApplication application(argc, argv);
    RainHostTest test;
    return QTest::qExec(&test, argc, argv);
}
#include "rain_host_test.moc"
