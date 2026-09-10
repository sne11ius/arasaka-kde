// SPDX-License-Identifier: GPL-3.0-or-later
#include "rainfieldrenderer.h"
#include <QOpenGLContext>
#include <QOpenGLExtraFunctions>
#include <QVector2D>
#include <algorithm>
#include <cmath>

namespace arasaka::rain {

RainFieldRenderer::~RainFieldRenderer()
{
    if (auto *context = QOpenGLContext::currentContext()) {
        auto *f = context->extraFunctions();
        if (vao_) f->glDeleteVertexArrays(1, &vao_);
        if (vbo_) f->glDeleteBuffers(1, &vbo_);
        if (mergeVao_) f->glDeleteVertexArrays(1, &mergeVao_);
        if (mergeVbo_) f->glDeleteBuffers(1, &mergeVbo_);
    }
}

bool RainFieldRenderer::initialize(QSizeF size, QString *error)
{
    auto caps = std::make_unique<QOpenGLShaderProgram>();
    auto history = std::make_unique<QOpenGLShaderProgram>();
    auto coalescence = std::make_unique<QOpenGLShaderProgram>();
    static_assert(DropSurface::maximumLobes == 4); // GLSL attribute layout below.
    const char *capVertex = R"(
#version 330 core
layout(location=0) in vec2 position;
layout(location=1) in vec4 endpoints;
layout(location=2) in vec3 profile;
layout(location=3) in vec4 deformation;
uniform vec2 logicalSize;
out vec2 point;
flat out vec4 segment;
flat out vec3 shape;
flat out vec4 ellipse;
void main() {
    point = position;
    segment = endpoints;
    shape = profile;
    ellipse = deformation;
    gl_Position = vec4(position / logicalSize * vec2(2.,-2.) + vec2(-1.,1.), 0., 1.);
})";
    // Both isolated caps and retained merge lobes use the same footprint AND height.
    // Screen Y points down. Widen the lower body; independently thin and soften the upper film.
    const QByteArray capProfile = R"(
vec2 capProfile(vec2 delta, float r, float h, vec4 ellipse) {
    float reach = r * length(vec2(ellipse.y * ellipse.z, ellipse.x / ellipse.z));
    float y = clamp(delta.y / reach, -1., 1.);
    float bulb = y * (1.5 - .5*y*y);
    float flow = ellipse.w;
    // Odd transverse scaling preserves footprint area; keep the CPU hit-test inverse in sync.
    delta.x /= 1. + .3*flow*bulb;
    float distance = length(vec2(dot(delta, ellipse.xy) / ellipse.z,
                                dot(delta, vec2(-ellipse.y, ellipse.x)) * ellipse.z));
    float sphere = (r*r + h*h) / (2.*h);
    float cap = sqrt(max(0., sphere*sphere - distance*distance)) - (sphere-h);
    if (distance > r) cap = -(distance-r) * r / max(sphere-h, .00001);
    float upper = 1. - smoothstep(-.5, 0., y);
    // Squaring the upper height eases its contact angle into the glass. The signed
    // quadratic continuation stays negative outside, so unions cannot create ghost sheets.
    cap *= 1. - flow*upper*(1. - abs(cap)/h);
    cap *= 1. + .6*flow*bulb;
    // Integral over the rest cap h/r=.6, including the width Jacobian. With s=z/h,
    // u=upper, g=bulb: integrate s*(1+.3*f*g)*(1+.6*f*g)*(1-f*u*(1-s)).
    // Odd terms vanish; the remaining cubic is independent of radius and ellipse orientation.
    // Trails have flow=0 and retain their original shallow spherical profile.
    float volumeScale = 1. + flow*(-.1103962 + flow*(.1260102 - flow*.0110236));
    return vec2(cap / volumeScale, distance);
}
)";
    const QByteArray capFragment = QByteArray(R"(
#version 330 core
in vec2 point;
flat in vec4 segment;
flat in vec3 shape;
flat in vec4 ellipse;
out vec4 field;
)") + capProfile + R"(
void main() {
    vec2 d = segment.zw - segment.xy;
    float t = clamp(dot(point - segment.xy, d) / max(dot(d,d), 0.0001), 0., 1.);
    vec2 offset = point - mix(segment.xy, segment.zw, t);
    float r = shape.x, h = shape.y;
    vec2 cap = capProfile(offset, r, h, ellipse);
    float z = max(0., cap.x);
    float wet = 1. - smoothstep(r*.65, r, cap.y);
    field = shape.z < .5 ? vec4(z, 0., wet, 0.) : vec4(0., z, wet*.7, 0.);
})";
    const char *historyVertex = R"(
