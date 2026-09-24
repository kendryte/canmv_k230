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
#include <unistd.h>
#include <array>

typedef struct BoxInfo
{
    float x1;   // 行人检测框左上顶点x坐标
    float y1;   // 行人检测框左上顶点y坐标
    float x2;   // 行人检测框右下顶点x坐标
    float y2;   // 行人检测框右下顶点y坐标
    float score;   // 行人检测框的得分
    int label;  // 行人检测框的标签

    int idx;    // 行人检测框的序号
} BoxInfo;

struct  OutputPose {
    cv::Rect_<float> box;  // 行人检测框 box
    int label =0;          // 检测框标签，默认为行人（0）
    float confidence =0.0; // 置信度
    std::array<float, 17 * 3> kps;
};

#define BOXNUM 2100 
#define ANCHORLENGTH 56

void nms_pose(std::vector<BoxInfo> &input_boxes, float nms_thresh,std::vector<int> &nms_result)
{
    (void)nms_result;
    std::sort(input_boxes.begin(), input_boxes.end(), [](BoxInfo a, BoxInfo b) { return a.score > b.score; });
    const size_t box_count = input_boxes.size();
    std::vector<float> vArea(box_count);
    std::vector<uint8_t> suppressed(box_count, 0);
    for (size_t i = 0; i < box_count; ++i)
    {
        vArea[i] = (input_boxes[i].x2 - input_boxes[i].x1 + 1)
            * (input_boxes[i].y2 - input_boxes[i].y1 + 1);
    }
    for (size_t i = 0; i < box_count; ++i)
    {
        if (suppressed[i]) {
            continue;
        }
        for (size_t j = i + 1; j < box_count; ++j)
        {
            if (suppressed[j]) {
                continue;
            }
            float xx1 = std::max(input_boxes[i].x1, input_boxes[j].x1);
            float yy1 = std::max(input_boxes[i].y1, input_boxes[j].y1);
            float xx2 = std::min(input_boxes[i].x2, input_boxes[j].x2);
            float yy2 = std::min(input_boxes[i].y2, input_boxes[j].y2);
            float w = std::max(float(0), xx2 - xx1 + 1);
            float h = std::max(float(0), yy2 - yy1 + 1);
            float inter = w * h;
            float ovr = inter / (vArea[i] + vArea[j] - inter);
            if (ovr >= nms_thresh)
            {
                suppressed[j] = 1;
            }
        }
    }
    size_t output_index = 0;
    for (size_t i = 0; i < box_count; ++i) {
        if (!suppressed[i]) {
            if (output_index != i) {
                input_boxes[output_index] = input_boxes[i];
            }
            ++output_index;
        }
    }
    input_boxes.resize(output_index);
}

bool BatchDetect(float* all_data,int num_box, std::vector<std::vector<OutputPose>>& output,cv::Vec4d params, float obj_thresh, float nms_thresh)
{


    std::vector<int64_t> _outputTensorShape = { 1, ANCHORLENGTH, num_box};
    int _anchorLength = ANCHORLENGTH;

    // [1, 56 ,8400] -> [1, 8400, 56]
    cv::Mat output0 = cv::Mat(cv::Size((int)_outputTensorShape[2], (int)_outputTensorShape[1]), CV_32F, all_data).t(); 
 
    float* pdata = (float*)output0.data; // [classid,x,y,w,h,x,y,...21个点]
    int rows = output0.rows; // 预测框的数量 8400
    // 一张图片的预测框
 
    std::vector<float> confidences;
    std::vector<cv::Rect> boxes;
    std::vector<int> labels;
    std::vector<std::array<float, 17 * 3>> kpss;
    confidences.reserve(rows);
    boxes.reserve(rows);
    labels.reserve(rows);
    kpss.reserve(rows);

    for (int r=0; r<rows; ++r){
 
        // 得到人类别概率
        auto kps_ptr = pdata + 5;
 
        // 预测框坐标映射到原图上
        float score = pdata[4];
        
        if(score > obj_thresh){
            float x = (pdata[0] - params[2]) / params[0]; //x
            float y = (pdata[1] - params[3]) / params[1]; //y
            float w = pdata[2] / params[0]; //w
            float h = pdata[3] / params[1]; //h
 
            // int left = MAX(int(x - 0.5 *w +0.5), 0);
            // int top = MAX(int(y - 0.5*h + 0.5), 0);
            float left = MAX(int(x - 0.5 *w +0.5), 0);
            float top = MAX(int(y - 0.5*h + 0.5), 0);
 
            std::array<float, 17 * 3> kps;
            for (int k=0; k< 17; k++){
                
                float kps_x = (*(kps_ptr + 3 * k) - params[2]) / params[0];
                float kps_y = (*(kps_ptr + 3 * k + 1) - params[3]) / params[1];
                float kps_s = *(kps_ptr + 3 * k + 2);
 
                kps[3 * k] = kps_x;
                kps[3 * k + 1] = kps_y;
                kps[3 * k + 2] = kps_s;
            }
 
            confidences.push_back(score);
            labels.push_back(0);
            kpss.push_back(kps);
            // boxes.push_back(Rect(left, top, int(w + 0.5), int(h + 0.5)));
            boxes.push_back(cv::Rect(left, top, float(w + 0.5), float(h + 0.5)));
        }
        pdata += _anchorLength; //下一个预测框
    }
 
    // 对一张图的预测框执行NMS处理
    std::vector<int> nms_result;
    
    std::vector<BoxInfo> boxinfo_results;
    boxinfo_results.reserve(boxes.size());
    BoxInfo res;
    float x1,y1,x2,y2,score_;
    int label,idx;
    for(int i=0;i<boxes.size();i++)
    {
        x1 =  float( boxes[i].tl().x ) ;
        y1 = float( boxes[i].tl().y ) ;
        x2 = float( boxes[i].br().x ) ;
        y2 = float( boxes[i].br().y ) ;
        score_ = confidences[i];
        label = labels[i];
        idx = i;

        res = {  x1,y1,x2,y2,score_,label,idx };
        boxinfo_results.push_back(res);
    }


    nms_pose(boxinfo_results, nms_thresh,nms_result);

    // 对一张图片：依据NMS处理得到的索引，得到类别id、confidence、box，并置于结构体OutputDet的容器中
    std::vector<OutputPose> temp_output;
    temp_output.reserve(boxinfo_results.size());
    for (size_t i=0; i<boxinfo_results.size(); ++i){
        int idx = boxinfo_results[i].idx;
        OutputPose result;
 
        result.confidence = confidences[idx];
        result.box = boxes[idx];
        result.label = labels[idx];
        result.kps = kpss[idx];

        temp_output.push_back(result);
    }
    output.push_back(temp_output); // 多张图片的输出；添加一张图片的输出置于此容器中
 
    if (output.size())
        return true;
    else
        return false;
 
}

