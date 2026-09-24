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
#include "segmentation_output.h"
#include "ai_rvv_kernels.h"

#include <array>
#include <stdlib.h>
#include <iostream>
#include <unistd.h>
#include <limits.h>

#define SEGCHANNELS 32
#define CLASSES_COUNT 80

typedef struct {
	cv::Rect box;
	float confidence;
	int index;
}BBOX;

struct OutputSeg {
	int id;             //结果类别id
	float confidence;   //结果置信度
	cv::Rect box;       //矩形框
	cv::Mat boxMask;       //矩形框内mask，节省内存空间和加快速度
};

const std::vector<cv::Scalar> color_four = {cv::Scalar(127, 220, 20, 60),
       cv::Scalar(127, 119, 11, 32),
       cv::Scalar(127, 0, 0, 142),
       cv::Scalar(127, 0, 0, 230),
       cv::Scalar(127, 106, 0, 228),
       cv::Scalar(127, 0, 60, 100),
       cv::Scalar(127, 0, 80, 100),
       cv::Scalar(127, 0, 0, 70),
       cv::Scalar(127, 0, 0, 192),
       cv::Scalar(127, 250, 170, 30),
       cv::Scalar(127, 100, 170, 30),
       cv::Scalar(127, 220, 220, 0),
       cv::Scalar(127, 175, 116, 175),
       cv::Scalar(127, 250, 0, 30),
       cv::Scalar(127, 165, 42, 42),
       cv::Scalar(127, 255, 77, 255),
       cv::Scalar(127, 0, 226, 252),
       cv::Scalar(127, 182, 182, 255),
       cv::Scalar(127, 0, 82, 0),
       cv::Scalar(127, 120, 166, 157),
       cv::Scalar(127, 110, 76, 0),
       cv::Scalar(127, 174, 57, 255),
       cv::Scalar(127, 199, 100, 0),
       cv::Scalar(127, 72, 0, 118),
       cv::Scalar(127, 255, 179, 240),
       cv::Scalar(127, 0, 125, 92),
       cv::Scalar(127, 209, 0, 151),
       cv::Scalar(127, 188, 208, 182),
       cv::Scalar(127, 0, 220, 176),
       cv::Scalar(127, 255, 99, 164),
       cv::Scalar(127, 92, 0, 73),
       cv::Scalar(127, 133, 129, 255),
       cv::Scalar(127, 78, 180, 255),
       cv::Scalar(127, 0, 228, 0),
       cv::Scalar(127, 174, 255, 243),
       cv::Scalar(127, 45, 89, 255),
       cv::Scalar(127, 134, 134, 103),
       cv::Scalar(127, 145, 148, 174),
       cv::Scalar(127, 255, 208, 186),
       cv::Scalar(127, 197, 226, 255),
       cv::Scalar(127, 171, 134, 1),
       cv::Scalar(127, 109, 63, 54),
       cv::Scalar(127, 207, 138, 255),
       cv::Scalar(127, 151, 0, 95),
       cv::Scalar(127, 9, 80, 61),
       cv::Scalar(127, 84, 105, 51),
       cv::Scalar(127, 74, 65, 105),
       cv::Scalar(127, 166, 196, 102),
       cv::Scalar(127, 208, 195, 210),
       cv::Scalar(127, 255, 109, 65),
       cv::Scalar(127, 0, 143, 149),
       cv::Scalar(127, 179, 0, 194),
       cv::Scalar(127, 209, 99, 106),
       cv::Scalar(127, 5, 121, 0),
       cv::Scalar(127, 227, 255, 205),
       cv::Scalar(127, 147, 186, 208),
       cv::Scalar(127, 153, 69, 1),
       cv::Scalar(127, 3, 95, 161),
       cv::Scalar(127, 163, 255, 0),
       cv::Scalar(127, 119, 0, 170),
       cv::Scalar(127, 0, 182, 199),
       cv::Scalar(127, 0, 165, 120),
       cv::Scalar(127, 183, 130, 88),
       cv::Scalar(127, 95, 32, 0),
       cv::Scalar(127, 130, 114, 135),
       cv::Scalar(127, 110, 129, 133),
       cv::Scalar(127, 166, 74, 118),
       cv::Scalar(127, 219, 142, 185),
       cv::Scalar(127, 79, 210, 114),
       cv::Scalar(127, 178, 90, 62),
       cv::Scalar(127, 65, 70, 15),
       cv::Scalar(127, 127, 167, 115),
       cv::Scalar(127, 59, 105, 106),
       cv::Scalar(127, 142, 108, 45),
       cv::Scalar(127, 196, 172, 0),
       cv::Scalar(127, 95, 54, 80),
       cv::Scalar(127, 128, 76, 255),
       cv::Scalar(127, 201, 57, 1),
       cv::Scalar(127, 246, 0, 122),
       cv::Scalar(127, 191, 162, 208)};