#version 330 core
out vec2 uv;
void main() {
    uv = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2);
    gl_Position = vec4(uv*2.-1., 0., 1.);
})";
    const char *mergeVertex = R"(
#version 330 core
layout(location=0) in vec2 position;
layout(location=1) in vec2 parameters;
layout(location=2) in vec4 lobe0;
layout(location=3) in vec4 lobe1;
layout(location=4) in vec4 lobe2;
layout(location=5) in vec4 lobe3;
layout(location=6) in vec4 axis0;
layout(location=7) in vec4 axis1;
layout(location=8) in vec4 axis2;
layout(location=9) in vec4 axis3;
layout(location=10) in vec3 join0;
layout(location=11) in vec3 join1;
layout(location=12) in vec3 join2;
uniform vec2 logicalSize;
out vec2 point;
flat out vec2 params;
flat out vec4 lobes[4];
flat out vec4 axes[4];
flat out vec3 joins[3];
void main() {
    point = position; params = parameters;
    lobes[0] = lobe0; lobes[1] = lobe1; lobes[2] = lobe2; lobes[3] = lobe3;
    axes[0] = axis0; axes[1] = axis1; axes[2] = axis2; axes[3] = axis3;
    joins[0] = join0; joins[1] = join1; joins[2] = join2;
    gl_Position = vec4(position / logicalSize * vec2(2.,-2.) + vec2(-1.,1.), 0., 1.);
})";
    const QByteArray mergeFragment = QByteArray(R"(
#version 330 core
in vec2 point;
flat in vec2 params;
flat in vec4 lobes[4];
flat in vec4 axes[4];
flat in vec3 joins[3];
out vec4 field;
)") + capProfile + R"(
void main() {
    float heights[7];
    float peak = 0.;
    for (int i = 0; i < int(params.x); ++i) {
        vec2 delta = point - lobes[i].xy;
        float r = lobes[i].z, h = lobes[i].w;
        heights[i] = capProfile(delta, r, h, axes[i]).x;
        peak = max(peak, h);
    }
    for (int i = 0; i < int(params.x)-1; ++i) {
        float a = heights[int(joins[i].x)], b = heights[int(joins[i].y)];
        float k = max(joins[i].z, .00001);
        float blend = max(k - abs(a-b), 0.) / k;
        heights[4+i] = max(a,b) + blend*blend*k*.25;
    }
    float height = max(0., heights[4+int(params.x)-2]);
    field = vec4(height, 0., smoothstep(0., max(.1, peak*.12), height), 0.);
})";
    const char *historyFragment = R"(
