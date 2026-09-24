#include <gtest/gtest.h>
#include "ai_rvv_kernels.h"
#include <cmath>
#include <limits>
#include <vector>

TEST(AiRvvKernels, AffineAndReverseHandleTailLengths) {
    for (size_t count : {0u, 1u, 3u, 31u, 32u, 33u, 257u}) {
        std::vector<float> data(count + 1, 12345.f);
        for (size_t i = 0; i < count; ++i) data[i] = float(i);
        ai_rvv_f32_affine_inplace(data.data(), count, 2.f, 3.f, -1.f);
        for (size_t i = 0; i < count; ++i)
            EXPECT_FLOAT_EQ(data[i], (float(i) - 2.f) * 3.f - 1.f);
        EXPECT_FLOAT_EQ(data[count], 12345.f);
        ai_rvv_f32_reverse_affine_inplace(data.data(), count, 4.f, 2.f, 1.f);
        for (size_t i = 0; i < count; ++i)
            EXPECT_FLOAT_EQ(data[i], (4.f - ((float(i) - 2.f) * 3.f - 1.f)) * 2.f + 1.f);
    }
}

TEST(AiRvvKernels, AudioOperationsMatchReference) {
    for (size_t count : {1u, 2u, 17u, 129u}) {
        std::vector<float> data(count), original(count), weights(count, .5f);
        for (size_t i = 0; i < count; ++i) data[i] = original[i] = float(i) - 5.f;
        ai_rvv_f32_preemphasis_inplace(data.data(), count, .97f);
        EXPECT_NEAR(data[0], original[0] * .03f, 1e-5f);
        for (size_t i = 1; i < count; ++i)
            EXPECT_NEAR(data[i], original[i] - .97f * original[i - 1], 1e-5f);
        auto before = data;
        ai_rvv_f32_mul_inplace(data.data(), weights.data(), count);
        ai_rvv_f32_sub_scalar_inplace(data.data(), count, 2.f);
        for (size_t i = 0; i < count; ++i)
            EXPECT_FLOAT_EQ(data[i], before[i] * .5f - 2.f);
        std::vector<float> power(count);
        ai_rvv_f32_power_spectrum(power.data(), data.data(), weights.data(), count);
        for (size_t i = 0; i < count; ++i)
            EXPECT_NEAR(power[i], data[i] * data[i] + .25f, 1e-4f);
    }
    ai_rvv_f32_preemphasis_inplace(nullptr, 0, .97f);
}

TEST(AiRvvKernels, ArgmaxPreservesFirstTieAndStrides) {
    float max_value;
    float values[] = {-4.f, -1.f, -1.f, -3.f};
    EXPECT_EQ(ai_rvv_f32_argmax(values, 4, &max_value), 1u);
    EXPECT_FLOAT_EQ(max_value, -1.f);
    float strided[] = {-4.f, 99.f, -1.f, 99.f, -1.f, 99.f};
    EXPECT_EQ(ai_rvv_f32_argmax_strided(strided, 3, 2, &max_value), 1u);
    float nan_values[] = {std::numeric_limits<float>::quiet_NaN(), 4.f};
    EXPECT_EQ(ai_rvv_f32_argmax(nan_values, 2, &max_value), 0u);
    EXPECT_TRUE(std::isnan(max_value));
    EXPECT_EQ(ai_rvv_f32_argmax(nullptr, 0, &max_value), 0u);
    EXPECT_FLOAT_EQ(max_value, 0.f);
}

TEST(AiRvvKernels, SegmentationUsesArgmaxWithoutChangingScores) {
    float scores[] = {-3.f, -1.f, -2.f, 4.f, 4.f, 1.f, 0.f, 2.f, 3.f};
    std::vector<float> original(scores, scores + 9);
    uint32_t colors[] = {0, 0x11223344, 0x55667788};
    uint32_t output[] = {0, 0, 0, 0xdeadbeef};
    ai_rvv_hwc_argmax_color(scores, 3, 3, colors, output);
    EXPECT_EQ(output[0], colors[1]);
    EXPECT_EQ(output[1], colors[0]);
    EXPECT_EQ(output[2], colors[2]);
    EXPECT_EQ(output[3], 0xdeadbeef);
    EXPECT_EQ(std::vector<float>(scores, scores + 9), original);
}