bool Detect(float* all_data,int num_box, std::vector<OutputPose> &output,cv::Vec4d params, float obj_thresh, float nms_thresh){
    std::vector<std::vector<OutputPose>> temp_output;

    bool flag = BatchDetect(all_data,num_box, temp_output,params,obj_thresh,nms_thresh);
    output = temp_output[0];
    return true;
}

PersonKPOutput* person_kp_postprocess(float *data, FrameSize frame_size, FrameSize kmodel_frame_size, float obj_thresh, float nms_thresh, int *box_cnt)
{
    std::vector<OutputPose> output;
    cv::Vec4d params; // 计算 这个padding值
    
    int ori_w = frame_size.width;
    int ori_h = frame_size.height;
    int width = kmodel_frame_size.width;
    int height = kmodel_frame_size.height;
    float ratiow = (float)width / ori_w;
    float ratioh = (float)height / ori_h;
    float ratio = ratiow < ratioh ? ratiow : ratioh;
    int new_w = (int)(ratio * ori_w);
    int new_h = (int)(ratio * ori_h);
    float dw = (float)(width - new_w) / 2;
    float dh = (float)(height - new_h) / 2;
    // int top = (int)(roundf(dh - 0.1));
    // int bottom = (int)(roundf(dh + 0.1));
    // int left = (int)(roundf(dw - 0.1));
    // int right = (int)(roundf(dw - 0.1));

    int top = (int)(roundf(dh ));
    int bottom = (int)(roundf(dh ));
    int left = (int)(roundf(dw ));
    // int right = (int)(roundf(dw - 0.1));
    int right = (int)(roundf(dw ));

    params[0] = ratio;
    params[1] = ratio;

    params[2] = left;
    params[3] = top;

    int num_box=((kmodel_frame_size.width/8)*(kmodel_frame_size.height/8)+(kmodel_frame_size.width/16)*(kmodel_frame_size.height/16)+(kmodel_frame_size.width/32)*(kmodel_frame_size.height/32));

    float *foutput_0 = data;
    bool find_ = Detect(foutput_0,num_box, output,params,obj_thresh,nms_thresh);

    *box_cnt = output.size();
    PersonKPOutput *personKPOutput = (PersonKPOutput *)malloc(*box_cnt * sizeof(PersonKPOutput));
    if (*box_cnt > 0 && personKPOutput == NULL) {
        return NULL;
    }
    for (int i = 0; i < *box_cnt; i++)
    {
        personKPOutput[i].confidence = output[i].confidence;
        personKPOutput[i].box[0] = int(output[i].box.tl().x);
        personKPOutput[i].box[1] = int(output[i].box.tl().y);
        personKPOutput[i].box[2] = int(output[i].box.br().x);
        personKPOutput[i].box[3] = int(output[i].box.br().y);
        for (int j = 0; j < 17; j++)
        {
            for (int k = 0; k < 3; k++)
            {
                personKPOutput[i].kps[j][k] = output[i].kps[j * 3 + k];
            }
        }
    }
    return personKPOutput;
}

void person_kp_free_outputs(void *context)
{
    free(context);
}
