// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include "dropletsimulation.h"
#include <QElapsedTimer>
#include <QPointer>
#include <QQuickItem>
#include <QQuickWindow>
#include <array>

namespace arasaka::rain {

// GUI-thread passive observer. Never polls the global cursor, grabs, or requests a frame.
class RainInput : public QObject {
    Q_OBJECT
public:
    explicit RainInput(QQuickItem *item);
    ~RainInput() override;
    void setEnabled(bool enabled);
    void setLockScreenHost(bool lockScreenHost);
    void invalidate();
    void refreshGeometry();
    PointerSnapshot snapshot() const { return pointer_; }
    // Map new source samples onto the host's admitted active timeline; held samples stay unchanged.
    PointerSnapshot synchronize(double activeSeconds);
    std::uint64_t invalidationSequence() const { return invalidationSequence_; }

protected:
    bool eventFilter(QObject *watched, QEvent *event) override;

private Q_SLOTS:
    void sessionLockChanged(bool locked);

private:
    void trackWindow(QQuickWindow *window);
    void querySessionLock();
    QQuickItem *item_;
    QPointer<QQuickWindow> window_;
    QElapsedTimer clock_;
    PointerSnapshot pointer_;
    PointerSnapshot activePointer_;
    double syncWallSeconds_ = 0, activeSeconds_ = 0;
    std::array<QPointF, 3> geometry_{};
    qreal dpr_ = 0;
    bool enabled_ = false;
    bool lockScreenHost_ = false;
    bool locked_ = true;
    std::uint64_t invalidationSequence_ = 0, lockRevision_ = 0;
};

} // namespace arasaka::rain
