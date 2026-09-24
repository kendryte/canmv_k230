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
	cv::Rect box;
	float score;
}YUNetBox;

float yunet_get_iou(cv::Rect rect1, cv::Rect rect2)
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

// // NMS 非极大值抑制
void yunet_det_nms(std::vector<YUNetBox> &bboxes, float confThreshold, float nmsThreshold)
{
    // 先排序，按照置信度降序排列
    std::sort(bboxes.begin(), bboxes.end(), [](const YUNetBox &a, const YUNetBox &b) { return a.score > b.score; });

    int updated_size = bboxes.size();
    for (int i = 0; i < updated_size; i++) {
        if (bboxes[i].score < confThreshold)
            continue;
        // 这里使用移除冗余框，而不是 erase 操作，减少内存移动的开销
        for (int j = i + 1; j < updated_size;) {
            float iou = yunet_get_iou(bboxes[i].box, bboxes[j].box);
            if (iou > nmsThreshold) {
                bboxes[j].score = -1;  // 设置为负值，后续不会再计算其IOU
            }
            j++;
        }
    }
    // 移除那些置信度小于0的框
    bboxes.erase(std::remove_if(bboxes.begin(), bboxes.end(), [](const YUNetBox &b) { return b.score < 0; }), bboxes.end());
}

YUNetFaceDetInfo* yunet_postprocess(float **outputs, FrameSize frame_shape, FrameSize input_shape, FrameSize display_shape, int* strides,float conf_thresh, float nms_thresh,int max_box_cnt, int *box_cnt)
{
    float ratio_w=input_shape.width/(frame_shape.width*1.0);
    float ratio_h=input_shape.height/(frame_shape.height*1.0);
    float scale=MIN(ratio_w,ratio_h);
    const float display_scale_x=display_shape.width/(frame_shape.width*1.0);
    const float display_scale_y=display_shape.height/(frame_shape.height*1.0);

	std::vector<YUNetBox> results;
    size_t candidate_count = 0;
    for (int i = 0; i < 3; ++i) {
        candidate_count +=
            (size_t)(input_shape.width / strides[i]) *
            (size_t)(input_shape.height / strides[i]);
    }
    results.reserve(std::min(candidate_count,
                             (size_t)std::max(max_box_cnt * 4, 64)));
    for(int i=0;i<3;i++){
        int w_=(int)(input_shape.width/strides[i]);
        int h_=(int)(input_shape.height/strides[i]);
        float* cls=outputs[i];
        float* obj=outputs[i+3];
        float* bbox=outputs[i+6];
        for(int r=0;r<h_;r++){
            for(int c=0;c<w_;c++){
                int idx=r*w_+c;
            	float cls_score=cls[idx];
                float obj_score=obj[idx];
                cls_score=MAX(MIN(cls_score,1.0),0.0);
                obj_score=MAX(MIN(obj_score,1.0),0.0);
                float score=sqrt(cls_score*obj_score);
                if(score>conf_thresh){
                	YUNetBox box_;
                    box_.score=score;
                    float b_cx=(c+bbox[idx*4])*strides[i];
                    float b_cy=(r+bbox[idx*4+1])*strides[i];
                    float b_w=exp(bbox[idx*4+2])*strides[i];
                    float b_h=exp(bbox[idx*4+3])*strides[i];
                    float b_x1=MAX((b_cx-b_w*0.5),0.0);
                    float b_y1=MAX((b_cy-b_h*0.5),0.0);
                    int new_x1=int(b_x1/scale*display_scale_x);
                    int new_y1=int(b_y1/scale*display_scale_y);
                    int new_w=int(b_w/scale*display_scale_x);
                    int new_h=int(b_h/scale*display_scale_y);
                    box_.box=cv::Rect(new_x1,new_y1,new_w,new_h);
                    results.push_back(box_);
                }
            }
        }
    }
	//执行非最大抑制以消除具有较低置信度的冗余重叠框（NMS）
	yunet_det_nms(results, conf_thresh, nms_thresh);
    *box_cnt = MIN(results.size(),max_box_cnt);
	YUNetFaceDetInfo* yunet_face_det_res = (YUNetFaceDetInfo *)malloc(*box_cnt * sizeof(YUNetFaceDetInfo));
	if (*box_cnt > 0 && yunet_face_det_res == NULL) {
		return NULL;
	}
	for (int i = 0; i < *box_cnt; i++)
	{
		yunet_face_det_res[i].score = results[i].score;
		yunet_face_det_res[i].x = results[i].box.x;
		yunet_face_det_res[i].y = results[i].box.y;
		yunet_face_det_res[i].w = results[i].box.width;
		yunet_face_det_res[i].h = results[i].box.height;
	}
	return yunet_face_det_res;
}

void yunet_free_outputs(void *context)
{
    free(context);
}
