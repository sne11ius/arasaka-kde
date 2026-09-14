// SPDX-License-Identifier: GPL-3.0-or-later
#include "windowcountmodel.h"

#include <taskmanager/abstracttasksmodel.h>
#include <QDBusConnection>
#include <QDBusPendingCallWatcher>
#include <QDBusPendingReply>
#include <QDBusServiceWatcher>
#include <QGuiApplication>
#include <QTimer>
#include <netwm_def.h>

namespace arasaka::rain {

WindowCountModel::WindowCountModel(QObject *parent)
    : TaskFilterProxyModel(parent)
    , m_windows(new TaskManager::WindowTasksModel(this))
    , m_x11(QGuiApplication::platformName() == QLatin1String("xcb"))
{
    setFilterSkipTaskbar(false);
    setFilterSkipPager(false);
    setDemandingAttentionSkipsFilters(false);
    setFilterMinimized(true);
    setFilterHidden(true);
    setFilterByScreen(true);
    // Plasma 6.7 can show different desktops on each output. Older task models
    // use the shared-desktop QML binding instead; never apply both filters.
    if (metaObject()->indexOfProperty("filterByCurrentVirtualDesktop") >= 0)
        setProperty("filterByCurrentVirtualDesktop", true);
    else
        setFilterByVirtualDesktop(true);
    setFilterByActivity(true);
    m_retry.setSingleShot(true);
    m_retry.setInterval(250);
    connect(&m_retry, &QTimer::timeout, this, &WindowCountModel::scheduleMetadata);
    connect(this, &QAbstractItemModel::rowsInserted, this, &WindowCountModel::countChanged);
    connect(this, &QAbstractItemModel::rowsRemoved, this, &WindowCountModel::countChanged);
    connect(this, &QAbstractItemModel::modelReset, this, &WindowCountModel::countChanged);
    connect(this, &QAbstractItemModel::layoutChanged, this, &WindowCountModel::countChanged);
    connect(m_windows, &QAbstractItemModel::rowsInserted, this, &WindowCountModel::scheduleMetadata);
    connect(m_windows, &QAbstractItemModel::rowsRemoved, this, &WindowCountModel::scheduleMetadata);
    connect(m_windows, &QAbstractItemModel::modelReset, this, &WindowCountModel::scheduleMetadata);
    connect(m_windows, &QAbstractItemModel::dataChanged, this, &WindowCountModel::scheduleMetadata);
    setSourceModel(m_windows);
    auto *service = new QDBusServiceWatcher(QStringLiteral("org.kde.KWin"), QDBusConnection::sessionBus(),
                                           QDBusServiceWatcher::WatchForOwnerChange, this);
    connect(service, &QDBusServiceWatcher::serviceOwnerChanged, this, [this] {
        ++m_generation;
        m_applications.clear();
        m_pending.clear();
        invalidate();
        scheduleMetadata();
    });
    scheduleMetadata();
}

QString WindowCountModel::windowId(int row) const
{
    const auto ids = m_windows->data(m_windows->index(row, 0), TaskManager::AbstractTasksModel::WinIdList).toList();
    return ids.isEmpty() ? QString() : ids.front().toString();
}

bool WindowCountModel::filterAcceptsRow(int row, const QModelIndex &parent) const
{
    if (!TaskFilterProxyModel::filterAcceptsRow(row, parent)) return false;
    // The X11 source already admits only application window types. Wayland's
    // public task roles do not distinguish shell surfaces from skip-taskbar apps.
    return m_x11 || m_applications.value(windowId(row), false);
}

void WindowCountModel::scheduleMetadata()
{
    if (m_x11 || m_refreshPending) return;
    m_refreshPending = true;
    QTimer::singleShot(0, this, [this] {
        m_refreshPending = false;
        refreshMetadata();
    });
}

void WindowCountModel::refreshMetadata()
{
    QSet<QString> live;
    for (int row = 0; row < m_windows->rowCount(); ++row) {
        const auto id = windowId(row);
        if (!id.isEmpty()) live.insert(id);
    }
    m_live = live;
    m_pending.intersect(live);
    for (auto it = m_applications.begin(); it != m_applications.end();) {
        if (!live.contains(it.key())) it = m_applications.erase(it);
        else ++it;
    }
    for (const auto &id : live) {
        if (m_applications.contains(id) || m_pending.contains(id)) continue;
        m_pending.insert(id); // Pending metadata is never a definitive classification.
        auto *call = new QDBusPendingCallWatcher(requestWindowInfo(id), this);
        connect(call, &QDBusPendingCallWatcher::finished, this, [this, id, generation = m_generation](QDBusPendingCallWatcher *call) {
            const QDBusPendingReply<QVariantMap> reply = *call;
            call->deleteLater();
            if (generation != m_generation || !m_live.contains(id)) return;
            m_pending.remove(id);
            const auto info = reply.isError() ? QVariantMap() : reply.value();
            if (reply.isError() || !info.contains(QStringLiteral("type"))) {
                // Wayland may announce a toplevel before its first buffer puts
                // it in KWin's workspace list. Retry unresolved live windows.
                if (!m_retry.isActive()) m_retry.start();
                return;
            }
            const int type = info.value(QStringLiteral("type")).toInt();
            m_applications[id] = type == NET::Normal || type == NET::Dialog || type == NET::Utility
                || type == NET::Unknown || type == NET::Override;
            invalidate();
        });
    }
}

QDBusPendingCall WindowCountModel::requestWindowInfo(const QString &id)
{
    auto request = QDBusMessage::createMethodCall(QStringLiteral("org.kde.KWin"), QStringLiteral("/KWin"),
                                                 QStringLiteral("org.kde.KWin"), QStringLiteral("getWindowInfo"));
    request << id;
    return QDBusConnection::sessionBus().asyncCall(request);
}

} // namespace arasaka::rain
