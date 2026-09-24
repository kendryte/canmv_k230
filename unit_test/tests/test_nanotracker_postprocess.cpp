#include <gtest/gtest.h>
#include <array>
#include <cmath>
#include <limits>
#include "aidemo_wrap.h"

namespace {
struct Input {
    std::array<float, 512> scores{};
    std::array<float, 1024> boxes{};
    std::array<float, 4> state{{320, 240, 60, 40}};
    Input() {
        boxes.fill(32);
        for (int i = 0; i < 256; ++i) scores[i + 256] = 2;
    }
    Tracker_box_center run(float threshold = .1f) {
        return nanotracker_post_process(scores.data(), boxes.data(), {640, 480},
                                       threshold, state.data(), 127, .5f);
    }
};

void expect_same(const Tracker_box_center &a, const Tracker_box_center &b) {
    ASSERT_EQ(a.exist, b.exist);
    for (int i = 0; i < 4; ++i) EXPECT_FLOAT_EQ(a.center_xy_wh[i], b.center_xy_wh[i]);
    EXPECT_EQ(a.tracker_box.x, b.tracker_box.x);
    EXPECT_EQ(a.tracker_box.y, b.tracker_box.y);
    EXPECT_EQ(a.tracker_box.w, b.tracker_box.w);
    EXPECT_EQ(a.tracker_box.h, b.tracker_box.h);
    EXPECT_FLOAT_EQ(a.tracker_box.score, b.tracker_box.score);
}
}

TEST(NanoTrackerPostprocess, LegacyCallAndExplicitScaleAgreeWithoutMutatingInputs) {
    Input input;
    const Input before = input;
    auto legacy = input.run();
    ASSERT_TRUE(legacy.exist);
    const float scale = 127.0f / std::sqrt((60.0f + 50.0f) * (40.0f + 50.0f));
    auto explicit_scale = nanotracker_post_process_with_scale(
        input.scores.data(), input.boxes.data(), {640, 480}, .1f,
        input.state.data(), 127, .5f, scale);
    expect_same(legacy, explicit_scale);
    EXPECT_EQ(input.scores, before.scores);
    EXPECT_EQ(input.boxes, before.boxes);
    EXPECT_EQ(input.state, before.state);
}

TEST(NanoTrackerPostprocess, CallsHaveNoSharedTrackingState) {
    Input first;
    auto expected = first.run();
    Input second;
    second.state = {{100, 100, 20, 30}};
    ASSERT_TRUE(second.run().exist);
    expect_same(first.run(), expected);
}

TEST(NanoTrackerPostprocess, ExtremeLogitsRemainFiniteAndThresholdIsPreserved) {
    Input input;
    input.scores.fill(1000);
    auto equal = input.run();
    ASSERT_TRUE(equal.exist);
    EXPECT_FLOAT_EQ(equal.tracker_box.score, .5f);
    EXPECT_FALSE(input.run(.5f).exist);
    for (int i = 0; i < 256; ++i) input.scores[i] = -1000;
    auto certain = input.run();
    ASSERT_TRUE(certain.exist);
    EXPECT_FLOAT_EQ(certain.tracker_box.score, 1);
    for (float value : certain.center_xy_wh) EXPECT_TRUE(std::isfinite(value));
}

TEST(NanoTrackerPostprocess, InvalidCandidatesDoNotCorruptState) {
    Input input;
    input.boxes.fill(std::numeric_limits<float>::quiet_NaN());
    auto output = input.run();
    EXPECT_FALSE(output.exist);
    for (int i = 0; i < 4; ++i) EXPECT_EQ(output.center_xy_wh[i], input.state[i]);
    input.boxes.fill(0);
    EXPECT_FALSE(input.run().exist);
    EXPECT_FALSE(nanotracker_post_process(nullptr, input.boxes.data(), {640, 480},
                                         .1f, input.state.data(), 127, .5f).exist);
}
