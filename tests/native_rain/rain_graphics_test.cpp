#include "rainfieldrenderer.h"
#include "raininput.h"

#include <QGuiApplication>
#include <QMouseEvent>
#include <QOffscreenSurface>
#include <QOpenGLContext>
#include <QOpenGLExtraFunctions>
#include <QQuickWindow>
#include <QtTest>
#include <cmath>

using namespace arasaka::rain;

namespace arasaka::rain {
struct DropletSimulationTestAccess {
    static void setDrops(DropletSimulation &simulation, std::vector<Drop> drops) {
        simulation.reset(128, 128, 1, 0);
        simulation.lengthScale_ = 1;
        simulation.drops_ = std::move(drops);
        for (const auto &d : simulation.drops_) simulation.nextId_ = std::max(simulation.nextId_, d.id + 1);
    }
    static void collide(DropletSimulation &simulation) {
        std::vector<Vec2> starts;
        for (const auto &d : simulation.drops_) starts.push_back(d.position);
        simulation.mergeCollisions(starts);
    }
    static void splash(DropletSimulation &simulation, Vec2 position) { simulation.splash(position); }
    static void append(DropletSimulation &simulation, Drop drop) {
        simulation.nextId_ = std::max(simulation.nextId_, drop.id + 1);
        simulation.drops_.push_back(drop);
    }
};
}

class RainGraphicsTest : public QObject {
    Q_OBJECT
    QOpenGLContext context;
    QOffscreenSurface surface;

    std::vector<float> pixels(const RainFieldRenderer &field) {
        auto *f = context.extraFunctions();
        GLuint fbo = 0;
        f->glGenFramebuffers(1, &fbo);
        f->glBindFramebuffer(GL_FRAMEBUFFER, fbo);
        f->glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, field.texture(), 0);
        std::vector<float> result(field.pixelSize().width() * field.pixelSize().height() * 4);
        f->glReadPixels(0, 0, field.pixelSize().width(), field.pixelSize().height(), GL_RGBA, GL_FLOAT, result.data());
        f->glDeleteFramebuffers(1, &fbo);
        return result;
    }

    float at(const std::vector<float> &p, int x, int y, int channel = 0) {
        // Input coordinates are top-left; native texture follows OpenGL's bottom-left.
        return p[((127 - y) * 128 + x) * 4 + channel];
    }

    void move(QQuickWindow &window, QPointF position, Qt::MouseButtons buttons = Qt::NoButton) {
        QMouseEvent event(QEvent::MouseMove, position, position, Qt::NoButton, buttons, Qt::NoModifier);
        QCoreApplication::sendEvent(&window, &event);
    }

