// SPDX-License-Identifier: GPL-3.0-or-later
#include <QDBusInterface>
#include <QDBusReply>
#include <QFile>
#include <QQmlComponent>
#include <QQmlEngine>
#include <QQuickWindow>
#include <QScreen>
#include <QTemporaryDir>
#include <QtTest>
#include <QBackingStore>
#include <QPainter>
#include "../../native/rain/windowcountmodel.h"
#include <taskmanager/virtualdesktopinfo.h>

// Model the compositor lookup before a toplevel becomes queryable. Qt versions
// can attach an initial buffer themselves, so hold this external boundary until ready.
class InitiallyUnmappedModel : public arasaka::rain::WindowCountModel {
public:
    bool metadataReady = false;
private:
    QDBusPendingCall requestWindowInfo(const QString &id) override {
        return WindowCountModel::requestWindowInfo(metadataReady ? id : QString());
    }
};

// Opt-in: run only inside the disposable two-output KWin session from
// tests/window_illumination_smoke.py. Exercises the actual Plasma TasksModel.
class WindowCountTest : public QObject {
    Q_OBJECT
    QTemporaryDir scripts;
    int serial = 0;

    void evaluate(const QString &code) {
        const auto name = QStringLiteral("illumination-probe-%1").arg(++serial);
        QFile script(scripts.filePath(name + QStringLiteral(".js")));
        QVERIFY(script.open(QIODevice::WriteOnly));
        script.write(code.toUtf8());
        script.close();
        QDBusInterface scripting(QStringLiteral("org.kde.KWin"), QStringLiteral("/Scripting"),
                                 QStringLiteral("org.kde.kwin.Scripting"));
        QDBusReply<int> id = scripting.call(QStringLiteral("loadScript"), script.fileName(), name);
        QVERIFY2(id.isValid(), qPrintable(id.error().message()));
        QDBusInterface runner(QStringLiteral("org.kde.KWin"),
                              QStringLiteral("/Scripting/Script%1").arg(id.value()), QStringLiteral("org.kde.kwin.Script"));
        QVERIFY(runner.call(QStringLiteral("run")).type() != QDBusMessage::ErrorMessage);
        scripting.call(QStringLiteral("unloadScript"), name);
    }

    void action(const QString &title, const QString &code) {
        evaluate(QStringLiteral("const w = workspace.windowList().find(w => w.caption === '%1'); if (!w) throw Error('missing fixture'); %2")
                     .arg(title, code));
    }

private Q_SLOTS:
    void delayedFirstBufferIsEventuallyCounted() {
        QCOMPARE(qEnvironmentVariable("ARASAKA_WINDOW_COUNT_TEST"), QStringLiteral("1"));
        InitiallyUnmappedModel model;
        QQmlEngine qml;
        QQmlComponent component(&qml, QUrl::fromLocalFile(QStringLiteral(RAIN_PACKAGE "/contents/ui/WindowModel.qml")));
        std::unique_ptr<QObject> consumer(component.createWithInitialProperties({
            {QStringLiteral("illuminationModel"), QVariant::fromValue(static_cast<QObject *>(&model))},
            {QStringLiteral("screenGeometry"), QGuiApplication::screens()[0]->geometry()}}));
        QVERIFY2(consumer, qPrintable(component.errorString()));
        TaskManager::WindowTasksModel raw;
        QTRY_COMPARE(raw.rowCount(), 0);
        QWindow delayed;
        delayed.setTitle(QStringLiteral("Illumination Delayed"));
        delayed.resize(300, 200);
        delayed.show();
        QTRY_COMPARE(raw.rowCount(), 1);
        QTest::qWait(250);

        QBackingStore backing(&delayed);
        backing.resize(delayed.size());
        const QRegion region(QRect(QPoint(), delayed.size()));
        backing.beginPaint(region);
        {
            QPainter painter(backing.paintDevice());
            painter.fillRect(region.boundingRect(), Qt::blue);
        }
        backing.endPaint();
        backing.flush(region);
        QTest::qWait(500); // Let window events settle before only metadata becomes available.
        QCOMPARE(consumer->property("visibleWindowCount").toInt(), 0);
        model.metadataReady = true;
        QTRY_COMPARE(model.rowCount(), 1);
        QTRY_COMPARE(consumer->property("visibleWindowCount").toInt(), 1);
    }

    void perOutputVisibility_data() {
        QTest::addColumn<bool>("skipTaskbar");
        QTest::newRow("ordinary") << false;
        QTest::newRow("skip-taskbar") << true;
    }

