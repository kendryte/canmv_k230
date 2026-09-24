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
#include <cstdlib>
#include <opencv2/highgui.hpp>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp>
#include <array>
#include "aidemo_wrap.h"
#include "aidemo_size.h"

typedef struct BoxPoint
{
    cv::Point2f vertices[4];
}BoxPoint;

float* mask_resize(float* dest, FrameSize ori_shape, FrameSize tag_shape)
{
    size_t result_size;
    if (!aidemo_checked_image_size(ori_shape.width, ori_shape.height, 1, &result_size)
        || !aidemo_checked_image_size(tag_shape.width, tag_shape.height, 1, &result_size)
        || result_size > SIZE_MAX / sizeof(float)) {
        return NULL;
    }

    cv::Mat dest_mat(ori_shape.height, ori_shape.width, CV_32FC1, dest);
    cv::Mat mask;
    resize(dest_mat, mask, cv::Size(tag_shape.width, tag_shape.height), cv::INTER_NEAREST);
    float *result = (float *)malloc(result_size * sizeof(float));
    if (result == NULL && result_size != 0) {
        return NULL;
    }
    if (result_size != 0) {
        hal_rvv_memcpy(result, mask.data, result_size * sizeof(float));
    }
    return result;
}

void mask_resize_free_output(void *context)
{
    free(context);
}

std::array<size_t, 4> sort_indices_(const std::array<cv::Point2f, 4>& points)
{
	std::array<size_t, 4> indices = {0, 1, 2, 3};
	std::sort(indices.begin(), indices.end(), [&points](size_t a, size_t b) {
		return points[a].x < points[b].x;
	});
	return indices;
}

void find_rectangle_vertices_(const std::array<cv::Point2f, 4>& points, cv::Point2f& topLeft, cv::Point2f& topRight, cv::Point2f& bottomRight, cv::Point2f& bottomLeft)
{
    //先按照x排序,比较左右，再按照y比较上下
	auto sorted_x_id = sort_indices_(points);

	if (points[sorted_x_id[0]].y < points[sorted_x_id[1]].y)
	{
		topLeft = points[sorted_x_id[0]];
		bottomLeft = points[sorted_x_id[1]];
	}
	else
	{
		topLeft = points[sorted_x_id[1]];
		bottomLeft = points[sorted_x_id[0]];
	}

	if (points[sorted_x_id[2]].y < points[sorted_x_id[3]].y)
	{
        bottomRight = points[sorted_x_id[3]];
		topRight = points[sorted_x_id[2]];

	}
	else
	{ 
        bottomRight = points[sorted_x_id[2]];
		topRight = points[sorted_x_id[3]];
	}
	
}

void warppersp_(const cv::Mat& src, cv::Mat& dst, const BoxPoint& b, std::array<cv::Point2f, 4>& vtd)
{
    cv::Mat rotation;
    std::array<cv::Point, 4> con;
    for (size_t i = 0; i < con.size(); ++i) con[i] = b.vertices[i];

    cv::Mat con_mat(4, 1, CV_32SC2, con.data());
    cv::RotatedRect minrect = minAreaRect(con_mat);
    std::array<cv::Point2f, 4> vtx, vt;
    minrect.points(vtx.data());

    find_rectangle_vertices_(vtx, vtd[0], vtd[1], vtd[2], vtd[3]);
    
    //w,h tmp_w=dist(p1,p0),tmp_h=dist(p1,p2)
    float tmp_w = cv::norm(vtd[1]-vtd[0]);
    float tmp_h = cv::norm(vtd[2]-vtd[1]);
    float w = std::max(tmp_w,tmp_h);
    float h = std::min(tmp_w,tmp_h);

    vt[0].x = 0;
    vt[0].y = 0;
    vt[1].x = w;//w
    vt[1].y = 0;
    vt[2].x = w;
    vt[2].y = h;
    vt[3].x = 0;
    vt[3].y = h;//h
    rotation = cv::getPerspectiveTransform(vtd.data(), vt.data());

    cv::warpPerspective(src, dst, rotation, cv::Size(w, h));
}

