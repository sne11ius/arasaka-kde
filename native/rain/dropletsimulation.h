#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <vector>

namespace arasaka::rain {

struct Vec2 {
    double x = 0;
    double y = 0;
    bool operator==(const Vec2 &) const = default;
};

struct PointerSnapshot {
    // Logical pixels, top-left origin. Sequence describes input, not frames. Monotonic sample time
    // must use the same admitted active clock as advance(); held sequences retain their timestamp.
    Vec2 position;
    bool valid = false;
    std::uint64_t sequence = 0;
    double sampleSeconds = 0;
};

struct SurfaceLobe {
    Vec2 offset; // Relative to the owning physical drop; never an independent particle.
    double radius = 1;
    Vec2 axis{0, 1};
    double stretch = 1;
    double weight = 1; // Share of the physical body's water, independent of overlapping optical radii.
};

struct SurfaceJoin {
    // Leaves are 0..3, preceding join results are 4..6 (postorder).
    int left = 0;
    int right = 1;
    double smoothing = 0;
};

struct DropSurface {
    static constexpr std::size_t maximumLobes = 4;
    std::array<SurfaceLobe, maximumLobes> lobes{};
    std::array<SurfaceJoin, maximumLobes - 1> joins{};
    std::size_t count = 1;
    double smoothing = 0; // Signed-height smooth-union width in logical pixels.
};

struct Drop {
    std::uint64_t id = 0;
    Vec2 position;
    Vec2 previousPosition; // Position at entry to the last positive-time displayed frame.
    Vec2 velocity;
    double volume = 1; // Normalized cap volume: radius^3, with cap height = 0.6 * radius.
    // Bounded optical history of a physical merge. Time advances only on fixed active ticks.
    std::vector<SurfaceLobe> merging{};
    double mergeAge = 0;
    double mergeDuration = 0;
    std::array<SurfaceJoin, DropSurface::maximumLobes - 1> mergeJoins{};

    double radius() const;
    double height() const;
    DropSurface surface() const;
    double top() const; // Conservative upper edge of the current solid surface, including liquid necks.
};

class DropletSimulation {
public:
    static constexpr double fixedStep = 1.0 / 120.0;
    static constexpr double maximumFrameSeconds = 0.25;
    static constexpr double maximumSpeed = 900.0;
    static constexpr std::size_t maximumPopulation = 1024;

    // Dimensions are logical pixels in [0, 1e6]. Invalid reset sizes produce an empty, suspended scene.
    void reset(double width, double height, std::uint64_t seed = 1, std::size_t population = 1024);
    // Zero size suspends without losing layout; unchanged/invalid sizes are ignored. Volume is unchanged.
    // Positions/velocities scale proportionally (speed capped); off-bottom drops retire and trails clip.
    void resize(double width, double height);
    // Elapsed active time, NOT an absolute timestamp. Zero/negative/nonfinite time changes nothing.
    // Catchup is capped at 0.25s; excess time is discarded. Call on the owning render thread only.
    void advance(double activeSeconds, const PointerSnapshot &pointer = {});
    // Cancel pending sweeps and require a fresh baseline. Call on pause, leave, or input cancellation.
    void invalidatePointer();
    // One-shot logical-pixel clicks, consumed at the next active fixed tick (bounded, FIFO).
    // Hover/button-release cancellation is separate; host/pause/geometry changes cancel both.
    void queueSplash(Vec2 position);
    void cancelSplashes() { splashes_.clear(); }
    const std::vector<Drop> &drops() const { return drops_; }

private:
    friend struct DropletSimulationTestAccess;
    struct PointerMotion {
        Vec2 start;
        Vec2 end;
        Vec2 impulse;
        double beginSeconds; // Relative to the next fixed tick; negative for partially consumed input.
        double durationSeconds;
    };

    double randomUnit();
    void spawn();
    void consumePointer(const PointerSnapshot &pointer);
    std::uint64_t splash(Vec2 position); // Nudge identity to depin for this tick, or zero for a split/miss.
    void step();
    void mergeCollisions(const std::vector<Vec2> &starts);

    std::vector<Drop> drops_;
    double width_ = 0;
    double height_ = 0;
    double lengthScale_ = 1;
    bool sizeActive_ = false;
    std::size_t targetPopulation_ = 0;
    std::uint64_t randomState_ = 1;
    std::uint64_t nextId_ = 1;
    double accumulator_ = 0;
    double rainCredit_ = 0;
    PointerSnapshot pointer_;
    double pointerTime_ = 0; // Playback endpoint of the last sample, relative to the next fixed tick.
    std::uint64_t pointerSequence_ = 0;
    bool hasPointerSequence_ = false;
    bool pointerArmed_ = false;
    std::vector<PointerMotion> pointerMotions_;
    std::vector<Vec2> splashes_;
};

} // namespace arasaka::rain
