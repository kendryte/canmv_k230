#include <opencv2/core.hpp>
#include <opencv2/highgui.hpp>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp>
#include "aidemo_wrap.h"
#include <stdlib.h>
#include <iostream>
#include <unistd.h>
#include <algorithm>
#include <utility>
#include <cmath>
#include <array>
#include "ai_rvv_kernels.h"

typedef struct {
	cv::Rect box;
    float angle;
	float confidence;
	int index;
    std::array<float, 3> covariance;
}YoloObbBox;

template<typename T>
T clamp(T value, T low, T high) {
    return (value < low) ? low : (value > high) ? high : value;
}


// obb = {x_center, y_center, width, height, angle}
std::array<float, 3> get_covariance_matrix(const YoloObbBox& obb) {
    float width = obb.box.width / 2.0f;
    float height = obb.box.height / 2.0f;
    float angle = obb.angle;

    float cos_angle = std::cos(angle);
    float sin_angle = std::sin(angle);

    const float width_cos = width * cos_angle;
    const float width_sin = width * sin_angle;
    const float height_cos = height * cos_angle;
    const float height_sin = height * sin_angle;
    float a = width_cos * width_cos + height_sin * height_sin;
    float b = width_sin * width_sin + height_cos * height_cos;
    float c = width * cos_angle * height * sin_angle;

    return {a, b, c};
}

float cal_rotate_iou(const YoloObbBox& obb1,const YoloObbBox& obb2,float eps = 1e-7f) {
    float x1 = obb1.box.x, y1 = obb1.box.y;
    float x2 = obb2.box.x, y2 = obb2.box.y;

    const auto [a1, b1, c1] = obb1.covariance;
    const auto [a2, b2, c2] = obb2.covariance;

    const float c_sum = c1 + c2;
    const float x_diff = x1 - x2;
    const float y_diff = y1 - y2;
    float denom = (a1 + a2) * (b1 + b2) - c_sum * c_sum + eps;

    float t1 = ((a1 + a2) * y_diff * y_diff + (b1 + b2) * x_diff * x_diff) / denom * 0.25f;
    float t2 = (c_sum * (x2 - x1) * y_diff) / denom * 0.5f;

    float numer = (a1 + a2) * (b1 + b2) - c_sum * c_sum;
    float denom_log = 4.0f * std::sqrt((a1 * b1 - c1 * c1) * (a2 * b2 - c2 * c2)) + eps;

    float t3 = 0.5f * std::log(numer / denom_log + eps);

    float bd = clamp(t1 + t2 + t3, eps, 100.0f);
    float hd = std::sqrt(1.0f - std::exp(-bd) + eps);

    return 1.0f - hd;
}


std::vector<std::pair<int, int>> calculate_obb_corners(float x_center, float y_center, float width, float height, float angle) {
    float cos_angle = std::cos(angle);  // 计算余弦
    float sin_angle = std::sin(angle);  // 计算正弦
    float dx = width / 2.0f;
    float dy = height / 2.0f;

    std::vector<std::pair<int, int>> corners = {
        { static_cast<int>(x_center + cos_angle * dx - sin_angle * dy),
          static_cast<int>(y_center + sin_angle * dx + cos_angle * dy) },

        { static_cast<int>(x_center - cos_angle * dx - sin_angle * dy),
          static_cast<int>(y_center - sin_angle * dx + cos_angle * dy) },

        { static_cast<int>(x_center - cos_angle * dx + sin_angle * dy),
          static_cast<int>(y_center - sin_angle * dx - cos_angle * dy) },

        { static_cast<int>(x_center + cos_angle * dx + sin_angle * dy),
          static_cast<int>(y_center + sin_angle * dx - cos_angle * dy) }
    };

    return corners;
}

// NMS 非极大值抑制
void rotate_nms(std::vector<YoloObbBox> &bboxes, float confThreshold, float nmsThreshold)
{
    // 先排序，按照置信度降序排列
    std::sort(bboxes.begin(), bboxes.end(), [](const YoloObbBox &a, const YoloObbBox &b) { return a.confidence > b.confidence; });

    int updated_size = bboxes.size();
    for (int i = 0; i < updated_size; i++) {
        if (bboxes[i].confidence < confThreshold)
            continue;
        // 这里使用移除冗余框，而不是 erase 操作，减少内存移动的开销
        for (int j = i + 1; j < updated_size;) {
            float iou = cal_rotate_iou(bboxes[i], bboxes[j]);
            if (iou > nmsThreshold) {
                bboxes[j].confidence = -1;  // 设置为负值，后续不会再计算其IOU
            }
            j++;
        }
    }
    // 移除那些置信度小于0的框
    bboxes.erase(std::remove_if(bboxes.begin(), bboxes.end(), [](const YoloObbBox &b) { return b.confidence < 0; }), bboxes.end());
}

