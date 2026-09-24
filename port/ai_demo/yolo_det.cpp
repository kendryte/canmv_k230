#include <opencv2/core.hpp>
#include <opencv2/highgui.hpp>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp>
#include "aidemo_wrap.h"
#include <stdlib.h>
#include <iostream>
#include <unistd.h>
#include <algorithm>
#include "ai_rvv_kernels.h"

typedef struct {
	cv::Rect box;
	float confidence;
	int index;
}YoloDetBox;

float get_iou(cv::Rect rect1, cv::Rect rect2)
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

// NMS 非极大值抑制
void nms(std::vector<YoloDetBox> &bboxes, float confThreshold, float nmsThreshold)
{
    // 先排序，按照置信度降序排列
    std::sort(bboxes.begin(), bboxes.end(), [](const YoloDetBox &a, const YoloDetBox &b) { return a.confidence > b.confidence; });

    int updated_size = bboxes.size();
    for (int i = 0; i < updated_size; i++) {
        if (bboxes[i].confidence < confThreshold)
            continue;
        // 这里使用移除冗余框，而不是 erase 操作，减少内存移动的开销
        for (int j = i + 1; j < updated_size;) {
            float iou = get_iou(bboxes[i].box, bboxes[j].box);
            if (iou > nmsThreshold) {
                bboxes[j].confidence = -1;  // 设置为负值，后续不会再计算其IOU
            }
            j++;
        }
    }

    // 移除那些置信度小于0的框
    bboxes.erase(std::remove_if(bboxes.begin(), bboxes.end(), [](const YoloDetBox &b) { return b.confidence < 0; }), bboxes.end());
}

YoloDetInfo* yolov8_det_postprocess(float *output0, FrameSize frame_shape, FrameSize input_shape, FrameSize display_shape, int class_num,float conf_thresh, float nms_thresh,int max_box_cnt, int *box_cnt)
{
    float ratio_w=input_shape.width/(frame_shape.width*1.0);
    float ratio_h=input_shape.height/(frame_shape.height*1.0);
    float scale=MIN(ratio_w,ratio_h);
    const float display_scale_x=display_shape.width/(frame_shape.width*1.0);
    const float display_scale_y=display_shape.height/(frame_shape.height*1.0);

	std::vector<YoloDetBox> results;
    int f_len=class_num+4;
    int num_box=((input_shape.width/8)*(input_shape.height/8)+(input_shape.width/16)*(input_shape.height/16)+(input_shape.width/32)*(input_shape.height/32));
    results.reserve(std::min(num_box, std::max(max_box_cnt * 4, 64)));
    for(int i=0;i<num_box;i++){
        float* vec=output0+i*f_len;
        float box[4]={vec[0],vec[1],vec[2],vec[3]};
        float* class_scores=vec+4;
        float score;
        int max_class_index =
            (int)ai_rvv_f32_argmax(class_scores, class_num, &score);
        if(score>conf_thresh){
            YoloDetBox bbox;
            float x_=box[0]/scale*display_scale_x;
            float y_=box[1]/scale*display_scale_y;
            float w_=box[2]/scale*display_scale_x;
            float h_=box[3]/scale*display_scale_y;
            int x=int(MAX(x_-0.5*w_,0));
            int y=int(MAX(y_-0.5*h_,0));
            int w=int(w_);
            int h=int(h_);
            if (w <= 0 || h <= 0) { continue; }
            bbox.box=cv::Rect(x,y,w,h);
            bbox.confidence=score;
            bbox.index=max_class_index;
            results.push_back(bbox);
        }
    }
    //执行非最大抑制以消除具有较低置信度的冗余重叠框（NMS）
    nms(results, conf_thresh, nms_thresh);
    *box_cnt = MIN(results.size(),max_box_cnt);
    YoloDetInfo* yolo_det_res = (YoloDetInfo *)malloc(*box_cnt * sizeof(YoloDetInfo));
    if (*box_cnt > 0 && yolo_det_res == NULL) {
        return NULL;
    }
    for (int i = 0; i < *box_cnt; i++)
    {
        yolo_det_res[i].confidence = results[i].confidence;
        yolo_det_res[i].index = results[i].index;
        yolo_det_res[i].x = results[i].box.x;
        yolo_det_res[i].y = results[i].box.y;
        yolo_det_res[i].w = results[i].box.width;
        yolo_det_res[i].h = results[i].box.height;
    }
    return yolo_det_res;
}

void yolo_det_free_outputs(void *context)
{
    free(context);
}

