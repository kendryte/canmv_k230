#include <gtest/gtest.h>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <set>
#include <stdexcept>
#include <vector>
#include "aidemo_wrap.h"
#include "../../port/ai_demo/aidemo_size.h"

// Only the drawing surface is stubbed. Allocation/cleanup is the production
// helper, with injected failures before and after ownership is established.
namespace cv {
struct Scalar { Scalar(int, int, int, int) {} };
struct Mat {
    int rows, cols;
    void *data;
    Mat(int h, int w, int, void *p) : rows(h), cols(w), data(p) {}
    void setTo(Scalar) { std::memset(data, 0, size_t(rows) * cols * 4); }
};
}
#define CV_8UC4 0
static std::set<void *> allocations;
static int fail_after = -1;
static void *tracked_malloc(size_t size) {
    if (fail_after == 0) return nullptr;
    if (fail_after > 0) --fail_after;
    void *p = std::malloc(size);
    if (p) allocations.insert(p);
    return p;
}
static void tracked_free(void *p) {
    if (!p) return;
    EXPECT_EQ(allocations.erase(p), 1u);
    std::free(p);
}
#define malloc tracked_malloc
#define free tracked_free
#include "../../port/ai_demo/segmentation_output.h"
#undef malloc
#undef free

struct Detection {
    float confidence = .8f;
    int id = 2;
    struct { int x = 1, y = 2, width = 3, height = 4; } box;
};

TEST(AiSegmentationOwnership, BorrowedMaskIsNotFreed) {
    uint8_t mask[64];
    int count;
    fail_after = -1;
    auto output = build_segmentation_output(std::vector<Detection>(1),
        FrameSize{4, 4}, &count, mask, [](cv::Mat &) {});
    EXPECT_EQ(count, 1);
    EXPECT_EQ(output.masks_results, mask);
    ASSERT_NE(output.segOutput, nullptr);
    EXPECT_EQ(output.segOutput[0].box[2], 3);
    tracked_free(output.segOutput);
    EXPECT_TRUE(allocations.empty());
}

TEST(AiSegmentationOwnership, FailurePathsReleaseEveryOwnedAllocation) {
    for (int failure : {0, 1, -1}) {
        fail_after = failure;
        int count;
        auto output = build_segmentation_output(std::vector<Detection>(1),
            FrameSize{4, 4}, &count, nullptr,
            [](cv::Mat &) { throw std::runtime_error("draw failed"); });
        EXPECT_EQ(count, -1);
        EXPECT_EQ(output.masks_results, nullptr);
        EXPECT_EQ(output.segOutput, nullptr);
        EXPECT_TRUE(allocations.empty());
    }
}

TEST(AiSegmentationOwnership, EmptyResultsStillReturnAValidMask) {
    fail_after = -1;
    int count;
    auto output = build_segmentation_output(std::vector<Detection>(),
        FrameSize{4, 4}, &count, nullptr, [](cv::Mat &) {});
    EXPECT_EQ(count, 0);
    ASSERT_NE(output.masks_results, nullptr);
    EXPECT_EQ(output.segOutput, nullptr);
    tracked_free(output.masks_results);
    EXPECT_TRUE(allocations.empty());
    output = build_segmentation_output(std::vector<Detection>(),
        FrameSize{SIZE_MAX, 4}, &count, nullptr, [](cv::Mat &) {});
    EXPECT_EQ(count, -1);
    EXPECT_EQ(output.masks_results, nullptr);
}
