// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include <algorithm>
#include <cmath>

namespace arasaka::rain {

// Per-display, critically damped illumination. Time is unscaled monotonic host
// time, including intervals without rendering, rather than rain simulation time.
class WindowIllumination {
public:
    double value() const { return m_value; }
    double minimum() const { return m_minimum; }
    double seconds() const { return m_seconds; }
    void setWindowCount(int count) { m_count = std::max(0, count); }
    void setMinimum(double value) {
        if (std::isfinite(value)) m_minimum = std::clamp(value, .01, 1.);
    }
    void setSeconds(double value) {
        if (std::isfinite(value)) m_seconds = std::clamp(value, .1, 3600.);
    }

    double advance(double elapsed) {
        if (!std::isfinite(elapsed) || elapsed <= 0) return m_value;
        const double target = m_minimum + (1. - m_minimum) * -std::expm1(-m_count / 3.);
        // Two cascaded first-order filters: 95% settled at 4.744 time constants.
        // Their exact solution is cadence-independent and has no step in value
        // or slope on retargeting. A one-second window produces <1.5% excursion.
        const double t = 4.743864518 * elapsed / m_seconds;
        const double decay = std::exp(-t);
        m_value = target + ((m_value - target) + (m_filtered - target) * t) * decay;
        m_filtered = target + (m_filtered - target) * decay;
        return m_value;
    }

private:
    int m_count = 0;
    double m_minimum = .15;
    double m_seconds = 30.;
    double m_filtered = .15;
    double m_value = .15;
};

} // namespace arasaka::rain
