// SPDX-License-Identifier: GPL-3.0-or-later
#include "raininput.h"
#include <QDBusConnection>
#include <QDBusError>
#include <QDBusMessage>
#include <QDBusPendingCallWatcher>
#include <QDBusPendingReply>
#include <QDBusServiceWatcher>
#include <QMouseEvent>
#include <algorithm>
#include <cmath>
#include <utility>

namespace arasaka::rain {

RainInput::RainInput(QQuickItem *item) : QObject(item), item_(item)
{
    clock_.start();
    connect(item, &QQuickItem::windowChanged, this, &RainInput::trackWindow);
    connect(item, &QQuickItem::visibleChanged, this, &RainInput::invalidate);
    connect(item, &QQuickItem::enabledChanged, this, &RainInput::invalidate);
    trackWindow(item->window());
    auto bus = QDBusConnection::sessionBus();
    bus.connect(QStringLiteral("org.freedesktop.ScreenSaver"), QStringLiteral("/ScreenSaver"),
                QStringLiteral("org.freedesktop.ScreenSaver"), QStringLiteral("ActiveChanged"),
                this, SLOT(sessionLockChanged(bool)));
    auto *watcher = new QDBusServiceWatcher(QStringLiteral("org.freedesktop.ScreenSaver"), bus,
                                          QDBusServiceWatcher::WatchForOwnerChange, this);
    connect(watcher, &QDBusServiceWatcher::serviceOwnerChanged, this, [this]() {
        sessionLockChanged(true);
        querySessionLock();
    });
    querySessionLock();
}

RainInput::~RainInput()
{
    if (window_) window_->removeEventFilter(this);
}

void RainInput::querySessionLock()
{
    const auto revision = lockRevision_;
    const auto message = QDBusMessage::createMethodCall(QStringLiteral("org.freedesktop.ScreenSaver"),
        QStringLiteral("/ScreenSaver"), QStringLiteral("org.freedesktop.ScreenSaver"), QStringLiteral("GetActive"));
    auto *call = new QDBusPendingCallWatcher(QDBusConnection::sessionBus().asyncCall(message), this);
    connect(call, &QDBusPendingCallWatcher::finished, this, [this, revision](QDBusPendingCallWatcher *finished) {
        const QDBusPendingReply<bool> reply = *finished;
        // An older GetActive must not undo a more recent lock signal.
        if (revision == lockRevision_) {
            if (!reply.isError()) sessionLockChanged(reply.value());
            else if (reply.error().type() == QDBusError::ServiceUnknown)
                sessionLockChanged(false); // No session locker in an isolated test/standalone session.
        }
        finished->deleteLater();
    });
}

void RainInput::sessionLockChanged(bool locked)
{
    ++lockRevision_;
    locked_ = locked;
    invalidate();
}

void RainInput::trackWindow(QQuickWindow *window)
{
    if (window_) window_->removeEventFilter(this);
    window_ = window;
    if (window_) window_->installEventFilter(this);
    invalidate();
    refreshGeometry();
}

void RainInput::setEnabled(bool enabled)
{
    if (enabled_ == enabled) return;
    enabled_ = enabled;
    invalidate();
}

void RainInput::invalidate()
{
    invalidateHover();
    splashes_.clear();
    ++splashCancellationSequence_;
}

void RainInput::invalidateHover()
{
    pointer_.valid = false;
    ++invalidationSequence_;
}

std::vector<Vec2> RainInput::takeSplashes()
{
    return std::exchange(splashes_, {});
}

void RainInput::setLockScreenHost(bool lockScreenHost)
{
    if (lockScreenHost_ == lockScreenHost) return;
    lockScreenHost_ = lockScreenHost;
    invalidate();
}

PointerSnapshot RainInput::synchronize(double activeSeconds)
{
    const double now = clock_.nsecsElapsed() / 1e9;
    const double wallSeconds = now - syncWallSeconds_;
    if (!std::isfinite(activeSeconds) || activeSeconds < 0) activeSeconds = 0;
    if (pointer_.sequence != activePointer_.sequence) {
        activePointer_ = pointer_;
        // Piecewise affine clock mapping includes both host and physics admission clamps.
        // Do not retimestamp a held sequence or serialize raw wall time at a different speed.
        const double fraction = wallSeconds > 0
            ? std::clamp((pointer_.sampleSeconds - syncWallSeconds_) / wallSeconds, 0.0, 1.0) : 0;
        activePointer_.sampleSeconds = activeSeconds_ + fraction * activeSeconds;
    }
    activePointer_.valid = pointer_.valid;
    activeSeconds_ += activeSeconds;
    syncWallSeconds_ = now;
    return activePointer_;
}

void RainInput::refreshGeometry()
{
    const std::array<QPointF, 3> geometry{item_->mapToScene({0, 0}),
        item_->mapToScene({item_->width(), 0}), item_->mapToScene({0, item_->height()})};
    const qreal dpr = window_ ? window_->devicePixelRatio() : 0;
    if (geometry != geometry_ || dpr != dpr_) {
        geometry_ = geometry;
        dpr_ = dpr;
        invalidate();
    }
}

bool RainInput::eventFilter(QObject *watched, QEvent *event)
{
    if (watched != window_) return false;
    switch (event->type()) {
    case QEvent::MouseMove: {
        refreshGeometry();
        auto *mouse = static_cast<QMouseEvent *>(event);
        // Only the explicit locker host may observe its own window while locked.
        if (!enabled_ || (locked_ && !lockScreenHost_) || !item_->isVisible() || !item_->isEnabled()
            || !window_->isVisible()) {
            invalidate();
            break;
        }
        const auto p = item_->mapFromScene(mouse->position());
        if (!std::isfinite(p.x()) || !std::isfinite(p.y()) || !item_->contains(p)) {
            invalidate();
            break;
        }
        if (mouse->buttons() != Qt::NoButton) {
            invalidateHover();
            break;
        }
        pointer_ = {{p.x(), p.y()}, true, pointer_.sequence + 1, clock_.nsecsElapsed() / 1e9};
        break;
    }
    case QEvent::MouseButtonPress: {
        refreshGeometry();
        invalidateHover();
        auto *mouse = static_cast<QMouseEvent *>(event);
        // At the window filter Qt sends both the second press and an extra DblClick.
        // Count presses only, while leaving both notifications available to the desktop.
        if (!enabled_ || locked_ || lockScreenHost_ || !item_->isVisible() || !item_->isEnabled()
            || !window_->isVisible() || mouse->button() != Qt::LeftButton
            || mouse->buttons() != Qt::LeftButton || mouse->modifiers() != Qt::NoModifier)
            break;
        const auto p = item_->mapFromScene(mouse->position());
        if (!std::isfinite(p.x()) || !std::isfinite(p.y()) || !item_->contains(p)) {
            invalidate();
            break;
        }
        if (splashes_.size() < 32) splashes_.push_back({p.x(), p.y()});
        break;
    }
    case QEvent::MouseButtonRelease:
        invalidateHover(); // A release between frames must not erase the preceding splash.
        break;
    case QEvent::Leave:
    case QEvent::Hide:
    case QEvent::Close:
    case QEvent::WindowDeactivate:
    case QEvent::UngrabMouse:
    case QEvent::TouchCancel:
    case QEvent::DevicePixelRatioChange:
        invalidate();
        break;
    default:
        break;
    }
    return false;
}

} // namespace arasaka::rain