private Q_SLOTS:
    void initTestCase() {
        QSurfaceFormat format;
        format.setVersion(3, 3);
        format.setProfile(QSurfaceFormat::CoreProfile);
        context.setFormat(format);
        QVERIFY2(context.create(), "A real OpenGL 3.3 context is required");
        surface.setFormat(context.format());
        surface.create();
        QVERIFY(context.makeCurrent(&surface));
        qInfo() << "GL renderer:" << reinterpret_cast<const char *>(context.functions()->glGetString(GL_RENDERER));
    }

    void capsHaveHeightAndCorrectOrientation() {
        QVERIFY(context.makeCurrent(&surface));
        RainFieldRenderer field;
        QString error;
        QVERIFY2(field.initialize({128, 128}, &error), qPrintable(error));
        auto *f = context.extraFunctions();
        // State inherited from Qt must not clip, mask, or depth-reject the field.
        f->glEnable(GL_SCISSOR_TEST);
        f->glScissor(0, 0, 1, 1);
        f->glColorMask(false, false, false, false);
        f->glEnable(GL_DEPTH_TEST);
        std::vector<Drop> drops{{1, {32.5, 24.5}, {32.5, 24.5}, {}, 1000}};
        QVERIFY(field.render(drops, 0));
        const auto p = pixels(field);
        QVERIFY(std::abs(at(p, 32, 24) - 6.0f) < 0.02f);
        QVERIFY(at(p, 37, 24) > 0 && at(p, 37, 24) < at(p, 32, 24));
        QCOMPARE(at(p, 60, 24), 0);
        QCOMPARE(at(p, 32, 103), 0);
        QCOMPARE(f->glGetError(), GLenum(GL_NO_ERROR));
    }

    void sweptTrailDecaysAndZeroDeltaFreezes() {
        QVERIFY(context.makeCurrent(&surface));
        RainFieldRenderer field;
        QString error;
        QVERIFY2(field.initialize({128, 128}, &error), qPrintable(error));
        std::vector<Drop> drops{{1, {80.5, 24.5}, {20.5, 24.5}, {}, 216}};
        QVERIFY(field.render(drops, 1.0 / 30));
        const auto first = pixels(field);
        QCOMPARE(at(first, 50, 24), 0);
        QVERIFY(at(first, 50, 24, 1) > 0.1);
        QVERIFY(at(first, 50, 24, 2) > 0.1);
        for (int i = 0; i < 3; ++i) QVERIFY(field.render(drops, 0));
        QCOMPARE(pixels(field), first);
        drops[0].previousPosition = drops[0].position;
        QVERIFY(field.render(drops, 0.25));
        const auto later = pixels(field);
        QVERIFY(at(later, 50, 24, 1) < at(first, 50, 24, 1));
        QVERIFY(at(later, 50, 24, 1) > 0);
        for (int i = 0; i < 80; ++i) QVERIFY(field.render(drops, 0.25));
        QVERIFY(at(pixels(field), 50, 24, 1) < 0.001);
    }

    void movingCapsElongateWithoutChangingAreaOrVolume() {
        QVERIFY(context.makeCurrent(&surface));
        double roundArea = 0, roundVolume = 0;
        for (const auto velocity : {Vec2{}, Vec2{0, 120}, Vec2{120, 0}, Vec2{120, 120}, Vec2{0, 900}}) {
            RainFieldRenderer field;
            QString error;
            QVERIFY2(field.initialize({128, 128}, &error), qPrintable(error));
            const std::vector<Drop> drops{{17, {64.5, 64.5}, {64.5, 64.5}, velocity, 1728}};
            // No swept segment: only actual velocity may deform the current physical cap.
            QVERIFY(field.render(drops, 0));
            const auto p = pixels(field);
            QVERIFY(std::abs(at(p, 64, 64) - 7.2f) < .02f);
            const double speed = std::hypot(velocity.x, velocity.y);
            const Vec2 axis = speed > 0 ? Vec2{velocity.x / speed, velocity.y / speed} : Vec2{0, 1};
            double area = 0, volume = 0, along = 0, across = 0;
            for (int y = 0; y < 128; ++y) {
                for (int x = 0; x < 128; ++x) {
                    const double height = at(p, x, y);
                    QVERIFY(std::isfinite(height) && height >= 0);
                    area += height > .01;
                    volume += height;
                    const double u = (x - 64) * axis.x + (y - 64) * axis.y;
                    const double v = (x - 64) * axis.y - (y - 64) * axis.x;
                    along += height * u * u;
                    across += height * v * v;
                    if (height > .01)
                        QVERIFY(std::hypot(x - 64, y - 64) < 24); // Even max-speed optics stay local.
                }
            }
            qInfo() << "CAP_SHAPE" << velocity.x << velocity.y << "axisRatio" << std::sqrt(along / across)
                    << "areaPixels" << area << "heightIntegral" << volume;
            if (speed == 0) {
                roundArea = area;
                roundVolume = volume;
                QVERIFY(std::abs(along - across) < .001 * along);
                QVERIFY(std::abs(at(p, 64, 70) - at(p, 70, 64)) < .001f);
                QVERIFY(std::abs(at(p, 64, 70) - 5.8049f) < .02f); // Original spherical-cap section.
            } else {
                const double axisRatio = std::sqrt(along / across);
                QVERIFY2(axisRatio > 1.2, "Moving caps retain a slight stretch along velocity");
                QVERIFY2(axisRatio < 1.5, "Fast caps must stay rounded rather than becoming long ovals");
                QVERIFY2(std::abs(area - roundArea) < .06 * roundArea, "Optical stretching preserves footprint area");
                QVERIFY2(std::abs(volume - roundVolume) < .015 * roundVolume, "Integrated physical height must not add water");
                if (velocity.x == 0) {
                    QVERIFY(at(p, 64, 77) > .1f); // Enlarged quad must not clip the long axis.
                    QCOMPARE(at(p, 75, 64), 0); // Reciprocal transverse compression, not inflated radius.
                }
            }
            QCOMPARE(context.functions()->glGetError(), GLenum(GL_NO_ERROR));
        }
    }

    void fieldResizeIsBoundedAndTransactional() {
        QVERIFY(context.makeCurrent(&surface));
        RainFieldRenderer field;
        QString error;
        QVERIFY(field.initialize({3840, 2160}, &error));
        QCOMPARE(field.pixelSize(), QSize(1920, 1080));
        const auto texture = field.texture();
        QVERIFY(!field.resize({0, 100}, &error));
        QVERIFY(!error.isEmpty());
        QCOMPARE(field.texture(), texture);
        QCOMPARE(field.logicalSize(), QSizeF(3840, 2160));
        QVERIFY(field.resize({128, 128}, &error));
        QVERIFY(field.render({}, 0));
        for (float value : pixels(field)) QCOMPARE(value, 0);
    }

    void mergingCapsRetainLobesAndGrowALiquidNeck() {
        QVERIFY(context.makeCurrent(&surface));
        DropletSimulation simulation;
        DropletSimulationTestAccess::setDrops(simulation, {
            {1, {52.5, 64.5}, {52.5, 64.5}, {}, 1728}, {2, {76.5, 64.5}, {76.5, 64.5}, {}, 1728}});
        RainFieldRenderer field;
        QString error;
        QVERIFY(field.initialize({128, 128}, &error));
        QVERIFY(field.render(simulation.drops(), 0));
        const auto separate = pixels(field);
        DropletSimulationTestAccess::collide(simulation);
        QCOMPARE(simulation.drops().size(), std::size_t(1));
        QVERIFY(field.render(simulation.drops(), 1.0 / 30));
        const auto contact = pixels(field);
        QVERIFY2(at(contact, 44, 64) > 1 && at(contact, 84, 64) > 1,
                 "both original outer lobes must remain visible at contact");
        QVERIFY(std::abs(at(contact, 52, 64) - at(separate, 52, 64)) < .1);
        QVERIFY(std::abs(at(contact, 76, 64) - at(separate, 76, 64)) < .1);
        QVERIFY2(at(contact, 64, 64) > .1 && at(contact, 64, 64) < 2,
                 "contact should create a thin neck, not instantly draw the final round cap");
        for (int x = 52; x <= 76; ++x) QVERIFY(at(contact, x, 64) > 0);
        simulation.advance(.075);
        QVERIFY(field.render(simulation.drops(), .075));
        const auto middle = pixels(field);
        QVERIFY2(at(middle, 64, 64) > at(contact, 64, 64) + 1,
                 "the neck thickens as the two lobes pull together");
        QVERIFY(at(middle, 44, 64) < at(contact, 44, 64));
        QVERIFY(field.render(simulation.drops(), 0));
        QCOMPARE(pixels(field), middle);
        simulation.advance(.25);
        QVERIFY(field.render(simulation.drops(), .25));
        const auto settled = pixels(field);
        RainFieldRenderer reference;
        QVERIFY(reference.initialize({128, 128}, &error));
        auto solid = simulation.drops();
        for (auto &d : solid) d.merging.clear();
        QVERIFY(reference.render(solid, 0));
        const auto expected = pixels(reference);
        for (std::size_t i = 0; i < settled.size(); i += 4) QCOMPARE(settled[i], expected[i]);
        QCOMPARE(context.extraFunctions()->glGetError(), GLenum(GL_NO_ERROR));
    }

    void clickingAMergingSurfaceLeavesOnlyTheFragments() {
        QVERIFY(context.makeCurrent(&surface));
        DropletSimulation simulation;
        DropletSimulationTestAccess::setDrops(simulation, {
            {1, {52.5, 64.5}, {52.5, 64.5}, {}, 1728}, {2, {76.5, 64.5}, {76.5, 64.5}, {}, 1728}});
        DropletSimulationTestAccess::collide(simulation);
        RainFieldRenderer field, reference;
        QString error;
        QVERIFY(field.initialize({128, 128}, &error));
        QVERIFY(reference.initialize({128, 128}, &error));
        QVERIFY(field.render(simulation.drops(), 0));
        QVERIFY(at(pixels(field), 44, 64) > 1);
        DropletSimulationTestAccess::splash(simulation, {84, 64});
        QVERIFY(simulation.drops().size() >= 3);
        QVERIFY(field.render(simulation.drops(), 1.0 / 30));
        QVERIFY(reference.render(simulation.drops(), 0));
        const auto actual = pixels(field), expected = pixels(reference);
        for (std::size_t i = 0; i < actual.size(); i += 4) QCOMPARE(actual[i], expected[i]);
        QCOMPARE(at(actual, 64, 64), 0); // No residual solid parent; wet fog history is allowed.
    }

    void splashImpactRetainsTheSmallReceivingLobe() {
        QVERIFY(context.makeCurrent(&surface));
        DropletSimulation simulation;
        DropletSimulationTestAccess::setDrops(simulation, {{1, {64, 64}, {64, 64}, {}, 1728}});
        DropletSimulationTestAccess::splash(simulation, {64, 64});
        auto fragment = simulation.drops().back();
        fragment.position = fragment.previousPosition = {40.5, 64.5};
        fragment.velocity = {300, 0};
        const Vec2 target{40.5 + fragment.radius() + 2, 64.5};
        DropletSimulationTestAccess::setDrops(simulation, {fragment, {100, target, target, {}, 8}});
        DropletSimulationTestAccess::collide(simulation);
        QCOMPARE(simulation.drops().size(), std::size_t(1));
        RainFieldRenderer field;
        QString error;
        QVERIFY(field.initialize({128, 128}, &error));
        QVERIFY(field.render(simulation.drops(), 0));
        QVERIFY2(at(pixels(field), qFloor(target.x), qFloor(target.y)) > .5,
                 "splash impacts visibly retain and absorb the receiving droplet");
    }

    void denseMergingBodiesFitTheGeometryBudget() {
        QVERIFY(context.makeCurrent(&surface));
        Drop body{1, {64, 64}, {60, 60}, {100, 100}, 256};
        body.merging = {{{-4, -4}, 4, {0, 1}, 1, .25}, {{4, -4}, 4, {0, 1}, 1, .25},
                        {{-4, 4}, 4, {0, 1}, 1, .25}, {{4, 4}, 4, {0, 1}, 1, .25}};
        body.mergeDuration = .2;
        body.mergeJoins = {{{0, 1, 1.2}, {2, 3, 1.2}, {4, 5, 1.2}}};
        std::vector<Drop> drops(1024, body);
        RainFieldRenderer field;
        QString error;
        QVERIFY(field.initialize({128, 128}, &error));
        QVERIFY2(field.render(drops, 1.0 / 30), "all merging caps and four trails per body must fit the allocated VBOs");
        for (const float value : pixels(field)) QVERIFY(std::isfinite(value) && value >= 0);
        QCOMPARE(context.extraFunctions()->glGetError(), GLenum(GL_NO_ERROR));
    }

    void reimpactPreservesTheExistingLiquidNeck() {
        QVERIFY(context.makeCurrent(&surface));
        DropletSimulation simulation;
        DropletSimulationTestAccess::setDrops(simulation, {
            {1, {52.5, 64.5}, {52.5, 64.5}, {}, 1728}, {2, {76.5, 64.5}, {76.5, 64.5}, {}, 1728}});
        DropletSimulationTestAccess::collide(simulation);
        simulation.advance(.05);
        RainFieldRenderer field;
        QString error;
        QVERIFY(field.initialize({128, 128}, &error));
        QVERIFY(field.render(simulation.drops(), 0));
        const auto before = pixels(field);
        const auto body = simulation.drops()[0];
        const Vec2 p{body.position.x + body.radius() + 4, body.position.y};
        DropletSimulationTestAccess::append(simulation, {3, p, p, {}, 64});
        DropletSimulationTestAccess::collide(simulation);
        QVERIFY(field.render(simulation.drops(), 1.0 / 30));
        const auto after = pixels(field);
        double change = 0;
        for (int y = 52; y <= 76; ++y)
            for (int x = 60; x <= 68; ++x)
                change = std::max(change, double(std::abs(at(before, x, y) - at(after, x, y))));
        QVERIFY2(change < .03, qPrintable(QStringLiteral("reimpact changed the existing neck by %1 pixels of height").arg(change)));
    }

    void steeringThroughPerpendicularKeepsTheSurfaceContinuous() {
        QVERIFY(context.makeCurrent(&surface));
        Drop body{1, {64.5, 64.5}, {64.5, 64.5}, {.0001, 120}, 1024};
        body.merging = {{{-8, 0}, 8, {1, 0}, 1.2, .5}, {{8, 0}, 8, {1, 0}, 1.2, .5}};
        body.mergeAge = .1;
        body.mergeDuration = .2;
        body.mergeJoins[0] = {0, 1, 2.4};
        RainFieldRenderer field;
        QString error;
        QVERIFY(field.initialize({128, 128}, &error));
        QVERIFY(field.render({body}, 0));
        const auto before = pixels(field);
        body.velocity.x = -.0001;
        QVERIFY(field.render({body}, 1.0 / 30));
        const auto after = pixels(field);
        double change = 0;
        for (std::size_t i = 0; i < before.size(); i += 4)
            change = std::max(change, double(std::abs(before[i] - after[i])));
        QVERIFY2(change < .01, qPrintable(QStringLiteral("tiny steering change rotated the footprint: %1").arg(change)));
    }

    void twoMergingGroupsKeepTheirIndependentNecks() {
        QVERIFY(context.makeCurrent(&surface));
        DropletSimulation left, right, combined;
        DropletSimulationTestAccess::setDrops(left, {
            {1, {56.5, 58.5}, {56.5, 58.5}, {}, 216}, {2, {56.5, 70.5}, {56.5, 70.5}, {}, 216}});
        DropletSimulationTestAccess::setDrops(right, {
            {3, {71.5, 58.5}, {71.5, 58.5}, {}, 216}, {4, {71.5, 70.5}, {71.5, 70.5}, {}, 216}});
        DropletSimulationTestAccess::collide(left);
        DropletSimulationTestAccess::collide(right);
        left.advance(.025);
        right.advance(.05);
        DropletSimulationTestAccess::setDrops(combined, {left.drops()[0], right.drops()[0]});
        RainFieldRenderer field;
        QString error;
        QVERIFY(field.initialize({128, 128}, &error));
        QVERIFY(field.render(combined.drops(), 0));
        const auto before = pixels(field);
        DropletSimulationTestAccess::collide(combined);
        QCOMPARE(combined.drops().size(), std::size_t(1));
        QCOMPARE(combined.drops()[0].surface().count, std::size_t(4));
        QVERIFY(field.render(combined.drops(), 1.0 / 30));
        const auto after = pixels(field);
        for (const int x : {56, 71}) {
            QVERIFY(at(before, x, 64) > .3);
            QVERIFY2(std::abs(at(before, x, 64) - at(after, x, 64)) < .03,
                     "joining two in-progress merges must preserve each old neck's shape and blending width");
        }
    }

    void passiveWindowCoordinatesAndCancellation() {
        QQuickWindow window;
        window.resize(320, 240);
        QQuickItem parent(window.contentItem());
        parent.setPosition({10, 20});
        parent.setScale(2);
        QQuickItem item(&parent);
        item.setPosition({5, 10});
        item.setSize({100, 80});
        window.show();
        QVERIFY(QTest::qWaitForWindowExposed(&window));
        RainInput input(&item);
        input.setEnabled(true);
        move(window, item.mapToScene({30, 25}));
        QVERIFY(!input.snapshot().valid); // Unknown initial lock state fails closed.
        // The private slot is the actual DBus signal consumer, not a test API.
        QVERIFY(QMetaObject::invokeMethod(&input, "sessionLockChanged", Q_ARG(bool, false)));
        move(window, item.mapToScene({30, 25}));
        QVERIFY(input.snapshot().valid);
        QCOMPARE(input.snapshot().position.x, 30);
        QCOMPARE(input.snapshot().position.y, 25);
        const auto first = input.snapshot();
        QTest::qWait(2);
        move(window, item.mapToScene({35, 25}));
        QVERIFY(input.snapshot().sequence > first.sequence);
        QVERIFY(input.snapshot().sampleSeconds > first.sampleSeconds);
        input.setEnabled(false);
        QVERIFY(!input.snapshot().valid);
        input.setEnabled(true);
        move(window, item.mapToScene({40, 25}));
        QVERIFY(input.snapshot().valid);
        auto revision = input.invalidationSequence();
        item.setX(8);
        input.refreshGeometry();
        QVERIFY(!input.snapshot().valid);
        QVERIFY(input.invalidationSequence() > revision);
        move(window, item.mapToScene({40, 25}));
        QEvent leave(QEvent::Leave);
        QCoreApplication::sendEvent(&window, &leave);
        QVERIFY(!input.snapshot().valid);
        move(window, item.mapToScene({40, 25}), Qt::LeftButton);
        QVERIFY(!input.snapshot().valid);
        move(window, item.mapToScene({40, 25}));
        QVERIFY(QMetaObject::invokeMethod(&input, "sessionLockChanged", Q_ARG(bool, true)));
        QVERIFY(!input.snapshot().valid);
        move(window, item.mapToScene({45, 25}));
        QVERIFY(!input.snapshot().valid);
        QVERIFY(QMetaObject::invokeMethod(&input, "sessionLockChanged", Q_ARG(bool, false)));
        move(window, item.mapToScene({45, 25}));
        QVERIFY(input.snapshot().valid);
        item.setVisible(false);
        QVERIFY(!input.snapshot().valid);
    }

    void buttonsRemainDeliveredAndWindowsAreIndependent() {
        class Window : public QQuickWindow {
        public:
            int presses = 0;
            void mousePressEvent(QMouseEvent *event) override { ++presses; event->accept(); }
        } first, second;
        first.resize(200, 200);
        second.resize(200, 200);
        QQuickItem item(first.contentItem());
        item.setSize({200, 200});
        RainInput input(&item);
        input.setEnabled(true);
        first.show();
        second.show();
        QVERIFY(QTest::qWaitForWindowExposed(&first));
        QVERIFY(QMetaObject::invokeMethod(&input, "sessionLockChanged", Q_ARG(bool, false)));
        move(second, {20, 20});
        QVERIFY(!input.snapshot().valid);
        QMouseEvent press(QEvent::MouseButtonPress, {20, 20}, {20, 20}, Qt::LeftButton, Qt::LeftButton, Qt::NoModifier);
        QCoreApplication::sendEvent(&first, &press);
        QCOMPARE(first.presses, 1);
        move(first, {20, 20});
        QVERIFY(input.snapshot().valid);
        item.setParentItem(second.contentItem());
        QVERIFY(!input.snapshot().valid);
        move(first, {30, 30});
        QVERIFY(!input.snapshot().valid);
        move(second, {30, 30});
        QVERIFY(input.snapshot().valid);
    }

    void quickClicksAreLocalOneShotAndPassive() {
        class Window : public QQuickWindow {
        public:
            int presses = 0, releases = 0;
            void mousePressEvent(QMouseEvent *event) override { ++presses; event->accept(); }
            void mouseReleaseEvent(QMouseEvent *event) override { ++releases; event->accept(); }
        } window, other;
        window.resize(400, 300);
        QQuickItem item(window.contentItem());
        item.setPosition({10, 20});
        item.setSize({160, 120});
        item.setScale(2);
        window.show();
        QVERIFY(QTest::qWaitForWindowExposed(&window));
        RainInput input(&item);
        input.setEnabled(true);
        QVERIFY(QMetaObject::invokeMethod(&input, "sessionLockChanged", Q_ARG(bool, false)));
        const auto click = [&](QQuickWindow &target, QPointF local, Qt::MouseButton button = Qt::LeftButton) {
            const auto p = item.mapToScene(local);
            QMouseEvent press(QEvent::MouseButtonPress, p, p, button, button, Qt::NoModifier);
            QCoreApplication::sendEvent(&target, &press);
            move(target, p, button); // A held button must neither repeat nor cancel an accepted press.
            QMouseEvent release(QEvent::MouseButtonRelease, p, p, button, Qt::NoButton, Qt::NoModifier);
            QCoreApplication::sendEvent(&target, &release);
        };
        click(window, {30, 25});
        click(window, {45, 35});
        QCOMPARE(window.presses, 2);
        QCOMPARE(window.releases, 2);
        QVERIFY(!input.snapshot().valid);
        const auto splashes = input.takeSplashes();
        QCOMPARE(splashes.size(), std::size_t(2));
        QCOMPARE(splashes[0], (Vec2{30, 25}));
        QCOMPARE(splashes[1], (Vec2{45, 35}));
        QVERIFY(input.takeSplashes().empty());
        click(other, {30, 25});
        click(window, {30, 25}, Qt::RightButton);
        click(window, {30, 25}, Qt::MiddleButton);
        click(window, {-1, 25});
        QVERIFY(input.takeSplashes().empty());

        QTest::mouseDClick(&window, Qt::LeftButton, Qt::NoModifier, {70, 70}, 1);
        QCOMPARE(input.takeSplashes().size(), std::size_t(2)); // Two physical presses, regardless of Qt's extra notification.
        for (int i = 0; i < 100; ++i) click(window, {30, 25});
        const auto burst = input.takeSplashes();
        QVERIFY(!burst.empty() && burst.size() <= 32);

        for (int cancel = 0; cancel < 7; ++cancel) {
            click(window, {30, 25});
            if (cancel == 0) { input.setEnabled(false); input.setEnabled(true); }
            if (cancel == 1) { input.setLockScreenHost(true); input.setLockScreenHost(false); }
            if (cancel == 2) {
                QVERIFY(QMetaObject::invokeMethod(&input, "sessionLockChanged", Q_ARG(bool, true)));
                QVERIFY(QMetaObject::invokeMethod(&input, "sessionLockChanged", Q_ARG(bool, false)));
            }
            if (cancel == 3) { item.setX(item.x() + 1); input.refreshGeometry(); }
            if (cancel == 4) { QEvent leave(QEvent::Leave); QCoreApplication::sendEvent(&window, &leave); }
            if (cancel == 5) { item.setVisible(false); item.setVisible(true); }
            if (cancel == 6) { item.setParentItem(other.contentItem()); item.setParentItem(window.contentItem()); }
            QVERIFY2(input.takeSplashes().empty(), "host/lifecycle changes must discard unconsumed clicks");
        }
        input.setLockScreenHost(true);
        click(window, {30, 25});
        QVERIFY(input.takeSplashes().empty());
        input.setLockScreenHost(false);
        QVERIFY(QMetaObject::invokeMethod(&input, "sessionLockChanged", Q_ARG(bool, true)));
        click(window, {30, 25});
        QVERIFY(input.takeSplashes().empty());
        input.setLockScreenHost(true);
        click(window, {30, 25});
        QVERIFY(input.takeSplashes().empty());
    }
};

QTEST_MAIN(RainGraphicsTest)
#include "rain_graphics_test.moc"
