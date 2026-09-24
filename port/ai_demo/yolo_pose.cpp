#include <opencv2/core.hpp>
#include <opencv2/highgui.hpp>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp>
#include "aidemo_wrap.h"
#include <stdlib.h>
#include <iostream>
#include <unistd.h>
#include <algorithm>
#include <climits>
#include <new>
#include <utility>

typedef struct {
    std::vector<float> kps;
    int kp_num;
    int kp_dim;
	cv::Rect box;
	float confidence;
	int index;
}YoloPoseBox;


float yolov8_pose_get_iou(cv::Rect rect1, cv::Rect rect2)
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
void yolov8_pose_nms(std::vector<YoloPoseBox> &bboxes, float confThreshold, float nmsThreshold)
{
    // 先排序，按照置信度降序排列
    std::sort(bboxes.begin(), bboxes.end(), [](const YoloPoseBox &a, const YoloPoseBox &b) { return a.confidence > b.confidence; });

    int updated_size = bboxes.size();
    for (int i = 0; i < updated_size; i++) {
        if (bboxes[i].confidence < confThreshold)
            continue;
        // 这里使用移除冗余框，而不是 erase 操作，减少内存移动的开销
        for (int j = i + 1; j < updated_size;) {
            float iou = yolov8_pose_get_iou(bboxes[i].box, bboxes[j].box);
            if (iou > nmsThreshold) {
                bboxes[j].confidence = -1;  // 设置为负值，后续不会再计算其IOU
            }
            j++;
        }
    }

    bboxes.erase(std::remove_if(bboxes.begin(), bboxes.end(),
        [](const YoloPoseBox &b) { return b.confidence < 0; }), bboxes.end());
}

YoloPoseInfo* yolov8_pose_postprocess(float *output0, FrameSize frame_shape, FrameSize input_shape, FrameSize display_shape, int calss_num,int kp_num,int kp_dim, float conf_thresh, float nms_thresh, int max_box_cnt,int *box_cnt)
{
    try {
	*box_cnt = -1;
	if (max_box_cnt < 0 || kp_num <= 0 || (kp_dim != 2 && kp_dim != 3) || kp_num > (INT_MAX - 5) / kp_dim) {
		return NULL;
	}
    float ratio_w=input_shape.width/(frame_shape.width*1.0);
    float ratio_h=input_shape.height/(frame_shape.height*1.0);
    float scale=MIN(ratio_w,ratio_h);
    const float display_scale_x=display_shape.width/(frame_shape.width*1.0);
    const float display_scale_y=display_shape.height/(frame_shape.height*1.0);

	std::vector<YoloPoseBox> results;
    int f_len=kp_num*kp_dim+5;
    int num_box=((input_shape.width/8)*(input_shape.height/8)+(input_shape.width/16)*(input_shape.height/16)+(input_shape.width/32)*(input_shape.height/32));
    const int kps_size = kp_num * kp_dim;
    results.reserve(std::min(num_box, std::max(std::min(max_box_cnt, num_box) * 4, 64)));
    for(int i=0;i<num_box;i++){
        float* vec=output0+i*f_len;
        float box[4]={vec[0],vec[1],vec[2],vec[3]};
        float score=vec[4];
        float* kps = vec+5;
        if(score>conf_thresh){
            float x_=box[0]/scale*display_scale_x;
            float y_=box[1]/scale*display_scale_y;
            float w_=box[2]/scale*display_scale_x;
            float h_=box[3]/scale*display_scale_y;
            int x=int(MAX(x_-0.5*w_,0));
            int y=int(MAX(y_-0.5*h_,0));
            int w=int(w_);
            int h=int(h_);
            if (w <= 0 || h <= 0) { continue; }

            YoloPoseBox bbox;
            bbox.box=cv::Rect(x,y,w,h);
            bbox.confidence=score;
            bbox.index=0;
            bbox.kp_num=kp_num;
            bbox.kp_dim=kp_dim;
            bbox.kps.resize(kps_size);
            if(kp_dim==3){
                for (int j = 0; j < kp_num; j++) {
                    const int offset = j * 3;
                    bbox.kps[offset] = kps[offset]/scale*display_scale_x;
                    bbox.kps[offset + 1] = kps[offset + 1]/scale*display_scale_y;
                    bbox.kps[offset + 2] = kps[offset + 2];
                }
            }
            else if(kp_dim==2){
                for (int j = 0; j < kp_num; j++) {
                    const int offset = j * 2;
                    bbox.kps[offset] = kps[offset]/scale*display_scale_x;
                    bbox.kps[offset + 1] = kps[offset + 1]/scale*display_scale_y;
                }
            }
			try {
				results.push_back(std::move(bbox));
			} catch (const std::bad_alloc &) {
				return NULL;
			}
        }
    }
	//执行非最大抑制以消除具有较低置信度的冗余重叠框（NMS）
	yolov8_pose_nms(results, conf_thresh, nms_thresh);
    *box_cnt = MIN(results.size(),max_box_cnt);
    YoloPoseInfo* yolo_pose_res = (YoloPoseInfo *)malloc(*box_cnt * sizeof(YoloPoseInfo));
    if (*box_cnt > 0 && yolo_pose_res == NULL) {
        return NULL;
    }
    for (int i = 0; i < *box_cnt; i++) {
        yolo_pose_res[i].kps = (float*)malloc(kps_size * sizeof(float));
        if (yolo_pose_res[i].kps == NULL && kps_size != 0) {
            for(int j = 0; j < i; j++) {
                free(yolo_pose_res[j].kps);
            }
            free(yolo_pose_res);
            return NULL;
        }
    }
	for (int i = 0; i < *box_cnt; i++)
	{
		yolo_pose_res[i].confidence = results[i].confidence;
		yolo_pose_res[i].index = results[i].index;
		yolo_pose_res[i].x = results[i].box.x;
		yolo_pose_res[i].y = results[i].box.y;
		yolo_pose_res[i].w = results[i].box.width;
		yolo_pose_res[i].h = results[i].box.height;
		if (kps_size != 0) {
			memcpy(yolo_pose_res[i].kps, results[i].kps.data(), kps_size * sizeof(float));
		}
		yolo_pose_res[i].kp_num = results[i].kp_num;
		yolo_pose_res[i].kp_dim = results[i].kp_dim;
	}
	return yolo_pose_res;
    } catch (...) {
        *box_cnt = -1;
        return NULL;
    }
}

