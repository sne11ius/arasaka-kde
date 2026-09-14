// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include <taskmanager/taskfilterproxymodel.h>
#include <taskmanager/windowtasksmodel.h>
#include <QHash>
#include <QSet>
#include <QDBusPendingCall>
#include <QTimer>

namespace arasaka::rain {

// Application windows, independently of taskbar grouping/exclusion/attention.
class WindowCountModel : public TaskManager::TaskFilterProxyModel {
    Q_OBJECT
    Q_PROPERTY(int count READ rowCount NOTIFY countChanged)
public:
    explicit WindowCountModel(QObject *parent = nullptr);

Q_SIGNALS:
    void countChanged();

protected:
    bool filterAcceptsRow(int row, const QModelIndex &parent) const override;
    virtual QDBusPendingCall requestWindowInfo(const QString &id);

private:
    void scheduleMetadata();
    void refreshMetadata();
    QString windowId(int row) const;
    TaskManager::WindowTasksModel *m_windows;
    QHash<QString, bool> m_applications;
    QSet<QString> m_pending;
    QSet<QString> m_live;
    QTimer m_retry;
    quint64 m_generation = 0;
    bool m_refreshPending = false;
    bool m_x11;
};

} // namespace arasaka::rain
