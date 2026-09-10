// Test-only native input-operation probe. Loaded only in the disposable KWin.
#include <QDBusConnection>
#include <QQmlExtensionPlugin>
#include <QtQml/qqml.h>
#include <QDir>
#include <window.h>
#include <workspace.h>

class DragProbe : public QObject
{
    Q_OBJECT
    Q_CLASSINFO("D-Bus Interface", "org.arasaka.TestDrag")
public:
    explicit DragProbe(QObject *parent = nullptr) : QObject(parent)
    {
        // Refuse even accidental use in the real compositor/session.
        if (!QDir::homePath().startsWith(QStringLiteral("/tmp/opencode/window-policy-"))) qFatal("Not an isolated test");
        QDBusConnection::sessionBus().registerObject(QStringLiteral("/PolicyDragProbe"), this,
                                                    QDBusConnection::ExportScriptableInvokables);
    }
    Q_INVOKABLE Q_SCRIPTABLE bool begin(const QString &caption)
    {
        auto *w = fixture(caption);
        if (!w) return false;
        KWin::workspace()->setActiveWindow(w);
        KWin::workspace()->slotWindowMove();
        return w->isInteractiveMove();
    }
    Q_INVOKABLE Q_SCRIPTABLE bool step(const QString &caption, int output)
    {
        auto *w = fixture(caption);
        const auto outputs = KWin::workspace()->outputs();
        if (!w || !w->isInteractiveMove() || output < 0 || output >= outputs.size()) return false;
        w->updateInteractiveMoveResize(outputs[output]->geometryF().center(), Qt::NoModifier);
        return true;
    }
    Q_INVOKABLE Q_SCRIPTABLE bool end(const QString &caption, bool cancel)
    {
        auto *w = fixture(caption);
        if (!w || !w->isInteractiveMove()) return false;
        if (cancel) w->cancelInteractiveMoveResize();
        else w->endInteractiveMoveResize();
        return true;
    }
private:
    KWin::Window *fixture(const QString &caption)
    {
        for (auto *w : KWin::workspace()->windows()) {
            if (w->resourceClass() == QStringLiteral("arasaka-policy-fixture") && w->caption() == caption) return w;
        }
        return nullptr;
    }
};

class ProbePlugin : public QQmlExtensionPlugin
{
    Q_OBJECT
    Q_PLUGIN_METADATA(IID QQmlExtensionInterface_iid)
public:
    void registerTypes(const char *uri) override { qmlRegisterType<DragProbe>(uri, 1, 0, "DragProbe"); }
};
#include "probe.moc"