YoloPoseInfo* yolo26_pose_postprocess(float *output0, FrameSize frame_shape, FrameSize input_shape, FrameSize display_shape, int class_num,int kp_num,int kp_dim,float conf_thresh,int max_box_cnt, int *box_cnt)
{
    try {
	*box_cnt = -1;
	if (max_box_cnt < 0 || kp_num <= 0 || (kp_dim != 2 && kp_dim != 3) || kp_num > (INT_MAX - 6) / kp_dim) {
		return NULL;
	}
    float ratio_w=input_shape.width/(frame_shape.width*1.0);
    float ratio_h=input_shape.height/(frame_shape.height*1.0);
    float scale=MIN(ratio_w,ratio_h);
    const float display_scale_x=display_shape.width/(frame_shape.width*1.0);
    const float display_scale_y=display_shape.height/(frame_shape.height*1.0);

	std::vector<YoloPoseBox> results;
    const int f_len=kp_num*kp_dim+6;
    const int num_box=300;
    const int kps_size = kp_num * kp_dim;
    results.reserve(num_box);
    
    for(int i=0;i<num_box;i++){
        float* vec=output0+i*f_len;
        float box[4]={vec[0],vec[1],vec[2],vec[3]};
        float score=vec[4];
        float class_id=vec[5];
        float* kps=vec+6;
        if(score>conf_thresh){
            float x_1=box[0]/scale*display_scale_x;
            float y_1=box[1]/scale*display_scale_y;
            float x_2=box[2]/scale*display_scale_x;
            float y_2=box[3]/scale*display_scale_y;
            int x=int(MAX(x_1,0));
            int y=int(MAX(y_1,0));
            int w=int(x_2-x_1);
            int h=int(y_2-y_1);
            if (w <= 0 || h <= 0) { continue; }
            
            YoloPoseBox bbox;
            bbox.box=cv::Rect(x,y,w,h);
            bbox.confidence=score;
            bbox.index=int(class_id);
            bbox.kp_num=kp_num;
            bbox.kp_dim=kp_dim;
            bbox.kps.resize(kps_size);
            if(kp_dim==3){
                for (int j = 0; j < kp_num; j++) {
                    const int offset = j * 3;
                    bbox.kps[offset] = kps[offset]/scale*display_scale_x;
                    bbox.kps[offset + 1] = kps[offset + 1]/scale*display_scale_y;
                    bbox.kps[offset + 2] = kps[offset + 2];
                }
            }
            else if(kp_dim==2){
                for (int j = 0; j < kp_num; j++) {
                    const int offset = j * 2;
                    bbox.kps[offset] = kps[offset]/scale*display_scale_x;
                    bbox.kps[offset + 1] = kps[offset + 1]/scale*display_scale_y;
                }
            }
           
			try {
				results.push_back(std::move(bbox));
			} catch (const std::bad_alloc &) {
				return NULL;
			}
        }
    }
    *box_cnt = MIN(results.size(),max_box_cnt);
    YoloPoseInfo* yolo_pose_res = (YoloPoseInfo *)malloc(*box_cnt * sizeof(YoloPoseInfo));
    if (*box_cnt > 0 && yolo_pose_res == NULL) {
        return NULL;
    }
    for (int i = 0; i < *box_cnt; i++) {
        yolo_pose_res[i].kps = (float*)malloc(kps_size * sizeof(float));
        if (yolo_pose_res[i].kps == NULL && kps_size != 0) {
            for(int j = 0; j < i; j++) {
                free(yolo_pose_res[j].kps);
            }
            free(yolo_pose_res);
            return NULL;
        }
    }
	for (int i = 0; i < *box_cnt; i++)
	{
		yolo_pose_res[i].confidence = results[i].confidence;
		yolo_pose_res[i].index = results[i].index;
		yolo_pose_res[i].x = results[i].box.x;
		yolo_pose_res[i].y = results[i].box.y;
		yolo_pose_res[i].w = results[i].box.width;
		yolo_pose_res[i].h = results[i].box.height;
		if (kps_size != 0) {
			memcpy(yolo_pose_res[i].kps, results[i].kps.data(), kps_size * sizeof(float));
		}
		yolo_pose_res[i].kp_num = results[i].kp_num;
		yolo_pose_res[i].kp_dim = results[i].kp_dim;
	}
	return yolo_pose_res;
    } catch (...) {
        *box_cnt = -1;
        return NULL;
    }
}

void yolo_pose_free_outputs(YoloPoseInfo *outputs, int count)
{
    if (outputs == NULL) {
        return;
    }

    for (int i = 0; i < count; i++) {
        free(outputs[i].kps);
    }
    free(outputs);
}