#version 330 core
in vec2 uv;
uniform sampler2D previousField;
uniform vec2 decay;
out vec4 field;
void main() {
    vec2 trail = texture(previousField, uv).gb * decay;
    field = vec4(0., trail, 0.);
})";
    if (!caps->addShaderFromSourceCode(QOpenGLShader::Vertex, capVertex)
        || !caps->addShaderFromSourceCode(QOpenGLShader::Fragment, capFragment)
        || !caps->link()) {
        if (error) *error = caps->log();
        return false;
    }
    if (!history->addShaderFromSourceCode(QOpenGLShader::Vertex, historyVertex)
        || !history->addShaderFromSourceCode(QOpenGLShader::Fragment, historyFragment)
        || !history->link()) {
        if (error) *error = history->log();
        return false;
    }
    if (!coalescence->addShaderFromSourceCode(QOpenGLShader::Vertex, mergeVertex)
        || !coalescence->addShaderFromSourceCode(QOpenGLShader::Fragment, mergeFragment)
        || !coalescence->link()) {
        if (error) *error = coalescence->log();
        return false;
    }
    auto *f = QOpenGLContext::currentContext()->extraFunctions();
    if (!vao_) f->glGenVertexArrays(1, &vao_);
    if (!vbo_) f->glGenBuffers(1, &vbo_);
    f->glBindVertexArray(vao_);
    f->glBindBuffer(GL_ARRAY_BUFFER, vbo_);
    // Ordinary caps plus up to four independently moving lobe trails per physical body.
    f->glBufferData(GL_ARRAY_BUFFER, DropletSimulation::maximumPopulation * 30 * 13 * sizeof(float), nullptr, GL_DYNAMIC_DRAW);
    for (int i = 0; i < 4; ++i) f->glEnableVertexAttribArray(i);
    f->glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 13 * sizeof(float), nullptr);
    f->glVertexAttribPointer(1, 4, GL_FLOAT, GL_FALSE, 13 * sizeof(float), reinterpret_cast<void *>(2 * sizeof(float)));
    f->glVertexAttribPointer(2, 3, GL_FLOAT, GL_FALSE, 13 * sizeof(float), reinterpret_cast<void *>(6 * sizeof(float)));
    f->glVertexAttribPointer(3, 4, GL_FLOAT, GL_FALSE, 13 * sizeof(float), reinterpret_cast<void *>(9 * sizeof(float)));
    if (!mergeVao_) f->glGenVertexArrays(1, &mergeVao_);
    if (!mergeVbo_) f->glGenBuffers(1, &mergeVbo_);
    f->glBindVertexArray(mergeVao_);
    f->glBindBuffer(GL_ARRAY_BUFFER, mergeVbo_);
    f->glBufferData(GL_ARRAY_BUFFER, DropletSimulation::maximumPopulation * 6 * 45 * sizeof(float), nullptr, GL_DYNAMIC_DRAW);
    for (int i = 0; i < 13; ++i) f->glEnableVertexAttribArray(i);
    f->glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 45 * sizeof(float), nullptr);
    f->glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, 45 * sizeof(float), reinterpret_cast<void *>(2 * sizeof(float)));
    for (int i = 0; i < 4; ++i) {
        f->glVertexAttribPointer(2 + i, 4, GL_FLOAT, GL_FALSE, 45 * sizeof(float), reinterpret_cast<void *>((4 + i * 4) * sizeof(float)));
        f->glVertexAttribPointer(6 + i, 4, GL_FLOAT, GL_FALSE, 45 * sizeof(float), reinterpret_cast<void *>((20 + i * 4) * sizeof(float)));
    }
    for (int i = 0; i < 3; ++i)
        f->glVertexAttribPointer(10 + i, 3, GL_FLOAT, GL_FALSE, 45 * sizeof(float), reinterpret_cast<void *>((36 + i * 3) * sizeof(float)));
    f->glBindVertexArray(0);
    if (!vao_ || !vbo_ || !mergeVao_ || !mergeVbo_ || f->glGetError() != GL_NO_ERROR) {
        if (error) *error = QStringLiteral("Rain geometry allocation failed");
        return false;
    }
    if (!resize(size, error)) return false;
    caps_ = std::move(caps);
    history_ = std::move(history);
    coalescence_ = std::move(coalescence);
    return true;
}

