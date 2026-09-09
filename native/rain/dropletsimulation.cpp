#include "dropletsimulation.h"

#include <algorithm>
#include <cmath>
#include <numeric>
#include <unordered_map>
#include <utility>

namespace arasaka::rain {

double Drop::radius() const { return std::cbrt(volume); }
double Drop::height() const { return 0.6 * radius(); }

double DropletSimulation::randomUnit()
{
    // SplitMix64 with an explicit 53-bit conversion is reproducible across STL implementations.
    auto value = (randomState_ += 0x9e3779b97f4a7c15ULL);
    value = (value ^ (value >> 30)) * 0xbf58476d1ce4e5b9ULL;
    value = (value ^ (value >> 27)) * 0x94d049bb133111ebULL;
    value ^= value >> 31;
    return static_cast<double>(value >> 11) * 0x1.0p-53;
}

void DropletSimulation::spawn()
{
    const double radius = lengthScale_ * (randomUnit() < 0.95 ? 1.0 + 2.4 * randomUnit() : 3.8 + 3.0 * randomUnit());
    const Vec2 position{randomUnit() * width_, randomUnit() * height_};
    drops_.push_back({nextId_++, position, position, {}, radius * radius * radius});
}

void DropletSimulation::reset(double width, double height, std::uint64_t seed, std::size_t population)
{
    drops_.clear();
    width_ = width;
    height_ = height;
    sizeActive_ = std::isfinite(width) && std::isfinite(height) && width > 0 && height > 0
        && width <= 1e6 && height <= 1e6;
    if (!sizeActive_)
        width_ = height_ = 0;
    // Match height-normalized Heartfelt footprints; bound degenerate and extreme logical sizes.
    lengthScale_ = std::clamp(height_ / 270.0, 0.25, 16.0);
    targetPopulation_ = std::min(population, maximumPopulation);
    randomState_ = seed;
    nextId_ = 1;
    accumulator_ = 0;
    rainCredit_ = 0;
    pointer_ = {};
    pointerSequence_ = 0;
    hasPointerSequence_ = false;
    invalidatePointer();
    drops_.reserve(targetPopulation_);
    if (sizeActive_) {
        for (std::size_t i = 0; i < targetPopulation_; ++i)
            spawn();
    }
}

void DropletSimulation::resize(double width, double height)
{
    if (!std::isfinite(width) || !std::isfinite(height) || width < 0 || height < 0
        || width > 1e6 || height > 1e6)
        return;
    if (sizeActive_ && width == width_ && height == height_)
        return;
    invalidatePointer();
    accumulator_ = 0;
    sizeActive_ = width > 0 && height > 0;
    if (!sizeActive_)
        return;
    if (width_ > 0 && height_ > 0) {
        // Wider intermediates keep even subnormal-to-screen resize ratios finite.
        const long double scaleX = static_cast<long double>(width) / width_;
        const long double scaleY = static_cast<long double>(height) / height_;
        for (auto &drop : drops_) {
            const long double bottom = height + drop.radius();
            drop.position.x = static_cast<double>(drop.position.x * scaleX);
            drop.position.y = static_cast<double>(std::min(drop.position.y * scaleY, bottom + 1));
            drop.previousPosition.x = static_cast<double>(drop.previousPosition.x * scaleX);
            drop.previousPosition.y = static_cast<double>(std::min(drop.previousPosition.y * scaleY, bottom));
            const long double vx = drop.velocity.x * scaleX;
            const long double vy = drop.velocity.y * scaleY;
            const long double divisor = std::max(1.0L, std::hypot(vx, vy) / maximumSpeed);
            drop.velocity.x = static_cast<double>(vx / divisor);
            drop.velocity.y = static_cast<double>(vy / divisor);
        }
        std::erase_if(drops_, [height](const auto &drop) { return drop.position.y - drop.radius() > height; });
    }
    width_ = width;
    height_ = height;
    lengthScale_ = std::clamp(height_ / 270.0, 0.25, 16.0);
}

void DropletSimulation::advance(double activeSeconds, const PointerSnapshot &pointer)
{
    if (!sizeActive_ || !std::isfinite(activeSeconds) || activeSeconds <= 0)
        return;
    for (auto &drop : drops_)
        drop.previousPosition = drop.position;
    accumulator_ += std::min(activeSeconds, maximumFrameSeconds);
    consumePointer(pointer);
    int steps = 0;
    while (accumulator_ + 1e-12 >= fixedStep && steps < 30) {
        step();
        accumulator_ = std::max(0.0, accumulator_ - fixedStep);
        ++steps;
    }
}

void DropletSimulation::consumePointer(const PointerSnapshot &pointer)
{
    if (!pointer.valid || !std::isfinite(pointer.position.x) || !std::isfinite(pointer.position.y)
        || !std::isfinite(pointer.sampleSeconds) || pointer.position.x < 0 || pointer.position.x > width_
        || pointer.position.y < 0 || pointer.position.y > height_) {
        invalidatePointer();
        if (!hasPointerSequence_ || pointer.sequence > pointerSequence_) {
            pointerSequence_ = pointer.sequence;
            hasPointerSequence_ = true;
        }
        return;
    }
    if (hasPointerSequence_ && pointer.sequence <= pointerSequence_)
        return;
    pointerSequence_ = pointer.sequence;
    hasPointerSequence_ = true;
    if (!pointerArmed_) {
        pointer_ = pointer;
        pointerTime_ = accumulator_;
        pointerArmed_ = true;
        return;
    }

    const auto start = pointer_.position;
    const Vec2 delta{pointer.position.x - start.x, pointer.position.y - start.y};
    const double seconds = pointer.sampleSeconds - pointer_.sampleSeconds;
    const double distance = std::hypot(delta.x, delta.y);
    pointer_ = pointer;
    if (!std::isfinite(seconds) || seconds <= 0) {
        invalidatePointer();
        return;
    }
    // Allow one tick of sample/frame-boundary skew at the admission limit. Larger gaps,
    // warps, and impossible speeds establish a new baseline, never a cross-screen kick.
    if (seconds > maximumFrameSeconds + fixedStep || distance > 256 || distance / seconds > 6000) {
        pointerMotions_.clear();
        pointerTime_ = accumulator_;
        return;
    }
    // Late input may shift playback to the next tick, but must never compress the represented interval.
    const double begin = std::max(0.0, pointerTime_);
    pointerTime_ = begin + seconds;
    if (distance <= 1e-9)
        return;
    if (pointerMotions_.size() == 32) {
        pointerMotions_.clear();
        pointerTime_ = accumulator_;
        return;
    }
    // Integrate bounded acceleration over sample time: subdividing a path cannot multiply its impulse.
    const double impulse = std::min(21600.0 * seconds, 10.8 * distance);
    pointerMotions_.push_back({start, pointer.position, {delta.x * impulse / distance, delta.y * impulse / distance},
                              begin, seconds});
}

void DropletSimulation::step()
{
    std::vector<Vec2> starts;
    starts.reserve(drops_.size());
    // Admit 15% of the mean birth-volume per target cap every 20 active seconds. Slow,
    // equal shares preserve small beads while still feeding every pinned cap, independent of area.
    const double water = drops_.empty() ? 0 : targetPopulation_ * (21.1653 * 0.15 / 20.0)
        * lengthScale_ * lengthScale_ * lengthScale_ * fixedStep / drops_.size();
    for (auto &drop : drops_) {
        starts.push_back(drop.position);
        const double oldVolume = drop.volume;
        drop.volume += water;
        drop.velocity.x *= oldVolume / drop.volume;
        drop.velocity.y *= oldVolume / drop.volume;
        const double radius = drop.radius();
        for (const auto &motion : pointerMotions_) {
            const double duration = motion.durationSeconds;
            const double pointerBegin = std::clamp(-motion.beginSeconds, 0.0, duration) / duration;
            const double pointerEnd = std::clamp(fixedStep - motion.beginSeconds, 0.0, duration) / duration;
            const double fraction = pointerEnd - pointerBegin;
            if (fraction <= 0)
                continue;
            const Vec2 path{motion.end.x - motion.start.x, motion.end.y - motion.start.y};
            const Vec2 start{motion.start.x + pointerBegin * path.x, motion.start.y + pointerBegin * path.y};
            const Vec2 delta{fraction * path.x, fraction * path.y};
            // Average contact along the path; using its peak would favor longer/coalesced segments.
            const int samples = std::max(1, static_cast<int>(std::ceil(std::hypot(delta.x, delta.y) / 2.0)));
            double influence = 0;
            for (int sample = 0; sample < samples; ++sample) {
                const double t = (sample + 0.5) / samples;
                const double distance = std::hypot(drop.position.x - start.x - t * delta.x,
                                                   drop.position.y - start.y - t * delta.y);
                const double weight = std::max(0.0, 1.0 - distance / (48.0 + radius));
                influence += weight * weight;
            }
            influence *= fraction / samples;
            drop.velocity.x += motion.impulse.x * influence;
            drop.velocity.y += motion.impulse.y * influence;
        }
        const double adhesion = 300.0 * std::pow(3.6 * lengthScale_ / radius, 2);
        drop.velocity.y += 300.0 * fixedStep;
        const double damping = std::exp(-1.8 * fixedStep);
        drop.velocity.x *= damping;
        drop.velocity.y *= damping;
        const double speed = std::hypot(drop.velocity.x, drop.velocity.y);
        if (speed > 0) {
            const double nextSpeed = std::min(maximumSpeed, std::max(0.0, speed - adhesion * fixedStep));
            drop.velocity.x *= nextSpeed / speed;
            drop.velocity.y *= nextSpeed / speed;
        }
        drop.position.x += drop.velocity.x * fixedStep;
        drop.position.y += drop.velocity.y * fixedStep;
        if (drop.position.x < 0 || drop.position.x > width_) {
            drop.position.x = std::clamp(drop.position.x, 0.0, width_);
            drop.velocity.x *= -0.25;
        }
        if (drop.position.y < 0) {
            drop.position.y = 0;
            drop.velocity.y = 0;
        }
    }
    // Keep fractional frame input until its part of the fixed timeline has actually executed.
    for (auto &motion : pointerMotions_)
        motion.beginSeconds -= fixedStep;
    if (pointerArmed_)
        pointerTime_ -= fixedStep;
    std::erase_if(pointerMotions_, [](const auto &motion) { return motion.beginSeconds + motion.durationSeconds <= 1e-12; });
    mergeCollisions(starts);
    std::erase_if(drops_, [this](const auto &drop) { return drop.position.y - drop.radius() > height_; });
    if (targetPopulation_ > 0) {
        rainCredit_ += std::max(1.0, static_cast<double>(targetPopulation_) / 20.0) * fixedStep;
        const auto arrivals = static_cast<std::size_t>(rainCredit_ + 1e-12);
        rainCredit_ = std::max(0.0, rainCredit_ - static_cast<double>(arrivals));
        // Cap identities, not condensation; never bank an instantaneous refill after a merge or exit.
        const auto count = std::min(arrivals, targetPopulation_ - std::min(targetPopulation_, drops_.size()));
        for (std::size_t i = 0; i < count; ++i)
            spawn();
    }
}

void DropletSimulation::invalidatePointer()
{
    pointerArmed_ = false;
    pointerTime_ = 0;
    pointerMotions_.clear();
}

void DropletSimulation::mergeCollisions(const std::vector<Vec2> &starts)
{
    const auto count = drops_.size();
    if (count < 2)
        return;

    std::vector<double> radii;
    radii.reserve(count);
    double cellSize = 24;
    for (const auto &drop : drops_) {
        radii.push_back(drop.radius());
        cellSize = std::max(cellSize, 2 * radii.back());
    }
    std::unordered_map<std::uint64_t, std::vector<std::size_t>> grid;
    std::vector<std::pair<std::size_t, std::size_t>> candidates;
    for (std::size_t i = 0; i < count; ++i) {
        const auto &end = drops_[i].position;
        const int left = static_cast<int>(std::floor((std::min(starts[i].x, end.x) - radii[i]) / cellSize));
        const int right = static_cast<int>(std::floor((std::max(starts[i].x, end.x) + radii[i]) / cellSize));
        const int top = static_cast<int>(std::floor((std::min(starts[i].y, end.y) - radii[i]) / cellSize));
        const int bottom = static_cast<int>(std::floor((std::max(starts[i].y, end.y) + radii[i]) / cellSize));
        for (int y = top; y <= bottom; ++y) {
            for (int x = left; x <= right; ++x) {
                const auto key = (std::uint64_t(static_cast<std::uint32_t>(x)) << 32)
                    | static_cast<std::uint32_t>(y);
                auto &cell = grid[key];
                for (const auto j : cell)
                    candidates.emplace_back(j, i);
                cell.push_back(i);
            }
        }
    }
    std::sort(candidates.begin(), candidates.end());
    candidates.erase(std::unique(candidates.begin(), candidates.end()), candidates.end());

    std::vector<std::size_t> parents(count);
    std::iota(parents.begin(), parents.end(), 0);
    const auto root = [&parents](std::size_t i) {
        while (parents[i] != i) {
            parents[i] = parents[parents[i]];
            i = parents[i];
        }
        return i;
    };
    bool merged = false;
    for (const auto &[i, j] : candidates) {
        const Vec2 relative{starts[i].x - starts[j].x, starts[i].y - starts[j].y};
        const Vec2 motion{drops_[i].position.x - drops_[j].position.x - relative.x,
                          drops_[i].position.y - drops_[j].position.y - relative.y};
        const double lengthSquared = motion.x * motion.x + motion.y * motion.y;
        const double t = lengthSquared > 0
            ? std::clamp(-(relative.x * motion.x + relative.y * motion.y) / lengthSquared, 0.0, 1.0)
            : 0;
        const double distance = std::hypot(relative.x + t * motion.x, relative.y + t * motion.y);
        if (distance > radii[i] + radii[j])
            continue;
        auto a = root(i);
        auto b = root(j);
        if (a == b)
            continue;
        if (drops_[a].id > drops_[b].id)
            std::swap(a, b);
        parents[b] = a;
        merged = true;
    }
    if (!merged)
        return;

    // Sum each original drop exactly once, in identity order, regardless of grid visitation.
    std::vector<std::size_t> order(count);
    std::iota(order.begin(), order.end(), 0);
    std::sort(order.begin(), order.end(), [this](auto a, auto b) { return drops_[a].id < drops_[b].id; });
    std::vector<Drop> totals(count);
    for (auto &total : totals)
        total.volume = 0;
    for (const auto i : order) {
        auto &total = totals[root(i)];
        const auto &drop = drops_[i];
        total.id = drops_[root(i)].id;
        total.position.x += drop.position.x * drop.volume;
        total.position.y += drop.position.y * drop.volume;
        total.previousPosition.x += drop.previousPosition.x * drop.volume;
        total.previousPosition.y += drop.previousPosition.y * drop.volume;
        total.velocity.x += drop.velocity.x * drop.volume;
        total.velocity.y += drop.velocity.y * drop.volume;
        total.volume += drop.volume;
    }
    drops_.clear();
    for (auto &total : totals) {
        if (total.volume == 0)
            continue;
        total.position.x /= total.volume;
        total.position.y /= total.volume;
        total.previousPosition.x /= total.volume;
        total.previousPosition.y /= total.volume;
        total.velocity.x /= total.volume;
        total.velocity.y /= total.volume;
        drops_.push_back(total);
    }
    std::sort(drops_.begin(), drops_.end(), [](const auto &a, const auto &b) { return a.id < b.id; });
}

} // namespace arasaka::rain
