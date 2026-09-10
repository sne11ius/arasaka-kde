// SPDX-License-Identifier: EUPL-1.2
#pragma once

#include <QFileSystemWatcher>
#include <QObject>
#include <QPointer>
#include <QSet>
#include <QtQml/qqmlregistration.h>

namespace KWin { class Window; }

// Loaded by Polonium inside KWin. No input is delivered to applications.
class WindowPolicy : public QObject
{
    Q_OBJECT
    QML_ELEMENT
    Q_CLASSINFO("D-Bus Interface", "org.arasaka.WindowPolicy1")
    Q_PROPERTY(QString pidFile READ pidFile WRITE setPidFile NOTIFY pidFileChanged)
public:
    explicit WindowPolicy(QObject *parent = nullptr);
    QString pidFile() const { return m_pidFile; }
    void setPidFile(const QString &path);
    Q_INVOKABLE bool isQuake(QObject *window) const;
    Q_INVOKABLE bool tiles(QObject *window) const;
    Q_INVOKABLE void ready(const QString &version) { m_version = version; }
    Q_SCRIPTABLE Q_INVOKABLE QString report() const;
    ~WindowPolicy() override;

Q_SIGNALS:
    void pidFileChanged();
    void changed();

private:
    void refreshQuake();
    void watch(KWin::Window *window);
    void enforce(KWin::Window *window);
    QString m_pidFile;
    QString m_version;
    QFileSystemWatcher m_watcher;
    QPointer<KWin::Window> m_quake;
    QSet<KWin::Window *> m_pending;
    bool m_registered = false;
};
