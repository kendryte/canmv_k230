#ifndef AIDEMO_SEGMENTATION_OUTPUT_H
#define AIDEMO_SEGMENTATION_OUTPUT_H

#include "aidemo_wrap.h"
#include "aidemo_size.h"
#include <climits>
#include <memory>

// Supplied masks are borrowed. Keep native allocations owned until drawing
// and result conversion succeed, including OpenCV exception paths.
template <typename Results, typename Draw>
static SegOutputs build_segmentation_output(const Results &results,
    FrameSize display, int *box_cnt, uint8_t *mask_output, Draw draw)
{
    *box_cnt = -1;
    size_t mask_bytes;
    if (!aidemo_checked_image_size(display.width, display.height, 4, &mask_bytes)
        || results.size() > (size_t)INT_MAX
        || results.size() > SIZE_MAX / sizeof(SegOutput)) return {};
    try {
        std::unique_ptr<uint8_t, decltype(&free)> owned_mask(nullptr, free);
        if (mask_output == nullptr) {
            owned_mask.reset(static_cast<uint8_t *>(malloc(mask_bytes)));
            if (!owned_mask) return {};
            mask_output = owned_mask.get();
        }
        std::unique_ptr<SegOutput, decltype(&free)> records(nullptr, free);
        if (!results.empty()) {
            records.reset(static_cast<SegOutput *>(malloc(results.size() * sizeof(SegOutput))));
            if (!records) return {};
        }
        cv::Mat frame(display.height, display.width, CV_8UC4, mask_output);
        frame.setTo(cv::Scalar(0, 0, 0, 0));
        draw(frame);
        for (size_t i = 0; i < results.size(); ++i) {
            records.get()[i].confidence = results[i].confidence;
            records.get()[i].id = results[i].id;
            records.get()[i].box[0] = results[i].box.x;
            records.get()[i].box[1] = results[i].box.y;
            records.get()[i].box[2] = results[i].box.width;
            records.get()[i].box[3] = results[i].box.height;
        }
        SegOutputs output = {};
        output.masks_results = mask_output;
        output.segOutput = records.release();
        owned_mask.release();
        *box_cnt = (int)results.size();
        return output;
    } catch (...) {
        return {};
    }
}

#endif
