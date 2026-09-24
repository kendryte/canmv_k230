#include "postprocess.h"
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

#include "hal_rvv_ops.h"
#include "ai_rvv_kernels.h"

// #include <opencv/cv.hpp>
#include <opencv2/core/core.hpp>
#include <opencv2/highgui/highgui.hpp>

using namespace std;

#define REG_MAX 16
#define STRIDE_NUM 3
#define STAGE_NUM 3

static ob_det_res decode_anchor_box(const float* record, int shift_x, int shift_y,
                                    int stride, const float* anchor,
                                    float gain, FrameSize frame_size,
                                    FrameSize kmodel_frame_size)
{
    float cx = (record[0] * 2.f - 0.5f + (float)shift_x) * (float)stride;
    float cy = (record[1] * 2.f - 0.5f + (float)shift_y) * (float)stride;
    const float width_scale = record[2] * 2.f;
    const float height_scale = record[3] * 2.f;
    float w = width_scale * width_scale * anchor[0];
    float h = height_scale * height_scale * anchor[1];
    cx -= (kmodel_frame_size.width - frame_size.width * gain) / 2;
    cy -= (kmodel_frame_size.height - frame_size.height * gain) / 2;
    cx /= gain;
    cy /= gain;
    w /= gain;
    h /= gain;

    ob_det_res box{};
    box.x1 = std::max(0, std::min(frame_size.width, int(cx - w / 2.f)));
    box.y1 = std::max(0, std::min(frame_size.height, int(cy - h / 2.f)));
    box.x2 = std::max(0, std::min(frame_size.width, int(cx + w / 2.f)));
    box.y2 = std::max(0, std::min(frame_size.height, int(cy + h / 2.f)));
    return box;
}

static ob_det_res decode_anchor_free_box(const float* record, int shift_x,
                                         int shift_y, int stride, float gain,
                                         FrameSize frame_size,
                                         FrameSize kmodel_frame_size)
{
    float cx = (record[0] + (float)shift_x) * (float)stride;
    float cy = (record[1] + (float)shift_y) * (float)stride;
    float w = exp(record[2]) * (float)stride;
    float h = exp(record[3]) * (float)stride;
    cx -= (kmodel_frame_size.width - frame_size.width * gain) / 2;
    cy -= (kmodel_frame_size.height - frame_size.height * gain) / 2;
    cx /= gain;
    cy /= gain;
    w /= gain;
    h /= gain;

    ob_det_res box{};
    box.x1 = std::max(0, std::min(frame_size.width, int(cx - w / 2.f)));
    box.y1 = std::max(0, std::min(frame_size.height, int(cy - h / 2.f)));
    box.x2 = std::max(0, std::min(frame_size.width, int(cx + w / 2.f)));
    box.y2 = std::max(0, std::min(frame_size.height, int(cy + h / 2.f)));
    return box;
}

vector<ob_det_res> anchorbasedet_decode_infer(float* data, FrameSize kmodel_frame_size, FrameSize frame_size, int stride, int num_class, float ob_det_thresh, float anchors[3][2])
{
    float ratiow = (float)kmodel_frame_size.width / frame_size.width;
    float ratioh = (float)kmodel_frame_size.height / frame_size.height;
    float gain = ratiow < ratioh ? ratiow : ratioh;
    std::vector<ob_det_res> result;
    int grid_size_w = kmodel_frame_size.width / stride;
    int grid_size_h = kmodel_frame_size.height / stride;
    int one_rsize = num_class + 5;
    result.reserve(std::min(grid_size_w * grid_size_h * 3, 256));
    for (int shift_y = 0; shift_y < grid_size_h; shift_y++)
    {
        for (int shift_x = 0; shift_x < grid_size_w; shift_x++)
        {
            int loc = shift_x + shift_y * grid_size_w;
            for (int i = 0; i < 3; i++)
            {
                float* record = data + (loc * 3 + i) * one_rsize;
                float* cls_ptr = record + 5;
                ob_det_res decoded_box{};
                bool box_decoded = false;
                for (int cls = 0; cls < num_class; cls++)
                {
                    float score = (cls_ptr[cls]) * (record[4]);
                    if (score > ob_det_thresh)
                    {
                        if (!box_decoded) {
                            decoded_box = decode_anchor_box(
                                record, shift_x, shift_y, stride, anchors[i],
                                gain, frame_size, kmodel_frame_size);
                            box_decoded = true;
                        }
                        ob_det_res box = decoded_box;
                        box.score = score;
                        box.label_index = cls;
                        result.push_back(box);
                    }
                }
            }
        }
    }
    return result;
}

