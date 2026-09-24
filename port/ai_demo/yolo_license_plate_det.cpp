#include <opencv2/core.hpp>
#include <opencv2/highgui.hpp>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp>
#include "aidemo_wrap.h"
#include <stdlib.h>
#include <iostream>
#include <unistd.h>
#include <algorithm>

typedef struct {
	float score;
	float box_kps[12];
}YoloLicensePlateDetBox;

float pose_get_iou(cv::Rect rect1, cv::Rect rect2)
{
	float xx1, yy1, xx2, yy2;
	xx1 = std::max(rect1.x, rect2.x);
	yy1 = std::max(rect1.y, rect2.y);
	xx2 = std::min(rect1.x + rect1.width - 1, rect2.x + rect2.width - 1);
	yy2 = std::min(rect1.y + rect1.height - 1, rect2.y + rect2.height - 1);
 
	float insection_width, insection_height;
	insection_width = std::max(0.0f, xx2 - xx1 + 1);
	insection_height = std::max(0.0f, yy2 - yy1 + 1);
	float insection_area, union_area, iou;
	insection_area = float(insection_width) * insection_height;
	union_area = float(rect1.width*rect1.height + rect2.width*rect2.height - insection_area);
	iou = insection_area / union_area;

	return iou;
}

// NMS 非极大值抑制
void pose_nms(std::vector<YoloLicensePlateDetBox> &bboxes, float confThreshold, float nmsThreshold)
{
    // 先排序，按照置信度降序排列
    std::sort(bboxes.begin(), bboxes.end(), [](const YoloLicensePlateDetBox &a, const YoloLicensePlateDetBox &b) { return a.score > b.score; });

    int updated_size = bboxes.size();
    for (int i = 0; i < updated_size; i++) {
        if (bboxes[i].score < confThreshold)
            continue;
        // 这里使用移除冗余框，而不是 erase 操作，减少内存移动的开销
        for (int j = i + 1; j < updated_size;) {
            cv::Rect rect1(bboxes[i].box_kps[0], bboxes[i].box_kps[1], bboxes[i].box_kps[2], bboxes[i].box_kps[3]);
            cv::Rect rect2(bboxes[j].box_kps[0], bboxes[j].box_kps[1], bboxes[j].box_kps[2], bboxes[j].box_kps[3]);
            float iou = pose_get_iou(rect1, rect2);
            if (iou > nmsThreshold) {
                bboxes[j].score = -1;  // 设置为负值，后续不会再计算其IOU
            }
            j++;
        }
    }

    // 移除那些置信度小于0的框
    bboxes.erase(std::remove_if(bboxes.begin(), bboxes.end(), [](const YoloLicensePlateDetBox &b) { return b.score < 0; }), bboxes.end());
}

YoloLicensePlateDetInfo* yolo_license_plate_det_postprocess(float *output0, FrameSize frame_shape, FrameSize input_shape, FrameSize display_shape, float conf_thresh, float nms_thresh,int max_box_cnt, int *box_cnt)
{
    float ratio_w=input_shape.width/(frame_shape.width*1.0);
    float ratio_h=input_shape.height/(frame_shape.height*1.0);
    float scale=MIN(ratio_w,ratio_h);
    
	std::vector<YoloLicensePlateDetBox> results;
    int f_len=1+4+8;
    int num_box=((input_shape.width/8)*(input_shape.height/8)+(input_shape.width/16)*(input_shape.height/16)+(input_shape.width/32)*(input_shape.height/32));
    results.reserve(std::min(num_box, std::max(max_box_cnt * 4, 64)));
    for(int i=0;i<num_box;i++){
        float* vec=output0+i*f_len;
        if(vec[4]>conf_thresh){
            YoloLicensePlateDetBox bbox;
            bbox.score=vec[4];
            
            bbox.box_kps[0]=vec[0]/scale;
            bbox.box_kps[1]=vec[1]/scale;
            bbox.box_kps[2]=vec[2]/scale;
            bbox.box_kps[3]=vec[3]/scale;
        
            for(int j=0;j<4;j++){
                bbox.box_kps[2*j+4]=vec[5+2*j]/scale;
                bbox.box_kps[2*j+5]=vec[6+2*j]/scale;
            }
            float x=float(MAX(bbox.box_kps[0]-0.5*bbox.box_kps[2],0.0));
            float y=float(MAX(bbox.box_kps[1]-0.5*bbox.box_kps[3],0.0));
            bbox.box_kps[0]=x;
            bbox.box_kps[1]=y;
            float w=float(bbox.box_kps[2]);
            float h=float(bbox.box_kps[3]);
            if (w <= 0 || h <= 0) { continue; }
            results.push_back(bbox);
        }
    }
	//执行非最大抑制以消除具有较低置信度的冗余重叠框（NMS）
	pose_nms(results, conf_thresh, nms_thresh);
    *box_cnt = MIN(results.size(),max_box_cnt);
	YoloLicensePlateDetInfo* yolo_license_plate_det_res = (YoloLicensePlateDetInfo *)malloc(*box_cnt * sizeof(YoloLicensePlateDetInfo));
	if (*box_cnt > 0 && yolo_license_plate_det_res == NULL) {
		return NULL;
	}
	for (int i = 0; i < *box_cnt; i++)
	{
		yolo_license_plate_det_res[i].score= results[i].score;
        hal_rvv_memcpy(yolo_license_plate_det_res[i].box_kps,results[i].box_kps,12*sizeof(float));
    }
	return yolo_license_plate_det_res;
}

void yolo_license_plate_det_free_outputs(void *context)
{
    free(context);
}