YoloDetInfo* yolov5_det_postprocess(float *output0, FrameSize frame_shape, FrameSize input_shape, FrameSize display_shape, int class_num,float conf_thresh, float nms_thresh,int max_box_cnt, int *box_cnt)
{
    float ratio_w=input_shape.width/(frame_shape.width*1.0);
    float ratio_h=input_shape.height/(frame_shape.height*1.0);
    float scale=MIN(ratio_w,ratio_h);
    const float display_scale_x=display_shape.width/(frame_shape.width*1.0);
    const float display_scale_y=display_shape.height/(frame_shape.height*1.0);

	std::vector<YoloDetBox> results;
    int f_len=class_num+5;
    int num_box=((input_shape.width/8)*(input_shape.height/8)+(input_shape.width/16)*(input_shape.height/16)+(input_shape.width/32)*(input_shape.height/32))*3;
    results.reserve(std::min(num_box, std::max(max_box_cnt * 4, 64)));
    for(int i=0;i<num_box;i++){
        float* vec=output0+i*f_len;
        float box[4]={vec[0],vec[1],vec[2],vec[3]};
        float base_score=vec[4];
        float* class_scores=vec+5;
        float max_class_score;
        int max_class_index =
            (int)ai_rvv_f32_argmax(class_scores, class_num, &max_class_score);
        float score=max_class_score*base_score;
        if(score>conf_thresh){
            YoloDetBox bbox;
            float x_=box[0]/scale*display_scale_x;
            float y_=box[1]/scale*display_scale_y;
            float w_=box[2]/scale*display_scale_x;
            float h_=box[3]/scale*display_scale_y;
            int x=int(MAX(x_-0.5*w_,0));
            int y=int(MAX(y_-0.5*h_,0));
            int w=int(w_);
            int h=int(h_);
            if (w <= 0 || h <= 0) { continue; }
            bbox.box=cv::Rect(x,y,w,h);
            bbox.confidence=score;
            bbox.index=max_class_index;
            results.push_back(bbox);
        }
    }
    //执行非最大抑制以消除具有较低置信度的冗余重叠框（NMS）
    nms(results, conf_thresh, nms_thresh);
    *box_cnt = MIN(results.size(),max_box_cnt);
    YoloDetInfo* yolo_det_res = (YoloDetInfo *)malloc(*box_cnt * sizeof(YoloDetInfo));
    if (*box_cnt > 0 && yolo_det_res == NULL) {
        return NULL;
    }
    for (int i = 0; i < *box_cnt; i++)
    {
        yolo_det_res[i].confidence = results[i].confidence;
        yolo_det_res[i].index = results[i].index;
        yolo_det_res[i].x = results[i].box.x;
        yolo_det_res[i].y = results[i].box.y;
        yolo_det_res[i].w = results[i].box.width;
        yolo_det_res[i].h = results[i].box.height;
    }
    return yolo_det_res;
}

YoloDetInfo* yolo26_det_postprocess(float *output0, FrameSize frame_shape, FrameSize input_shape, FrameSize display_shape, int class_num,float conf_thresh, int max_box_cnt, int *box_cnt)
{
    float ratio_w=input_shape.width/(frame_shape.width*1.0);
    float ratio_h=input_shape.height/(frame_shape.height*1.0);
    float scale=MIN(ratio_w,ratio_h);
    const float display_scale_x=display_shape.width/(frame_shape.width*1.0);
    const float display_scale_y=display_shape.height/(frame_shape.height*1.0);

	std::vector<YoloDetBox> results;
    int f_len=6;
    int num_box=300;
    results.reserve(num_box);
    for(int i=0;i<num_box;i++){
        float* vec=output0+i*f_len;
        float box[4]={vec[0],vec[1],vec[2],vec[3]};
        float score=vec[4];
        float class_id=vec[5];
        if(score>conf_thresh){
            YoloDetBox bbox;
            float x_1=box[0]/scale*display_scale_x;
            float y_1=box[1]/scale*display_scale_y;
            float x_2=box[2]/scale*display_scale_x;
            float y_2=box[3]/scale*display_scale_y;
            int x=int(MAX(x_1,0));
            int y=int(MAX(y_1,0));
            int w=int(x_2-x_1);
            int h=int(y_2-y_1);
            if (w <= 0 || h <= 0) { continue; }
            bbox.box=cv::Rect(x,y,w,h);
            bbox.confidence=score;
            bbox.index=int(class_id);
            results.push_back(bbox);
        }
    }
    *box_cnt = MIN(results.size(),max_box_cnt);
    YoloDetInfo* yolo_det_res = (YoloDetInfo *)malloc(*box_cnt * sizeof(YoloDetInfo));
    if (*box_cnt > 0 && yolo_det_res == NULL) {
        return NULL;
    }
    for (int i = 0; i < *box_cnt; i++)
    {
        yolo_det_res[i].confidence = results[i].confidence;
        yolo_det_res[i].index = results[i].index;
        yolo_det_res[i].x = results[i].box.x;
        yolo_det_res[i].y = results[i].box.y;
        yolo_det_res[i].w = results[i].box.width;
        yolo_det_res[i].h = results[i].box.height;
    }
    return yolo_det_res;
}