vector<vector<ob_det_res>> anchorbasedet_decode_infer_class(float* data, FrameSize kmodel_frame_size, FrameSize frame_size, int stride, int num_class, float ob_det_thresh, float anchors[3][2])
{
    float ratiow = (float)kmodel_frame_size.width / frame_size.width;
    float ratioh = (float)kmodel_frame_size.height / frame_size.height;
    float gain = ratiow < ratioh ? ratiow : ratioh;
    std::vector<std::vector<ob_det_res>> result(num_class);
    int grid_size_w = kmodel_frame_size.width / stride;
    int grid_size_h = kmodel_frame_size.height / stride;
    int one_rsize = num_class + 5;
    for (int shift_y = 0; shift_y < grid_size_h; shift_y++)
    {
        for (int shift_x = 0; shift_x < grid_size_w; shift_x++)
        {
            int loc = shift_x + shift_y * grid_size_w;
            for (int i = 0; i < 3; i++)
            {
                float* record = data + (loc * 3 + i) * one_rsize;
                float* cls_ptr = record + 5;
                ob_det_res decoded_box{};
                bool box_decoded = false;
                for (int cls = 0; cls < num_class; cls++)
                {
                    float score = (cls_ptr[cls]) * (record[4]);
                    if (score > ob_det_thresh)
                    {
                        if (!box_decoded) {
                            decoded_box = decode_anchor_box(
                                record, shift_x, shift_y, stride, anchors[i],
                                gain, frame_size, kmodel_frame_size);
                            box_decoded = true;
                        }
                        ob_det_res box = decoded_box;
                        box.score = score;
                        box.label_index = cls;
                        result[cls].push_back(box);
                    }
                }
            }
        }
    }
    return result;
}


vector<ob_det_res> anchorfreedet_decode_infer(float* data, FrameSize kmodel_frame_size, FrameSize frame_size, int stride, int num_class, float ob_det_thresh)
{
    float ratiow = (float)kmodel_frame_size.width / frame_size.width;
    float ratioh = (float)kmodel_frame_size.height / frame_size.height;
    float gain = ratiow < ratioh ? ratiow : ratioh;
    std::vector<ob_det_res> result;
    int grid_size_w = kmodel_frame_size.width / stride;
    int grid_size_h = kmodel_frame_size.height / stride;
    int one_rsize = num_class + 5;
    result.reserve(std::min(grid_size_w * grid_size_h, 256));
    for (int shift_y = 0; shift_y < grid_size_h; shift_y++)
    {
        for (int shift_x = 0; shift_x < grid_size_w; shift_x++)
        {

            int loc = shift_x + shift_y * grid_size_w;
            {
                float* record = data + loc * one_rsize;
                float* cls_ptr = record + 5;
                ob_det_res decoded_box{};
                bool box_decoded = false;
                for (int cls = 0; cls < num_class; cls++)
                {
                    float score = record[4] * cls_ptr[cls];
                    if (score > ob_det_thresh)
                    {
                        if (!box_decoded) {
                            decoded_box = decode_anchor_free_box(
                                record, shift_x, shift_y, stride, gain,
                                frame_size, kmodel_frame_size);
                            box_decoded = true;
                        }
                        ob_det_res box = decoded_box;
                        box.score = score;
                        box.label_index = cls;
                        result.push_back(box);
                    }
                }
            }
        }
    }
    return result;
}

