#include <opencv2/core.hpp>
#include <opencv2/highgui.hpp>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp>
#include "aidemo_wrap.h"
#include "segmentation_output.h"
#include "ai_rvv_kernels.h"
#include <stdlib.h>
#include <iostream>
#include <algorithm>

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


std::vector<cv::Scalar> getColorsForClasses(int num_classes) {
    std::vector<cv::Scalar> colors;
    int num_available_colors = color_four.size(); // 获取可用颜色的数量
    for (int i = 0; i < num_classes; ++i) {
        // 使用模运算来循环获取颜色
        colors.push_back(color_four[i % num_available_colors]);
    }
    return colors;
}

float get_iou_yolo_value(cv::Rect rect1, cv::Rect rect2)
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

void nms_yolo_boxes(std::vector<cv::Rect> &boxes, std::vector<float> &confidences, float confThreshold, float nmsThreshold, std::vector<int> &indices)
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
			float iou = get_iou_yolo_value(bboxes[i].box, bboxes[j].box);

			if (iou > nmsThreshold)
			{
				suppressed[j] = 1;
			}
		}
	}
}

void draw_yolo_segmentation(cv::Mat& frame,std::vector<OutputSeg>& results,std::vector<cv::Scalar>& class_colors)
{
	for (int i = 0; i < results.size(); i++) {
		int left, top;
		left = results[i].box.x;
		top = results[i].box.y;
		int color_num = i;
		rectangle(frame, results[i].box, class_colors[results[i].id], 2, 8);
		frame(results[i].box).setTo(class_colors[results[i].id], results[i].boxMask);
	}
}

static SegOutputs build_yolo_seg_outputs(
    std::vector<OutputSeg>& results, FrameSize display_shape,
    std::vector<cv::Scalar>& class_colors, int *box_cnt, uint8_t *masks_output)
{
    return build_segmentation_output(results, display_shape, box_cnt,
        masks_output, [&](cv::Mat &frame) {
            draw_yolo_segmentation(frame, results, class_colors);
        });
}

