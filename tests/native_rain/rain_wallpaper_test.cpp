#include <KConfigLoader>
#include <KConfigPropertyMap>
#include <PlasmaQuick/QuickViewSharedEngine>
#include <PlasmaQuick/SharedQmlEngine>
#include <QDir>
#include <QFile>
#include <QQmlContext>
#include <QQmlEngine>
#include <QQmlProperty>
#include <QQuickItem>
#include <QTemporaryDir>
#include <QtTest>

// Observe actual property transitions, including the loader's pre-attachment interval.
class EnableWatch : public QObject {
    Q_OBJECT
public:
    EnableWatch(QObject *object, const char *name, bool *forbidden, QStringList *leaks)
        : property(object, QString::fromLatin1(name)), forbidden(forbidden), leaks(leaks) {
        property.connectNotifySignal(this, SLOT(sample()));
        sample();
    }
    int disables = 0;
private Q_SLOTS:
    void sample() {
        if (!property.read().toBool()) ++disables;
        else if (*forbidden) leaks->append(QString::fromLatin1(property.object()->metaObject()->className())
                                           + QLatin1Char('.') + property.name());
    }
private:
    QQmlProperty property;
    bool *forbidden;
    QStringList *leaks;
};

class RainWallpaperTest : public QObject {
    Q_OBJECT
    QObject *loader = nullptr, *system = nullptr, *engine = nullptr, *tracker = nullptr, *area = nullptr;
    bool forbidGeneric = true;
    QStringList leaks;
    std::vector<std::unique_ptr<EnableWatch>> watches;

public Q_SLOTS:
    void observeLoadedSystem() {
        system = loader->property("item").value<QObject *>();
        if (!system) return;
        for (auto *object : system->children()) {
            if (object->metaObject()->indexOfProperty("rainActive") >= 0) engine = object;
            if (object->inherits("CursorTracker")) tracker = object;
            if (object->metaObject()->indexOfProperty("propagateComposedEvents") >= 0) area = object;
        }
        if (tracker && area) {
            watches.push_back(std::make_unique<EnableWatch>(tracker, "enabled", &forbidGeneric, &leaks));
            watches.push_back(std::make_unique<EnableWatch>(area, "enabled", &forbidGeneric, &leaks));
            watches.push_back(std::make_unique<EnableWatch>(area, "hoverEnabled", &forbidGeneric, &leaks));
        }
    }

private Q_SLOTS:
    void startupAndReattachment_data() {
        QTest::addColumn<bool>("rain");
        QTest::newRow("native-rain") << true;
        QTest::newRow("ordinary-shader") << false;
    }