vector<vector<ob_det_res>> anchorfreedet_decode_infer_class(float* data, FrameSize kmodel_frame_size, FrameSize frame_size, int stride, int num_class, float ob_det_thresh)
{
    float ratiow = (float)kmodel_frame_size.width / frame_size.width;
    float ratioh = (float)kmodel_frame_size.height / frame_size.height;
    float gain = ratiow < ratioh ? ratiow : ratioh;
    std::vector<std::vector<ob_det_res>> result(num_class);
    int grid_size_w = kmodel_frame_size.width / stride;
    int grid_size_h = kmodel_frame_size.height / stride;
    int one_rsize = num_class + 5;
    for (int shift_y = 0; shift_y < grid_size_h; shift_y++)
    {
        for (int shift_x = 0; shift_x < grid_size_w; shift_x++)
        {

            int loc = shift_x + shift_y * grid_size_w;
            {
                float* record = data + loc * one_rsize;
                float* cls_ptr = record + 5;
                ob_det_res decoded_box{};
                bool box_decoded = false;
                for (int cls = 0; cls < num_class; cls++)
                {
                    float score = record[4] * cls_ptr[cls];
                    if (score > ob_det_thresh)
                    {
                        if (!box_decoded) {
                            decoded_box = decode_anchor_free_box(
                                record, shift_x, shift_y, stride, gain,
                                frame_size, kmodel_frame_size);
                            box_decoded = true;
                        }
                        ob_det_res box = decoded_box;
                        box.score = score;
                        box.label_index = cls;
                        result[cls].push_back(box);
                    }
                }
            }
        }
    }
    return result;
}

void nms(vector<ob_det_res>& input_boxes, float ob_nms_thresh)
{
    std::sort(input_boxes.begin(), input_boxes.end(), [](ob_det_res a, ob_det_res b) { return a.score > b.score; });
    const size_t box_count = input_boxes.size();
    std::vector<float> vArea(box_count);
    std::vector<uint8_t> suppressed(box_count, 0);
    for (size_t i = 0; i < box_count; ++i)
    {
        vArea[i] = (input_boxes[i].x2 - input_boxes[i].x1 + 1)
            * (input_boxes[i].y2 - input_boxes[i].y1 + 1);
    }
    for (size_t i = 0; i < box_count; ++i)
    {
        if (suppressed[i]) {
            continue;
        }
        for (size_t j = i + 1; j < box_count; ++j)
        {
            if (suppressed[j]) {
                continue;
            }
            float xx1 = std::max(input_boxes[i].x1, input_boxes[j].x1);
            float yy1 = std::max(input_boxes[i].y1, input_boxes[j].y1);
            float xx2 = std::min(input_boxes[i].x2, input_boxes[j].x2);
            float yy2 = std::min(input_boxes[i].y2, input_boxes[j].y2);
            float w = std::max(float(0), xx2 - xx1 + 1);
            float h = std::max(float(0), yy2 - yy1 + 1);
            float inter = w * h;
            float ovr = inter / (vArea[i] + vArea[j] - inter);
            if (ovr >= ob_nms_thresh)
            {
                suppressed[j] = 1;
            }
        }
    }
    size_t output_index = 0;
    for (size_t i = 0; i < box_count; ++i) {
        if (!suppressed[i]) {
            if (output_index != i) {
                input_boxes[output_index] = input_boxes[i];
            }
            ++output_index;
        }
    }
    input_boxes.resize(output_index);
}

static ob_det_res* copy_detection_results(const vector<ob_det_res>& results, int* results_size)
{
    *results_size = static_cast<int>(results.size());
    if (results.empty()) {
        return nullptr;
    }

    ob_det_res* output = static_cast<ob_det_res*>(
        malloc(results.size() * sizeof(ob_det_res)));
    if (output == nullptr) {
        *results_size = 0;
        return nullptr;
    }
    std::copy(results.begin(), results.end(), output);
    return output;
}

