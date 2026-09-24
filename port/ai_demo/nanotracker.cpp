/* Copyright (c) 2023, Canaan Bright Sight Co., Ltd
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are met:
 * 1. Redistributions of source code must retain the above copyright
 * notice, this list of conditions and the following disclaimer.
 * 2. Redistributions in binary form must reproduce the above copyright
 * notice, this list of conditions and the following disclaimer in the
 * documentation and/or other materials provided with the distribution.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND
 * CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES,
 * INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF
 * MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
 * DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
 * CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
 * SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
 * BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
 * SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
 * INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
 * WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
 * NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
 * OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.f
 */

#include "aidemo_wrap.h"

#include <algorithm>
#include <cmath>
#include <limits>

namespace {

constexpr int OUTPUT_GRID = 16;
constexpr int OUTPUT_GRID_SIZE = OUTPUT_GRID * OUTPUT_GRID;
constexpr float WINDOW_INFLUENCE = 0.46f;
constexpr float TRACK_LR = 0.34f;
constexpr float PENALTY_K = 0.16f;
constexpr float MIN_BOX_SIZE = 10.0f;

const float kHanning[OUTPUT_GRID] = {
    0.0f, 0.04322727f, 0.1654347f, 0.3454915f,
    0.55226423f, 0.75f, 0.9045085f, 0.9890738f,
    0.9890738f, 0.9045085f, 0.75f, 0.55226423f,
    0.3454915f, 0.1654347f, 0.04322727f, 0.0f
};

struct Candidate {
    float cx;
    float cy;
    float width;
    float height;
    float score;
    float penalty;
};

float foreground_score(float background_logit, float foreground_logit)
{
    if (!std::isfinite(background_logit) || !std::isfinite(foreground_logit)) {
        return std::numeric_limits<float>::quiet_NaN();
    }

    const float diff = background_logit - foreground_logit;
    if (diff >= 0.0f) {
        const float exp_neg_diff = std::exp(-diff);
        return exp_neg_diff / (1.0f + exp_neg_diff);
    }
    return 1.0f / (1.0f + std::exp(diff));
}

float change(float ratio)
{
    return std::max(ratio, 1.0f / ratio);
}

float padded_size(float width, float height)
{
    const float pad = (width + height) * 0.5f;
    return std::sqrt((width + pad) * (height + pad));
}

void bbox_clip(float &x, float &y, float &width, float &height,
               int image_width, int image_height)
{
    x = std::max(0.0f, std::min(x, static_cast<float>(image_width)));
    y = std::max(0.0f, std::min(y, static_cast<float>(image_height)));
    width = std::max(MIN_BOX_SIZE,
                     std::min(width, static_cast<float>(image_width)));
    height = std::max(MIN_BOX_SIZE,
                      std::min(height, static_cast<float>(image_height)));
}

bool valid_positive(float value)
{
    return std::isfinite(value) && value > 0.0f;
}

bool track_post_process(const float *score, const float *box,
                        int image_width, int image_height,
                        float &center_x, float &center_y,
                        float &rect_width, float &rect_height,
                        int &box_x, int &box_y, int &box_width, int &box_height,
                        float &best_score, int crop_size, float context_amount,
                        bool use_scale_override, float scale_z_override)
{
    const float size_sum = rect_width + rect_height;
    const float width_context = rect_width + context_amount * size_sum;
    const float height_context = rect_height + context_amount * size_sum;
    const float search_base_size = std::sqrt(width_context * height_context);
    if (!valid_positive(search_base_size)) {
        return false;
    }

    const float scale_z = use_scale_override
        ? scale_z_override
        : static_cast<float>(crop_size) / search_base_size;
    const float reference_size = padded_size(rect_width * scale_z,
                                             rect_height * scale_z);
    if (!valid_positive(scale_z) || !valid_positive(reference_size)) {
        return false;
    }

    Candidate best = {};
    float best_pscore = -std::numeric_limits<float>::infinity();
    bool found = false;

    for (int i = 0; i < OUTPUT_GRID_SIZE; ++i) {
        const float left = box[i];
        const float top = box[OUTPUT_GRID_SIZE + i];
        const float right = box[OUTPUT_GRID_SIZE * 2 + i];
        const float bottom = box[OUTPUT_GRID_SIZE * 3 + i];
        const float width = left + right;
        const float height = top + bottom;
        if (!valid_positive(left) || !valid_positive(top) ||
            !valid_positive(right) || !valid_positive(bottom) ||
            !valid_positive(width) || !valid_positive(height)) {
            continue;
        }

        const float candidate_size = padded_size(width, height);
        const float scale_change = change(candidate_size / reference_size);
        const float ratio_change = change((rect_width / rect_height) /
                                          (width / height));
        if (!valid_positive(candidate_size) || !std::isfinite(scale_change) ||
            !std::isfinite(ratio_change)) {
            continue;
        }

        const float penalty = std::exp(
            -(ratio_change * scale_change - 1.0f) * PENALTY_K);
        const float raw_score = foreground_score(
            score[i], score[OUTPUT_GRID_SIZE + i]);
        const int row = i / OUTPUT_GRID;
        const int col = i % OUTPUT_GRID;
        const float window = kHanning[row] * kHanning[col];
        const float pscore = penalty * raw_score * (1.0f - WINDOW_INFLUENCE) +
                             window * WINDOW_INFLUENCE;
        if (!std::isfinite(penalty) || !std::isfinite(pscore) ||
            pscore <= best_pscore) {
            continue;
        }

        const float point_x = static_cast<float>((col - OUTPUT_GRID / 2) *
                                                 OUTPUT_GRID);
        const float point_y = static_cast<float>((row - OUTPUT_GRID / 2) *
                                                 OUTPUT_GRID);
        best.cx = point_x + (right - left) * 0.5f;
        best.cy = point_y + (bottom - top) * 0.5f;
        best.width = width;
        best.height = height;
        best.score = raw_score;
        best.penalty = penalty;
        best_pscore = pscore;
        found = true;
    }

    if (!found) {
        return false;
    }

    float new_center_x = center_x + best.cx / scale_z;
    float new_center_y = center_y + best.cy / scale_z;
    const float learning_rate = best.penalty * best.score * TRACK_LR;
    float new_width = rect_width * (1.0f - learning_rate) +
                      best.width / scale_z * learning_rate;
    float new_height = rect_height * (1.0f - learning_rate) +
                       best.height / scale_z * learning_rate;
    if (!std::isfinite(new_center_x) || !std::isfinite(new_center_y) ||
        !valid_positive(new_width) || !valid_positive(new_height)) {
        return false;
    }

    bbox_clip(new_center_x, new_center_y, new_width, new_height,
              image_width, image_height);
    center_x = new_center_x;
    center_y = new_center_y;
    rect_width = new_width;
    rect_height = new_height;
    best_score = best.score;
    box_x = std::max(0, static_cast<int>(new_center_x - new_width * 0.5f));
    box_y = std::max(0, static_cast<int>(new_center_y - new_height * 0.5f));
    box_width = static_cast<int>(new_width);
    box_height = static_cast<int>(new_height);
    return true;
}

} // namespace