YoloObbInfo* yolo_obb_postprocess(float *output0, FrameSize frame_shape, FrameSize input_shape, FrameSize display_shape, int class_num,float conf_thresh, float nms_thresh,int max_box_cnt, int *box_cnt)
{
    float ratio_w=input_shape.width/(frame_shape.width*1.0);
    float ratio_h=input_shape.height/(frame_shape.height*1.0);
    float scale=MIN(ratio_w,ratio_h);
    const float display_scale_x=display_shape.width/(frame_shape.width*1.0);
    const float display_scale_y=display_shape.height/(frame_shape.height*1.0);
	std::vector<YoloObbBox> results;
    int f_len=class_num+5;
    int num_box=((input_shape.width/8)*(input_shape.height/8)+(input_shape.width/16)*(input_shape.height/16)+(input_shape.width/32)*(input_shape.height/32));
    results.reserve(std::min(num_box, std::max(max_box_cnt * 4, 64)));

    for(int i=0;i<num_box;i++){
        float* vec=output0+i*f_len;
        float box[4]={vec[0],vec[1],vec[2],vec[3]};
        float* class_scores=vec+4;
        float score;
        int max_class_index =
            (int)ai_rvv_f32_argmax(class_scores, class_num, &score);
        float angle=vec[4+class_num];
        if(score>conf_thresh){
            YoloObbBox bbox;
            float cx_=box[0]/scale*display_scale_x;
            float cy_=box[1]/scale*display_scale_y;
            float w_=box[2]/scale*display_scale_x;
            float h_=box[3]/scale*display_scale_y;
            int cx=int(cx_);
            int cy=int(cy_);
            int w=int(w_);
            int h=int(h_);
            if (w <= 0 || h <= 0) { continue; }
            bbox.box=cv::Rect(cx,cy,w,h);
            bbox.confidence=score;
            bbox.angle=angle;
            bbox.index=max_class_index;
            bbox.covariance=get_covariance_matrix(bbox);
            results.push_back(bbox);
        }
    }
	//执行非最大抑制以消除具有较低置信度的冗余重叠框（NMS）
	rotate_nms(results, conf_thresh, nms_thresh);
    *box_cnt = MIN(results.size(),max_box_cnt);
	YoloObbInfo* yolo_obb_res = (YoloObbInfo *)malloc(*box_cnt * sizeof(YoloObbInfo));
	if (*box_cnt > 0 && yolo_obb_res == NULL) {
		return NULL;
	}
	for (int i = 0; i < *box_cnt; i++)
	{
        std::vector<std::pair<int, int>> corners=calculate_obb_corners(results[i].box.x, results[i].box.y, results[i].box.width, results[i].box.height, results[i].angle);
        yolo_obb_res[i].x1=corners[0].first;
        yolo_obb_res[i].y1=corners[0].second;
        yolo_obb_res[i].x2=corners[1].first;
        yolo_obb_res[i].y2=corners[1].second;
        yolo_obb_res[i].x3=corners[2].first;
        yolo_obb_res[i].y3=corners[2].second;
        yolo_obb_res[i].x4=corners[3].first;
        yolo_obb_res[i].y4=corners[3].second;
		yolo_obb_res[i].confidence = results[i].confidence;
		yolo_obb_res[i].index = results[i].index;
	}
	return yolo_obb_res;
}

void yolo_obb_free_outputs(void *context)
{
    free(context);
}

YoloObbInfo* yolo26_obb_postprocess(float *output0, FrameSize frame_shape, FrameSize input_shape, FrameSize display_shape, int class_num,float conf_thresh, int max_box_cnt, int *box_cnt)
{
    float ratio_w=input_shape.width/(frame_shape.width*1.0);
    float ratio_h=input_shape.height/(frame_shape.height*1.0);
    float scale=MIN(ratio_w,ratio_h);
    const float display_scale_x=display_shape.width/(frame_shape.width*1.0);
    const float display_scale_y=display_shape.height/(frame_shape.height*1.0);
	std::vector<YoloObbBox> results;
    int f_len=7;
    int num_box=300;
    results.reserve(num_box);

    for(int i=0;i<num_box;i++){
        float* vec=output0+i*f_len;
        float box[4]={vec[0],vec[1],vec[2],vec[3]};
        float score=vec[4];
        float class_id=vec[5];
        float angle=vec[6];
        if(score>conf_thresh){
            YoloObbBox bbox;
            float cx_=box[0]/scale*display_scale_x;
            float cy_=box[1]/scale*display_scale_y;
            float w_=box[2]/scale*display_scale_x;
            float h_=box[3]/scale*display_scale_y;
            int cx=int(cx_);
            int cy=int(cy_);
            int w=int(w_);
            int h=int(h_);
            if (w <= 0 || h <= 0) { continue; }
            bbox.box=cv::Rect(cx,cy,w,h);
            bbox.confidence=score;
            bbox.angle=angle;
            bbox.index=class_id;
            results.push_back(bbox);
        }
    }

    *box_cnt = MIN(results.size(),max_box_cnt);
	YoloObbInfo* yolo_obb_res = (YoloObbInfo *)malloc(*box_cnt * sizeof(YoloObbInfo));
	if (*box_cnt > 0 && yolo_obb_res == NULL) {
		return NULL;
	}
	for (int i = 0; i < *box_cnt; i++)
	{
        std::vector<std::pair<int, int>> corners=calculate_obb_corners(results[i].box.x, results[i].box.y, results[i].box.width, results[i].box.height, results[i].angle);
        yolo_obb_res[i].x1=corners[0].first;
        yolo_obb_res[i].y1=corners[0].second;
        yolo_obb_res[i].x2=corners[1].first;
        yolo_obb_res[i].y2=corners[1].second;
        yolo_obb_res[i].x3=corners[2].first;
        yolo_obb_res[i].y3=corners[2].second;
        yolo_obb_res[i].x4=corners[3].first;
        yolo_obb_res[i].y4=corners[3].second;
		yolo_obb_res[i].confidence = results[i].confidence;
		yolo_obb_res[i].index = results[i].index;
	}
	return yolo_obb_res;
}