float fast_exp(float x)
{
    union {
        uint32_t i;
        float f;
    } v{};
    v.i = (1 << 23) * (1.4426950409 * x + 126.93490512f);
    return v.f;
}

float sigmoid(float x)
{
    return 1.0f / (1.0f + fast_exp(-x));
    //return 1.0f / (1.0f + exp(-x));
}

ob_det_res disPred2Bbox(const float*& dfl_det, int label, float score, int x, int y, int stride, int reg_max, int input_height,int input_width,float ratiow, float ratioh, float gain,FrameSize frame_size, FrameSize kmodel_frame_size)
{
    float ct_x = x * stride;
    float ct_y = y * stride;

    ct_x -= ((kmodel_frame_size.width - frame_size.width * gain) / 2);
    ct_y -= ((kmodel_frame_size.height - frame_size.height * gain) / 2);
    ct_x /= gain;
    ct_y /= gain;

    float dis_pred[4];
    for (int i = 0; i < 4; i++)
    {
        const float *logits = dfl_det + i * (reg_max + 1);
        const float alpha = *std::max_element(logits, logits + reg_max + 1);
        float denominator = 0.0f;
        float weighted_sum = 0.0f;
        for (int j = 0; j < reg_max + 1; j++) {
            const float value = fast_exp(logits[j] - alpha);
            denominator += value;
            weighted_sum += j * value;
        }
        dis_pred[i] = weighted_sum / denominator * stride;
    }
    float xmin = (std::max)(ct_x - dis_pred[0] /gain, .0f);
    float ymin = (std::max)(ct_y - dis_pred[1] /gain, .0f);
    float xmax = (std::min)(ct_x + dis_pred[2] / gain, (float)frame_size.width);
    float ymax = (std::min)(ct_y + dis_pred[3] / gain, (float)frame_size.height);

    return ob_det_res{ xmin, ymin, xmax, ymax, score, label};
}


static void gfldet_decode_infer(float* pred, int feat_w, int feat_h, int stride,
                               std::vector<ob_det_res>& results,
                               FrameSize frame_size, FrameSize kmodel_frame_size,
                               int num_class, float ob_det_thresh)
{
    if (num_class <= 0) {
        return;
    }
    int reg_max = REG_MAX;
    float ratiow = (float)kmodel_frame_size.width / frame_size.width;
    float ratioh = (float)kmodel_frame_size.height / frame_size.height;
    float gain = ratiow < ratioh ? ratiow : ratioh;
    const int num_points = feat_w * feat_h;
    const int num_channels = num_class + (reg_max + 1) * 4;
    results.reserve(results.size() + std::min(num_points, 256));
    for (int idx = 0; idx < num_points; idx++)
    {
        int ct_x = idx % feat_w;
        int ct_y = idx / feat_w;
        const float* class_logits = pred + idx * num_channels;
        float max_logit;
        int cur_label = (int)ai_rvv_f32_argmax(
            class_logits, (size_t)num_class, &max_logit);
        const float score = sigmoid(max_logit);

        if (score > ob_det_thresh)
        {
            const float* bbox_pred = pred + idx * num_channels + num_class;
            results.push_back(disPred2Bbox(bbox_pred, cur_label, score, ct_x, ct_y, stride, reg_max, kmodel_frame_size.height, kmodel_frame_size.width, ratiow, ratioh, gain, frame_size, kmodel_frame_size));
        }
    }
}

