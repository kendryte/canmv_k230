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
#include <opencv2/core.hpp>
#include <opencv2/highgui.hpp>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp>
#include "aidemo_wrap.h"

#include <stdlib.h>
#include <iostream>

#define LOC_SIZE  4
#define CONF_SIZE 2
#define LAND_SIZE 8

typedef struct sortable_obj_t
{
	int index;
	float* probs;
} sortable_obj_t;

typedef struct landmarks_t
{
	float points[8];
} landmarks_t;

typedef struct BoxPoint
{
    cv::Point2f vertices[4];
} BoxPoint;

extern float anchors[16800][4];

int nms_comparator(const void *pa, const void *pb)
{
	sortable_obj_t a = *(sortable_obj_t*)pa;
	sortable_obj_t b = *(sortable_obj_t*)pb;
	float diff = a.probs[a.index] - b.probs[b.index];

	if (diff < 0)
		return 1;
	else if (diff > 0)
		return -1;
	return 0;
}

int argmax(float* x, uint32_t len)
{
	float max_value = x[0];
	int max_index = 0;
	for (uint32_t ll = 1; ll < len; ll++)
	{
		if (max_value < x[ll])
		{
			max_value = x[ll];
			max_index = ll;
		}
	}
	return max_index;
}

void local_softmax(float* x, float* dx, uint32_t len)
{
	float max_value = x[0];
	for (uint32_t i = 0; i < len; i++)
	{
		if (max_value < x[i])
		{
			max_value = x[i];
		}
	}
	for (uint32_t i = 0; i < len; i++)
	{
		x[i] -= max_value;
		x[i] = expf(x[i]);
	}
	float sum_value = 0.0f;
	for (uint32_t i = 0; i < len; i++)
	{
		sum_value += x[i];
	}
	for (uint32_t i = 0; i < len; i++)
	{
		dx[i] = x[i] / sum_value;
	}
}

void deal_conf(float* conf, float* s_probs, sortable_obj_t* s, int size, int& obj_cnt)
{
	float prob[CONF_SIZE] = { 0.0 };
	for (uint32_t ww = 0; ww < size; ww++)
	{
		for (uint32_t hh = 0; hh < 2; hh++)
		{
			for (uint32_t cc = 0; cc < CONF_SIZE; cc++)
			{
				prob[cc] = conf[(hh * CONF_SIZE + cc) * size + ww];
			}
			local_softmax(prob, prob, 2);
			s[obj_cnt].index = obj_cnt;
			s_probs[obj_cnt] = prob[1];
			obj_cnt += 1;
		}
	}
}


void deal_loc(float* loc, float* boxes, int size, int& obj_cnt)
{
	for (uint32_t ww = 0; ww < size; ww++)
	{
		for (uint32_t hh = 0; hh < 2; hh++)
		{
			for (uint32_t cc = 0; cc < LOC_SIZE; cc++)
			{
				boxes[obj_cnt * LOC_SIZE + cc] = loc[(hh * LOC_SIZE + cc) * size + ww];
			}
			obj_cnt += 1;
		}
	}
}

void deal_landms(float* landms, float* landmarks, int size, int& obj_cnt)
{
	for (uint32_t ww = 0; ww < size; ww++)
	{
		for (uint32_t hh = 0; hh < 2; hh++)
		{
			for (uint32_t cc = 0; cc < LAND_SIZE; cc++)
			{
				landmarks[obj_cnt * LAND_SIZE + cc] = landms[(hh * LAND_SIZE + cc) * size + ww];
			}
			obj_cnt += 1;
		}
	}
}

Bbox get_box(float* boxes, int obj_index)
{
	float x, y, w, h;
	x = boxes[obj_index * LOC_SIZE + 0];
	y = boxes[obj_index * LOC_SIZE + 1];
	w = boxes[obj_index * LOC_SIZE + 2];
	h = boxes[obj_index * LOC_SIZE + 3];
	x = anchors[obj_index][0] + x * 0.1 * anchors[obj_index][2];
	y = anchors[obj_index][1] + y * 0.1 * anchors[obj_index][3];
	w = anchors[obj_index][2] * expf(w * 0.2);
	h = anchors[obj_index][3] * expf(h * 0.2);
	Bbox box;
	box.x = x;
	box.y = y;
	box.w = w;
	box.h = h;
	return box;
}

landmarks_t get_landmark(float* landmarks, int obj_index)
{
	landmarks_t landmark;
	for (uint32_t ll = 0; ll < 4; ll++)
	{
		landmark.points[2 * ll + 0] = anchors[obj_index][0] + landmarks[obj_index * LAND_SIZE + 2 * ll + 0] * 0.1 * anchors[obj_index][2];
		landmark.points[2 * ll + 1] = anchors[obj_index][1] + landmarks[obj_index * LAND_SIZE + 2 * ll + 1] * 0.1 * anchors[obj_index][3];
	}
	return landmark;
}

float overlap(float x1, float w1, float x2, float w2)
{
	float l1 = x1 - w1 / 2;
	float l2 = x2 - w2 / 2;
	float left = l1 > l2 ? l1 : l2;
	float r1 = x1 + w1 / 2;
	float r2 = x2 + w2 / 2;
	float right = r1 < r2 ? r1 : r2;

	return right - left;
}

float box_intersection(Bbox a, Bbox b)
{
	float w = overlap(a.x, a.w, b.x, b.w);
	float h = overlap(a.y, a.h, b.y, b.h);

	if (w < 0 || h < 0)
		return 0;
	return w * h;
}

float box_union(Bbox a, Bbox b)
{
	float i = box_intersection(a, b);
	float u = a.w * a.h + b.w * b.h - i;

	return u;
}