ArrayWrapperMat1* ocr_rec_pre_process(uint8_t* data, FrameSize ori_shape, BoxPoint8* boxpoint8, int box_cnt)
{
    if (data == nullptr || boxpoint8 == nullptr || box_cnt <= 0 ||
        ori_shape.width == 0 || ori_shape.height == 0 ||
        ori_shape.width > SIZE_MAX / ori_shape.height) {
        return nullptr;
    }
    ArrayWrapperMat1 *arrayWrapperMat1 = nullptr;
    try {
    size_t matsize = ori_shape.width * ori_shape.height;
    cv::Mat ori_img;
    cv::Mat ori_img_R = cv::Mat(ori_shape.height, ori_shape.width, CV_8UC1, data);
    cv::Mat ori_img_G = cv::Mat(ori_shape.height, ori_shape.width, CV_8UC1, data + 1 * matsize);
    cv::Mat ori_img_B = cv::Mat(ori_shape.height, ori_shape.width, CV_8UC1, data + 2 * matsize);
    std::vector<cv::Mat> sensor_bgr;
    sensor_bgr.push_back(ori_img_B);
    sensor_bgr.push_back(ori_img_G);
    sensor_bgr.push_back(ori_img_R);
    cv::merge(sensor_bgr, ori_img);
    std::vector<BoxPoint> results_det;
    results_det.clear();
    for(int i = 0; i < box_cnt; i++)
    {
        BoxPoint boxpoint;
        for(int j = 0; j < 4; j++)
        {
            boxpoint.vertices[j].x = boxpoint8[i].points8[2 * j + 0];
            boxpoint.vertices[j].y = boxpoint8[i].points8[2 * j + 1];
        }
        results_det.push_back(boxpoint);
    }

    arrayWrapperMat1 =
        (ArrayWrapperMat1 *)calloc((size_t)box_cnt, sizeof(ArrayWrapperMat1));
    if (arrayWrapperMat1 == nullptr) {
        return nullptr;
    }

    for(int i = 0; i < results_det.size(); i++)
    {
        std::array<cv::Point2f, 4> sort_vtd;
        cv::Mat crop;
        warppersp_(ori_img, crop, results_det[i], sort_vtd);
		cv::Mat crop_gray;
		cv::cvtColor(crop, crop_gray, cv::COLOR_BGR2GRAY);

		size_t crop_size;
		if (!aidemo_checked_image_size(crop_gray.cols, crop_gray.rows, 1, &crop_size)) {
			for (int j = 0; j < i; j++) {
				free(arrayWrapperMat1[j].data);
			}
			free(arrayWrapperMat1);
			return NULL;
		}
		arrayWrapperMat1[i].data = (uint8_t *)malloc(crop_size);
		if (arrayWrapperMat1[i].data == NULL && crop_size != 0) {
			for (int j = 0; j < i; j++) {
				free(arrayWrapperMat1[j].data);
			}
			free(arrayWrapperMat1);
			return NULL;
		}
		if (crop_size != 0) {
			hal_rvv_memcpy(arrayWrapperMat1[i].data, crop_gray.data, crop_size);
		}
        arrayWrapperMat1[i].framesize.width = crop_gray.cols;
        arrayWrapperMat1[i].framesize.height = crop_gray.rows;
        for(int j = 0; j < 4; j++)
        {
            arrayWrapperMat1[i].coordinates[2 * j + 0] = sort_vtd[j].x;
            arrayWrapperMat1[i].coordinates[2 * j + 1] = sort_vtd[j].y;
        }
    }
    return arrayWrapperMat1;
    } catch (...) {
        if (arrayWrapperMat1 != nullptr) {
            for (int i = 0; i < box_cnt; ++i) free(arrayWrapperMat1[i].data);
            free(arrayWrapperMat1);
        }
        return nullptr;
    }
}

void ocr_rec_free_outputs(ArrayWrapperMat1 *outputs, int count)
{
    if (outputs == nullptr) return;
    for (int i = 0; i < count; ++i) free(outputs[i].data);
    free(outputs);
}