static void gfldet_decode_infer_class(
    float* pred, int feat_w, int feat_h, int stride,
    std::vector<std::vector<ob_det_res>>& results, FrameSize frame_size,
    FrameSize kmodel_frame_size, int num_class, float ob_det_thresh)
{
    if (num_class <= 0) {
        return;
    }
    int reg_max = REG_MAX;
    float ratiow = (float)kmodel_frame_size.width / frame_size.width;
    float ratioh = (float)kmodel_frame_size.height / frame_size.height;
    float gain = ratiow < ratioh ? ratiow : ratioh;
    const int num_points = feat_w * feat_h;
    const int num_channels = num_class + (reg_max + 1) * 4;
    for (int idx = 0; idx < num_points; idx++)
    {
        int ct_x = idx % feat_w;
        int ct_y = idx / feat_w;
        const float* class_logits = pred + idx * num_channels;
        float max_logit;
        int cur_label = (int)ai_rvv_f32_argmax(
            class_logits, (size_t)num_class, &max_logit);
        const float score = sigmoid(max_logit);

        if (score > ob_det_thresh)
        {
            const float* bbox_pred = pred + idx * num_channels + num_class;
            ob_det_res tmp_res = disPred2Bbox(bbox_pred, cur_label, score, ct_x, ct_y, stride, reg_max, kmodel_frame_size.height, kmodel_frame_size.width, ratiow, ratioh, gain, frame_size, kmodel_frame_size);
            results[tmp_res.label_index].push_back(tmp_res);
        }
    }
}

static vector<ob_det_res> merge_stage_boxes(const vector<ob_det_res>& box0,
                                            const vector<ob_det_res>& box1,
                                            const vector<ob_det_res>& box2)
{
    vector<ob_det_res> merged;
    merged.reserve(box0.size() + box1.size() + box2.size());
    merged.insert(merged.end(), box2.begin(), box2.end());
    merged.insert(merged.end(), box1.begin(), box1.end());
    merged.insert(merged.end(), box0.begin(), box0.end());
    return merged;
}

static void merge_class_boxes(vector<vector<ob_det_res>>& box0,
                              const vector<vector<ob_det_res>>& box1,
                              const vector<vector<ob_det_res>>& box2,
                              vector<ob_det_res>& results,
                              float ob_nms_thresh)
{
    size_t result_count = 0;
    for (size_t i = 0; i < box0.size(); ++i) {
        vector<ob_det_res> merged =
            merge_stage_boxes(box0[i], box1[i], box2[i]);
        nms(merged, ob_nms_thresh);
        result_count += merged.size();
        box0[i] = std::move(merged);
    }

    results.reserve(result_count);
    for (size_t i = box0.size(); i > 0; --i) {
        const vector<ob_det_res>& class_boxes = box0[i - 1];
        results.insert(results.end(), class_boxes.begin(), class_boxes.end());
    }
}



ob_det_res* anchorbasedet_post_process(float* data0, float* data1, float* data2, FrameSize kmodel_frame_size, FrameSize frame_size, int* strides, int num_class, float ob_det_thresh, float ob_nms_thresh, float* anchors, bool nms_option, int* results_size)
{
    if (results_size != nullptr) *results_size = 0;
    try {
    float *output_0 = data0;
    float *output_1 = data1;
    float *output_2 = data2;

    float anchors_0[3][2];
    float anchors_1[3][2];
    float anchors_2[3][2];
    for(int i = 0; i < 3; i++)
    {
        for(int j = 0; j < 2; j++)
        {
            anchors_0[i][j] = anchors[i*2+j];
        }

    }

    for(int i = 0; i < 3; i++)
    {
        for(int j = 0; j < 2; j++)
        {
            anchors_1[i][j] = anchors[1*2*3 + i*2 + j];
        }

    }

    for(int i = 0; i < 3; i++)
    {
        for(int j = 0; j < 2; j++)
        {
            anchors_2[i][j] = anchors[2*2*3 + i*2 + j];
        }

    }


    vector<ob_det_res> results;
    if (nms_option)
    {
        vector<ob_det_res> box0, box1, box2;
        box0 = anchorbasedet_decode_infer(output_0, kmodel_frame_size, frame_size, strides[0], num_class, ob_det_thresh, anchors_0);
        box1 = anchorbasedet_decode_infer(output_1, kmodel_frame_size, frame_size, strides[1], num_class, ob_det_thresh, anchors_1);
        box2 = anchorbasedet_decode_infer(output_2, kmodel_frame_size, frame_size, strides[2], num_class, ob_det_thresh, anchors_2);

        results = merge_stage_boxes(box0, box1, box2);
        nms(results, ob_nms_thresh);
    }
    else
    {
        vector<vector<ob_det_res>> box0, box1, box2;

        box0 = anchorbasedet_decode_infer_class(output_0, kmodel_frame_size, frame_size, strides[0], num_class, ob_det_thresh, anchors_0);
        box1 = anchorbasedet_decode_infer_class(output_1, kmodel_frame_size, frame_size, strides[1], num_class, ob_det_thresh, anchors_1);
        box2 = anchorbasedet_decode_infer_class(output_2, kmodel_frame_size, frame_size, strides[2], num_class, ob_det_thresh, anchors_2);

        merge_class_boxes(box0, box1, box2, results, ob_nms_thresh);
    }

    return copy_detection_results(results, results_size);
    } catch (...) {
        if (results_size != nullptr) *results_size = 0;
        return nullptr;
    }
}