static SegOutputs yolov5_seg_postprocess_impl(
    float *output0, float *output1, FrameSize frame_shape,
    FrameSize input_shape, FrameSize display_shape, int class_num,
    float conf_thresh, float nms_thresh, float mask_thresh, int *box_cnt,
    uint8_t *masks_output)
{
    *box_cnt = -1;
    try {
    std::vector<cv::Scalar> class_colors = getColorsForClasses(class_num);
    float ratio_w=input_shape.width/(frame_shape.width*1.0);
    float ratio_h=input_shape.height/(frame_shape.height*1.0);
    float scale=MIN(ratio_w,ratio_h);
    int new_w=int(frame_shape.width*scale);
    int new_h=int(frame_shape.height*scale);
    int pad_w=MAX(input_shape.width-new_w,0);
    int pad_h=MAX(input_shape.height-new_h,0);

	std::vector<OutputSeg> results;
    std::vector<int> classIds;//结果id数组
	std::vector<float> confidences;//结果每个id对应置信度数组
	std::vector<cv::Rect> boxes;//每个id矩形框
	std::vector<cv::Mat> picked_proposals;  //后续计算mask
    // output0 (6300,40);output1 (32,80,80)
    int f_len=class_num+5+32;
    int mask_w=input_shape.width/4;
    int mask_h=input_shape.height/4;
    int num_box=3*((input_shape.width/8)*(input_shape.height/8)+(input_shape.width/16)*(input_shape.height/16)+(input_shape.width/32)*(input_shape.height/32));

    cv::Mat protos = cv::Mat(32, mask_w * mask_h, CV_32FC1, output1);

    for(int i=0;i<num_box;i++){
        float* vec=output0+i*f_len;
        float box[4]={vec[0],vec[1],vec[2],vec[3]};
        float base_score=vec[4];
        float* class_scores=vec+5;
        float max_class_score;
        int max_class_index = (int)ai_rvv_f32_argmax(
            class_scores, (size_t)class_num, &max_class_score);
        float score=max_class_score*base_score;
        if(score>conf_thresh){
            float x_=box[0]/scale*(display_shape.width/(frame_shape.width*1.0));
            float y_=box[1]/scale*(display_shape.height/(frame_shape.height*1.0));
            float w_=box[2]/scale*(display_shape.width/(frame_shape.width*1.0));
            float h_=box[3]/scale*(display_shape.height/(frame_shape.height*1.0));
            int x=int(MAX(x_-0.5*w_,0));
            int y=int(MAX(y_-0.5*h_,0));
            int w=int(w_);
            int h=int(h_);
            if (w <= 0 || h <= 0) { continue; }
            cv::Mat mask_map(1, 32, CV_32F, vec + class_num + 5);
            classIds.push_back(max_class_index);
			confidences.push_back(score);
			boxes.push_back(cv::Rect(x,y,w,h));
            picked_proposals.push_back(mask_map);
        }

    }

	//执行非最大抑制以消除具有较低置信度的冗余重叠框（NMS）
	std::vector<int> nms_result;
	nms_yolo_boxes(boxes, confidences, conf_thresh, nms_thresh, nms_result);

	std::vector<cv::Mat> temp_mask_proposals;
	std::vector<OutputSeg> output;
	cv::Rect holeImgRect(0, 0, display_shape.width, display_shape.height);
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
	int segWidth = mask_w;
    int segHeight = mask_h;
	if(temp_mask_proposals.size() > 0)
	{	cv::Mat maskProposals;
		for (int i = 0; i < temp_mask_proposals.size(); ++i)
		{
			maskProposals.push_back(temp_mask_proposals[i]);
		}

		cv::Mat matmulRes = (maskProposals * protos).t();//n*32 32*6400 A*B是以数学运算中矩阵相乘的方式实现的，要求A的列数等于B的行数时
		cv::Mat masks = matmulRes.reshape(output.size(), { segHeight,segWidth });//n*80*80
		std::vector<cv::Mat> maskChannels;
		cv::split(masks, maskChannels);
		cv::Rect roi(0, 0, int(segWidth-int(pad_w*((segWidth*1.0)/input_shape.width))), int(segHeight - int(pad_h*((segHeight*1.0)/input_shape.height))));

		for (int i = 0; i < output.size(); ++i) {
			cv::Mat dest, mask;
			cv::exp(-maskChannels[i], dest);//sigmoid
			dest = 1.0 / (1.0 + dest);//80*80
			dest = dest(roi);
			resize(dest, mask, cv::Size(display_shape.width, display_shape.height), cv::INTER_NEAREST);
			//crop----截取box中的mask作为该box对应的mask
			cv::Rect temp_rect = output[i].box;
			mask = mask(temp_rect) > mask_thresh;
			output[i].boxMask = mask;
		}
		results=output;
	}

	return build_yolo_seg_outputs(
	    results, display_shape, class_colors, box_cnt, masks_output);
    } catch (...) {
        *box_cnt = -1;
        return {};
    }
}