float box_iou(Bbox a, Bbox b)
{
	return box_intersection(a, b) / box_union(a, b);
}

BoxPoint8* licence_det_post_process(float* p_outputs_0,float* p_outputs_1,float* p_outputs_2,float* p_outputs_3,float* p_outputs_4,float* p_outputs_5,float* p_outputs_6,float* p_outputs_7,float* p_outputs_8,FrameSize frame_size,FrameSize kmodel_frame_size,float obj_thresh,float nms_thresh,int* box_cnt)
{
	float ratio_w=kmodel_frame_size.width/(frame_size.width*1.0);
    float ratio_h=kmodel_frame_size.height/(frame_size.height*1.0);
    float scale=MIN(ratio_w,ratio_h);

    float* loc0 = p_outputs_0;
    float* loc1 = p_outputs_1;
    float* loc2 = p_outputs_2;
    float* conf0 = p_outputs_3;
    float* conf1 = p_outputs_4;
    float* conf2 = p_outputs_5;
    float* landms0 = p_outputs_6;
    float* landms1 = p_outputs_7;
    float* landms2 = p_outputs_8;

    int min_size = (kmodel_frame_size.height == 320 ? 200 : 800);

    float box[LOC_SIZE] = { 0.0 };
	float landms[LAND_SIZE] = { 0.0 };
	int objs_num = min_size * (1 + 4 + 16);
	sortable_obj_t* s = (sortable_obj_t*)malloc(objs_num * sizeof(sortable_obj_t));
	float* s_probs = (float*)malloc(objs_num * sizeof(float));
	float* boxes = (float*)malloc(objs_num * LOC_SIZE * sizeof(float));
	float* landmarks = (float*)malloc(objs_num * LAND_SIZE * sizeof(float));
	if (s == NULL || s_probs == NULL || boxes == NULL || landmarks == NULL) {
		free(s);
		free(s_probs);
		free(boxes);
		free(landmarks);
		*box_cnt = -1;
		return NULL;
	}
	int obj_cnt = 0;
	deal_conf(conf0, s_probs, s, 16 * min_size / 2, obj_cnt);
	deal_conf(conf1, s_probs, s, 4 * min_size / 2, obj_cnt);
	deal_conf(conf2, s_probs, s, 1 * min_size / 2, obj_cnt);
	obj_cnt = 0;
	deal_loc(loc0, boxes, 16 * min_size / 2, obj_cnt);
	deal_loc(loc1, boxes, 4 * min_size / 2, obj_cnt);
	deal_loc(loc2, boxes, 1 * min_size / 2, obj_cnt);
	obj_cnt = 0;
	deal_landms(landms0, landmarks, 16 * min_size / 2, obj_cnt);
	deal_landms(landms1, landmarks, 4 * min_size / 2, obj_cnt);
	deal_landms(landms2, landmarks, 1 * min_size / 2, obj_cnt);
	for (uint32_t oo = 0; oo < objs_num; oo++)
	{
		s[oo].probs = s_probs;
	}
	qsort(s, objs_num, sizeof(sortable_obj_t), nms_comparator);

	std::vector<landmarks_t> valid_landmarks;
    valid_landmarks.reserve(64);
	int iou_cal_times = 0;
	int i, j, k, obj_index;
	for (i = 0; i < objs_num; ++i)
	{
		obj_index = s[i].index;
		if (s_probs[obj_index] < obj_thresh)
			continue;
		Bbox a = get_box(boxes, obj_index);
		landmarks_t l = get_landmark(landmarks, obj_index);
		valid_landmarks.push_back(l);

		for (j = i + 1; j < objs_num; ++j)
		{
			obj_index = s[j].index;
			if (s_probs[obj_index] < obj_thresh)
				continue;
			Bbox b = get_box(boxes, obj_index);
			iou_cal_times += 1;
			if (box_iou(a, b) >= nms_thresh)
				s_probs[obj_index] = 0;
		}
	}



    *box_cnt = valid_landmarks.size();
    BoxPoint8 *boxPoint = (BoxPoint8 *)malloc(*box_cnt * sizeof(BoxPoint8));
	if (*box_cnt > 0 && boxPoint == NULL) {
		free(s_probs);
		free(boxes);
		free(landmarks);
		free(s);
		return NULL;
	}
	for (int i = 0; i < *box_cnt; i++)
	{
		boxPoint[i].points8[0] = (valid_landmarks[i].points[2 * 0 + 0] * kmodel_frame_size.width) / scale;
        boxPoint[i].points8[1] = (valid_landmarks[i].points[2 * 0 + 1] * kmodel_frame_size.height) / scale;
        boxPoint[i].points8[2] = (valid_landmarks[i].points[2 * 1 + 0] * kmodel_frame_size.width) / scale;
        boxPoint[i].points8[3] = (valid_landmarks[i].points[2 * 1 + 1] * kmodel_frame_size.height) / scale;
        boxPoint[i].points8[4] = (valid_landmarks[i].points[2 * 2 + 0] * kmodel_frame_size.width) / scale;
        boxPoint[i].points8[5] = (valid_landmarks[i].points[2 * 2 + 1] * kmodel_frame_size.height) / scale;
        boxPoint[i].points8[6] = (valid_landmarks[i].points[2 * 3 + 0] * kmodel_frame_size.width) / scale;
        boxPoint[i].points8[7] = (valid_landmarks[i].points[2 * 3 + 1] * kmodel_frame_size.height) / scale;
	}

    free(s_probs);
	free(boxes);
	free(landmarks);
	free(s);
    return boxPoint;
}

void licence_det_free_outputs(void *context)
{
    free(context);
}