ob_det_res* anchorfreedet_post_process(float* data0, float* data1, float* data2, FrameSize kmodel_frame_size, FrameSize frame_size, int* strides, int num_class, float ob_det_thresh, float ob_nms_thresh, bool nms_option, int* results_size)
{
    if (results_size != nullptr) *results_size = 0;
    try {
    float *output_0 = data0;
    float *output_1 = data1;
    float *output_2 = data2;


    vector<ob_det_res> results;
    if (nms_option)
    {
        vector<ob_det_res> box0, box1, box2;

        box0 = anchorfreedet_decode_infer(output_0, kmodel_frame_size, frame_size, strides[0], num_class, ob_det_thresh);
        box1 = anchorfreedet_decode_infer(output_1, kmodel_frame_size, frame_size, strides[1], num_class, ob_det_thresh);
        box2 = anchorfreedet_decode_infer(output_2, kmodel_frame_size, frame_size, strides[2], num_class, ob_det_thresh);

        results = merge_stage_boxes(box0, box1, box2);
        nms(results, ob_nms_thresh);
    }
    else
    {
        vector<vector<ob_det_res>> box0, box1, box2;

        box0 = anchorfreedet_decode_infer_class(output_0, kmodel_frame_size, frame_size, strides[0], num_class, ob_det_thresh);
        box1 = anchorfreedet_decode_infer_class(output_1, kmodel_frame_size, frame_size, strides[1], num_class, ob_det_thresh);
        box2 = anchorfreedet_decode_infer_class(output_2, kmodel_frame_size, frame_size, strides[2], num_class, ob_det_thresh);

        merge_class_boxes(box0, box1, box2, results, ob_nms_thresh);
    }

    return copy_detection_results(results, results_size);
    } catch (...) {
        if (results_size != nullptr) *results_size = 0;
        return nullptr;
    }
}


