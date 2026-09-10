// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once

#include <QCoreApplication>
#include <QDBusConnection>
#include <QDBusMessage>
#include <QMouseEvent>
#include <QQuickWindow>
#include <QScreen>
#include <cmath>

namespace arasaka::login {

// PLM's existing session bus joins its top-layer greeter to its background process.
// Only screen identity and normalized, screen-local pointer activity cross it.
// 0 = cancel, 1 = hover, 2 = left press, 3 = release/other button, 4 = held move.
inline void forwardPointer(QQuickWindow *window, QEvent *event)
{
    if (!window || !window->screen()) return;
    int action = 0;
    double x = 0, y = 0;
    switch (event->type()) {
    case QEvent::MouseMove:
    case QEvent::MouseButtonPress:
    case QEvent::MouseButtonRelease: {
        const auto *mouse = static_cast<QMouseEvent *>(event);
        if (window->isVisible() && window->width() > 0 && window->height() > 0) {
            x = mouse->position().x() / window->width();
            y = mouse->position().y() / window->height();
            if (std::isfinite(x) && std::isfinite(y) && x >= 0 && x < 1 && y >= 0 && y < 1) {
                action = 3;
                if (event->type() == QEvent::MouseMove)
                    action = mouse->buttons() == Qt::NoButton ? 1 : 4;
                else if (event->type() == QEvent::MouseButtonPress && mouse->button() == Qt::LeftButton
                         && mouse->buttons() == Qt::LeftButton && mouse->modifiers() == Qt::NoModifier)
                    action = 2;
            }
        }
        break;
    }
    case QEvent::Leave:
    case QEvent::Hide:
    case QEvent::Close:
    case QEvent::WindowDeactivate:
    case QEvent::UngrabMouse:
    case QEvent::TouchCancel:
    case QEvent::Resize:
    case QEvent::DevicePixelRatioChange:
        break;
    default:
        return; // No keyboard, focus, password, global cursor or duplicate double-click data.
    }
    if (!action) x = y = 0;
    auto message = QDBusMessage::createMethodCall(QStringLiteral("org.kde.plasma.wallpaper"),
        QStringLiteral("/Wallpaper"), QStringLiteral("org.kde.plasma.wallpaper"), QStringLiteral("rainPointer"));
    message.setAutoStartService(false);
    message << window->screen()->name() << action << x << y;
    QDBusConnection::sessionBus().call(message, QDBus::NoBlock);
}

inline void deliverPointer(QQuickWindow *window, const QString &screen, int action, double x, double y)
{
    if (!window || !window->screen() || window->screen()->name() != screen) return;
    if (action < 0 || action > 4 || !std::isfinite(x) || !std::isfinite(y)
        || x < 0 || x >= 1 || y < 0 || y >= 1) return;
    if (!action || !window->isVisible()) {
        QEvent cancel(QEvent::Leave);
        QCoreApplication::sendEvent(window, &cancel);
        return;
    }
    const QPointF point(x * window->width(), y * window->height());
    const auto type = action == 2 ? QEvent::MouseButtonPress : action == 3 ? QEvent::MouseButtonRelease : QEvent::MouseMove;
    const auto button = action == 2 || action == 3 ? Qt::LeftButton : Qt::NoButton;
    const auto buttons = action == 2 || action == 4 ? Qt::LeftButton : Qt::NoButton;
    QMouseEvent event(type, point, point, button, buttons, Qt::NoModifier);
    // The same passive RainInput observes this window. No focus or input grab is changed.
    QCoreApplication::sendEvent(window, &event);
}

} // namespace arasaka::login