    void perOutputVisibility() {
        QFETCH(bool, skipTaskbar);
        QCOMPARE(qEnvironmentVariable("ARASAKA_WINDOW_COUNT_TEST"), QStringLiteral("1"));
        QCOMPARE(QGuiApplication::screens().size(), 2);
        evaluate(QStringLiteral("workspace.screens.forEach(s => workspace.setCurrentDesktopForScreen(workspace.desktops[0], s));"));
        QQmlEngine qml;
        arasaka::rain::WindowCountModel leftSource, rightSource;
        QQmlComponent component(&qml, QUrl::fromLocalFile(QStringLiteral(RAIN_PACKAGE "/contents/ui/WindowModel.qml")));
        std::unique_ptr<QObject> left(component.createWithInitialProperties({
            {QStringLiteral("illuminationModel"), QVariant::fromValue(static_cast<QObject *>(&leftSource))},
            {QStringLiteral("screenGeometry"), QGuiApplication::screens()[0]->geometry()},
            {QStringLiteral("activeScreenOnly"), false},
            {QStringLiteral("excludeWindows"), QStringList{QStringLiteral("arasaka-illumination-fixture")}}}));
        std::unique_ptr<QObject> right(component.createWithInitialProperties({
            {QStringLiteral("illuminationModel"), QVariant::fromValue(static_cast<QObject *>(&rightSource))},
            {QStringLiteral("screenGeometry"), QGuiApplication::screens()[1]->geometry()}}));
        QVERIFY2(left && right, qPrintable(component.errorString()));
        const auto count = [](const auto &model) { return model->property("visibleWindowCount").toInt(); };
        QVERIFY(left->property("visibleWindowCount").isValid());
        QTRY_COMPARE(count(left), 0);
        QTRY_COMPARE(count(right), 0);

        QQuickWindow first, second;
        first.setTitle(QStringLiteral("Illumination One"));
        second.setTitle(QStringLiteral("Illumination Two"));
        first.resize(300, 200);
        second.resize(300, 200);
        first.show();
        second.show();
        QVERIFY(QTest::qWaitForWindowExposed(&first));
        QVERIFY(QTest::qWaitForWindowExposed(&second));
        for (const auto &title : {first.title(), second.title()})
            action(title, QStringLiteral("const g = workspace.screens[0].geometry; w.frameGeometry = {x:g.x+100,y:g.y+100,width:300,height:200};"));
        QTRY_COMPARE(count(left), 2); // Same app, one unfocused/covered, pause exclusions ignored.
        QTRY_COMPARE(count(right), 0);
        if (skipTaskbar) {
            action(second.title(), QStringLiteral("w.skipTaskbar = true;"));
            QTest::qWait(150);
            QCOMPARE(count(left), 2);
        }

        action(second.title(), QStringLiteral("const g = workspace.screens[1].geometry; w.frameGeometry = {x:g.x+100,y:g.y+100,width:300,height:200};"));
        QTRY_COMPARE(count(left), 1);
        QTRY_COMPARE(count(right), 1);
        action(second.title(), QStringLiteral("w.minimized = true;"));
        QTRY_COMPARE(count(right), 0);
        action(second.title(), QStringLiteral("w.minimized = false;"));
        QTRY_COMPARE(count(right), 1);

        action(second.title(), QStringLiteral("w.desktops = [workspace.desktops[1]];"));
        QTRY_COMPARE(count(right), 0);
        action(second.title(), QStringLiteral("w.demandsAttention = true;"));
        QTest::qWait(150);
        QCOMPARE(count(right), 0);
        action(second.title(), QStringLiteral("w.demandsAttention = false;"));

        action(second.title(), QStringLiteral("w.desktops = [];")); // All desktops still counts once.
        QTRY_COMPARE(count(right), 1);
        QDBusInterface activities(QStringLiteral("org.kde.ActivityManager"), QStringLiteral("/ActivityManager/Activities"),
                                   QStringLiteral("org.kde.ActivityManager.Activities"));
        QDBusReply<QString> added = activities.call(QStringLiteral("AddActivity"), QStringLiteral("Illumination Other"));
        QVERIFY(added.isValid() && !added.value().isEmpty());
        action(second.title(), QStringLiteral("w.activities = ['%1']; w.demandsAttention = true;").arg(added.value()));
        QTRY_COMPARE(count(right), 0);
        QTest::qWait(150);
        QCOMPARE(count(right), 0);
        action(second.title(), QStringLiteral("w.activities = []; w.demandsAttention = false;"));
        QTRY_COMPARE(count(right), 1); // All activities must remain eligible.
        action(second.title(), QStringLiteral("w.desktops = [workspace.desktops[1]];"));
        QTRY_COMPARE(count(right), 0);
        evaluate(QStringLiteral("workspace.screens.forEach(s => workspace.setCurrentDesktopForScreen(workspace.desktops[1], s));"));
        QTRY_COMPARE(count(left), 0);
        QTRY_COMPARE(count(right), 1);
        evaluate(QStringLiteral("workspace.slotToggleShowDesktop();"));
        QTRY_COMPARE(count(right), 0);
        evaluate(QStringLiteral("workspace.slotToggleShowDesktop();"));
        QTRY_COMPARE(count(right), 1);
        if (qEnvironmentVariable("ARASAKA_PER_OUTPUT_DESKTOPS") == QStringLiteral("1")) {
            TaskManager::VirtualDesktopInfo desktops;
            evaluate(QStringLiteral("workspace.setCurrentDesktopForScreen(workspace.desktops[0], workspace.screens[0]);"));
            QTRY_COMPARE(desktops.currentDesktopByScreenName(QGuiApplication::screens()[0]->name()), desktops.desktopIds()[0]);
            QTRY_COMPARE(desktops.currentDesktopByScreenName(QGuiApplication::screens()[1]->name()), desktops.desktopIds()[1]);
            QTRY_COMPARE(count(left), 1);
            QTRY_COMPARE(count(right), 1);
            // Focus alone must not make the other screen use the active screen's desktop.
            for (const auto &title : {first.title(), second.title()}) {
                action(title, QStringLiteral("workspace.activeWindow = w;"));
                QTest::qWait(150);
                QCOMPARE(count(left), 1);
                QCOMPARE(count(right), 1);
            }
        }
        second.close();
        QTRY_COMPARE(count(right), 0);
    }
};

int main(int argc, char **argv)
{
    QGuiApplication app(argc, argv);
    app.setDesktopFileName(QStringLiteral("arasaka-illumination-fixture"));
    WindowCountTest test;
    return QTest::qExec(&test, argc, argv);
}

#include "window_count_test.moc"