float get_iou_value(cv::Rect rect1, cv::Rect rect2)
{
	int xx1, yy1, xx2, yy2;
 
	xx1 = std::max(rect1.x, rect2.x);
	yy1 = std::max(rect1.y, rect2.y);
	xx2 = std::min(rect1.x + rect1.width - 1, rect2.x + rect2.width - 1);
	yy2 = std::min(rect1.y + rect1.height - 1, rect2.y + rect2.height - 1);
 
	int insection_width, insection_height;
	insection_width = std::max(0, xx2 - xx1 + 1);
	insection_height = std::max(0, yy2 - yy1 + 1);
 
	float insection_area, union_area, iou;
	insection_area = float(insection_width) * insection_height;
	union_area = float(rect1.width*rect1.height + rect2.width*rect2.height - insection_area);
	iou = insection_area / union_area;

	return iou;
}

void nms_boxes(std::vector<cv::Rect> &boxes, std::vector<float> &confidences, float confThreshold, float nmsThreshold, std::vector<int> &indices)
{	
	BBOX bbox;
	std::vector<BBOX> bboxes;
	bboxes.reserve(boxes.size());
	for (size_t i = 0; i < boxes.size(); i++)
	{
		bbox.box = boxes[i];
		bbox.confidence = confidences[i];
		bbox.index = i;
		bboxes.push_back(bbox);
	}

	sort(bboxes.begin(), bboxes.end(), [](BBOX a, BBOX b) { return a.confidence > b.confidence; });

	const size_t box_count = bboxes.size();
	std::vector<uint8_t> suppressed(box_count, 0);
	indices.reserve(indices.size() + box_count);
	for (size_t i = 0; i < box_count; i++)
	{
		if (suppressed[i])
			continue;
		if (bboxes[i].confidence < confThreshold)
			continue;
		indices.push_back(bboxes[i].index);

		for (size_t j = i + 1; j < box_count; j++)
		{
			if (suppressed[j])
				continue;
			float iou = get_iou_value(bboxes[i].box, bboxes[j].box);

			if (iou > nmsThreshold)
			{
				suppressed[j] = 1;
			}
		}
	}
}



void draw_segmentation(cv::Mat& frame,std::vector<OutputSeg>& results)
{

	for (int i = 0; i < results.size(); i++) {
		int left, top;
		left = results[i].box.x;
		top = results[i].box.y;
		int color_num = i;
		rectangle(frame, results[i].box, color_four[results[i].id], 2, 8);
		
		frame(results[i].box).setTo(color_four[results[i].id], results[i].boxMask);
	}
}



void object_seg_free_outputs(void *context)
{
	SegOutputs *segOutputs = static_cast<SegOutputs *>(context);
	if (segOutputs == NULL) {
		return;
	}

	free(segOutputs->masks_results);
	segOutputs->masks_results = NULL;
	free(segOutputs->segOutput);
	segOutputs->segOutput = NULL;
}


