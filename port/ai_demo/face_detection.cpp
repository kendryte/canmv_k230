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
 * OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 */
#include <vector>
#include <memory>
#include <new>
#include <math.h>
#include <string.h>
#include "aidemo_wrap.h"

using std::vector;

#define LOC_SIZE 4
#define CONF_SIZE 2
#define LAND_SIZE 10
#define PI 3.1415926

/**
 * @brief 单张/帧图片大小
 */
typedef struct FrameCHWSize
{
    size_t channel; // 通道
    size_t height;  // 高
    size_t width;   // 宽
} FrameCHWSize;

/**
 * @brief 用于NMS排序的roi对象
 */
typedef struct NMSRoiObj
{
    int index;        // roi对象所在原列表的索引
    float confidence; // roi对象的置信度
} NMSRoiObj;

/**
 * @brief 预测人脸roi信息
 */
typedef struct FaceDetectionInfo
{
    Bbox bbox;                  // 人脸检测框
    SparseLandmarks sparse_kps; // 人脸五官关键点
    float score;                // 人脸检测框置信度
} FaceDetectionInfo;

float obj_thresh_;
float nms_thresh_;
int min_size_ = 0;
int objs_num_ = 0;
NMSRoiObj *so_ = nullptr;    // 指向经过softmax之后首个roi置信度的指针
float *boxes_ = nullptr;     // 指向首个roi检测框的指针
float *landmarks_ = nullptr; // 指向首个roi对应五官关键点的指针
float *g_anchors;

int face_nms_comparator(const void *pa, const void *pb)
{
    NMSRoiObj a = *(NMSRoiObj *)pa;
    NMSRoiObj b = *(NMSRoiObj *)pb;
    float diff = a.confidence - b.confidence;

    if (diff < 0)
        return 1;
    else if (diff > 0)
        return -1;
    return 0;
}

//Implemented in licence_det.cpp
void local_softmax(float *x, float *dx, uint32_t len);

void face_deal_conf(float *conf, NMSRoiObj *so, int size, int &obj_cnt)
{
    float confidence[CONF_SIZE] = {0.0};
    for (uint32_t ww = 0; ww < size; ww++)
    {
        for (uint32_t hh = 0; hh < 2; hh++)
        {
            for (uint32_t cc = 0; cc < CONF_SIZE; cc++)
            {
                confidence[cc] = conf[(hh * CONF_SIZE + cc) * size + ww];
            }
            local_softmax(confidence, confidence, 2);
            so_[obj_cnt].index = obj_cnt;
            so_[obj_cnt].confidence = confidence[1];
            obj_cnt += 1;
        }
    }
}

void face_deal_loc(float *loc, float *boxes, int size, int &obj_cnt)
{
    for (uint32_t ww = 0; ww < size; ww++)
    {
        for (uint32_t hh = 0; hh < 2; hh++)
        {
            for (uint32_t cc = 0; cc < LOC_SIZE; cc++)
            {
                boxes_[obj_cnt * LOC_SIZE + cc] = loc[(hh * LOC_SIZE + cc) * size + ww];
            }
            obj_cnt += 1;
        }
    }
}

void face_deal_landms(float *landms, float *landmarks, int size, int &obj_cnt)
{
    // chw->hwc
    for (uint32_t ww = 0; ww < size; ww++)
    {
        for (uint32_t hh = 0; hh < 2; hh++)
        {
            for (uint32_t cc = 0; cc < LAND_SIZE; cc++)
            {
                landmarks_[obj_cnt * LAND_SIZE + cc] = landms[(hh * LAND_SIZE + cc) * size + ww];
            }
            obj_cnt += 1;
        }
    }
}

Bbox face_get_box(float *boxes, int obj_index)
{
    float cx, cy, w, h;
    cx = boxes_[obj_index * LOC_SIZE + 0];
    cy = boxes_[obj_index * LOC_SIZE + 1];
    w = boxes_[obj_index * LOC_SIZE + 2];
    h = boxes_[obj_index * LOC_SIZE + 3];
    float *g_anchors_obj_index = g_anchors + obj_index * LOC_SIZE;
    cx = g_anchors_obj_index[0] + cx * 0.1 * g_anchors_obj_index[2];
    cy = g_anchors_obj_index[1] + cy * 0.1 * g_anchors_obj_index[3];
    w = g_anchors_obj_index[2] * expf(w * 0.2);
    h = g_anchors_obj_index[3] * expf(h * 0.2);
    Bbox box;
    box.x = cx;
    box.y = cy;
    box.w = w;
    box.h = h;
    return box;
}

