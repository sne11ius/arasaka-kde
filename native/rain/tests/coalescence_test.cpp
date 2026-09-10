#include "dropletsimulation.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <functional>
#include <iostream>
#include <stdexcept>
#include <string>

using namespace arasaka::rain;

namespace arasaka::rain {
struct DropletSimulationTestAccess {
    static void setDrops(DropletSimulation &simulation, std::vector<Drop> drops, double width = 2000, double height = 2000) {
        simulation.reset(width, height, 1, 0);
        simulation.lengthScale_ = 1;
        simulation.drops_ = std::move(drops);
        for (const auto &d : simulation.drops_) simulation.nextId_ = std::max(simulation.nextId_, d.id + 1);
    }
    static void collide(DropletSimulation &simulation) {
        std::vector<Vec2> starts;
        for (const auto &d : simulation.drops_) starts.push_back(d.position);
        simulation.mergeCollisions(starts);
    }
    static void append(DropletSimulation &simulation, Drop drop) {
        simulation.nextId_ = std::max(simulation.nextId_, drop.id + 1);
        simulation.drops_.push_back(drop);
    }
    static void splash(DropletSimulation &simulation, Vec2 point) { simulation.splash(point); }
};
}

namespace {
void require(bool condition, const std::string &message) {
    if (!condition) throw std::runtime_error(message);
}
void near(double actual, double expected, const std::string &message) {
    require(std::isfinite(actual) && std::abs(actual - expected) < 1e-7, message);
}
Drop bead(std::uint64_t id, Vec2 p, double radius, Vec2 velocity = {}) {
    return {id, p, p, velocity, radius * radius * radius};
}

DropSurface surface(const Drop &drop) { return drop.surface(); }

DropletSimulation pair(double firstRadius = 12, double secondRadius = 12) {
    DropletSimulation simulation;
    DropletSimulationTestAccess::setDrops(simulation, {
        bead(1, {500, 500}, firstRadius), bead(2, {500 + firstRadius + secondRadius, 500}, secondRadius)});
    DropletSimulationTestAccess::collide(simulation);
    return simulation;
}

void contactRetainsBothLobesAndSettlesInActiveTime() {
    auto simulation = pair();
    require(simulation.drops().size() == 1, "physical water merges once at contact");
    const auto start = surface(simulation.drops()[0]);
    require(start.count == 2, "contact must retain both visible lobes rather than replacing them with one circle");
    near(start.lobes[0].offset.x, -12, "first lobe remains at its original world position");
    near(start.lobes[1].offset.x, 12, "second lobe remains at its original world position");
    near(start.lobes[0].radius, 12, "initial lobe radius");
    near(start.lobes[1].radius, 12, "initial second radius");
    near(simulation.drops()[0].volume, 3456, "coalescence cannot add or lose physical water");
    require(start.smoothing > 0, "the joined surface needs a smooth connecting neck");
    simulation.advance(0);
    near(surface(simulation.drops()[0]).lobes[0].offset.x, -12, "pause freezes shape as well as position");
    simulation.advance(.075);
    const auto middle = surface(simulation.drops()[0]);
    require(middle.count == 2 && middle.lobes[0].offset.x > -12 && middle.lobes[0].offset.x < -1,
            "lobes pull together over several frames");
    require(middle.lobes[0].radius > 12 && middle.lobes[0].radius < simulation.drops()[0].radius(),
            "the joined shape rounds out progressively");
    simulation.advance(.25);
    const auto end = surface(simulation.drops()[0]);
    require(end.count == 1, "settled merges release their temporary lobes");
    near(end.lobes[0].radius, std::cbrt(3456), "settled cap matches the combined water");
    near(end.smoothing, 0, "settled caps retain their original isolated optics");
}

void smallImpactsSettleSoonerAndFreshImpactsRebase() {
    auto equal = pair();
    auto unequal = pair(12, 2);
    equal.advance(.15);
    unequal.advance(.15);
    require(surface(equal.drops()[0]).count > 1 && surface(unequal.drops()[0]).count == 1,
            "small splinters should flow into a large drop faster than equal drops combine");
    auto simulation = pair();
    simulation.advance(.05);
    const auto beforeDrop = simulation.drops()[0];
    const auto before = surface(beforeDrop);
    DropletSimulationTestAccess::append(simulation, bead(3, {beforeDrop.position.x + beforeDrop.radius() + 4, beforeDrop.position.y}, 4));
    DropletSimulationTestAccess::collide(simulation);
    require(simulation.drops().size() == 1, "a fresh collision joins the existing merging body");
    const auto after = surface(simulation.drops()[0]);
    require(after.count == 3, "repeated collisions retain the current visible lobes");
    for (std::size_t i = 0; i < 2; ++i) {
        near(simulation.drops()[0].position.x + after.lobes[i].offset.x,
             beforeDrop.position.x + before.lobes[i].offset.x, "remerging cannot revive old lobe positions");
        near(after.lobes[i].radius, before.lobes[i].radius, "remerging starts from the current shape");
    }
    near(simulation.drops()[0].volume, 3520, "repeated impacts retain all physical water");
}

void unrelatedCollisionsAndResizePreserveShape() {
    auto simulation = pair();
    simulation.advance(.05);
    const auto before = surface(simulation.drops()[0]);
    DropletSimulationTestAccess::append(simulation, bead(20, {1200, 1000}, 5));
    DropletSimulationTestAccess::append(simulation, bead(21, {1210, 1000}, 5));
    DropletSimulationTestAccess::collide(simulation);
    const auto untouched = surface(simulation.drops()[0]);
    require(untouched.count == 2, "an unrelated merge must not reset another body's surface");
    near(untouched.lobes[0].offset.x, before.lobes[0].offset.x, "unrelated collision retains shape progress");
    simulation.resize(4000, 2000);
    const auto resized = surface(simulation.drops()[0]);
    near(resized.lobes[0].offset.x, before.lobes[0].offset.x * 2, "resize maps lobes with their owning drop");
    near(resized.lobes[0].radius, before.lobes[0].radius, "resize still preserves droplet volume and radii");
    simulation.reset(2000, 2000, 1, 8);
    for (const auto &d : simulation.drops()) require(surface(d).count == 1, "reset removes old merge silhouettes");
}

void denseContactsHaveBoundedDeterministicSurfaces() {
    std::vector<Drop> drops;
    for (int i = 0; i < 40; ++i) drops.push_back(bead(i + 1, {500 + .5 * i, 500}, 2));
    DropletSimulation a, b;
    DropletSimulationTestAccess::setDrops(a, drops);
    std::reverse(drops.begin(), drops.end());
    DropletSimulationTestAccess::setDrops(b, drops);
    DropletSimulationTestAccess::collide(a);
    DropletSimulationTestAccess::collide(b);
    require(a.drops().size() == 1 && b.drops().size() == 1, "dense contact becomes one physical body");
    near(a.drops()[0].volume, 320, "dense merging conserves water");
    const auto x = surface(a.drops()[0]), y = surface(b.drops()[0]);
    require(x.count >= 2 && x.count <= 4 && x.count == y.count, "surface complexity is bounded even for dense splashes");
    double weight = 0;
    for (std::size_t i = 0; i < x.count; ++i) {
        near(x.lobes[i].offset.x, y.lobes[i].offset.x, "surface clustering is independent of input order");
        near(x.lobes[i].radius, y.lobes[i].radius, "deterministic surface radii");
        require(x.lobes[i].radius > 0 && std::isfinite(x.lobes[i].radius), "clustered lobes stay finite");
        weight += x.lobes[i].weight;
    }
    near(weight, 1, "every parent's share remains represented within the visual budget");
}

void clickingTheVisibleMergeSplitsWithoutGhosts() {
    DropletSimulation simulation;
    DropletSimulationTestAccess::setDrops(simulation, {
        bead(1, {500, 500}, 40), bead(2, {580, 500}, 40),
        bead(3, {660, 500}, 40), bead(4, {740, 500}, 40)});
    DropletSimulationTestAccess::collide(simulation);
    require(surface(simulation.drops()[0]).count == 4, "prepare an extended merging silhouette");
    // Inside the fingertip margin of the right visible lobe, far outside the final cap's hit area.
    DropletSimulationTestAccess::splash(simulation, {784, 500});
    require(simulation.drops().size() >= 3, "click targeting must follow the visible merging shape");
    double water = 0, furthest = 0;
    for (const auto &d : simulation.drops()) {
        require(d.id > 4 && surface(d).count == 1, "a split retires all parent merge lobes; fragments have no ghost surfaces");
        water += d.volume;
        furthest = std::max(furthest, std::hypot(d.position.x - 620, d.position.y - 500));
    }
    near(water, 256000, "clicking during coalescence conserves the entire merging body's water");
    require(furthest >= 160, "splinters spread from the full visible body instead of collapsing it to the final cap");
}

void clickFragmentsUseTheSameLiquidImpact() {
    DropletSimulation simulation;
    DropletSimulationTestAccess::setDrops(simulation, {bead(1, {500, 500}, 12)});
    DropletSimulationTestAccess::splash(simulation, {500, 500});
    auto fragment = simulation.drops().back();
    fragment.position = fragment.previousPosition = {800, 800};
    fragment.velocity = {300, 0};
    auto target = bead(100, {800 + fragment.radius() + 2.5, 800}, 2);
    DropletSimulationTestAccess::setDrops(simulation, {fragment, target});
    simulation.advance(DropletSimulation::fixedStep);
    require(simulation.drops().size() == 1, "splash impact combines the two physical drops");
    near(simulation.drops()[0].volume, fragment.volume + 8, "splash impact conserves water");
    require(simulation.drops()[0].velocity.x > 100, "the hit drop receives splash momentum");
    const auto contact = surface(simulation.drops()[0]);
    require(contact.count == 2, "splash fragments must form a liquid neck on impact too");
    near(contact.lobes[0].radius, fragment.radius(), "impact retains the splinter's initial shape");
    simulation.advance(.05);
    require(surface(simulation.drops()[0]).count == 2, "the fragment should be visibly absorbed over several frames");
}

void retirementWaitsForTheVisibleMergingSurface() {
    DropletSimulation simulation;
    DropletSimulationTestAccess::setDrops(simulation, {
        bead(1, {500, 1040}, 20, {0, 900}), bead(2, {500, 1080}, 20, {0, 900})}, 1920, 1080);
    DropletSimulationTestAccess::collide(simulation);
    simulation.advance(7 * DropletSimulation::fixedStep);
    require(simulation.drops().size() == 1, "a visible upper lobe cannot vanish when the physical cap crosses the bottom");
    require(simulation.drops()[0].position.y - simulation.drops()[0].radius() > 1080,
            "fixture must exercise a body whose final cap has already left");
    auto resized = simulation;
    resized.resize(1900, 1080);
    require(resized.drops().size() == 1, "resize retirement must also retain the visible merging surface");
    simulation.advance(.25);
    resized.advance(.25);
    require(simulation.drops().empty() && resized.drops().empty(), "fully departed surfaces must still retire");
}

void clicksFollowTheBroadLowerBelly() {
    for (bool merging : {false, true}) {
        DropletSimulation simulation;
        std::vector<Drop> drops{bead(1, {900, 900}, 200, {0, 120})};
        if (merging) drops.push_back(bead(2, {1300, 900}, 200, {0, 120}));
        DropletSimulationTestAccess::setDrops(simulation, drops);
        if (merging) DropletSimulationTestAccess::collide(simulation);
        auto missed = simulation;
        DropletSimulationTestAccess::splash(missed, {900, 1190});
        require(missed.drops().size() == 1 && missed.drops()[0].id == 1,
                "the old tapered tip below the rounded body must not remain as an invisible hit target");
        const auto &body = simulation.drops()[0];
        require(body.surface().height({1048 - body.position.x, 980 - body.position.y}) > 0,
                "the belly fixture must target visible water on the taller deformed cap");
        DropletSimulationTestAccess::splash(simulation, {1048, 980});
        require(simulation.drops().size() >= 3,
                "the wide lower sides must remain clickable, including during a merge");
        double volume = 0;
        for (const auto &d : simulation.drops()) volume += d.volume;
        near(volume, merging ? 16000000 : 8000000, "a belly click conserves the whole body's water");
    }
}

void fallingProfileHasNoCreaseOutsideTheRim() {
    for (Vec2 velocity : {Vec2{0, 120}, Vec2{120, 120}, Vec2{-120, 120}}) {
        const auto lobe = bead(1, {}, 16, velocity).surface().lobes[0];
        for (double side : {-1., 1.}) {
            // Smooth unions turn exterior signed heights into visible liquid necks.
            // Their normals must remain continuous where the width profile reaches either end.
            const double y = side * lobe.halfExtent().y, epsilon = .0001;
            const double center = lobe.distance({5, y});
            const double leftSlope = (center - lobe.distance({5, y - epsilon})) / epsilon;
            const double rightSlope = (lobe.distance({5, y + epsilon}) - center) / epsilon;
            require(std::abs(leftSlope - rightSlope) < .001,
                    "the gravity profile must not introduce a crease into a liquid neck");
        }
    }
}
}

int main() {
    const std::pair<const char *, std::function<void()>> tests[] = {
        {"contact lobes, settling and pause", contactRetainsBothLobesAndSettlesInActiveTime},
        {"small and repeated impacts", smallImpactsSettleSoonerAndFreshImpactsRebase},
        {"unrelated collisions, resize and reset", unrelatedCollisionsAndResizePreserveShape},
        {"bounded deterministic dense contacts", denseContactsHaveBoundedDeterministicSurfaces},
        {"clicking a merge without ghosts", clickingTheVisibleMergeSplitsWithoutGhosts},
        {"click-fragment liquid impact", clickFragmentsUseTheSameLiquidImpact},
        {"visible bottom-edge retirement", retirementWaitsForTheVisibleMergingSurface},
        {"clicks follow the falling profile", clicksFollowTheBroadLowerBelly},
        {"smooth falling-profile exterior", fallingProfileHasNoCreaseOutsideTheRim},
    };
    int failures = 0;
    for (const auto &[name, test] : tests) {
        try { test(); std::cout << "PASS: " << name << '\n'; }
        catch (const std::exception &e) { ++failures; std::cerr << "FAIL: " << name << ": " << e.what() << '\n'; }
    }
    return failures ? 1 : 0;
}
