#include <stdint.h>
typedef struct ob_det_res
{
    float x1;
    float y1;
    float x2;
    float y2;
    float score;
    int label_index;
}ob_det_res;

typedef struct FrameSize
{
    int width;
    int height;
} FrameSize;

typedef struct CenterPrior
{
    int x;
    int y;
    int stride;
}CenterPrior;

typedef struct ArrayWrapper
{
    uint8_t* data;         // 指向数组的指针
    int* dimensions;   // 数组的维度信息
    float coordinates[8];   // 画图的四个点的位置
}ArrayWrapper;

#ifdef __cplusplus
extern "C" {
#endif
    ArrayWrapper* ocr_post_process(FrameSize frame_size,FrameSize kmodel_frame_size,float box_thresh,float threshold, float* data_0, uint8_t* data_1, int* results_size);
    ob_det_res* anchorbasedet_post_process(float* data0, float* data1, float* data2, FrameSize kmodel_frame_size, FrameSize frame_size, int* strides, int num_class, float ob_det_thresh, float ob_nms_thresh, float* anchors, bool nms_option, int* results_size);
    ob_det_res* anchorfreedet_post_process(float* data0, float* data1, float* data2, FrameSize kmodel_frame_size, FrameSize frame_size, int* strides, int num_class, float ob_det_thresh, float ob_nms_thresh, bool nms_option, int* results_size);
    ob_det_res* gfldet_post_process(float* data0, float* data1, float* data2, FrameSize kmodel_frame_size, FrameSize frame_size, int* strides, int num_class, float ob_det_thresh, float ob_nms_thresh, bool nms_option, int* results_size);
    uint8_t* seg_post_process(float* data, int num_class, FrameSize ori_shape, FrameSize dst_shape);
    bool seg_post_process_into(float* data, int num_class, FrameSize ori_shape, FrameSize dst_shape, uint8_t* result);
#ifdef __cplusplus
}
#endif