SparseLandmarks face_get_landmark(float *landmarks, int obj_index)
{
    SparseLandmarks landmark;
    float *g_anchors_obj_index = g_anchors + obj_index * LOC_SIZE;
    for (uint32_t ll = 0; ll < 5; ll++)
    {
        landmark.points[2 * ll + 0] = g_anchors_obj_index[0] + landmarks_[obj_index * LAND_SIZE + 2 * ll + 0] * 0.1 * g_anchors_obj_index[2];
        landmark.points[2 * ll + 1] = g_anchors_obj_index[1] + landmarks_[obj_index * LAND_SIZE + 2 * ll + 1] * 0.1 * g_anchors_obj_index[3];
    }
    return landmark;
}

float overlap(float x1, float w1, float x2, float w2);

//Implemented in licence_det.cpp
float box_intersection(Bbox a, Bbox b);

//Implemented in licence_det.cpp
float box_union(Bbox a, Bbox b);

//Implemented in licence_det.cpp
float box_iou(Bbox a, Bbox b);

void face_get_final_box(FrameSize &frame_size, vector<FaceDetectionInfo> &results)
{
    int iou_cal_times = 0;
    int i, j, obj_index;
    for (i = 0; i < objs_num_; ++i)
    {
        obj_index = so_[i].index;
        if (so_[i].confidence < obj_thresh_)
            continue;
        FaceDetectionInfo obj;
        obj.bbox = face_get_box(boxes_, obj_index);
        obj.sparse_kps = face_get_landmark(landmarks_, obj_index);

        for (j = i + 1; j < objs_num_; ++j)
        {
            obj_index = so_[j].index;
            if (so_[j].confidence < obj_thresh_)
                continue;
            Bbox b = face_get_box(boxes_, obj_index);
            iou_cal_times += 1;
            if (box_iou(obj.bbox, b) >= nms_thresh_) // thres
                so_[j].confidence = 0;
        }
        obj.score = so_[i].confidence;
        results.push_back(obj);
    }

    // for src img
    int max_src_size = std::max(frame_size.width, frame_size.height);
    for (int i = 0; i < results.size(); ++i)
    {
        auto &l = results[i].sparse_kps;
        for (uint32_t ll = 0; ll < 5; ll++)
        {
            l.points[2 * ll + 0] = l.points[2 * ll + 0] * max_src_size;
            l.points[2 * ll + 1] = l.points[2 * ll + 1] * max_src_size;
        }

        auto &b = results[i].bbox;
        float x1 = (b.x + b.w / 2) * max_src_size;
        float x0 = (b.x - b.w / 2) * max_src_size;
        float y0 = (b.y - b.h / 2) * max_src_size;
        float y1 = (b.y + b.h / 2) * max_src_size;
        x1 = std::max(float(0), std::min(x1, float(frame_size.width)));
        x0 = std::max(float(0), std::min(x0, float(frame_size.width)));
        y0 = std::max(float(0), std::min(y0, float(frame_size.height)));
        y1 = std::max(float(0), std::min(y1, float(frame_size.height)));
        b.x = x0;
        b.y = y0;
        b.w = x1 - x0;
        b.h = y1 - y0;
    }
}

