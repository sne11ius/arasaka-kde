// SPDX-License-Identifier: EUPL-1.2
#include "windowpolicy.h"

#include <QDir>
#include <QDBusConnection>
#include <QFile>
#include <QFileInfo>
#include <QRegularExpression>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QStandardPaths>
#include <QTimer>
#include <unistd.h>
#include <window.h>
#include <workspace.h>

namespace {
bool applicationWindow(KWin::Window *w)
{
    return w && !w->isDeleted() && !w->isPopupWindow()
        && (w->isNormalWindow() || w->isDialog());
}
}

WindowPolicy::WindowPolicy(QObject *parent) : QObject(parent)
{
    m_registered = QDBusConnection::sessionBus().registerObject(QStringLiteral("/ArasakaWindowPolicy"), this,
                                                              QDBusConnection::ExportScriptableInvokables);
    connect(&m_watcher, &QFileSystemWatcher::fileChanged, this, &WindowPolicy::refreshQuake);
    connect(&m_watcher, &QFileSystemWatcher::directoryChanged, this, &WindowPolicy::refreshQuake);
    connect(KWin::workspace(), &KWin::Workspace::windowAdded, this, [this](KWin::Window *w) {
        refreshQuake();
        watch(w);
    });
    connect(KWin::workspace(), &KWin::Workspace::windowRemoved, this, [this](KWin::Window *w) {
        m_pending.remove(w);
        if (m_quake == w) {
            m_quake.clear();
            Q_EMIT changed();
        }
    });
    setPidFile(QStringLiteral("/tmp/konsole-quake.pid"));
    for (auto *w : KWin::workspace()->windows()) {
        watch(w);
    }
}

WindowPolicy::~WindowPolicy()
{
    if (m_registered) {
        QDBusConnection::sessionBus().unregisterObject(QStringLiteral("/ArasakaWindowPolicy"));
    }
}

QString WindowPolicy::report() const
{
    QJsonArray windows;
    for (auto *w : KWin::workspace()->windows()) {
        if (!applicationWindow(w)) continue;
        windows.append(QJsonObject{
            {"id", w->internalId().toString()}, {"app", w->resourceClass()}, {"pid", qint64(w->pid())},
            {"quake", isQuake(w)}, {"tiled", w->requestedTile() != nullptr},
            {"minimized", w->isMinimized()}, {"maximized", int(w->maximizeMode())},
            {"fullscreen", w->isFullScreen()}, {"moving", w->isInteractiveMove()},
            {"resizing", w->isInteractiveResize()}, {"noBorder", w->noBorder()},
            {"keepAbove", w->keepAbove()}
        });
    }
    return QString::fromUtf8(QJsonDocument(QJsonObject{{"version", m_version}, {"windows", windows},
                                 {"nativeRevision", QStringLiteral(ARASAKA_POLICY_REVISION)}})
                                .toJson(QJsonDocument::Compact));
}

void WindowPolicy::setPidFile(const QString &path)
{
    if (m_pidFile == path) return;
    if (!m_watcher.files().isEmpty()) m_watcher.removePaths(m_watcher.files());
    if (!m_watcher.directories().isEmpty()) m_watcher.removePaths(m_watcher.directories());
    m_pidFile = path;
    m_watcher.addPath(QFileInfo(path).absolutePath());
    refreshQuake();
    Q_EMIT pidFileChanged();
}

void WindowPolicy::refreshQuake()
{
    const QFileInfo info(m_pidFile);
    if (info.exists() && !m_watcher.files().contains(m_pidFile)) m_watcher.addPath(m_pidFile);
    KWin::Window *match = nullptr;
    QFile file(m_pidFile);
    if (info.isFile() && !info.isSymLink() && info.size() <= 32 && info.ownerId() == getuid() && file.open(QIODevice::ReadOnly)) {
        const QByteArray text = file.read(32).trimmed();
        static const QRegularExpression digits(QStringLiteral("^[1-9][0-9]*$"));
        bool ok = false;
        const qlonglong pid = text.toLongLong(&ok);
        const QString proc = QStringLiteral("/proc/%1").arg(pid);
        const QString konsole = QFileInfo(QStandardPaths::findExecutable(QStringLiteral("konsole"))).canonicalFilePath();
        if (ok && digits.match(QString::fromLatin1(text)).hasMatch() && pid > 0 && !konsole.isEmpty()
            && QFileInfo(proc).ownerId() == getuid()
            && QFileInfo(proc + QStringLiteral("/exe")).canonicalFilePath() == konsole) {
            for (auto *w : KWin::workspace()->windows()) {
                if (applicationWindow(w) && w->isNormalWindow() && !w->isTransient()
                    && w->pid() == pid && (w->resourceClass() == QStringLiteral("org.kde.konsole")
                                          || w->resourceClass() == QStringLiteral("konsole"))) {
                    // Keep the same window if the process creates another top-level.
                    if (!match || w == m_quake) match = w;
                }
            }
        }
    }
    if (match != m_quake) {
        auto previous = m_quake;
        m_quake = match;
        if (previous) enforce(previous);
        Q_EMIT changed();
    }
}

bool WindowPolicy::isQuake(QObject *window) const
{
    return m_quake && m_quake == qobject_cast<KWin::Window *>(window);
}

bool WindowPolicy::tiles(QObject *window) const
{
    auto *w = qobject_cast<KWin::Window *>(window);
    return applicationWindow(w) && !isQuake(w);
}

void WindowPolicy::watch(KWin::Window *w)
{
    if (!applicationWindow(w)) return;
    connect(w, &KWin::Window::interactiveMoveResizeStarted, this, [this, w] { enforce(w); });
    connect(w, &KWin::Window::interactiveMoveResizeFinished, this, [this, w] { enforce(w); });
    connect(w, &KWin::Window::maximizedChanged, this, [this, w] { enforce(w); });
    connect(w, &KWin::Window::fullScreenChanged, this, [this, w] { enforce(w); });
    enforce(w);
}

void WindowPolicy::enforce(KWin::Window *window)
{
    if (!tiles(window) || m_pending.contains(window)) return;
    m_pending.insert(window);
    // KWin is still inside startInteractiveMoveResize/maximize when it emits.
    // Cancel on the next event-loop turn, never reenter that transition.
    QTimer::singleShot(0, this, [this, guard = QPointer<KWin::Window>(window)] {
        auto *w = guard.data();
        m_pending.remove(w);
        if (!tiles(w) || w->isInteractiveMove()) return;
        if (w->isInteractiveResize()) {
            w->cancelInteractiveMoveResize();
        }
        w->setFullScreen(false);
        w->setMaximize(false, false);
        // false restores PreferredByClient; unlike a noborder=false rule it
        // does not force an extra server decoration onto CSD applications.
        w->setNoBorder(false);
    });
}