static Tracker_box_center nanotracker_post_process_impl(
    float *output_0, float *output_1, FrameSize sensor_size, float thresh,
    float *center_xy_wh, int crop_size, float context_amount,
    bool use_scale_override, float scale_z_override)
{
    Tracker_box_center result = {};
    result.exist = false;
    if (center_xy_wh == nullptr) {
        return result;
    }

    float center_x = center_xy_wh[0];
    float center_y = center_xy_wh[1];
    float rect_width = center_xy_wh[2];
    float rect_height = center_xy_wh[3];
    result.center_xy_wh[0] = center_x;
    result.center_xy_wh[1] = center_y;
    result.center_xy_wh[2] = rect_width;
    result.center_xy_wh[3] = rect_height;

    if (output_0 == nullptr || output_1 == nullptr ||
        sensor_size.width <= 0 || sensor_size.height <= 0 || crop_size <= 0 ||
        !std::isfinite(context_amount) || context_amount < 0.0f ||
        (use_scale_override && !valid_positive(scale_z_override)) ||
        !std::isfinite(center_x) || !std::isfinite(center_y) ||
        !valid_positive(rect_width) || !valid_positive(rect_height)) {
        return result;
    }

    int box_x = 0;
    int box_y = 0;
    int box_width = 0;
    int box_height = 0;
    float best_score = 0.0f;
    if (!track_post_process(output_0, output_1,
                            sensor_size.width, sensor_size.height,
                            center_x, center_y, rect_width, rect_height,
                            box_x, box_y, box_width, box_height, best_score,
                            crop_size, context_amount,
                            use_scale_override, scale_z_override)) {
        return result;
    }

    result.center_xy_wh[0] = center_x;
    result.center_xy_wh[1] = center_y;
    result.center_xy_wh[2] = rect_width;
    result.center_xy_wh[3] = rect_height;
    if (best_score > thresh) {
        result.tracker_box.x = box_x;
        result.tracker_box.y = box_y;
        result.tracker_box.w = box_width;
        result.tracker_box.h = box_height;
        result.tracker_box.score = best_score;
        result.exist = true;
    }
    return result;
}

Tracker_box_center nanotracker_post_process(float *output_0, float *output_1,
                                            FrameSize sensor_size, float thresh,
                                            float *center_xy_wh, int crop_size,
                                            float context_amount)
{
    return nanotracker_post_process_impl(
        output_0, output_1, sensor_size, thresh, center_xy_wh, crop_size,
        context_amount, false, 0.0f);
}

Tracker_box_center nanotracker_post_process_with_scale(
    float *output_0, float *output_1, FrameSize sensor_size, float thresh,
    float *center_xy_wh, int crop_size, float context_amount, float scale_z)
{
    return nanotracker_post_process_impl(
        output_0, output_1, sensor_size, thresh, center_xy_wh, crop_size,
        context_amount, true, scale_z);
}