FaceDetectionInfoVector* face_detetion_post_process(float obj_thresh,float nms_thresh,int net_len,float* anchors,FrameSize* frame_size,float** p_outputs_)
{
    int obj_cnt = 0;
    obj_thresh_ = obj_thresh;
    nms_thresh_ = nms_thresh;
    min_size_ = (net_len == 320 ? 200 : 800);
    objs_num_ = min_size_ * (1 + 4 + 16);
    // RAII without vector(size)'s value-initialization: these work buffers are
    // completely overwritten below, so clearing them wastes memory bandwidth.
    std::unique_ptr<NMSRoiObj[]> so_buf(
        new (std::nothrow) NMSRoiObj[objs_num_]);
    std::unique_ptr<float[]> boxes_buf(
        new (std::nothrow) float[(size_t)objs_num_ * LOC_SIZE]);
    std::unique_ptr<float[]> landmarks_buf(
        new (std::nothrow) float[(size_t)objs_num_ * LAND_SIZE]);
    if (!so_buf || !boxes_buf || !landmarks_buf) {
        return NULL;
    }
    so_ = so_buf.get();
    boxes_ = boxes_buf.get();
    landmarks_ = landmarks_buf.get();
    g_anchors = anchors;

    face_deal_conf(p_outputs_[3], so_, 16 * min_size_ / 2, obj_cnt);
    face_deal_conf(p_outputs_[4], so_, 4 * min_size_ / 2, obj_cnt);
    face_deal_conf(p_outputs_[5], so_, 1 * min_size_ / 2, obj_cnt);
    obj_cnt = 0;
    face_deal_loc(p_outputs_[0], boxes_, 16 * min_size_ / 2, obj_cnt);
    face_deal_loc(p_outputs_[1], boxes_, 4 * min_size_ / 2, obj_cnt);
    face_deal_loc(p_outputs_[2], boxes_, 1 * min_size_ / 2, obj_cnt);
    obj_cnt = 0;
    face_deal_landms(p_outputs_[6], landmarks_, 16 * min_size_ / 2, obj_cnt);
    face_deal_landms(p_outputs_[7], landmarks_, 4 * min_size_ / 2, obj_cnt);
    face_deal_landms(p_outputs_[8], landmarks_, 1 * min_size_ / 2, obj_cnt);
    qsort(so_, objs_num_, sizeof(NMSRoiObj), face_nms_comparator);

    vector<FaceDetectionInfo> results;
    try {
        results.reserve(64);
        face_get_final_box(*frame_size, results);
    } catch (...) {
        // Never allow an STL allocation exception to cross the C ABI.
        return NULL;
    }

    FaceDetectionInfoVector* mp_results = (FaceDetectionInfoVector *)malloc(sizeof(FaceDetectionInfoVector));
    if (mp_results == NULL) {
        // Tiny allocation; on OOM report nothing rather than dereferencing NULL.
        return NULL;
    }
    mp_results->vec_len = results.size();
    mp_results->bbox = NULL;
    mp_results->sparse_kps = NULL;
    mp_results->score = NULL;
    if(results.size()>0)
    {
        mp_results->bbox = (Bbox *)malloc((results.size()) * sizeof(Bbox));
        mp_results->sparse_kps = (SparseLandmarks *)malloc((results.size()) * sizeof(SparseLandmarks));
        mp_results->score = (float *)malloc((results.size()) * sizeof(float));
        if (mp_results->bbox == NULL || mp_results->sparse_kps == NULL ||
            mp_results->score == NULL) {
            free(mp_results->bbox);
            free(mp_results->sparse_kps);
            free(mp_results->score);
            mp_results->bbox = NULL;
            mp_results->sparse_kps = NULL;
            mp_results->score = NULL;
            free(mp_results);
            return NULL;
        }
        else
        {
            for(int ret_i = 0;ret_i <results.size();++ret_i)
            {
                (mp_results->bbox + ret_i)->x = results[ret_i].bbox.x;
                (mp_results->bbox + ret_i)->y = results[ret_i].bbox.y;
                (mp_results->bbox + ret_i)->w = results[ret_i].bbox.w;
                (mp_results->bbox + ret_i)->h = results[ret_i].bbox.h;
                hal_rvv_memcpy((mp_results->sparse_kps + ret_i)->points,results[ret_i].sparse_kps.points,sizeof(SparseLandmarks));
                mp_results->score[ret_i] = results[ret_i].score;
            }
        }
    }

    return mp_results;
}

void face_detection_free_outputs(void *context)
{
    FaceDetectionInfoVector *outputs = static_cast<FaceDetectionInfoVector *>(context);
    if (outputs == NULL) {
        return;
    }

    free(outputs->bbox);
    free(outputs->sparse_kps);
    free(outputs->score);
    free(outputs);
}
