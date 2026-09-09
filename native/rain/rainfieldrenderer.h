// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include "dropletsimulation.h"
#include <QOpenGLFramebufferObject>
#include <QOpenGLShaderProgram>
#include <QSizeF>
#include <array>
#include <memory>

namespace arasaka::rain {

// Render-thread owned. All methods and destruction require the owning GL context.
// RGBA16F: cap height, decaying trail height (logical px), wetness [0,1], reserved 0.
// Texture UV has the OpenGL bottom-left origin; simulation coordinates are top-left.
class RainFieldRenderer {
public:
    ~RainFieldRenderer();
    bool initialize(QSizeF logicalSize, QString *error);
    bool resize(QSizeF logicalSize, QString *error);
    bool render(const std::vector<Drop> &drops, double activeSeconds);
    GLuint texture() const { return surfaces_[front_] ? surfaces_[front_]->texture() : 0; }
    QSize pixelSize() const { return surfaces_[front_] ? surfaces_[front_]->size() : QSize(); }
    QSizeF logicalSize() const { return logicalSize_; }

private:
    std::array<std::unique_ptr<QOpenGLFramebufferObject>, 2> surfaces_;
    std::unique_ptr<QOpenGLShaderProgram> caps_, history_;
    QSizeF logicalSize_;
    GLuint vao_ = 0, vbo_ = 0;
    int front_ = 0;
    bool hasFrame_ = false;
};

} // namespace arasaka::rain