bool RainFieldRenderer::resize(QSizeF size, QString *error)
{
    if (!std::isfinite(size.width()) || !std::isfinite(size.height())
        || size.width() <= 0 || size.height() <= 0
        || size.width() > 1e6 || size.height() > 1e6) {
        if (error) *error = QStringLiteral("Invalid rain logical size");
        return false;
    }
    if (size == logicalSize_) return true;
    auto *f = QOpenGLContext::currentContext()->extraFunctions();
    GLint maxSize = 0;
    f->glGetIntegerv(GL_MAX_TEXTURE_SIZE, &maxSize);
    const double scale = std::min({1., 1080. / size.height(),
                                  std::min(4096, maxSize) / size.width(), maxSize / size.height()});
    const QSize pixels(std::max(1, qRound(size.width() * scale)), std::max(1, qRound(size.height() * scale)));
    std::array<std::unique_ptr<QOpenGLFramebufferObject>, 2> candidate;
    f->glDisable(GL_SCISSOR_TEST);
    f->glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
    f->glActiveTexture(GL_TEXTURE4);
    for (auto &surface : candidate) {
        surface = std::make_unique<QOpenGLFramebufferObject>(pixels, QOpenGLFramebufferObject::NoAttachment, GL_TEXTURE_2D, GL_RGBA16F);
        if (!surface->isValid()) {
            if (error) *error = QStringLiteral("Rain RGBA16F framebuffer allocation failed");
            return false;
        }
        surface->bind();
        f->glViewport(0, 0, pixels.width(), pixels.height());
        f->glClearColor(0, 0, 0, 0);
        f->glClear(GL_COLOR_BUFFER_BIT);
        f->glBindTexture(GL_TEXTURE_2D, surface->texture());
        f->glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
        f->glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
        f->glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
        f->glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
    }
    f->glBindTexture(GL_TEXTURE_2D, 0);
    if (f->glGetError() != GL_NO_ERROR) {
        if (error) *error = QStringLiteral("Rain framebuffer initialization failed");
        return false;
    }
    surfaces_ = std::move(candidate);
    logicalSize_ = size;
    front_ = 0;
    hasFrame_ = false;
    return true;
}