ob_det_res* gfldet_post_process(float* data0, float* data1, float* data2, FrameSize kmodel_frame_size, FrameSize frame_size, int* strides, int num_class, float ob_det_thresh, float ob_nms_thresh, bool nms_option, int* results_size)
{
    if (results_size != nullptr) *results_size = 0;
    try {
    float *output_0 = data0;
    float *output_1 = data1;
    float *output_2 = data2;

    int feature_widths[STAGE_NUM];
    int feature_heights[STAGE_NUM];
    for (int i = 0; i < STAGE_NUM; i++)
    {
        int stride = strides[i];
        feature_widths[i] = ceil((float)kmodel_frame_size.width / stride);
        feature_heights[i] = ceil((float)kmodel_frame_size.height / stride);
    }

    vector<ob_det_res> results;
    if(nms_option)
    {
        vector<ob_det_res> b0, b1, b2;

        gfldet_decode_infer(output_0, feature_widths[0], feature_heights[0],
                            strides[0], b0, frame_size, kmodel_frame_size,
                            num_class, ob_det_thresh);
        gfldet_decode_infer(output_1, feature_widths[1], feature_heights[1],
                            strides[1], b1, frame_size, kmodel_frame_size,
                            num_class, ob_det_thresh);
        gfldet_decode_infer(output_2, feature_widths[2], feature_heights[2],
                            strides[2], b2, frame_size, kmodel_frame_size,
                            num_class, ob_det_thresh);

        results = merge_stage_boxes(b0, b1, b2);
        nms(results, ob_nms_thresh);
    }
    else
    {
        vector<vector<ob_det_res>> b0(num_class), b1(num_class), b2(num_class);

        gfldet_decode_infer_class(
            output_0, feature_widths[0], feature_heights[0], strides[0], b0,
            frame_size, kmodel_frame_size, num_class, ob_det_thresh);
        gfldet_decode_infer_class(
            output_1, feature_widths[1], feature_heights[1], strides[1], b1,
            frame_size, kmodel_frame_size, num_class, ob_det_thresh);
        gfldet_decode_infer_class(
            output_2, feature_widths[2], feature_heights[2], strides[2], b2,
            frame_size, kmodel_frame_size, num_class, ob_det_thresh);

        merge_class_boxes(b0, b1, b2, results, ob_nms_thresh);
    }
    return copy_detection_results(results, results_size);
    } catch (...) {
        if (results_size != nullptr) *results_size = 0;
        return nullptr;
    }
}

bool seg_post_process_into(float* data, int num_class, FrameSize ori_shape,
                           FrameSize dst_shape, uint8_t* result)
{
    if (data == nullptr || result == nullptr || num_class <= 0 ||
        ori_shape.width <= 0 || ori_shape.height <= 0 ||
        dst_shape.width <= 0 || dst_shape.height <= 0) {
        return false;
    }

    try {
    vector<uint32_t> packed_colors((size_t)num_class);
    packed_colors[0] = 128;
    for (int idx = 1; idx < num_class; ++idx) {
        const uint8_t channels[4] = {
            128,
            (uint8_t)max(255 - (num_class - idx) * 100, 0),
            (uint8_t)min(idx * 80, 255),
            (uint8_t)max(255 - idx * 60, 0)
        };
        memcpy(&packed_colors[idx], channels, sizeof(uint32_t));
    }

    const bool resize_required =
        ori_shape.width != dst_shape.width || ori_shape.height != dst_shape.height;
    cv::Mat source;
    if (resize_required) {
        source = cv::Mat(ori_shape.height, ori_shape.width, CV_8UC4);
    } else {
        source = cv::Mat(ori_shape.height, ori_shape.width, CV_8UC4, result);
    }

    ai_rvv_hwc_argmax_color(
        data, (size_t)ori_shape.width * ori_shape.height, (size_t)num_class,
        packed_colors.data(), reinterpret_cast<uint32_t*>(source.data));

    if (resize_required) {
        cv::Mat destination(dst_shape.height, dst_shape.width, CV_8UC4, result);
        cv::resize(source, destination,
                   cv::Size(dst_shape.width, dst_shape.height));
    }
    return true;
    } catch (...) {
        return false;
    }
}

uint8_t* seg_post_process(float* data, int num_class, FrameSize ori_shape,
                          FrameSize dst_shape)
{
    if (dst_shape.height <= 0 ||
        (size_t)dst_shape.width > std::numeric_limits<size_t>::max() /
                                      (size_t)dst_shape.height / 4) {
        return nullptr;
    }
    const size_t result_size =
        (size_t)dst_shape.width * (size_t)dst_shape.height * 4;
    uint8_t *result = (uint8_t *)malloc(result_size);
    if (result == nullptr ||
        !seg_post_process_into(data, num_class, ori_shape, dst_shape, result)) {
        free(result);
        return nullptr;
    }
    return result;
}