    void startupAndReattachment() {
        QFETCH(bool, rain);
        QTest::failOnWarning(QRegularExpression(QStringLiteral(".*(rainLockScreenHost|non-existent property).*")));
        watches.clear();
        leaks.clear();
        forbidGeneric = true;
        loader = system = engine = tracker = area = nullptr;
        const QString package = qEnvironmentVariable("RAIN_WALLPAPER_PACKAGE", QStringLiteral(RAIN_PACKAGE));
        const bool previous = qEnvironmentVariableIsSet("RAIN_PREVIOUS_NATIVE");
        QTemporaryDir files;
        QVERIFY(files.isValid());
        QFile schema(package + QStringLiteral("/contents/config/main.xml"));
        KConfigLoader configLoader(files.filePath("wallpaper-config"), &schema);
        KConfigPropertyMap config(&configLoader);
        config.insert(QStringLiteral("selectedShaderPath"), QString());
        config.insert(QStringLiteral("selectedShaderCode"),
                      (rain ? QStringLiteral("// @arasaka-effect rain-v1\n") : QString())
                      + QStringLiteral("void mainImage(out vec4 c, in vec2 p) { c = vec4(.2,.3,.4,1); }"));
        config.insert(QStringLiteral("mouseEnabled"), true);
        config.insert(QStringLiteral("running"), true);
        config.insert(QStringLiteral("pauseMode"), 3);
        config.insert(QStringLiteral("targetFps"), 30);

        PlasmaQuick::SharedQmlEngine wallpaper;
        wallpaper.setTranslationDomain(QStringLiteral("plasma_wallpaper_online.knowmad.shaderwallpaper"));
        wallpaper.setInitializationDelayed(true);
        wallpaper.setSource(QUrl::fromLocalFile(package + QStringLiteral("/contents/ui/main.qml")));
        auto *item = qobject_cast<QQuickItem *>(wallpaper.rootObject());
        QVERIFY2(item, qPrintable(wallpaper.mainComponent()->errorString()));
        QVERIFY(item->inherits("WallpaperItem"));
        for (auto *object : item->children()) {
            if (object->metaObject()->indexOfProperty("item") >= 0
                && object->property("source").toUrl().fileName() == QLatin1String("ShaderSystem.qml")) loader = object;
        }
        QVERIFY(loader);
        QVERIFY(QQmlProperty(loader, QStringLiteral("item")).connectNotifySignal(this, SLOT(observeLoadedSystem())));
        // Same completion-before-view-source/parent order as the actual locker integration.
        wallpaper.completeInitialization({{QStringLiteral("configuration"), QVariant::fromValue(&config)},
                                          {QStringLiteral("width"), 320}, {QStringLiteral("height"), 240}});
        QVERIFY(system && engine && tracker && area);
        QCOMPARE(engine->property("rainLockScreenHost").isValid(), !previous);
        QVERIFY(!item->window());
        QCOMPARE(engine->property("rainActive").toBool(), false);
        QTest::qWait(40); // Yield while unattached; readiness must not depend on non-reentrant startup.
        QVERIFY2(leaks.isEmpty(), qPrintable("Generic input before classification: " + leaks.join(", ")));
        QCOMPARE(engine->property("mouseEnabled").toBool(), false);

        // These are empty native component views, not greeter/authentication UI.
        const auto viewSource = [&](const QString &path) {
            const auto name = files.filePath(path);
            QDir().mkpath(QFileInfo(name).path());
            QFile file(name);
            if (!file.open(QIODevice::WriteOnly)
                || file.write("import QtQuick\nItem { width: 320; height: 240 }\n") < 0) return QUrl();
            return QUrl::fromLocalFile(name);
        };
        const auto lockSource = viewSource(QStringLiteral("LockScreen.qml"));
        const auto desktopSource = viewSource(QStringLiteral("Desktop.qml"));
        const auto unclassifiedSource = viewSource(QStringLiteral("Unclassified.qml"));
        const auto loginSource = viewSource(QStringLiteral("plasma/login/wallpaper/LockScreen.qml"));
        QVERIFY(!lockSource.isEmpty() && !desktopSource.isEmpty() && !loginSource.isEmpty());
        PlasmaQuick::QuickViewSharedEngine lockView, desktopView, secondDesktopView, loginView, unknownView;
        lockView.setSource(lockSource);
        desktopView.setSource(desktopSource);
        secondDesktopView.setSource(desktopSource);
        loginView.setSource(loginSource); // Both match patterns: login must win.
        lockView.resize(320, 240);
        lockView.show();
        QVERIFY(QTest::qWaitForWindowExposed(&lockView));
        item->setParentItem(lockView.rootObject());
        QTRY_COMPARE(engine->property("rainActive").toBool(), rain);
        QTRY_COMPARE(engine->property("mouseEnabled").toBool(), rain && !previous);
        QVERIFY2(leaks.isEmpty(), qPrintable(leaks.join(", ")));
        QVERIFY(!tracker->property("enabled").toBool());
        QVERIFY(!area->property("enabled").toBool());

        // Detach and same-window reparent must revoke permission, not retain a ready role.
        QSignalSpy mouseChanges(engine, SIGNAL(mouseEnabledChanged()));
        item->setParentItem(nullptr);
        QCOMPARE(engine->property("mouseEnabled").toBool(), false);
        QVERIFY(!tracker->property("enabled").toBool() && !area->property("enabled").toBool());
        item->setParentItem(lockView.rootObject());
        QCOMPARE(engine->property("mouseEnabled").toBool(), rain && !previous);
        if (rain && !previous) QVERIFY(mouseChanges.count() >= 2);
        QQuickItem newParent(lockView.rootObject());
        newParent.setSize({320, 240});
        mouseChanges.clear();
        item->setParentItem(&newParent);
        if (rain && !previous) QVERIFY2(mouseChanges.count() >= 2, "Reparent must invalidate native input even in the same window");

        item->setParentItem(loginView.rootObject());
        QCOMPARE(engine->property("mouseEnabled").toBool(), false);
        if (!previous) QCOMPARE(engine->property("rainLockScreenHost").toBool(), false);
        item->setParentItem(unknownView.contentItem());
        QCOMPARE(engine->property("mouseEnabled").toBool(), false);
        QVERIFY(!tracker->property("enabled").toBool() && !area->property("enabled").toBool());

        unknownView.setSource(unclassifiedSource);
        QCOMPARE(engine->property("mouseEnabled").toBool(), false);
        QVERIFY(!tracker->property("enabled").toBool() && !area->property("enabled").toBool());

        // A late recognized source establishes the role without another attachment.
        unknownView.setSource(lockSource);
        QCOMPARE(engine->property("mouseEnabled").toBool(), rain && !previous);
        QVERIFY2(leaks.isEmpty(), qPrintable(leaks.join(", ")));
        item->setParentItem(nullptr);
        forbidGeneric = false;
        item->setParentItem(desktopView.rootObject());
        QCOMPARE(engine->property("mouseEnabled").toBool(), true);
        QCOMPARE(tracker->property("enabled").toBool(), !rain);
        QCOMPARE(area->property("enabled").toBool(), !rain);

        // Plasma can attach/move a whole containment after its wallpaper is loaded.
        // The wallpaper's own parent stays the same while its ancestors change windows.
        item->setParentItem(&newParent);
        forbidGeneric = true;
        newParent.setParentItem(nullptr);
        QCOMPARE(engine->property("mouseEnabled").toBool(), false);
        forbidGeneric = false;
        newParent.setParentItem(desktopView.rootObject());
        QCOMPARE(engine->property("mouseEnabled").toBool(), true);
        newParent.setParentItem(secondDesktopView.rootObject());
        QCOMPARE(engine->property("mouseEnabled").toBool(), true);
        QCOMPARE(tracker->property("enabled").toBool(), !rain);
        QCOMPARE(area->property("enabled").toBool(), !rain);
        forbidGeneric = true;
        newParent.setParentItem(lockView.rootObject());
        QCOMPARE(engine->property("mouseEnabled").toBool(), rain && !previous);
        QVERIFY(!tracker->property("enabled").toBool());
        QVERIFY(!area->property("enabled").toBool());
        QVERIFY(!area->property("hoverEnabled").toBool());
        newParent.setParentItem(loginView.rootObject());
        QCOMPARE(engine->property("mouseEnabled").toBool(), false);
        QVERIFY(!tracker->property("enabled").toBool());
        QVERIFY(!area->property("enabled").toBool());
        QVERIFY(!area->property("hoverEnabled").toBool());
        QVERIFY2(leaks.isEmpty(), qPrintable(leaks.join(", ")));

        // Reclassify the same attached window without reparenting the wallpaper.
        forbidGeneric = false;
        item->setParentItem(desktopView.contentItem());
        forbidGeneric = true;
        desktopView.setSource(loginSource);
        QCOMPARE(engine->property("mouseEnabled").toBool(), false);
        QVERIFY(!tracker->property("enabled").toBool() && !area->property("enabled").toBool());
        QVERIFY2(leaks.isEmpty(), qPrintable(leaks.join(", ")));
        item->setParentItem(nullptr);
        watches.clear();
    }
};

int main(int argc, char **argv)
{
    QTemporaryDir sandbox;
    if (!sandbox.isValid()) return 1;
    for (const auto name : {"DATA", "CONFIG", "CACHE"})
        qputenv(QByteArray("XDG_") + name + "_HOME", (sandbox.path() + QLatin1Char('/') + QLatin1String(name)).toUtf8());
    const QString library = sandbox.path() + QStringLiteral("/DATA/plasma/wallpapers/online.knowmad.shaderwallpaper/contents/ui/Shaders");
    if (!QDir().mkpath(library)) return 1;
    QFile seed(library + QStringLiteral("/Default.frag"));
    if (!seed.open(QIODevice::WriteOnly) || seed.write("void mainImage(out vec4 c, in vec2 p) { c = vec4(1.); }\n") < 0) return 1;
    seed.close();
    qputenv("QSG_RENDER_LOOP", "basic");
    qputenv("QML_DISABLE_DISK_CACHE", "1");
    QQuickWindow::setGraphicsApi(QSGRendererInterface::OpenGL);
    QGuiApplication app(argc, argv);
    RainWallpaperTest test;
    return QTest::qExec(&test, argc, argv);
}

#include "rain_wallpaper_test.moc"
