// SPDX-License-Identifier: GPL-3.0-or-later
#include "raininput.h"
#include "../login/pointerbridge.h"
#include <QDBusConnection>
#include <QProcess>
#include <QtTest>
#include <limits>

class WallpaperEndpoint : public QObject {
    Q_OBJECT
    Q_CLASSINFO("D-Bus Interface", "org.kde.plasma.wallpaper")
public:
    QQuickWindow window;
    QQuickItem item{window.contentItem()};
    arasaka::rain::RainInput input{&item};
    int calls = 0;
    WallpaperEndpoint() {
        window.resize(320, 240);
        item.setSize({320, 240});
        input.setEnabled(true);
        input.setLockScreenHost(true);
        window.show();
    }
public Q_SLOTS:
    Q_SCRIPTABLE void rainPointer(const QString &screen, int action, double x, double y) {
        ++calls;
        arasaka::login::deliverPointer(&window, screen, action, x, y);
    }
};

class LoginPointerTest : public QObject {
    Q_OBJECT
private Q_SLOTS:
    void crossProcessDeliveryReachesTheSamePassiveRainObserver() {
        WallpaperEndpoint wallpaper;
        QVERIFY(QTest::qWaitForWindowExposed(&wallpaper.window));
        auto bus = QDBusConnection::sessionBus();
        QVERIFY(bus.registerService(QStringLiteral("org.kde.plasma.wallpaper")));
        QVERIFY(bus.registerObject(QStringLiteral("/Wallpaper"), &wallpaper, QDBusConnection::ExportScriptableSlots));
        for (const QString &action : {QStringLiteral("hover"), QStringLiteral("click"), QStringLiteral("cancel")}) {
            QProcess greeter;
            greeter.start(QCoreApplication::applicationFilePath(), {QStringLiteral("--sender"), action});
            QVERIFY(greeter.waitForStarted());
            QTRY_VERIFY_WITH_TIMEOUT(greeter.state() == QProcess::NotRunning, 5000);
            QCOMPARE(greeter.exitCode(), 0);
            QTRY_VERIFY(wallpaper.calls > 0);
            if (action == QLatin1String("hover")) {
                QTRY_VERIFY(wallpaper.input.snapshot().valid);
                QCOMPARE(wallpaper.input.snapshot().position, (arasaka::rain::Vec2{80, 120}));
            } else if (action == QLatin1String("click")) {
                QTRY_VERIFY(wallpaper.calls >= 3); // press and release
                QCOMPARE(wallpaper.input.takeSplashes(), (std::vector<arasaka::rain::Vec2>{{80, 120}}));
                QVERIFY(!wallpaper.input.snapshot().valid);
            } else {
                QTRY_VERIFY(wallpaper.calls >= 4);
                QVERIFY(!wallpaper.input.snapshot().valid);
            }
        }
        bus.unregisterObject(QStringLiteral("/Wallpaper"));
        bus.unregisterService(QStringLiteral("org.kde.plasma.wallpaper"));
    }

    void invalidCoordinatesOtherScreensAndLockedDesktopRejectClicks() {
        WallpaperEndpoint wallpaper;
        QVERIFY(QTest::qWaitForWindowExposed(&wallpaper.window));
        const auto screen = wallpaper.window.screen()->name();
        using arasaka::login::deliverPointer;
        deliverPointer(&wallpaper.window, QStringLiteral("missing-screen"), 2, .25, .5);
        for (double bad : {-1., 1., std::numeric_limits<double>::infinity(), std::numeric_limits<double>::quiet_NaN()})
            deliverPointer(&wallpaper.window, screen, 2, bad, .5);
        deliverPointer(&wallpaper.window, screen, 99, .25, .5);
        QVERIFY(wallpaper.input.takeSplashes().empty());
        wallpaper.input.setLockScreenHost(false);
        QVERIFY(QMetaObject::invokeMethod(&wallpaper.input, "sessionLockChanged", Q_ARG(bool, true)));
        deliverPointer(&wallpaper.window, screen, 1, .25, .5);
        deliverPointer(&wallpaper.window, screen, 2, .25, .5);
        QVERIFY(!wallpaper.input.snapshot().valid);
        QVERIFY(wallpaper.input.takeSplashes().empty());
        wallpaper.input.setLockScreenHost(true);
        deliverPointer(&wallpaper.window, screen, 2, .25, .5);
        QCOMPARE(wallpaper.input.takeSplashes().size(), std::size_t(1));
    }
};

int main(int argc, char **argv) {
    QGuiApplication app(argc, argv);
    if (app.arguments().contains(QStringLiteral("--sender"))) {
        class Window : public QQuickWindow {
        public:
            int presses = 0, keys = 0;
            void mousePressEvent(QMouseEvent *) override { ++presses; }
            void keyPressEvent(QKeyEvent *) override { ++keys; }
        } window;
        class Observer : public QObject {
            bool eventFilter(QObject *obj, QEvent *event) override {
                arasaka::login::forwardPointer(qobject_cast<QQuickWindow *>(obj), event);
                return false;
            }
        } observer;
        window.resize(800, 600);
        window.show();
        if (!QTest::qWaitForWindowExposed(&window)) return 2;
        window.installEventFilter(&observer);
        const auto action = app.arguments().last();
        if (action == QLatin1String("hover")) {
            QMouseEvent move(QEvent::MouseMove, {200, 300}, {200, 300}, Qt::NoButton, Qt::NoButton, Qt::NoModifier);
            QCoreApplication::sendEvent(&window, &move);
        } else if (action == QLatin1String("click")) {
            QMouseEvent press(QEvent::MouseButtonPress, {200, 300}, {200, 300}, Qt::LeftButton, Qt::LeftButton, Qt::NoModifier);
            QCoreApplication::sendEvent(&window, &press);
            QMouseEvent release(QEvent::MouseButtonRelease, {200, 300}, {200, 300}, Qt::LeftButton, Qt::NoButton, Qt::NoModifier);
            QCoreApplication::sendEvent(&window, &release);
            if (window.presses != 1) return 3;
        } else {
            QEvent leave(QEvent::Leave);
            QCoreApplication::sendEvent(&window, &leave);
        }
        QKeyEvent key(QEvent::KeyPress, Qt::Key_A, Qt::NoModifier, QStringLiteral("a"));
        QCoreApplication::sendEvent(&window, &key);
        if (window.keys != 1) return 4;
        // Drain the connection before exit; a call to the bus follows the pointer messages.
        auto barrier = QDBusMessage::createMethodCall(QStringLiteral("org.freedesktop.DBus"),
            QStringLiteral("/org/freedesktop/DBus"), QStringLiteral("org.freedesktop.DBus"), QStringLiteral("GetId"));
        QDBusConnection::sessionBus().call(barrier);
        window.removeEventFilter(&observer);
        return 0;
    }
    LoginPointerTest test;
    return QTest::qExec(&test, argc, argv);
}

#include "login_pointer_test.moc"