bool RainFieldRenderer::render(const std::vector<Drop> &drops, double seconds)
{
    if (!caps_ || !history_ || !coalescence_ || !texture()) return false;
    const double dt = std::isfinite(seconds) ? std::clamp(seconds, 0., DropletSimulation::maximumFrameSeconds) : 0.;
    if (hasFrame_ && dt == 0) return true;
    auto *f = QOpenGLContext::currentContext()->extraFunctions();
    f->glDisable(GL_BLEND);
    f->glDisable(GL_DEPTH_TEST);
    f->glDepthMask(GL_FALSE);
    f->glDisable(GL_STENCIL_TEST);
    f->glDisable(GL_SCISSOR_TEST);
    f->glDisable(GL_CULL_FACE);
    f->glDisable(GL_RASTERIZER_DISCARD);
    f->glDisable(GL_FRAMEBUFFER_SRGB);
    f->glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
    const int back = 1 - front_;
    surfaces_[back]->bind();
    const auto size = pixelSize();
    f->glViewport(0, 0, size.width(), size.height());
    f->glBindVertexArray(vao_);
    history_->bind();
    history_->setUniformValue("previousField", 4);
    history_->setUniformValue("decay", QVector2D(std::exp(-dt / 1.5), std::exp(-dt / 4.)));
    f->glActiveTexture(GL_TEXTURE4);
    f->glBindTexture(GL_TEXTURE_2D, texture());
    f->glDrawArrays(GL_TRIANGLES, 0, 3);
    f->glBindTexture(GL_TEXTURE_2D, 0);

    std::vector<float> vertices;
    std::vector<float> mergeVertices;
    vertices.reserve(std::min(drops.size(), DropletSimulation::maximumPopulation) * 12 * 13);
    auto quad = [&](Vec2 start, Vec2 end, const SurfaceLobe &lobe, double h, float trail) {
        const auto extent = lobe.halfExtent();
        const double left = std::min(start.x, end.x) - extent.x, right = std::max(start.x, end.x) + extent.x;
        const double top = std::min(start.y, end.y) - extent.y, bottom = std::max(start.y, end.y) + extent.y;
        for (Vec2 p : {Vec2{left, top}, Vec2{left, bottom}, Vec2{right, bottom},
                       Vec2{left, top}, Vec2{right, bottom}, Vec2{right, top}}) {
            for (double value : {p.x, p.y, start.x, start.y, end.x, end.y, lobe.radius, h, double(trail),
                                 lobe.axis.x, lobe.axis.y, lobe.stretch, lobe.flow})
                vertices.push_back(float(value));
        }
    };
    for (std::size_t i = 0; i < std::min(drops.size(), DropletSimulation::maximumPopulation); ++i) {
        const auto &drop = drops[i];
        const auto shape = drop.surface();
        const double margin = shape.margin();
        std::array<float, 43> payload{};
        payload[0] = float(shape.count); payload[1] = float(shape.smoothing);
        double left = 1e20, right = -1e20, top = 1e20, bottom = -1e20;
        for (std::size_t j = 0; j < shape.count; ++j) {
            const auto &lobe = shape.lobes[j];
            const Vec2 p{drop.position.x + lobe.offset.x, drop.position.y + lobe.offset.y};
            const double h = .6 * lobe.radius;
            if (shape.count == 1) {
                quad(p, p, lobe, h, 0);
            } else {
                const auto extent = lobe.halfExtent();
                left = std::min(left, p.x - extent.x - margin); right = std::max(right, p.x + extent.x + margin);
                top = std::min(top, p.y - extent.y - margin); bottom = std::max(bottom, p.y + extent.y + margin);
                payload[2 + j*4] = float(p.x); payload[3 + j*4] = float(p.y);
                payload[4 + j*4] = float(lobe.radius); payload[5 + j*4] = float(h);
                payload[18 + j*4] = float(lobe.axis.x); payload[19 + j*4] = float(lobe.axis.y);
                payload[20 + j*4] = float(lobe.stretch); payload[21 + j*4] = float(lobe.flow);
            }
            // Shape contraction leaves wetness through history, not fictitious solid trails.
            if (dt > 0 && drop.previousPosition != drop.position) {
                const Vec2 start{drop.previousPosition.x + lobe.offset.x, drop.previousPosition.y + lobe.offset.y};
                quad(start, p, {{}, lobe.radius * .4}, h * .12, 1);
            }
        }
        if (shape.count > 1) {
            for (std::size_t j = 0; j + 1 < shape.count; ++j) {
                payload[34 + j*3] = float(shape.joins[j].left);
                payload[35 + j*3] = float(shape.joins[j].right);
                payload[36 + j*3] = float(shape.joins[j].smoothing);
            }
            for (const Vec2 p : {Vec2{left, top}, Vec2{left, bottom}, Vec2{right, bottom},
                                Vec2{left, top}, Vec2{right, bottom}, Vec2{right, top}}) {
                mergeVertices.push_back(float(p.x)); mergeVertices.push_back(float(p.y));
                mergeVertices.insert(mergeVertices.end(), payload.begin(), payload.end());
            }
        }
    }
    caps_->bind();
    caps_->setUniformValue("logicalSize", QVector2D(logicalSize_.width(), logicalSize_.height()));
    f->glBindBuffer(GL_ARRAY_BUFFER, vbo_);
    f->glBufferSubData(GL_ARRAY_BUFFER, 0, vertices.size() * sizeof(float), vertices.data());
    f->glEnable(GL_BLEND);
    f->glBlendEquation(GL_MAX);
    f->glBlendFunc(GL_ONE, GL_ONE);
    f->glDrawArrays(GL_TRIANGLES, 0, int(vertices.size() / 13));
    if (!mergeVertices.empty()) {
        // All merging bodies share one draw call; a dense splash never creates per-drop GL calls.
        coalescence_->bind();
        coalescence_->setUniformValue("logicalSize", QVector2D(logicalSize_.width(), logicalSize_.height()));
        f->glBindVertexArray(mergeVao_);
        f->glBindBuffer(GL_ARRAY_BUFFER, mergeVbo_);
        f->glBufferSubData(GL_ARRAY_BUFFER, 0, mergeVertices.size() * sizeof(float), mergeVertices.data());
        f->glDrawArrays(GL_TRIANGLES, 0, int(mergeVertices.size() / 45));
        coalescence_->release();
    }
    f->glDisable(GL_BLEND);
    f->glBlendEquation(GL_FUNC_ADD);
    f->glBindVertexArray(0);
    caps_->release();
    if (f->glGetError() != GL_NO_ERROR) return false;
    front_ = back;
    hasFrame_ = true;
    return true;
}

} // namespace arasaka::rain