static SegOutputs object_seg_post_process_impl(
    float *data_0, float *data_1, FrameSize frame_size,
    FrameSize kmodel_frame_size, FrameSize display_frame_size,
    float conf_thres, float nms_thres, float mask_thres, int *box_cnt,
    uint8_t *masks_output)
{
    *box_cnt = -1;
    try {
	std::vector<OutputSeg> results;
    float *output_0 = data_0;
    float *output_1 = data_1;

    int w, h, x, y;
	float r_w = kmodel_frame_size.width / (frame_size.width*1.0);
	float r_h = kmodel_frame_size.height / (frame_size.height*1.0);
	if (r_h > r_w) {
		w = kmodel_frame_size.width;
		h = r_w * frame_size.height;
		x = 0;
		y = (kmodel_frame_size.height - h) / 2;
	}
	else {
		w = r_h * frame_size.width;
		h = kmodel_frame_size.height;
		x = (kmodel_frame_size.width - w) / 2;
		y = 0;
	}

    int newh = h, neww = w, padh = y, padw = x;
	float ratio_h = (float)frame_size.height / newh;
	float ratio_w = (float)frame_size.width / neww;

    std::vector<int> classIds;//结果id数组
	std::vector<float> confidences;//结果每个id对应置信度数组
	std::vector<cv::Rect> boxes;//每个id矩形框
	std::vector<std::array<float, SEGCHANNELS>> picked_proposals;


	// 处理box
	int Num_box = (kmodel_frame_size.width/8) * (kmodel_frame_size.height/8) + (kmodel_frame_size.width/16) * (kmodel_frame_size.height/16) + (kmodel_frame_size.width/32) * (kmodel_frame_size.height/32);
	int net_length = CLASSES_COUNT + 4 + SEGCHANNELS;
	cv::Mat out1 = cv::Mat(net_length, Num_box, CV_32F, output_0);

	for (int i = 0; i < Num_box; i++) {
		//输出是1*net_length*Num_box;所以每个box的属性是每隔Num_box取一个值，共net_length个值
		float max_class_socre;
		const int class_id = (int)ai_rvv_f32_argmax_strided(
		    output_0 + 4 * Num_box + i, CLASSES_COUNT, Num_box,
		    &max_class_socre);
		if (max_class_socre >= conf_thres) {
			float x = (out1.at<float>(0, i) - padw) * ratio_w * display_frame_size.width / frame_size.width;  //cx
			float y = (out1.at<float>(1, i) - padh) * ratio_h * display_frame_size.height / frame_size.height;  //cy
			float w = out1.at<float>(2, i) * ratio_w * display_frame_size.width / frame_size.width;  //w
			float h = out1.at<float>(3, i) * ratio_h * display_frame_size.height / frame_size.height;  //h
			int left = MAX((x - 0.5 * w), 0);
			int top = MAX((y - 0.5 * h), 0);
			int width = (int)w;
			int height = (int)h;
			if (width <= 0 || height <= 0) { continue; }

			std::array<float, SEGCHANNELS> coefficients;
			for (int channel = 0; channel < SEGCHANNELS; ++channel) {
				coefficients[channel] =
				    output_0[(4 + CLASSES_COUNT + channel) * Num_box + i];
			}
			picked_proposals.push_back(coefficients);
			classIds.push_back(class_id);
			confidences.push_back(max_class_socre);
			boxes.push_back(cv::Rect(left, top, width, height));
		}

	}

	//执行非最大抑制以消除具有较低置信度的冗余重叠框（NMS）
	std::vector<int> nms_result;
	nms_boxes(boxes, confidences, conf_thres, nms_thres, nms_result);

	std::vector<std::array<float, SEGCHANNELS>> temp_mask_proposals;
	std::vector<OutputSeg> output;
	cv::Rect holeImgRect(0, 0, display_frame_size.width, display_frame_size.height);
	for (int i = 0; i < nms_result.size(); ++i) {
		int idx = nms_result[i];
		OutputSeg result;
		result.id = classIds[idx];
		result.confidence = confidences[idx];
		result.box = boxes[idx]& holeImgRect;
		output.push_back(result);
		temp_mask_proposals.push_back(picked_proposals[idx]);
	}

	// 处理mask
	int segWidth = kmodel_frame_size.width/4;
    int segHeight = kmodel_frame_size.height/4;
	if(temp_mask_proposals.size() > 0)
	{	cv::Mat maskProposals((int)temp_mask_proposals.size(), SEGCHANNELS,
		                      CV_32F, temp_mask_proposals.data());

		cv::Mat protos = cv::Mat(SEGCHANNELS, segWidth * segHeight, CV_32FC1, output_1);
		cv::Mat matmulRes = (maskProposals * protos).t();//n*32 32*25600 A*B是以数学运算中矩阵相乘的方式实现的，要求A的列数等于B的行数时
		cv::Mat masks = matmulRes.reshape(output.size(), { segHeight,segWidth });//n*160*160

		std::vector<cv::Mat> maskChannels;
		cv::split(masks, maskChannels);
		cv::Rect roi(int((float)padw / kmodel_frame_size.width * segWidth), int((float)padh / kmodel_frame_size.height * segHeight), int(segWidth - padw / 2), int(segHeight - padh / 2));

		for (int i = 0; i < output.size(); ++i) {
			cv::Mat dest, mask;
			cv::exp(-maskChannels[i], dest);//sigmoid
			dest = 1.0 / (1.0 + dest);//160*160
			dest = dest(roi);
			resize(dest, mask, cv::Size(display_frame_size.width, display_frame_size.height), cv::INTER_NEAREST);
			//crop----截取box中的mask作为该box对应的mask
			cv::Rect temp_rect = output[i].box;
			mask = mask(temp_rect) > mask_thres;
			output[i].boxMask = mask;
		}
		results=output;
	}
	return build_segmentation_output(results, display_frame_size, box_cnt,
        masks_output, [&](cv::Mat &frame) { draw_segmentation(frame, results); });
    } catch (...) {
        *box_cnt = -1;
        return {};
    }
}

SegOutputs object_seg_post_process(
    float *data_0, float *data_1, FrameSize frame_size,
    FrameSize kmodel_frame_size, FrameSize display_frame_size,
    float conf_thres, float nms_thres, float mask_thres, int *box_cnt)
{
	return object_seg_post_process_impl(
	    data_0, data_1, frame_size, kmodel_frame_size, display_frame_size,
	    conf_thres, nms_thres, mask_thres, box_cnt, nullptr);
}

SegOutputs object_seg_post_process_into(
    float *data_0, float *data_1, FrameSize frame_size,
    FrameSize kmodel_frame_size, FrameSize display_frame_size,
    float conf_thres, float nms_thres, float mask_thres, int *box_cnt,
    uint8_t *masks_output)
{
	return object_seg_post_process_impl(
	    data_0, data_1, frame_size, kmodel_frame_size, display_frame_size,
	    conf_thres, nms_thres, mask_thres, box_cnt, masks_output);
}
