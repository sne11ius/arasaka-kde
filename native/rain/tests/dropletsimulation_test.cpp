#include "dropletsimulation.h"

#include <algorithm>
#include <cfenv>
#include <cmath>
#include <functional>
#include <iostream>
#include <limits>
#include <numbers>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace arasaka::rain {

struct DropletSimulationTestAccess {
    static void setDrops(DropletSimulation &simulation, std::vector<Drop> drops, std::size_t population = 0)
    {
        simulation.reset(2000, 2000, 1, population);
        // Isolated force/collision fixtures use base physical units, not viewport calibration.
        simulation.lengthScale_ = 1;
        simulation.drops_ = std::move(drops);
        for (const auto &drop : simulation.drops_)
            simulation.nextId_ = std::max(simulation.nextId_, drop.id + 1);
    }

    static void collide(DropletSimulation &simulation, const std::vector<Vec2> &starts)
    {
        simulation.mergeCollisions(starts);
    }

    static void replaceDrops(DropletSimulation &simulation, std::vector<Drop> drops)
    {
        simulation.drops_ = std::move(drops);
    }

    static void splash(DropletSimulation &simulation, Vec2 position)
    {
        simulation.splash(position);
    }
};

} // namespace arasaka::rain

using namespace arasaka::rain;

namespace {

void require(bool condition, const std::string &message)
{
    if (!condition)
        throw std::runtime_error(message);
}

void near(double actual, double expected, const std::string &message, double tolerance = 1e-9)
{
    require(std::isfinite(actual) && std::abs(actual - expected) <= tolerance,
            message + ": expected " + std::to_string(expected) + ", got " + std::to_string(actual));
}

Drop drop(std::uint64_t id, Vec2 position, double radius, Vec2 velocity = {})
{
    return {id, position, position, velocity, radius * radius * radius};
}

void samePhysicalState(const DropletSimulation &a, const DropletSimulation &b)
{
    require(a.drops().size() == b.drops().size(), "population differs");
    for (std::size_t i = 0; i < a.drops().size(); ++i) {
        const auto &x = a.drops()[i];
        const auto &y = b.drops()[i];
        require(x.id == y.id, "identity differs");
        near(x.position.x, y.position.x, "x differs");
        near(x.position.y, y.position.y, "y differs");
        near(x.velocity.x, y.velocity.x, "vx differs");
        near(x.velocity.y, y.velocity.y, "vy differs");
        near(x.volume, y.volume, "volume differs");
    }
}

void splashConservesWaterAndInheritedMomentum()
{
    DropletSimulation simulation;
    DropletSimulationTestAccess::setDrops(simulation, {drop(1, {500, 500}, 12, {35, 20})});
    DropletSimulationTestAccess::splash(simulation, {500, 500});
    require(simulation.drops().size() >= 3 && simulation.drops().size() <= 8,
            "a clicked large drop must become several physical droplets");
    double volume = 0, px = 0, py = 0, cx = 0, cy = 0;
    bool left = false, right = false, up = false, down = false;
    double smallest = 1728, largest = 0;
    for (const auto &d : simulation.drops()) {
        require(d.id > 1 && d.volume > 0 && d.volume < 1728, "fragments have fresh identities and less water");
        require(d.previousPosition == d.position, "fragment birth must not invent a swept collision/trail from the parent");
        const Vec2 offset{d.position.x - 500, d.position.y - 500};
        const Vec2 kick{d.velocity.x - 35, d.velocity.y - 20};
        require(offset.x * kick.x + offset.y * kick.y > 0, "every fragment initially travels outward");
        left |= kick.x < -30; right |= kick.x > 30; up |= kick.y < -30; down |= kick.y > 30;
        volume += d.volume;
        px += d.volume * d.velocity.x; py += d.volume * d.velocity.y;
        cx += d.volume * d.position.x; cy += d.volume * d.position.y;
        smallest = std::min(smallest, d.volume); largest = std::max(largest, d.volume);
        for (const auto &other : simulation.drops()) {
            if (d.id != other.id)
                require(std::hypot(d.position.x - other.position.x, d.position.y - other.position.y)
                            > d.radius() + other.radius(), "siblings must start separated");
        }
    }
    near(volume, 1728, "splitting conserves water");
    near(px, 60480, "symmetric burst preserves inherited x momentum", 1e-7);
    near(py, 34560, "symmetric burst preserves inherited y momentum", 1e-7);
    near(cx / volume, 500, "burst center of mass x");
    near(cy / volume, 500, "burst center of mass y");
    require(left && right && up && down, "splash spreads in every direction");
    require(largest > smallest * 1.05, "fragment sizes have organic variation");
    for (int i = 0; i < 3; ++i) simulation.advance(1.0 / 30);
    require(simulation.drops().size() >= 3, "isolated splash must survive long enough to be visible");
    require(std::all_of(simulation.drops().begin(), simulation.drops().end(), [](const auto &d) {
        return std::hypot(d.position.x - 500, d.position.y - 500) > 25;
    }), "fragments visibly spread across several 30 FPS frames");
}

void splashTargetsOneNearbyDropAndMergesOnImpact()
{
    DropletSimulation simulation;
    DropletSimulationTestAccess::setDrops(simulation, {drop(1, {500, 500}, 8), drop(2, {560, 500}, 8)});
    auto unchanged = simulation;
    DropletSimulationTestAccess::splash(simulation, {800, 800});
    samePhysicalState(simulation, unchanged);
    DropletSimulationTestAccess::splash(simulation, {500, 518}); // Near the rim, not a pixel-perfect hit.
    require(simulation.drops().size() > 2, "fingertip margin must admit a near miss");
    require(std::count_if(simulation.drops().begin(), simulation.drops().end(), [](const auto &d) {
        return d.id == 2 && d.volume == 512 && d.position == Vec2{560, 500};
    }) == 1, "only the closest eligible drop splits");

    // Place a real splash fragment just before a smaller resting target in its path.
    auto fragment = simulation.drops().back();
    fragment.position = fragment.previousPosition = {800, 800};
    fragment.velocity = {300, 0};
    auto target = drop(100, {800 + fragment.radius() + 2.5, 800}, 2);
    DropletSimulationTestAccess::setDrops(simulation, {fragment, target});
    simulation.advance(DropletSimulation::fixedStep);
    require(simulation.drops().size() == 1, "fragment impact merges rather than shattering its target");
    near(simulation.drops()[0].volume, fragment.volume + 8, "impact retains both drops' water");
    require(simulation.drops()[0].velocity.x > 100, "the merged target receives the fragment's momentum");
}

void splashQueueUsesActiveTicksAndCancels()
{
    DropletSimulation initial;
    DropletSimulationTestAccess::setDrops(initial, {drop(1, {500, 500}, 8), drop(2, {900, 900}, 8)});
    auto simulation = initial;
    simulation.queueSplash({500, 500});
    simulation.advance(0);
    samePhysicalState(simulation, initial);
    simulation.advance(DropletSimulation::fixedStep / 2);
    samePhysicalState(simulation, initial);
    simulation.advance(DropletSimulation::fixedStep / 2);
    require(simulation.drops().size() > 2, "click survives a fractional frame until the first active tick");
    auto control = simulation;
    simulation.advance(1.0 / 30);
    control.advance(1.0 / 30);
    samePhysicalState(simulation, control);
    const auto count = simulation.drops().size();
    for (int i = 0; i < 5; ++i) simulation.advance(1.0 / 30);
    require(simulation.drops().size() <= count, "a queued press must not repeat on later frames");

    simulation = initial;
    simulation.queueSplash({500, 500});
    simulation.queueSplash({900, 900});
    simulation.invalidatePointer(); // Release/hover cancellation is independent of accepted clicks.
    simulation.advance(1.0 / 30);
    require(std::none_of(simulation.drops().begin(), simulation.drops().end(), [](const auto &d) {
        return d.id == 1 || d.id == 2;
    }), "two fast clicks survive hover invalidation and are both consumed");

    for (int cancellation = 0; cancellation < 3; ++cancellation) {
        simulation = initial;
        simulation.queueSplash({500, 500});
        if (cancellation == 0) simulation.cancelSplashes();
        if (cancellation == 1) simulation.resize(2100, 2000);
        if (cancellation == 2) simulation.reset(2000, 2000, 1, 0);
        control = initial;
        if (cancellation == 1) control.resize(2100, 2000);
        if (cancellation == 2) control.reset(2000, 2000, 1, 0);
        simulation.advance(1.0 / 30);
        control.advance(1.0 / 30);
        samePhysicalState(simulation, control);
    }
}

void splashRespectsCapacityEdgesAndInvalidInput()
{
    for (const std::size_t count : {1022, 1023, 1024}) {
        std::vector<Drop> drops{drop(1, {500, 500}, 8)};
        for (std::size_t i = 1; i < count; ++i)
            drops.push_back(drop(i + 1, {1000 + double(i % 32) * 10, 1000 + double(i / 32) * 10}, 1));
        DropletSimulation simulation;
        DropletSimulationTestAccess::setDrops(simulation, drops);
        DropletSimulationTestAccess::splash(simulation, {500, 500});
        require(simulation.drops().size() <= 1024, "splashes obey the renderer's hard population bound");
        double volume = 0;
        for (const auto &d : simulation.drops()) volume += d.volume;
        near(volume, 512 + count - 1, "capacity pressure cannot discard water or unrelated drops");
        if (count < 1024) require(simulation.drops().size() > count, "use available room for a smaller burst");
        else require(std::hypot(simulation.drops()[0].velocity.x, simulation.drops()[0].velocity.y) > 0,
                     "a full scene still responds with a nudge");
    }
    DropletSimulation simulation;
    DropletSimulationTestAccess::setDrops(simulation, {drop(1, {500, 500}, 8)});
    auto control = simulation;
    for (auto point : {Vec2{-1, 500}, Vec2{500, 2001}, Vec2{NAN, 500}, Vec2{500, INFINITY}})
        simulation.queueSplash(point);
    simulation.advance(1.0 / 30);
    control.advance(1.0 / 30);
    samePhysicalState(simulation, control);
    for (auto position : {Vec2{0, 0}, Vec2{2000, 2000}, Vec2{500, 500}}) {
        for (double radius : {0.5, 8.0}) {
            DropletSimulationTestAccess::setDrops(simulation, {drop(1, position, radius, {899, 0})});
            DropletSimulationTestAccess::splash(simulation, position);
            double volume = 0;
            for (const auto &d : simulation.drops()) {
                volume += d.volume;
                require(d.position.x >= 0 && d.position.x <= 2000 && d.position.y >= 0 && d.position.y <= 2000,
                        "edge splashes cannot place fragments outside the viewport");
                require(std::hypot(d.velocity.x, d.velocity.y) <= 900 + 1e-9, "inherited velocity plus kick stays bounded");
            }
            near(volume, radius * radius * radius, "small and edge drops retain their water");
        }
    }
}

void restingTinyDropNudgeSurvivesAdhesion()
{
    for (const double radius : {.5, 1.0}) {
        DropletSimulation simulation;
        DropletSimulationTestAccess::setDrops(simulation, {drop(1, {500, 500}, radius)});
        simulation.queueSplash({500, 500});
        simulation.advance(1.0 / 30);
        require(simulation.drops().size() == 1, "an undersized cap receives a nudge rather than subpixel fragments");
        const auto &d = simulation.drops()[0];
        near(d.volume, radius * radius * radius, "a tiny nudge preserves water");
        require(std::hypot(d.position.x - 500, d.position.y - 500) >= 2,
                "the tiny-drop fallback must visibly displace a resting drop despite adhesion");
    }
    for (double radius : {.25, .9}) {
        DropletSimulation simulation;
        DropletSimulationTestAccess::setDrops(simulation, {drop(1, {500, 500}, radius)});
        simulation.resize(320, 60);
        simulation.resize(1920, 1080); // Resize preserves volume but increases relative adhesion.
        const auto before = simulation.drops()[0].position;
        simulation.queueSplash(before);
        simulation.advance(1.0 / 30);
        const auto &d = simulation.drops()[0];
        near(d.volume, radius * radius * radius, "resized nudge preserves the small bead's water");
        require(std::hypot(d.position.x - before.x, d.position.y - before.y) >= 2,
                "a resized speck must respond even when adhesion exceeds the bounded launch speed");
        require(std::hypot(d.velocity.x, d.velocity.y) <= 900, "temporary depinning cannot exceed the speed cap");
    }
}

void seededPopulationAndProfile()
{
    DropletSimulation a;
    DropletSimulation b;
    a.reset(1920, 1080, 42);
    b.reset(1920, 1080, 42);
    require(a.drops().size() == 1024, "default population must contain 1024 real drops");
    samePhysicalState(a, b);
    std::uint64_t lastId = 0;
    for (const auto &d : a.drops()) {
        require(d.id > lastId, "initial identities must be unique");
        lastId = d.id;
        require(d.position.x >= 0 && d.position.x <= 1920, "initial x bounds");
        require(d.position.y >= 0 && d.position.y <= 1080, "initial y bounds");
        require(d.position == d.previousPosition, "new drops have no artificial trail");
    }
    auto d = drop(1, {10, 10}, 2);
    near(d.radius(), 2, "radius is the cube root of normalized volume");
    near(d.height(), 1.2, "constant spherical-cap profile height");
    d.volume *= 8;
    near(d.radius(), 4, "eight times volume doubles radius");
}

void pinningSlidingAndPersistence()
{
    DropletSimulation simulation;
    DropletSimulationTestAccess::setDrops(simulation, {
        drop(1, {100, 100}, 1.5), drop(2, {400, 100}, 6),
    });
    for (int i = 0; i < 120; ++i)
        simulation.advance(1.0 / 120);
    require(simulation.drops().size() == 2, "isolated drops persist");
    const auto &small = simulation.drops()[0];
    const auto &large = simulation.drops()[1];
    near(small.position.y, 100, "small drops pin against gravity");
    near(small.velocity.y, 0, "pinned drops stay still");
    require(large.id == 2 && large.position.y > 130, "larger drops slide without changing identity");
    require(large.velocity.y > 0, "gravity is positive y");
    near(large.volume, 216, "motion preserves volume");
    const auto before = large.position;
    simulation.advance(1.0 / 30);
    require(simulation.drops()[1].previousPosition == before,
            "previous position belongs to the displayed frame, not the last substep");
    require(simulation.drops()[1].position.y > before.y, "sliding motion persists");
}

void fixedStepAndZeroTime()
{
    DropletSimulation simulation;
    DropletSimulationTestAccess::setDrops(simulation, {drop(1, {100, 100}, 6)});
    auto unchanged = simulation;
    simulation.advance(0, {{80, 100}, true, 1, 1});
    samePhysicalState(simulation, unchanged);
    simulation.advance(1.0 / 240);
    samePhysicalState(simulation, unchanged);
    simulation.advance(1.0 / 240);
    require(simulation.drops()[0].position.y > 100, "two half steps must execute one fixed tick");
    unchanged = simulation;
    simulation.advance(0);
    samePhysicalState(simulation, unchanged);
    require(simulation.drops()[0].previousPosition == unchanged.drops()[0].previousPosition,
            "zero elapsed must not change trails");
}

void pairMergeConservesMassAndMomentum()
{
    DropletSimulation simulation;
    auto a = drop(9, {100, 100}, 2, {20, 10});
    auto b = drop(4, {103, 100}, 1, {-10, 40});
    a.previousPosition = {98, 99};
    b.previousPosition = {104, 96};
    DropletSimulationTestAccess::setDrops(simulation, {a, b});
    DropletSimulationTestAccess::collide(simulation, {a.position, b.position});
    require(simulation.drops().size() == 1, "touching pair must merge");
    const auto &merged = simulation.drops()[0];
    require(merged.id == 4, "oldest identity survives a merge");
    near(merged.volume, 9, "pair conserves actual volume");
    near(merged.position.x, 301.0 / 3, "mass-weighted position");
    near(merged.velocity.x, 50.0 / 3, "mass-weighted x velocity");
    near(merged.velocity.y, 40.0 / 3, "mass-weighted y velocity");
    near(merged.previousPosition.x, 296.0 / 3, "mass-weighted trail origin");
}

void tripleMergeIsDeterministic()
{
    DropletSimulation a;
    DropletSimulation b;
    const std::vector<Drop> initial = {
        drop(3, {100, 100}, 2, {10, 0}),
        drop(1, {104, 100}, 2, {0, 20}),
        drop(2, {108, 100}, 2, {-10, 10}),
        drop(8, {800, 800}, 2),
    };
    DropletSimulationTestAccess::setDrops(a, initial);
    DropletSimulationTestAccess::collide(a, {{100, 100}, {104, 100}, {108, 100}, {800, 800}});
    DropletSimulationTestAccess::setDrops(b, {initial[3], initial[2], initial[0], initial[1]});
    DropletSimulationTestAccess::collide(b, {{800, 800}, {108, 100}, {100, 100}, {104, 100}});
    require(a.drops().size() == 2, "three-drop connected contact merges once");
    samePhysicalState(a, b);
    near(a.drops()[0].volume, 24, "no double-counting in three-drop contacts");
    near(a.drops()[0].position.x, 104, "three-drop center of mass");
    near(a.drops()[0].velocity.x, 0, "three-drop x momentum");
    near(a.drops()[0].velocity.y, 10, "three-drop y momentum");
    require(a.drops()[1].id == 8, "distant drops do not merge");
}

void sweptCollisionsPreventTunneling()
{
    DropletSimulation simulation;
    DropletSimulationTestAccess::setDrops(simulation, {
        drop(1, {109, 100}, 1, {900, 0}),
        drop(2, {101, 100}, 1, {-900, 0}),
        drop(3, {109, 110}, 1),
    });
    DropletSimulationTestAccess::collide(simulation, {{101, 100}, {109, 100}, {101, 110}});
    require(simulation.drops().size() == 2, "crossing paths collide, parallel separated paths do not");
    near(simulation.drops()[0].volume, 2, "swept collision conserves volume");
    near(simulation.drops()[0].position.x, 105, "swept merge center of mass");

    DropletSimulationTestAccess::setDrops(simulation, {
        drop(1, {100, 100}, 1, {900, 0}), drop(2, {108, 100}, 1, {-900, 0}),
    });
    simulation.advance(1.0 / 120);
    require(simulation.drops().size() == 1, "production tick must use swept collision detection");
}

void deterministicFrameRates()
{
    DropletSimulation reference;
    reference.reset(800, 600, 123, 100);
    require(reference.drops().size() == 100, "frame-rate test needs real seeded drops");
    for (int i = 0; i < 600; ++i)
        reference.advance(1.0 / 120);
    for (const int fps : {30, 60, 144}) {
        DropletSimulation simulation;
        simulation.reset(800, 600, 123, 100);
        for (int i = 0; i < 5 * fps; ++i)
            simulation.advance(1.0 / fps);
        samePhysicalState(simulation, reference);
    }
}

void pointerSweepAndInertia()
{
    DropletSimulation simulation;
    DropletSimulationTestAccess::setDrops(simulation, {
        drop(1, {200, 200}, 3), drop(2, {200, 600}, 3), drop(3, {140, 200}, 3),
    });
    simulation.advance(1.0 / 120, {{120, 200}, true, 1, 10});
    near(simulation.drops()[0].velocity.x, 0, "entry only establishes a baseline");
    const PointerSnapshot moved{{280, 200}, true, 2, 10.1};
    simulation.advance(0.1, moved);
    require(simulation.drops()[0].velocity.x > 25, "sweep interior receives a motion impulse");
    require(simulation.drops()[2].velocity.x > 25, "sweep must also influence drops away from its midpoint");
    near(simulation.drops()[1].velocity.x, 0, "sweep has bounded spatial influence");
    auto noPointer = simulation;
    noPointer.invalidatePointer();
    const double x = simulation.drops()[0].position.x;
    for (int i = 0; i < 6; ++i) {
        simulation.advance(1.0 / 120, moved);
        noPointer.advance(1.0 / 120);
    }
    samePhysicalState(simulation, noPointer);
    require(noPointer.drops()[0].position.x > x + 5, "drops retain inertia after the mouse leaves");
}

void pointerSampleTimeAndSequence()
{
    DropletSimulation baseline;
    DropletSimulationTestAccess::setDrops(baseline, {drop(1, {200, 200}, 3)});
    baseline.advance(1.0 / 120, {{200, 200}, true, 10, 5});
    auto slow = baseline;
    auto fast = baseline;
    slow.advance(1.0 / 120, {{240, 200}, true, 11, 5.2});
    fast.advance(1.0 / 120, {{240, 200}, true, 11, 5.1});
    require(fast.drops()[0].velocity.x > slow.drops()[0].velocity.x + 10,
            "the same path over less sample time must impart more force per tick");
    require(fast.drops()[0].velocity.x > 25 && fast.drops()[0].velocity.x < 800,
            "sample-timed transfer remains meaningful without hiding behind the drop speed cap");
    auto limited = baseline;
    limited.advance(1.0 / 120, {{240, 200}, true, 11, 5.008});
    require(limited.drops()[0].velocity.x > fast.drops()[0].velocity.x && limited.drops()[0].velocity.x < 100,
            "the source acceleration cap bounds very fast motion within its represented interval");
    for (const auto &sample : std::vector<PointerSnapshot>{
             {{280, 200}, true, 10, 5.1}, {{280, 200}, true, 9, 5.1},
             {{280, 200}, true, 11, 5}, {{280, 200}, true, 11, 4},
             {{280, 200}, true, 11, 6}, {{1000, 200}, true, 11, 5.1},
         }) {
        auto simulation = baseline;
        simulation.advance(1.0 / 120, sample);
        near(simulation.drops()[0].velocity.x, 0, "stale or discontinuous input must not kick drops");
    }
    auto stationary = baseline;
    stationary.advance(0.1, {{240, 200}, true, 11, 5.1});
    const auto moving = stationary;
    auto released = moving;
    released.invalidatePointer();
    for (std::uint64_t i = 12; i < 32; ++i) {
        stationary.advance(1.0 / 120, {{240, 200}, true, i, 5.1 + double(i - 11) / 120});
        released.advance(1.0 / 120);
    }
    samePhysicalState(stationary, released);
}

void pointerCancellationAndReentry()
{
    DropletSimulation baseline;
    DropletSimulationTestAccess::setDrops(baseline, {drop(1, {200, 200}, 3)});
    baseline.advance(1.0 / 120, {{120, 200}, true, 1, 1});
    auto queued = baseline;
    queued.advance(1.0 / 480, {{280, 200}, true, 2, 1.1});
    near(queued.drops()[0].velocity.x, 0, "impulses wait for a fixed tick");
    auto delivered = queued;
    delivered.advance(0.1, {{280, 200}, true, 2, 1.1});
    require(delivered.drops()[0].velocity.x > 25, "substep input must not be lost");
    queued.invalidatePointer();
    queued.advance(1.0 / 120, {{120, 200}, true, 3, 1.2});
    near(queued.drops()[0].velocity.x, 0, "invalidation cancels queued impulses and reentry sweep");
    queued.advance(0.1, {{280, 200}, true, 4, 1.3});
    require(queued.drops()[0].velocity.x > 25, "fresh motion after reentry must work");

    auto invalid = baseline;
    invalid.advance(1.0 / 480, {{280, 200}, true, 2, 1.1});
    invalid.advance(1.0 / 120, {{}, false, 2, 1.1});
    invalid.advance(1.0 / 120, {{280, 200}, true, 3, 1.2});
    near(invalid.drops()[0].velocity.x, 0, "invalid snapshots cancel pending input, even with repeated sequence");
}

void zeroTimeDoesNotConsumePointer()
{
    DropletSimulation simulation;
    DropletSimulationTestAccess::setDrops(simulation, {drop(1, {200, 200}, 3)});
    simulation.advance(1.0 / 120, {{120, 200}, true, 1, 1});
    auto reference = simulation;
    const PointerSnapshot moved{{280, 200}, true, 2, 1.1};
    simulation.advance(0, moved);
    simulation.advance(0, {});
    simulation.advance(0.1, moved);
    reference.advance(0.1, moved);
    samePhysicalState(simulation, reference);
    require(simulation.drops()[0].velocity.x > 25, "zero time did not swallow the motion sequence");
}

std::vector<Drop> continuousPointerTrajectory(int fps, double speed, bool stationaryUpdates = false)
{
    DropletSimulation simulation;
    DropletSimulationTestAccess::setDrops(simulation, {drop(1, {200, 200}, 3.5)});
    const double startX = speed == 30 ? 185 : 140;
    simulation.advance(1.0 / 120, {{startX, 200}, true, 1, 1});
    std::vector<Drop> checkpoints;
    PointerSnapshot pointer;
    for (int frame = 1; frame <= 2 * fps; ++frame) {
        const double time = double(frame) / fps;
        // Coalesce a common 2880 Hz straight input stream to the latest sample on each displayed frame.
        if (frame <= fps || stationaryUpdates)
            pointer = {{startX + speed * std::min(time, 1.0), 200}, true,
                       1 + std::uint64_t(frame) * (2880 / fps), 1 + time};
        simulation.advance(1.0 / fps, pointer);
        require(simulation.drops().size() == 1, "continuous input must retain the isolated drop");
        require(std::hypot(simulation.drops()[0].velocity.x, simulation.drops()[0].velocity.y)
                    <= DropletSimulation::maximumSpeed + 1e-9,
                "continuous input must respect the speed bound");
        if (frame % (fps / 6) == 0)
            checkpoints.push_back(simulation.drops()[0]);
    }
    return checkpoints;
}

void continuousPointerSamplingIsRateIndependent()
{
    for (const double speed : {30.0, 240.0}) {
        const auto reference = continuousPointerTrajectory(120, speed);
        for (const int fps : {30, 60, 144, 960}) {
            const auto actual = continuousPointerTrajectory(fps, speed);
            double positionError = 0;
            double velocityError = 0;
            for (std::size_t i = 0; i < reference.size(); ++i) {
                positionError = std::max({positionError, std::abs(actual[i].position.x - reference[i].position.x),
                                         std::abs(actual[i].position.y - reference[i].position.y)});
                velocityError = std::max({velocityError, std::abs(actual[i].velocity.x - reference[i].velocity.x),
                                         std::abs(actual[i].velocity.y - reference[i].velocity.y)});
                near(actual[i].position.x, reference[i].position.x, "continuous pointer x", 0.1);
                near(actual[i].position.y, reference[i].position.y, "continuous pointer y", 0.1);
                near(actual[i].velocity.x, reference[i].velocity.x, "continuous pointer vx", 0.5);
                near(actual[i].velocity.y, reference[i].velocity.y, "continuous pointer vy", 0.5);
                require(actual[i].id == 1 && actual[i].volume == 42.875,
                        "continuous pointer transfer preserves identity and volume");
            }
            require(actual[5].position.x > (speed == 30 ? 204 : 220),
                    "rate normalization must retain meaningful motion, including at 30 fps");
            std::cout << "INFO: continuous " << speed << " px/s at " << fps
                      << " Hz: moving x=" << actual[5].position.x << ", vx=" << actual[5].velocity.x
                      << "; maximum component errors vs 120 Hz: position=" << positionError
                      << ", velocity=" << velocityError << '\n';
        }
    }
}

void highFrequencyStationarySamplesDoNotAddMomentum()
{
    DropletSimulation fresh;
    DropletSimulationTestAccess::setDrops(fresh, {drop(1, {200, 200}, 3)});
    const PointerSnapshot moved{{280, 200}, true, 2, 1.1};
    fresh.advance(1.0 / 960, {{120, 200}, true, 1, 1});
    fresh.advance(1.0 / 960, moved);
    auto held = fresh;
    for (int frame = 3; frame <= 960; ++frame) {
        fresh.advance(1.0 / 960, {{280, 200}, true, std::uint64_t(frame), 1.1 + double(frame - 2) / 960});
        held.advance(1.0 / 960, moved);
        samePhysicalState(fresh, held);
        if (frame == 120)
            require(fresh.drops()[0].velocity.x > 25, "stationary samples must not erase the represented motion interval");
    }
    for (const double speed : {30.0, 240.0}) {
        const auto repeated = continuousPointerTrajectory(960, speed);
        const auto stationary = continuousPointerTrajectory(960, speed, true);
        for (std::size_t i = 0; i < repeated.size(); ++i) {
            near(stationary[i].position.x, repeated[i].position.x, "fresh stationary samples cannot move x");
            near(stationary[i].position.y, repeated[i].position.y, "fresh stationary samples cannot move y");
            near(stationary[i].velocity.x, repeated[i].velocity.x, "fresh stationary samples cannot add vx");
            near(stationary[i].velocity.y, repeated[i].velocity.y, "fresh stationary samples cannot add vy");
        }
    }
}

void tinyPositiveFrameKeepsPointerFinite()
{
    DropletSimulation simulation;
    DropletSimulationTestAccess::setDrops(simulation, {drop(1, {200, 200}, 3)});
    const PointerSnapshot baseline{{120, 200}, true, 1, 1};
    const PointerSnapshot moved{{280, 200}, true, 2, 1.1};
    simulation.advance(1.0 / 120, baseline);
    simulation.advance(1.0 / 240, baseline);
    simulation.advance(std::numeric_limits<double>::denorm_min(), moved);
    std::feclearexcept(FE_DIVBYZERO | FE_INVALID);
    simulation.advance(0.1, moved);
    require(std::fetestexcept(FE_DIVBYZERO | FE_INVALID) == 0, "positive input intervals cannot cause invalid arithmetic");
    require(std::isfinite(simulation.drops()[0].velocity.x), "tiny frame intervals must not divide by rounded-zero duration");
    require(simulation.drops()[0].velocity.x > 25, "tiny positive frames still queue their single motion");
}

void slowerInputCannotChangeDepinning()
{
    DropletSimulation sixty;
    DropletSimulationTestAccess::setDrops(sixty, {drop(1, {200, 200}, 1)});
    const PointerSnapshot baseline{{200, 200}, true, 1, 1};
    const PointerSnapshot moved{{204, 200}, true, 2, 1 + 1.0 / 60};
    sixty.advance(1.0 / 120, baseline);
    auto oneTwenty = sixty;
    sixty.advance(1.0 / 60, moved);
    oneTwenty.advance(1.0 / 120, baseline);
    oneTwenty.advance(1.0 / 120, moved);
    near(sixty.drops()[0].position.x, 200, "60 Hz delivery remains below adhesion threshold");
    near(oneTwenty.drops()[0].position.x, 200, "a repeated moving-input snapshot must not concentrate the next impulse");
    samePhysicalState(sixty, oneTwenty);

    DropletSimulationTestAccess::setDrops(sixty, {drop(1, {200, 200}, 3.5)});
    sixty.advance(1.0 / 120, baseline);
    oneTwenty = sixty;
    sixty.advance(1.0 / 60, moved);
    oneTwenty.advance(1.0 / 120, baseline);
    oneTwenty.advance(1.0 / 120, moved);
    oneTwenty.advance(1.0 / 120, moved);
    require(sixty.drops()[0].position.x > 200.25, "larger drops must respond to the same 60 Hz input");
    samePhysicalState(sixty, oneTwenty); // One tick of delivery latency, not a different physical response.
}

void sixtyHertzInputAcrossRenderRates()
{
    const auto run = [](int fps, double radius) {
        DropletSimulation simulation;
        DropletSimulationTestAccess::setDrops(simulation, {drop(1, {200, 200}, radius)});
        simulation.advance(1.0 / 120, {{200, 200}, true, 1, 1});
        for (int frame = 1; frame <= 3 * fps; ++frame) {
            const int sample = std::min(60, frame * 60 / fps);
            simulation.advance(1.0 / fps, {{200.0 + 4 * sample, 200}, true,
                                           std::uint64_t(sample + 1), 1 + double(sample) / 60});
            require(simulation.drops().size() == 1, "mixed-cadence input retains the isolated drop");
            const auto &d = simulation.drops()[0];
            require(std::hypot(d.velocity.x, d.velocity.y) <= DropletSimulation::maximumSpeed + 1e-9,
                    "mixed-cadence input respects the speed bound");
            if (radius <= 1.2) {
                require(d.position == Vec2{200, 200} && d.velocity == Vec2{},
                        "subthreshold 60 Hz input must keep small drops pinned at every render cadence");
            } else if (frame == fps) {
                require(d.position.x > 220, "60 Hz moving input remains effective with repeated render snapshots");
            }
        }
        return simulation.drops()[0];
    };
    for (const double radius : {1.0, 1.2, 3.5}) {
        const auto reference = run(60, radius);
        for (const int fps : {30, 120, 144}) {
            const auto actual = run(fps, radius);
            // Compare after decay: a late sample may shift onset by a tick, but cannot change the response.
            near(actual.position.x, reference.position.x, "60 Hz source final x", 0.1);
            near(actual.position.y, reference.position.y, "60 Hz source final y", 0.1);
            near(actual.velocity.x, reference.velocity.x, "60 Hz source final vx", 0.5);
            near(actual.velocity.y, reference.velocity.y, "60 Hz source final vy", 0.5);
            require(actual.id == reference.id && actual.volume == reference.volume,
                    "mixed-cadence input preserves identity and volume");
            std::cout << "INFO: 60 Hz source, radius=" << radius << ", render=" << fps
                      << " Hz: final x=" << actual.position.x << ", y=" << actual.position.y
                      << "; 60 Hz render x=" << reference.position.x << ", y=" << reference.position.y << '\n';
        }
    }
}

void activeTimeRainAndRetirement()
{
    DropletSimulation simulation;
    DropletSimulationTestAccess::setDrops(simulation, {drop(42, {100, 2008}, 6, {0, 900})}, 10);
    simulation.advance(1.0 / 120);
    require(simulation.drops().empty(), "bottom exit retires a drop instead of teleporting it");
    for (int i = 0; i < 100; ++i)
        simulation.advance(0);
    require(simulation.drops().empty(), "paused time cannot create rain");
    simulation.advance(0.25);
    require(simulation.drops().empty(), "replacement rain must not appear every frame");
    for (int i = 0; i < 120; ++i)
        simulation.advance(1.0 / 120);
    require(simulation.drops().size() == 1, "new rain replenishes on active time");
    require(simulation.drops()[0].id > 42, "retired identities are never reused");
    for (int i = 0; i < 2400; ++i) {
        simulation.advance(1.0 / 120);
        require(simulation.drops().size() <= 10, "replenishment respects the requested population cap");
    }
    require(simulation.drops().size() >= 5, "active rain continues replenishing");
}

void resizePreservesLayoutAndSuspendsZeroSize()
{
    DropletSimulation simulation;
    auto initial = drop(1, {100, 200}, 6, {20, 30});
    initial.previousPosition = {90, 180};
    DropletSimulationTestAccess::setDrops(simulation, {initial});
    simulation.resize(4000, 1000);
    const auto &resized = simulation.drops()[0];
    near(resized.position.x, 200, "resize proportional x");
    near(resized.position.y, 100, "resize proportional y");
    near(resized.previousPosition.x, 180, "resize proportional trail origin");
    near(resized.previousPosition.y, 90, "resize proportional trail y");
    near(resized.velocity.x, 40, "resize proportional velocity x");
    near(resized.velocity.y, 15, "resize proportional velocity y");
    near(resized.volume, 216, "resize must preserve physical volume");
    auto suspended = simulation;
    simulation.resize(0, 0);
    simulation.advance(100);
    samePhysicalState(simulation, suspended);
    simulation.resize(2000, 2000);
    near(simulation.drops()[0].position.x, 100, "restored x uses last nonzero layout");
    near(simulation.drops()[0].position.y, 200, "restored y uses last nonzero layout");

    simulation.reset(0, 0, 1, 5);
    simulation.advance(1);
    require(simulation.drops().empty(), "zero-size reset is safe and empty");
    simulation.resize(100, 100);
    for (int i = 0; i < 120; ++i)
        simulation.advance(1.0 / 120);
    require(!simulation.drops().empty(), "rain resumes after an initially empty viewport");
}

void resetClearsTimeAndInput()
{
    DropletSimulation simulation;
    simulation.reset(1000, 1000, 42, 50);
    simulation.advance(1.0 / 120, {{120, 200}, true, 900, 90});
    simulation.advance(1.0 / 480, {{280, 200}, true, 901, 90.1});
    simulation.reset(1000, 1000, 42, 50);
    DropletSimulation reference;
    reference.reset(1000, 1000, 42, 50);
    simulation.advance(1.0 / 240, {{120, 200}, true, 1, 1});
    reference.advance(1.0 / 240, {{120, 200}, true, 1, 1});
    samePhysicalState(simulation, reference);
    simulation.advance(1.0 / 240, {{280, 200}, true, 2, 1.1});
    reference.advance(1.0 / 240, {{280, 200}, true, 2, 1.1});
    samePhysicalState(simulation, reference);
}

void repeatedResizeDoesNotDiscardTimeOrInput()
{
    DropletSimulation simulation;
    DropletSimulationTestAccess::setDrops(simulation, {drop(1, {200, 200}, 6)});
    auto reference = simulation;
    for (int frame = 0; frame < 120; ++frame) {
        simulation.resize(2000, 2000);
        simulation.advance(1.0 / 240);
        reference.advance(1.0 / 240);
    }
    samePhysicalState(simulation, reference);
    simulation.advance(1.0 / 120, {{120, 200}, true, 1, 1});
    reference.advance(1.0 / 120, {{120, 200}, true, 1, 1});
    simulation.resize(2000, 2000);
    simulation.advance(1.0 / 120, {{280, 200}, true, 2, 1.1});
    reference.advance(1.0 / 120, {{280, 200}, true, 2, 1.1});
    samePhysicalState(simulation, reference);
}

void extremeFiniteResizeStaysSafe()
{
    DropletSimulation simulation;
    const double tiny = std::numeric_limits<double>::denorm_min();
    simulation.reset(tiny, tiny, 5, 10);
    simulation.resize(1e6, 1e6);
    for (const auto &d : simulation.drops()) {
        require(std::isfinite(d.position.x) && std::isfinite(d.position.y),
                "finite dimensions must not overflow proportional positions");
        require(std::isfinite(d.velocity.x) && std::isfinite(d.velocity.y),
                "finite dimensions must not produce NaN velocities");
    }
    DropletSimulationTestAccess::setDrops(simulation, {drop(1, {100, 200}, 6, {100, 100})});
    simulation.resize(1e-300, 1e-300);
    simulation.advance(1.0 / 120);
    simulation.resize(1e6, 1e6);
    require(simulation.drops().empty(), "resize retires drops scaled completely below the new viewport");
    simulation.advance(1.0 / 120);
}

void boundedCatchupAndExternalValues()
{
    DropletSimulation baseline;
    DropletSimulationTestAccess::setDrops(baseline, {drop(1, {100, 100}, 6)});
    auto stalled = baseline;
    auto bounded = baseline;
    stalled.advance(1e100);
    bounded.advance(0.25);
    samePhysicalState(stalled, bounded);
    stalled.advance(1.0 / 120);
    bounded.advance(1.0 / 120);
    samePhysicalState(stalled, bounded);
    const double nan = std::numeric_limits<double>::quiet_NaN();
    const double inf = std::numeric_limits<double>::infinity();
    for (const double invalid : {nan, inf, -inf, -1.0}) {
        auto simulation = baseline;
        simulation.advance(invalid);
        simulation.resize(invalid, 2000);
        simulation.resize(2000, invalid);
        samePhysicalState(simulation, baseline);
        simulation.reset(invalid, 1000);
        simulation.advance(1);
        require(simulation.drops().empty(), "invalid reset dimensions produce safe empty state");
    }
    for (const auto &sample : std::vector<PointerSnapshot>{
             {{nan, 200}, true, 2, 1.1}, {{200, inf}, true, 2, 1.1},
             {{280, 200}, true, 2, nan}, {{280, 200}, true, 2, inf},
             {{-20, 200}, true, 2, 1.1},
         }) {
        DropletSimulation simulation;
        DropletSimulationTestAccess::setDrops(simulation, {drop(1, {200, 200}, 3)});
        simulation.advance(1.0 / 120, {{120, 200}, true, 1, 1});
        simulation.advance(1.0 / 480, {{280, 200}, true, 2, 1.05});
        simulation.advance(1.0 / 120, sample);
        simulation.advance(1.0 / 120, {{280, 200}, true, 3, 1.2});
        near(simulation.drops()[0].velocity.x, 0, "malformed input cancels queued motion and reentry");
    }
}

void finiteBoundedLongRun()
{
    DropletSimulation simulation;
    simulation.reset(1920, 1080, 7, std::numeric_limits<std::size_t>::max());
    require(simulation.drops().size() <= DropletSimulation::maximumPopulation, "reset caps population");
    simulation.reset(1920, 1080, 7);
    std::uint64_t largestId = 0;
    for (int frame = 0; frame < 7200; ++frame) {
        const double x = 960 + 400 * std::sin(frame * 0.02);
        simulation.advance(1.0 / 60, {{x, 500}, true, std::uint64_t(frame + 1), frame / 60.0});
        require(simulation.drops().size() <= DropletSimulation::maximumPopulation, "long-run population remains bounded");
        std::uint64_t lastId = 0;
        for (const auto &d : simulation.drops()) {
            require(d.id > lastId, "long-run identities remain unique and ordered");
            lastId = d.id;
            largestId = std::max(largestId, d.id);
            require(std::isfinite(d.position.x) && std::isfinite(d.position.y), "finite position");
            require(std::isfinite(d.previousPosition.x) && std::isfinite(d.previousPosition.y), "finite trails");
            require(std::isfinite(d.volume) && d.volume > 0, "positive finite volume");
            require(std::isfinite(d.radius()) && std::isfinite(d.height()), "finite cap profile");
            require(std::hypot(d.velocity.x, d.velocity.y) <= DropletSimulation::maximumSpeed + 1e-9,
                    "bounded finite speed");
            require(d.position.x >= 0 && d.position.x <= 1920 && d.position.y >= 0,
                    "top and side boundaries retain drops");
            require(d.position.y - d.radius() <= 1080, "drops fully below the viewport are retired");
        }
    }
    require(largestId > 1024, "long run exercises ongoing rain, not only static seeded drops");
    require(simulation.drops().size() >= 100, "rain retains a useful visible population");
}

void fullCapacityAccretesFairlyAndPauses()
{
    DropletSimulation simulation;
    simulation.reset(2000, 270, 1, 2);
    const std::vector<Drop> initial{drop(1, {100, 100}, 1), drop(2, {1000, 100}, 2)};
    DropletSimulationTestAccess::replaceDrops(simulation, initial);
    for (int tick = 0; tick < 10 * 120; ++tick)
        simulation.advance(DropletSimulation::fixedStep);
    require(simulation.drops().size() == 2, "full capacity preserves particle count");
    const double added = simulation.drops()[0].volume - initial[0].volume;
    require(added > 1 && added < 5, "ten active seconds admit modest bounded water, not zero water or rapid cap inflation");
    for (std::size_t i = 0; i < initial.size(); ++i) {
        const auto &d = simulation.drops()[i];
        require(d.id == initial[i].id && d.position == initial[i].position,
                "pinned accretion preserves identity and position");
        near(d.volume - initial[i].volume, added, "small pinned caps receive equal volume shares");
        near(d.radius(), std::cbrt(initial[i].volume + added), "growth is real volume, not optical radius");
    }
    auto paused = simulation;
    for (int i = 0; i < 100; ++i)
        simulation.advance(0);
    samePhysicalState(simulation, paused);
    simulation.resize(0, 0);
    simulation.advance(0.25);
    samePhysicalState(simulation, paused);

    simulation.resize(2000, 270);
    bool escaped[2]{};
    for (int tick = 0; tick < 600 * 120; ++tick) {
        simulation.advance(DropletSimulation::fixedStep);
        for (const auto &d : simulation.drops()) {
            if (d.id <= 2 && d.position.y > 101 && d.volume > initial[d.id - 1].volume)
                escaped[d.id - 1] = true;
        }
    }
    require(escaped[0] && escaped[1], "both pinned size classes escape through growth without pointer input or identity reset");
    simulation.reset(2400, 1350, 1, 0);
    for (int i = 0; i < 240; ++i)
        simulation.advance(0.25);
    require(simulation.drops().empty(), "explicit zero population remains rain-free");
}

void accretionAccountsForMomentumAndGrowingContacts()
{
    DropletSimulation simulation;
    simulation.reset(2000, 270, 1, 1);
    const auto initial = drop(1, {100, 100}, 2, {100, 30});
    DropletSimulationTestAccess::replaceDrops(simulation, {initial});
    simulation.advance(DropletSimulation::fixedStep);
    const auto &d = simulation.drops()[0];
    require(d.volume > initial.volume, "water source operates even while a real cap is moving");
    // External water is at rest in-plane; gravity, drag and adhesion then act on the diluted velocity.
    const double ratio = initial.volume / d.volume;
    const double damping = std::exp(-1.8 * DropletSimulation::fixedStep);
    const Vec2 damped{100 * ratio * damping, (30 * ratio + 300 * DropletSimulation::fixedStep) * damping};
    const double factor = 1 - 300 * std::pow(3.6 / d.radius(), 2) * DropletSimulation::fixedStep
        / std::hypot(damped.x, damped.y);
    near(d.velocity.x, damped.x * factor, "zero-momentum deposition dilutes lateral velocity");
    near(d.velocity.y, damped.y * factor, "deposition accounts for vertical momentum before forces");
    const double added = d.volume - initial.volume;

    simulation.reset(2000, 270, 1, 2);
    DropletSimulationTestAccess::replaceDrops(simulation,
        {drop(1, {100, 100}, 2), drop(2, {104.00001, 100}, 2)});
    simulation.advance(DropletSimulation::fixedStep);
    require(simulation.drops().size() == 1 && simulation.drops()[0].id == 1,
            "growing contacts use the existing conservative collision merger in the same tick");
    near(simulation.drops()[0].volume, 16 + 2 * added,
         "growth and merging account for external mass separately");
}

void waterBudgetIsBoundedByPopulationNotCapArea()
{
    double unitGrowth = 0;
    for (const int population : {1, 16, 512, 1024}) {
        for (const double radius : {1., 6.}) {
            DropletSimulation simulation;
            simulation.reset(10000, 270, 1, population);
            std::vector<Drop> initial;
            for (int i = 0; i < population; ++i)
                initial.push_back(drop(i + 1, {10. + 15 * i, 100}, radius));
            // Isolate deposition from contact: wide separated columns at a fixed optical height.
            simulation.resize(20000, 270);
            DropletSimulationTestAccess::replaceDrops(simulation, initial);
            simulation.advance(DropletSimulation::fixedStep);
            require(simulation.drops().size() == std::size_t(population), "deposition cannot allocate extra particles");
            double added = 0;
            for (const auto &d : simulation.drops())
                added += d.volume - radius * radius * radius;
            require(added > 0 && added < population * 5 * DropletSimulation::fixedStep,
                    "external water budget is positive and bounded per second and particle");
            if (unitGrowth == 0) unitGrowth = added;
            near(added, unitGrowth * population, "source cannot grow with total cap area", 1e-8);
        }
    }
}

void apparentScaleTracksViewportHeight()
{
    DropletSimulation small;
    DropletSimulation large;
    small.reset(1920, 1080, 1);
    large.reset(2400, 1350, 1);
    double sum = 0;
    for (std::size_t i = 0; i < small.drops().size(); ++i) {
        const auto &a = small.drops()[i];
        const auto &b = large.drops()[i];
        require(a.radius() >= 4 && a.radius() <= 28, "production births must have broad, not speck-sized footprints");
        near(b.radius() / a.radius(), 1.25, "radius tracks viewport height");
        near(b.volume / a.volume, 1.953125, "water volume calibration is cubic");
        sum += a.radius();
    }
    require(sum / small.drops().size() > 9, "mean birth radius must retain original apparent scale");
    // A lone drop has the same pinning balance and bounded gravity at both heights.
    small.reset(1920, 1080, 1, 0);
    large.reset(2400, 1350, 1, 0);
    for (const double radius : {8., 24.}) {
        DropletSimulationTestAccess::replaceDrops(small, {drop(1, {100, 100}, radius)});
        DropletSimulationTestAccess::replaceDrops(large, {drop(1, {100, 100}, radius * 1.25)});
        for (int i = 0; i < 120; ++i) {
            small.advance(DropletSimulation::fixedStep);
            large.advance(DropletSimulation::fixedStep);
        }
        near(small.drops()[0].velocity.y, large.drops()[0].velocity.y, "adhesion scales together with births");
        require(radius == 8 ? small.drops()[0].position.y == 100 : small.drops()[0].position.y > 130,
                "visual calibration retains both pinned and naturally sliding caps");
    }
}

void sustainedDefaultRainWithoutPointer()
{
    bool sustained = true, renewed = true, broad = true;
    bool populated = true, varied = true;
    for (const auto size : {Vec2{2400, 1350}, Vec2{1970, 1231}}) {
        for (const auto seed : {1, 7}) {
            DropletSimulation simulation;
            simulation.reset(size.x, size.y, seed);
            auto thirty = simulation;
            auto sixty = simulation;
            std::uint64_t largestId = 1024;
            int birthsInWindow = 0;
            int minimumMoving = 1024;
            for (int second = 1; second <= 600; ++second) {
                for (int tick = 0; tick < 120; ++tick) {
                    simulation.advance(DropletSimulation::fixedStep);
                    require(simulation.drops().size() <= DropletSimulation::maximumPopulation, "production population remains bounded");
                    for (const auto &d : simulation.drops()) {
                        if (d.id > largestId) {
                            require(d.id == largestId + 1, "observe each fresh birth, not just a cumulative ID");
                            largestId = d.id;
                            ++birthsInWindow;
                        }
                        require(std::isfinite(d.volume) && d.volume > 0 && d.radius() < size.y * .08,
                                "no nonfinite state or huge-cap runaway");
                        require(std::isfinite(d.position.x) && std::isfinite(d.position.y)
                                    && std::hypot(d.velocity.x, d.velocity.y) <= DropletSimulation::maximumSpeed + 1e-9,
                                "long-run positions and velocities remain finite and bounded");
                    }
                }
                for (int frame = 0; frame < 40; ++frame) thirty.advance(.75 / 30);
                for (int frame = 0; frame < 80; ++frame) sixty.advance(.75 / 60);
                samePhysicalState(thirty, simulation);
                samePhysicalState(sixty, simulation);
                const int moving = std::count_if(simulation.drops().begin(), simulation.drops().end(),
                    [](const auto &d) { return std::hypot(d.velocity.x, d.velocity.y) > 1; });
                minimumMoving = std::min(minimumMoving, moving);
                if (second >= 60) {
                    sustained &= moving >= 20 && moving >= .08 * simulation.drops().size();
                }
                if (second % 10 == 0) {
                    if (second >= 60)
                        renewed &= birthsInWindow >= 10;
                    std::vector<double> radii;
                    int smallBeads = 0, largeMoving = 0;
                    for (const auto &d : simulation.drops()) {
                        radii.push_back(d.radius());
                        smallBeads += d.radius() < size.y / 100;
                        largeMoving += d.radius() > size.y / 60 && std::hypot(d.velocity.x, d.velocity.y) > 1;
                    }
                    std::sort(radii.begin(), radii.end());
                    require(!radii.empty(), "default rain cannot disappear");
                    const double p10 = radii[radii.size() / 10];
                    const double median = radii[radii.size() / 2];
                    const double p90 = radii[radii.size() * 9 / 10];
                    const double p95 = radii[radii.size() * 19 / 20];
                    // A few giant bubbles can satisfy total coverage while losing the original bead field.
                    if (second == 10 || second >= 60) {
                        // Approximately 300-700, allowing a small stochastic dip below 300.
                        populated &= radii.size() >= 280 && radii.size() <= 700;
                        varied &= smallBeads >= 100 && smallBeads >= .4 * radii.size()
                            && p10 < size.y / 140 && median < size.y / 90
                            && p95 > size.y / 70 && p95 > 2 * p10 && largeMoving >= 8;
                    }
                    if (second == 10 || second == 60 || second == 300 || second == 600) {
                        double area = 0, radiusSum = 0, maxRadius = 0;
                        for (const auto &d : simulation.drops()) {
                            area += std::numbers::pi * d.radius() * d.radius();
                            radiusSum += d.radius();
                            maxRadius = std::max(maxRadius, d.radius());
                        }
                        const double coverage = area / (size.x * size.y);
                        const double meanRadius = radiusSum / simulation.drops().size();
                        std::cout << "INFO: default " << size.x << 'x' << size.y << " seed=" << seed
                                  << " seconds=" << second << " count=" << simulation.drops().size()
                                  << " moving=" << moving << " minMoving10s=" << minimumMoving
                                  << " births10s=" << birthsInWindow << " meanRadius=" << meanRadius
                                  << " maxRadius=" << maxRadius << " diskSumCoverage=" << coverage
                                  << " smallBeads=" << smallBeads << " largeMoving=" << largeMoving
                                  << " p10=" << p10 << " median=" << median << " p90=" << p90 << " p95=" << p95 << '\n';
                        broad &= coverage > .05 && coverage < .3
                            && meanRadius > size.y / 120 && meanRadius < size.y / 35;
                    }
                    birthsInWindow = 0;
                    minimumMoving = 1024;
                }
            }
        }
    }
    require(sustained, "every settled second must retain meaningful natural flow without a pointer");
    require(renewed, "each late ten-second window needs fresh natural births");
    require(broad, "early and late physical footprint must retain broad optical scale, not sparse specks");
    require(populated, "early and each late window need roughly 300-700 distinct real caps, not 150 large bubbles");
    require(varied, "retain many small beads, a broad radius distribution and fewer large moving drops");
}

} // namespace

