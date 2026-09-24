#include <opencv2/imgproc.hpp>
#include <vector>
#include <string>
#include <string.h>
#include <cmath>
#include <algorithm>
#include <stdlib.h>
#include <iostream>
#include <stdint.h>
#include <limits>
// #include <opencv/cv.hpp>
#include <opencv2/core/core.hpp>
#include <opencv2/highgui/highgui.hpp>
#include "aidemo_wrap.h"
#include "aidemo_size.h"
#include "ai_rvv_kernels.h"

using namespace std;


using std::vector;

bool body_seg_postprocess_into(float* data, int num_class, FrameSize ori_shape,
                               FrameSize dst_shape, uint8_t* color,
                               uint8_t* result)
{
    size_t pixel_count, result_size;
    if (data == nullptr || color == nullptr || result == nullptr ||
        num_class <= 0 ||
        !aidemo_checked_image_size(ori_shape.width, ori_shape.height, 1, &pixel_count) ||
        !aidemo_checked_image_size(dst_shape.width, dst_shape.height, 4, &result_size) ||
        pixel_count > SIZE_MAX / (size_t)num_class / sizeof(float)) {
        return false;
    }

    try {
    std::vector<uint32_t> packed_colors((size_t)num_class);
    packed_colors[0] = 0;
    for (int i = 1; i < num_class; ++i) {
        memcpy(&packed_colors[i], color + (size_t)i * 4, sizeof(uint32_t));
    }

    const bool resize_required =
        ori_shape.width != dst_shape.width || ori_shape.height != dst_shape.height;
    cv::Mat source;
    if (resize_required) {
        source = cv::Mat((int)ori_shape.height, (int)ori_shape.width, CV_8UC4);
    } else {
        source = cv::Mat((int)ori_shape.height, (int)ori_shape.width, CV_8UC4,
                         result);
    }

    ai_rvv_hwc_argmax_color(data, pixel_count, (size_t)num_class,
                            packed_colors.data(),
                            reinterpret_cast<uint32_t*>(source.data));

    if (resize_required) {
        cv::Mat destination((int)dst_shape.height, (int)dst_shape.width,
                            CV_8UC4, result);
        cv::resize(source, destination,
                   cv::Size((int)dst_shape.width, (int)dst_shape.height));
    }
    return true;
    } catch (...) {
        return false;
    }
}

uint8_t* body_seg_postprocess(float* data, int num_class, FrameSize ori_shape,
                              FrameSize dst_shape, uint8_t* color)
{
    size_t result_size;
    if (!aidemo_checked_image_size(dst_shape.width, dst_shape.height, 4, &result_size)) {
        return nullptr;
    }
    uint8_t *result = (uint8_t *)malloc(result_size);
    if (result == nullptr ||
        !body_seg_postprocess_into(data, num_class, ori_shape, dst_shape, color,
                                   result)) {
        free(result);
        return nullptr;
    }
    return result;
}

void body_seg_free_output(void *context)
{
    free(context);
}
