#include <cstdlib>
#include <vector>
#include <opencv2/highgui.hpp>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp>
#include "aidemo_wrap.h"

using std::vector;

int* opencv_grayscale_findblobs(FrameSize frame_shape,uint8_t* data, int threshold_min, int threshold_max, int* ret_num) {
    int width = frame_shape.width;
    int height = frame_shape.height;
    // 直接创建 cv::Mat 对象，避免手动复制数据
    cv::Mat gray(height, width, CV_8UC1, data);
    // 二值化处理，使用指定的阈值范围
    cv::Mat binary;
    cv::inRange(gray, cv::Scalar(threshold_min), cv::Scalar(threshold_max), binary);
    // 查找轮廓
    std::vector<std::vector<cv::Point>> contours;
    cv::findContours(binary, contours, cv::RETR_EXTERNAL, cv::CHAIN_APPROX_SIMPLE);
    // 提取边界框坐标
    std::vector<int> temp_results;
    for (const auto& contour : contours) {
        cv::Rect boundingRect = cv::boundingRect(contour);
        temp_results.push_back(boundingRect.x);
        temp_results.push_back(boundingRect.y);
        temp_results.push_back(boundingRect.width);
        temp_results.push_back(boundingRect.height);
    }
    *ret_num = temp_results.size() / 4;
    if (*ret_num == 0) return nullptr;
    // 分配内存并复制数据
    int* ret = (int *)malloc(*ret_num * 4 * sizeof(int));
    if (ret == nullptr) {
        return nullptr;
    }
    std::copy(temp_results.begin(), temp_results.end(), ret);
    return ret;
}

void opencv_grayscale_findblobs_free_outputs(void *context)
{
    free(context);
}