int main()
{
    const std::vector<std::pair<std::string, std::function<void()>>> tests = {
        {"splash water, momentum and visible separation", splashConservesWaterAndInheritedMomentum},
        {"splash targeting and merging impact", splashTargetsOneNearbyDropAndMergesOnImpact},
        {"splash active ticks and cancellation", splashQueueUsesActiveTicksAndCancels},
        {"splash capacity, edges and invalid input", splashRespectsCapacityEdgesAndInvalidInput},
        {"resting tiny-drop nudge survives adhesion", restingTinyDropNudgeSurvivesAdhesion},
        {"seeded population and cap profile", seededPopulationAndProfile},
        {"pinning, sliding, and persistent frame trails", pinningSlidingAndPersistence},
        {"fixed steps and zero elapsed", fixedStepAndZeroTime},
        {"pair merge conservation", pairMergeConservesMassAndMomentum},
        {"deterministic triple merge", tripleMergeIsDeterministic},
        {"swept collision detection", sweptCollisionsPreventTunneling},
        {"deterministic frame rates", deterministicFrameRates},
        {"pointer swept influence and inertia", pointerSweepAndInertia},
        {"pointer sample time and monotonic sequence", pointerSampleTimeAndSequence},
        {"pointer cancellation and reentry", pointerCancellationAndReentry},
        {"zero time does not consume pointer input", zeroTimeDoesNotConsumePointer},
        {"continuous pointer sampling rate independence", continuousPointerSamplingIsRateIndependent},
        {"high-frequency stationary pointer samples", highFrequencyStationarySamplesDoNotAddMomentum},
        {"tiny positive pointer frame remains finite", tinyPositiveFrameKeepsPointerFinite},
        {"slower input preserves the adhesion threshold", slowerInputCannotChangeDepinning},
        {"60 Hz input across render rates", sixtyHertzInputAcrossRenderRates},
        {"active-time rain and bottom retirement", activeTimeRainAndRetirement},
        {"proportional resize and zero-size suspension", resizePreservesLayoutAndSuspendsZeroSize},
        {"reset clears time and input", resetClearsTimeAndInput},
        {"unchanged resize preserves time and input", repeatedResizeDoesNotDiscardTimeOrInput},
        {"extreme finite resize remains safe", extremeFiniteResizeStaysSafe},
        {"bounded catchup and rejected external values", boundedCatchupAndExternalValues},
        {"finite bounded long run", finiteBoundedLongRun},
        {"full-capacity fair accretion, escape and pause", fullCapacityAccretesFairlyAndPauses},
        {"accretion momentum and growing contacts", accretionAccountsForMomentumAndGrowingContacts},
        {"bounded population-based water budget", waterBudgetIsBoundedByPopulationNotCapArea},
        {"viewport-relative apparent scale and adhesion", apparentScaleTracksViewportHeight},
        {"sustained production-default rain without pointer", sustainedDefaultRainWithoutPointer},
    };
    int failed = 0;
    for (const auto &[name, run] : tests) {
        try {
            run();
            std::cout << "PASS: " << name << '\n';
        } catch (const std::exception &error) {
            std::cerr << "FAIL: " << name << ": " << error.what() << '\n';
            ++failed;
        }
    }
    std::cout << tests.size() - failed << '/' << tests.size() << " tests passed\n";
    return failed == 0 ? 0 : 1;
}