static SegOutputs yolov8_seg_postprocess_impl(
    float *output0, float *output1, FrameSize frame_shape,
    FrameSize input_shape, FrameSize display_shape, int class_num,
    float conf_thresh, float nms_thresh, float mask_thresh, int *box_cnt,
    uint8_t *masks_output)
{
    *box_cnt = -1;
    try {
    std::vector<cv::Scalar> class_colors = getColorsForClasses(class_num);
    float ratio_w=input_shape.width/(frame_shape.width*1.0);
    float ratio_h=input_shape.height/(frame_shape.height*1.0);
    float scale=MIN(ratio_w,ratio_h);
    int new_w=int(frame_shape.width*scale);
    int new_h=int(frame_shape.height*scale);
    int pad_w=MAX(input_shape.width-new_w,0);
    int pad_h=MAX(input_shape.height-new_h,0);

	std::vector<OutputSeg> results;
    std::vector<int> classIds;//结果id数组
	std::vector<float> confidences;//结果每个id对应置信度数组
	std::vector<cv::Rect> boxes;//每个id矩形框
	std::vector<cv::Mat> picked_proposals;  //后续计算mask
    // output0 (39,2100);output1 (32,80,80)
    int f_len=class_num+4+32;
    int mask_w=input_shape.width/4;
    int mask_h=input_shape.height/4;
    int num_box=((input_shape.width/8)*(input_shape.height/8)+(input_shape.width/16)*(input_shape.height/16)+(input_shape.width/32)*(input_shape.height/32));

    cv::Mat protos = cv::Mat(32, mask_w * mask_h, CV_32FC1, output1);

    for(int i=0;i<num_box;i++){
        float* vec=output0+i*f_len;
        float box[4]={vec[0],vec[1],vec[2],vec[3]};
        float* class_scores=vec+4;
        float score;
        int max_class_index = (int)ai_rvv_f32_argmax(
            class_scores, (size_t)class_num, &score);
        if(score>conf_thresh){
            float x_=box[0]/scale*(display_shape.width/(frame_shape.width*1.0));
            float y_=box[1]/scale*(display_shape.height/(frame_shape.height*1.0));
            float w_=box[2]/scale*(display_shape.width/(frame_shape.width*1.0));
            float h_=box[3]/scale*(display_shape.height/(frame_shape.height*1.0));
            int x=int(MAX(x_-0.5*w_,0));
            int y=int(MAX(y_-0.5*h_,0));
            int w=int(w_);
            int h=int(h_);
            if (w <= 0 || h <= 0) { continue; }
            cv::Mat mask_map(1, 32, CV_32F, vec + class_num + 4);
            classIds.push_back(max_class_index);
			confidences.push_back(score);
			boxes.push_back(cv::Rect(x,y,w,h));
            picked_proposals.push_back(mask_map);
        }

    }
	//执行非最大抑制以消除具有较低置信度的冗余重叠框（NMS）
	std::vector<int> nms_result;
	nms_yolo_boxes(boxes, confidences, conf_thresh, nms_thresh, nms_result);

	std::vector<cv::Mat> temp_mask_proposals;
	std::vector<OutputSeg> output;
	cv::Rect holeImgRect(0, 0, display_shape.width, display_shape.height);
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
	int segWidth = mask_w;
    int segHeight = mask_h;
	if(temp_mask_proposals.size() > 0)
	{	cv::Mat maskProposals;
		for (int i = 0; i < temp_mask_proposals.size(); ++i)
		{
			maskProposals.push_back(temp_mask_proposals[i]);
		}

		cv::Mat matmulRes = (maskProposals * protos).t();//n*32 32*6400 A*B是以数学运算中矩阵相乘的方式实现的，要求A的列数等于B的行数时
		cv::Mat masks = matmulRes.reshape(output.size(), { segHeight, segWidth });//n*80*80
		std::vector<cv::Mat> maskChannels;
		cv::split(masks, maskChannels);

		cv::Rect roi(0, 0, int(segWidth-int(pad_w*((segWidth*1.0)/input_shape.width))),int(segHeight - int(pad_h*((segHeight*1.0)/input_shape.height))));
		for (int i = 0; i < output.size(); ++i) {
			cv::Mat dest, mask;
			cv::exp(-maskChannels[i], dest);//sigmoid
			dest = 1.0 / (1.0 + dest);//80*80
			dest = dest(roi);
			resize(dest, mask, cv::Size(display_shape.width, display_shape.height), cv::INTER_NEAREST);
			//crop----截取box中的mask作为该box对应的mask
			cv::Rect temp_rect = output[i].box;
			mask = mask(temp_rect) > mask_thresh;
			output[i].boxMask = mask;
		}
		results=output;
	}

	return build_yolo_seg_outputs(
	    results, display_shape, class_colors, box_cnt, masks_output);
    } catch (...) {
        *box_cnt = -1;
        return {};
    }
}

