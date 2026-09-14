// SPDX-License-Identifier: GPL-3.0-or-later
#include "windowillumination.h"

#include <cmath>
#include <cstdlib>
#include <iostream>

using arasaka::rain::WindowIllumination;

static void check(bool condition, const char *message)
{
    if (!condition) {
        std::cerr << message << '\n';
        std::exit(1);
    }
}

int main()
{
    // Wrong curve, immediate changes, and cross-instance state all break these checks.
    WindowIllumination empty;
    check(std::abs(empty.advance(60) - .15) < 1e-9, "Empty display must stay dim");
    for (const auto [count, expected] : {std::pair{1, .391}, {2, .564}, {4, .776}, {8, .941}}) {
        WindowIllumination screen;
        screen.setWindowCount(count);
        check(screen.value() == .15, "New target must not change illumination instantly");
        const double settled = screen.advance(30);
        check(settled > .15 + (expected - .15) * .94
              && settled < .15 + (expected - .15) * .96, "Should settle 95% in 30 real seconds");
        check(std::abs(screen.advance(90) - expected) < .001, "Window count must determine brightness");
        screen.setWindowCount(0);
        check(screen.advance(30) < .15 + (expected - .15) * .06, "Dimming must also settle in 30 seconds");
    }
    check(empty.value() == .15, "Other displays must adapt independently");

    WindowIllumination pulse;
    pulse.setWindowCount(1);
    check(pulse.advance(1) < .154, "A briefly opened window must barely brighten the screen");
    pulse.setWindowCount(0);
    for (int i = 0; i < 600; ++i)
        check(pulse.advance(.1) < .165, "Brief windows must not produce a delayed visible flash");
    check(pulse.value() < .1501, "Brief changes must decay back to the empty baseline");

    WindowIllumination coarse, fine;
    coarse.setWindowCount(4);
    fine.setWindowCount(4);
    coarse.advance(12);
    for (int i = 0; i < 720; ++i) fine.advance(1. / 60.);
    check(std::abs(coarse.value() - fine.value()) < 1e-9, "Frame rate and hidden rendering must not alter adaptation");
    coarse.setWindowCount(1);
    fine.setWindowCount(1);
    coarse.advance(18);
    for (int i = 0; i < 18; ++i) fine.advance(1);
    check(std::abs(coarse.value() - fine.value()) < 1e-9, "Retargeting must preserve the continuous filter state");
    const double before = coarse.value();
    check(coarse.advance(-1) == before, "Invalid time must not reverse adaptation");
    coarse.setWindowCount(1000000);
    check(coarse.advance(300) <= 1., "Crowded displays must never exceed the brightness ceiling");
    coarse.setWindowCount(-1);
    check(std::abs(coarse.advance(300) - .15) < 1e-9, "Invalid counts must behave as empty displays");
    std::cout << "Window illumination checks passed\n";
}