static SegOutputs yolo26_seg_postprocess_impl(
    float *output0, float *output1, FrameSize frame_shape,
    FrameSize input_shape, FrameSize display_shape, int class_num,
    float conf_thresh, float mask_thresh, int *box_cnt,
    uint8_t *masks_output)
{
    *box_cnt = -1;
    try {
    std::vector<cv::Scalar> class_colors = getColorsForClasses(class_num);
    float ratio_w=input_shape.width/(frame_shape.width*1.0);
    float ratio_h=input_shape.height/(frame_shape.height*1.0);
    float scale=MIN(ratio_w,ratio_h);
    int new_w=int(frame_shape.width*scale);
    int new_h=int(frame_shape.height*scale);
    int pad_w=MAX(input_shape.width-new_w,0);
    int pad_h=MAX(input_shape.height-new_h,0);

	std::vector<OutputSeg> results;
    std::vector<int> classIds;//结果id数组
	std::vector<float> confidences;//结果每个id对应置信度数组
	std::vector<cv::Rect> boxes;//每个id矩形框
	std::vector<cv::Mat> picked_proposals;  //后续计算mask
    int f_len=38;
    int mask_w=input_shape.width/4;
    int mask_h=input_shape.height/4;
    int num_box=300;

    cv::Mat protos = cv::Mat(32, mask_w * mask_h, CV_32FC1, output1);

    for(int i=0;i<num_box;i++){
        float* vec=output0+i*f_len;
        float box[4]={vec[0],vec[1],vec[2],vec[3]};
		float score=vec[4];
		float class_id=vec[5];
        if(score>conf_thresh){
            float x_1=box[0]/scale*(display_shape.width/(frame_shape.width*1.0));
            float y_1=box[1]/scale*(display_shape.height/(frame_shape.height*1.0));
            float x_2=box[2]/scale*(display_shape.width/(frame_shape.width*1.0));
            float y_2=box[3]/scale*(display_shape.height/(frame_shape.height*1.0));
            int x=int(MAX(x_1,0));
            int y=int(MAX(y_1,0));
            int w=int(x_2-x_1);
            int h=int(y_2-y_1);
            if (w <= 0 || h <= 0) { continue; }
            cv::Mat mask_map(1, 32, CV_32F, vec + 6);
            classIds.push_back(class_id);
			confidences.push_back(score);
			boxes.push_back(cv::Rect(x,y,w,h));
            picked_proposals.push_back(mask_map);
        }
    }

	std::vector<cv::Mat> temp_mask_proposals;
	std::vector<OutputSeg> output;
	cv::Rect holeImgRect(0, 0, display_shape.width, display_shape.height);
	for (int i = 0; i < picked_proposals.size(); ++i) {
		OutputSeg result;
		result.id = classIds[i];
		result.confidence = confidences[i];
		result.box = boxes[i]& holeImgRect;
		output.push_back(result);
		temp_mask_proposals.push_back(picked_proposals[i]);
	}
	// 处理mask
	int segWidth = mask_w;
    int segHeight = mask_h;
	if(temp_mask_proposals.size() > 0)
	{	cv::Mat maskProposals;
		for (int i = 0; i < temp_mask_proposals.size(); ++i)
		{
			maskProposals.push_back(temp_mask_proposals[i]);
		}

		cv::Mat matmulRes = (maskProposals * protos).t();
		cv::Mat masks = matmulRes.reshape(output.size(), { segHeight, segWidth });
		std::vector<cv::Mat> maskChannels;
		cv::split(masks, maskChannels);

		cv::Rect roi(0, 0, int(segWidth-int(pad_w*((segWidth*1.0)/input_shape.width))),int(segHeight - int(pad_h*((segHeight*1.0)/input_shape.height))));
		for (int i = 0; i < output.size(); ++i) {
			cv::Mat dest, mask;
			cv::exp(-maskChannels[i], dest);//sigmoid
			dest = 1.0 / (1.0 + dest);//80*80
			dest = dest(roi);
			resize(dest, mask, cv::Size(display_shape.width, display_shape.height), cv::INTER_NEAREST);
			//crop----截取box中的mask作为该box对应的mask
			cv::Rect temp_rect = output[i].box;
			mask = mask(temp_rect) > mask_thresh;
			output[i].boxMask = mask;
		}
		results=output;
	}

	return build_yolo_seg_outputs(
	    results, display_shape, class_colors, box_cnt, masks_output);
    } catch (...) {
        *box_cnt = -1;
        return {};
    }
}

SegOutputs yolov5_seg_postprocess(
    float *output0, float *output1, FrameSize frame_shape,
    FrameSize input_shape, FrameSize display_shape, int class_num,
    float conf_thresh, float nms_thresh, float mask_thresh, int *box_cnt)
{
    return yolov5_seg_postprocess_impl(
        output0, output1, frame_shape, input_shape, display_shape, class_num,
        conf_thresh, nms_thresh, mask_thresh, box_cnt, nullptr);
}

SegOutputs yolov5_seg_postprocess_into(
    float *output0, float *output1, FrameSize frame_shape,
    FrameSize input_shape, FrameSize display_shape, int class_num,
    float conf_thresh, float nms_thresh, float mask_thresh, int *box_cnt,
    uint8_t *masks_output)
{
    return yolov5_seg_postprocess_impl(
        output0, output1, frame_shape, input_shape, display_shape, class_num,
        conf_thresh, nms_thresh, mask_thresh, box_cnt, masks_output);
}

SegOutputs yolov8_seg_postprocess(
    float *output0, float *output1, FrameSize frame_shape,
    FrameSize input_shape, FrameSize display_shape, int class_num,
    float conf_thresh, float nms_thresh, float mask_thresh, int *box_cnt)
{
    return yolov8_seg_postprocess_impl(
        output0, output1, frame_shape, input_shape, display_shape, class_num,
        conf_thresh, nms_thresh, mask_thresh, box_cnt, nullptr);
}

SegOutputs yolov8_seg_postprocess_into(
    float *output0, float *output1, FrameSize frame_shape,
    FrameSize input_shape, FrameSize display_shape, int class_num,
    float conf_thresh, float nms_thresh, float mask_thresh, int *box_cnt,
    uint8_t *masks_output)
{
    return yolov8_seg_postprocess_impl(
        output0, output1, frame_shape, input_shape, display_shape, class_num,
        conf_thresh, nms_thresh, mask_thresh, box_cnt, masks_output);
}

SegOutputs yolo26_seg_postprocess(
    float *output0, float *output1, FrameSize frame_shape,
    FrameSize input_shape, FrameSize display_shape, int class_num,
    float conf_thresh, float mask_thresh, int *box_cnt)
{
    return yolo26_seg_postprocess_impl(
        output0, output1, frame_shape, input_shape, display_shape, class_num,
        conf_thresh, mask_thresh, box_cnt, nullptr);
}

SegOutputs yolo26_seg_postprocess_into(
    float *output0, float *output1, FrameSize frame_shape,
    FrameSize input_shape, FrameSize display_shape, int class_num,
    float conf_thresh, float mask_thresh, int *box_cnt,
    uint8_t *masks_output)
{
    return yolo26_seg_postprocess_impl(
        output0, output1, frame_shape, input_shape, display_shape, class_num,
        conf_thresh, mask_thresh, box_cnt, masks_output);
}

void yolo_seg_free_outputs(void *context)
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
