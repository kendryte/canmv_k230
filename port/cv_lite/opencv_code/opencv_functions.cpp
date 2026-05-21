#include <vector>
#include <opencv2/highgui.hpp>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp>
#include <opencv2/opencv.hpp>
#include "cv_lite_wrap.h"
#include <sys/time.h>  // gettimeofday
#include <stdio.h>     // printf
#include <string>
#include <iostream>
// #include <dirent.h>  // ✅ 必须添加
// #include <sys/types.h>  // 建议一并添加

#include <riscv_vector.h>

#include "hal_rvv_ops.h"

#define MIN(a,b) ((a)<(b)?(a):(b))
#define MAX(a,b) ((a)>(b)?(a):(b))

using std::vector;
using namespace std;
using namespace cv;

/**
 * @brief 灰度图像查找斑点（优化版）
 *
 * @param frame_shape 图像尺寸
 * @param data 图像数据
 * @param threshold_min 最小灰度阈值
 * @param threshold_max 最大灰度阈值
 * @param min_area 最小斑点面积，用于过滤小斑点
 * @param kernel_size 形态学操作使用的核大小
 * @param ret_num 检测到的斑点数量
 * @return int* 检测到的斑点坐标数组，每个斑点包含x, y, width, height四个值
 */
int* grayscale_find_blobs(FrameCHWSize frame_shape, uint8_t* data,int threshold_min, int threshold_max,int min_area, int kernel_size,int* ret_num) {
    int width = frame_shape.width;
    int height = frame_shape.height;

    // 直接创建灰度图 cv::Mat 对象（无需复制数据）
    cv::Mat gray(height, width, CV_8UC1, data);

    // 二值化处理
    cv::Mat binary;
    cv::inRange(gray, cv::Scalar(threshold_min), cv::Scalar(threshold_max), binary);

    // 形态学去噪（开运算）
    if (kernel_size > 1) {
        cv::morphologyEx(binary, binary, cv::MORPH_OPEN,
                         cv::getStructuringElement(cv::MORPH_RECT, cv::Size(kernel_size, kernel_size)));
    }

    // 查找外部轮廓（RETR_EXTERNAL），减少计算量
    std::vector<std::vector<cv::Point>> contours;
    cv::findContours(binary, contours, cv::RETR_EXTERNAL, cv::CHAIN_APPROX_SIMPLE);

    std::vector<int> temp_results;

    // 过滤面积较小的斑点，并提取边界框
    for (const auto& contour : contours) {
        double area = cv::contourArea(contour);
        if (area < min_area) continue;

        cv::Rect rect = cv::boundingRect(contour);
        // 可选：再过滤宽度或高度为0的情况
        if (rect.width <= 0 || rect.height <= 0)
            continue;

        temp_results.push_back(rect.x);
        temp_results.push_back(rect.y);
        temp_results.push_back(rect.width);
        temp_results.push_back(rect.height);
    }

    *ret_num = temp_results.size() / 4;
    if (*ret_num == 0)
        return nullptr;

    // 分配内存并复制结果
    int* ret = static_cast<int*>(malloc((size_t)*ret_num * 4 * sizeof(int)));
    if (ret) {
        std::copy(temp_results.begin(), temp_results.end(), ret);
    }

    return ret;
}

/**
 * @brief 彩色图像查找斑点
 * 
 * @param frame_shape 图像尺寸
 * @param data 图像数据
 * @param threshold 阈值，包含6个值，分别为minB, maxB, minG, maxG, minR, maxR
 * @param min_area 最小面积阈值，过滤掉面积较小的斑点
 * @param kernel_size 形态学操作核大小
 * @param ret_num 检测到的斑点数量
 * @return int* 检测到的斑点坐标数组，每个斑点包含x, y, width, height四个值
*/
int* rgb888_find_blobs(FrameCHWSize frame_shape, uint8_t* data, int threshold[6], int min_area, int kernel_size, int* ret_num) {
    int width = frame_shape.width;
    int height = frame_shape.height;

    // 构造 BGR 图像
    cv::Mat img(height, width, CV_8UC3, data);
    cv::Mat bgr_img;
    cv::cvtColor(img, bgr_img, cv::COLOR_RGB2BGR);

    // 正确的 inRange 参数顺序：BGR -> Scalar(B_min, G_min, R_min), Scalar(B_max, G_max, R_max)
    cv::Mat binary;
    cv::inRange(bgr_img,
                cv::Scalar(threshold[4], threshold[2], threshold[0]),
                cv::Scalar(threshold[5], threshold[3], threshold[1]),
                binary);

    // 使用可配置的核大小进行形态学去噪（开运算）
    cv::morphologyEx(binary, binary, cv::MORPH_OPEN,
                     cv::getStructuringElement(cv::MORPH_RECT, cv::Size(kernel_size, kernel_size)));

    // 查找轮廓
    std::vector<std::vector<cv::Point>> contours;
    cv::findContours(binary, contours, cv::RETR_EXTERNAL, cv::CHAIN_APPROX_SIMPLE);

    std::vector<int> temp_results;

    // 使用可配置的面积阈值过滤小斑点
    for (const auto& contour : contours) {
        double area = cv::contourArea(contour);
        if (area < min_area) continue;  // 忽略小于设定值的轮廓

        cv::Rect rect = cv::boundingRect(contour);
        temp_results.push_back(rect.x);
        temp_results.push_back(rect.y);
        temp_results.push_back(rect.width);
        temp_results.push_back(rect.height);
    }

    *ret_num = temp_results.size() / 4;
    if (*ret_num == 0) return nullptr;

    int* ret = (int*)malloc((size_t)*ret_num * 4 * sizeof(int));
    std::copy(temp_results.begin(), temp_results.end(), ret);
    return ret;
}

/**
 * @brief 灰度图像查找圆（不缩放图像，优化性能）
 *
 * @param frame_shape 图像尺寸
 * @param data 图像数据
 * @param dp 累加器分辨率与图像分辨率的反比
 * @param minDist 检测到的圆的中心之间的最小距离
 * @param param1 边缘检测梯度值
 * @param param2 累加器阈值
 * @param minRadius 最小圆半径
 * @param maxRadius 最大圆半径
 * @param ret_num 检测到的圆数量
 * @return int* 圆数组，每个包含 x_center, y_center, radius
 */
int* grayscale_find_circles(FrameCHWSize frame_shape, uint8_t* data,int dp, int minDist, int param1, int param2,int minRadius, int maxRadius, int* ret_num)
{
    int width = frame_shape.width;
    int height = frame_shape.height;

    // 输入检查
    if (!data || width <= 0 || height <= 0) {
        *ret_num = 0;
        return nullptr;
    }

    // 创建灰度图像（直接使用传入数据，不复制）
    cv::Mat gray(height, width, CV_8UC1, data);

    // 【优化】使用 medianBlur 替代 GaussianBlur：对圆检测效果更好，速度略快
    cv::Mat blurred;
    cv::medianBlur(gray, blurred, 5);  // 5x5 核

    // 使用 HoughCircles 检测圆
    std::vector<cv::Vec3f> circles;
    cv::HoughCircles(blurred, circles, cv::HOUGH_GRADIENT, dp, minDist,
                     param1, param2, minRadius, maxRadius);

    *ret_num = circles.size();
    if (*ret_num == 0) return nullptr;

    // 分配输出内存
    int* ret = static_cast<int*>(malloc(*ret_num * 3 * sizeof(int)));
    for (int i = 0; i < *ret_num; ++i) {
        ret[i * 3 + 0] = cvRound(circles[i][0]);
        ret[i * 3 + 1] = cvRound(circles[i][1]);
        ret[i * 3 + 2] = cvRound(circles[i][2]);
    }

    return ret;
}

/**
 * @brief 彩色图像查找圆（不缩放图像，优化性能）
 * 
 * @param frame_shape 图像尺寸
 * @param data 图像数据
 * @param dp 累加器分辨率与图像分辨率的反比
 * @param minDist 检测到的圆的中心之间的最小距离
 * @param param1 边缘检测梯度值
 * @param param2 累加器阈值
 * @param minRadius 最小圆半径
 * @param maxRadius 最大圆半径
 * @param ret_num 检测到的圆数量
 * @return int* 圆数组，每个包含 x_center, y_center, radius
*/
int* rgb888_find_circles(FrameCHWSize frame_shape, uint8_t* data, int dp, int minDist, int param1, int param2, int minRadius, int maxRadius, int* ret_num){
    int width = frame_shape.width;
    int height = frame_shape.height;

    // 构造 RGB 图像（RGB888 每像素3字节）
    cv::Mat rgb(height, width, CV_8UC3, data);

    // 转为灰度图
    cv::Mat gray;
    cv::cvtColor(rgb, gray, cv::COLOR_RGB2GRAY);

    // 【优化】使用 medianBlur 替代 GaussianBlur：对圆检测效果更好，速度略快
    cv::Mat blurred;
    cv::medianBlur(gray, blurred, 5);  // 5x5 核

    // 使用 HoughCircles 检测圆
    std::vector<cv::Vec3f> circles;
    cv::HoughCircles(blurred, circles, cv::HOUGH_GRADIENT, dp, minDist,
                     param1, param2, minRadius, maxRadius);

    *ret_num = circles.size();
    if (*ret_num == 0) return nullptr;

    // 分配输出内存
    int* ret = static_cast<int*>(malloc(*ret_num * 3 * sizeof(int)));
    for (int i = 0; i < *ret_num; ++i) {
        ret[i * 3 + 0] = cvRound(circles[i][0]);
        ret[i * 3 + 1] = cvRound(circles[i][1]);
        ret[i * 3 + 2] = cvRound(circles[i][2]);
    }
    return ret;
}

/**
 * @brief 灰度图像查找矩形
 * 
 * @param frame_shape 图像尺寸
 * @param data 灰度图像数据
 * @param canny_thresh1 Canny 边缘检测阈值1
 * @param canny_thresh2 Canny 边缘检测阈值2
 * @param approx_epsilon_ratio 轮廓逼近系数
 * @param area_min_ratio 最小矩形面积比例
 * @param max_angle_cos 最大角度余弦值
 * @param gaussian_blur_size 高斯模糊核大小
 * @param ret_num 输出：返回的矩形数量
 * @return int* 每个矩形包含 4 个整数：x, y, width, height，共 ret_num × 4 个整数
*/
int* grayscale_find_rectangles(FrameCHWSize frame_shape, uint8_t* data,int canny_thresh1, int canny_thresh2,float approx_epsilon_ratio, float area_min_ratio,float max_angle_cos, int gaussian_blur_size, int* ret_num)
{
    int width = frame_shape.width;
    int height = frame_shape.height;

    cv::Mat gray(height, width, CV_8UC1, data);

    // 高斯模糊降噪
    if (gaussian_blur_size > 1 && gaussian_blur_size % 2 == 1) {
        cv::GaussianBlur(gray, gray, cv::Size(gaussian_blur_size, gaussian_blur_size), 0);
    }

    // Canny 边缘检测
    cv::Mat edges;
    cv::Canny(gray, edges, canny_thresh1, canny_thresh2);

    // 查找外层轮廓
    std::vector<std::vector<cv::Point>> contours;
    cv::findContours(edges, contours, cv::RETR_EXTERNAL, cv::CHAIN_APPROX_SIMPLE);

    const double min_area = width * height * area_min_ratio;
    std::vector<cv::Rect> bounding_boxes;

    for (auto& contour : contours) {
        // 快速剪枝：小面积轮廓直接跳过
        if (cv::contourArea(contour) < min_area) continue;

        // 获取轮廓周长并近似为多边形
        double perimeter = cv::arcLength(contour, true);
        std::vector<cv::Point> approx;
        cv::approxPolyDP(contour, approx, perimeter * approx_epsilon_ratio, true);

        // 检查是否是4个点的凸多边形
        if (approx.size() != 4 || !cv::isContourConvex(approx)) continue;

        // 角度检查：判断是否接近矩形
        bool is_rect = true;
        auto angleCos = [](cv::Point pt1, cv::Point pt2, cv::Point pt0) {
            double dx1 = pt1.x - pt0.x, dy1 = pt1.y - pt0.y;
            double dx2 = pt2.x - pt0.x, dy2 = pt2.y - pt0.y;
            return (dx1 * dx2 + dy1 * dy2) /
                   (std::sqrt((dx1*dx1 + dy1*dy1) * (dx2*dx2 + dy2*dy2)) + 1e-10);
        };

        for (int i = 0; i < 4; ++i) {
            double cos_val = angleCos(
                approx[(i + 1) % 4],
                approx[(i + 3) % 4],
                approx[i]
            );
            if (std::abs(cos_val) > max_angle_cos) {
                is_rect = false;
                break;
            }
        }

        if (is_rect) {
            bounding_boxes.push_back(cv::boundingRect(approx));
        }
    }

    *ret_num = bounding_boxes.size();
    if (*ret_num == 0) return nullptr;

    int* ret = (int*)malloc(*ret_num * 4 * sizeof(int));
    if (!ret) {
        *ret_num = 0;
        return nullptr;
    }

    for (int i = 0; i < *ret_num; ++i) {
        ret[i * 4 + 0] = bounding_boxes[i].x;
        ret[i * 4 + 1] = bounding_boxes[i].y;
        ret[i * 4 + 2] = bounding_boxes[i].width;
        ret[i * 4 + 3] = bounding_boxes[i].height;
    }

    return ret;
}

int* grayscale_find_rectangles_with_corners(FrameCHWSize frame_shape, uint8_t* data,int canny_thresh1, int canny_thresh2, float approx_epsilon_ratio,float area_min_ratio, float max_angle_cos, int gaussian_blur_size,int* ret_num)
{
    int width = frame_shape.width;
    int height = frame_shape.height;

    cv::Mat gray(height, width, CV_8UC1, data);

    // 高斯模糊降噪
    if (gaussian_blur_size > 1 && gaussian_blur_size % 2 == 1) {
        cv::GaussianBlur(gray, gray, cv::Size(gaussian_blur_size, gaussian_blur_size), 0);
    }

    // Canny 边缘检测
    cv::Mat edges;
    cv::Canny(gray, edges, canny_thresh1, canny_thresh2);

    // 查找外层轮廓
    std::vector<std::vector<cv::Point>> contours;
    cv::findContours(edges, contours, cv::RETR_EXTERNAL, cv::CHAIN_APPROX_SIMPLE);

    const double min_area = width * height * area_min_ratio;
    std::vector<cv::Rect> bounding_boxes;
    std::vector<std::vector<cv::Point>> rect_corners;

    for (auto& contour : contours) {
        if (cv::contourArea(contour) < min_area) continue;

        double perimeter = cv::arcLength(contour, true);
        std::vector<cv::Point> approx;
        cv::approxPolyDP(contour, approx, perimeter * approx_epsilon_ratio, true);

        if (approx.size() != 4 || !cv::isContourConvex(approx)) continue;

        // 判断是否为近似矩形
        bool is_rect = true;
        auto angleCos = [](cv::Point pt1, cv::Point pt2, cv::Point pt0) {
            double dx1 = pt1.x - pt0.x, dy1 = pt1.y - pt0.y;
            double dx2 = pt2.x - pt0.x, dy2 = pt2.y - pt0.y;
            return (dx1 * dx2 + dy1 * dy2) /
                   (std::sqrt((dx1 * dx1 + dy1 * dy1) * (dx2 * dx2 + dy2 * dy2)) + 1e-10);
        };

        for (int i = 0; i < 4; ++i) {
            double cos_val = angleCos(
                approx[(i + 1) % 4],
                approx[(i + 3) % 4],
                approx[i]
            );
            if (std::abs(cos_val) > max_angle_cos) {
                is_rect = false;
                break;
            }
        }

        if (is_rect) {
            bounding_boxes.push_back(cv::boundingRect(approx));
            rect_corners.push_back(approx);
        }
    }

    *ret_num = bounding_boxes.size();
    if (*ret_num == 0) return nullptr;

    int* ret = (int*)malloc(*ret_num * 12 * sizeof(int));
    if (!ret) {
        *ret_num = 0;
        return nullptr;
    }

    for (int i = 0; i < *ret_num; ++i) {
        // 保存位置信息
        ret[i * 12 + 0] = bounding_boxes[i].x;
        ret[i * 12 + 1] = bounding_boxes[i].y;
        ret[i * 12 + 2] = bounding_boxes[i].width;
        ret[i * 12 + 3] = bounding_boxes[i].height;

        // 保存角点信息
        for (int j = 0; j < 4; ++j) {
            ret[i * 12 + 4 + j * 2 + 0] = rect_corners[i][j].x;
            ret[i * 12 + 4 + j * 2 + 1] = rect_corners[i][j].y;
        }
    }

    return ret;
}

int* rgb888_find_rectangles_with_corners(FrameCHWSize frame_shape, uint8_t* data,int canny_thresh1, int canny_thresh2, float approx_epsilon_ratio,float area_min_ratio, float max_angle_cos, int gaussian_blur_size,int* ret_num)
{
    int width = frame_shape.width;
    int height = frame_shape.height;

    // 构造 RGB 图像（RGB888 每像素3字节）
    cv::Mat rgb(height, width, CV_8UC3, data);

    // 转为灰度图
    cv::Mat gray;
    cv::cvtColor(rgb, gray, cv::COLOR_RGB2GRAY);

    // 高斯模糊降噪
    if (gaussian_blur_size > 1 && gaussian_blur_size % 2 == 1) {
        cv::GaussianBlur(gray, gray, cv::Size(gaussian_blur_size, gaussian_blur_size), 0);
    }

    // Canny 边缘检测
    cv::Mat edges;
    cv::Canny(gray, edges, canny_thresh1, canny_thresh2);

    // 查找外层轮廓
    std::vector<std::vector<cv::Point>> contours;
    cv::findContours(edges, contours, cv::RETR_EXTERNAL, cv::CHAIN_APPROX_SIMPLE);

    const double min_area = width * height * area_min_ratio;
    std::vector<cv::Rect> bounding_boxes;
    std::vector<std::vector<cv::Point>> rect_corners;

    for (auto& contour : contours) {
        if (cv::contourArea(contour) < min_area) continue;

        double perimeter = cv::arcLength(contour, true);
        std::vector<cv::Point> approx;
        cv::approxPolyDP(contour, approx, perimeter * approx_epsilon_ratio, true);

        if (approx.size() != 4 || !cv::isContourConvex(approx)) continue;

        // 判断是否为近似矩形
        bool is_rect = true;
        auto angleCos = [](cv::Point pt1, cv::Point pt2, cv::Point pt0) {
            double dx1 = pt1.x - pt0.x, dy1 = pt1.y - pt0.y;
            double dx2 = pt2.x - pt0.x, dy2 = pt2.y - pt0.y;
            return (dx1 * dx2 + dy1 * dy2) /
                   (std::sqrt((dx1 * dx1 + dy1 * dy1) * (dx2 * dx2 + dy2 * dy2)) + 1e-10);
        };

        for (int i = 0; i < 4; ++i) {
            double cos_val = angleCos(
                approx[(i + 1) % 4],
                approx[(i + 3) % 4],
                approx[i]
            );
            if (std::abs(cos_val) > max_angle_cos) {
                is_rect = false;
                break;
            }
        }

        if (is_rect) {
            bounding_boxes.push_back(cv::boundingRect(approx));
            rect_corners.push_back(approx);
        }
    }

    *ret_num = bounding_boxes.size();
    if (*ret_num == 0) return nullptr;

    int* ret = (int*)malloc(*ret_num * 12 * sizeof(int));
    if (!ret) {
        *ret_num = 0;
        return nullptr;
    }

    for (int i = 0; i < *ret_num; ++i) {
        // 保存位置信息
        ret[i * 12 + 0] = bounding_boxes[i].x;
        ret[i * 12 + 1] = bounding_boxes[i].y;
        ret[i * 12 + 2] = bounding_boxes[i].width;
        ret[i * 12 + 3] = bounding_boxes[i].height;

        // 保存角点信息
        for (int j = 0; j < 4; ++j) {
            ret[i * 12 + 4 + j * 2 + 0] = rect_corners[i][j].x;
            ret[i * 12 + 4 + j * 2 + 1] = rect_corners[i][j].y;
        }
    }

    return ret;
}


/**
 * @brief RGB888 图像中查找矩形（返回外接矩形 x, y, width, height）
 * 
 * @param frame_shape 图像尺寸
 * @param data RGB888 图像数据
 * @param canny_thresh1 Canny 边缘检测阈值1
 * @param canny_thresh2 Canny 边缘检测阈值2
 * @param approx_epsilon_ratio 轮廓逼近系数
 * @param area_min_ratio 最小矩形面积比例
 * @param max_angle_cos 最大角度余弦值
 * @param gaussian_blur_size 高斯模糊核大小
 * @param ret_num 输出：返回的矩形数量
 * @return int* 每个矩形包含 4 个整数（x, y, width, height），共 ret_num × 4 个整数 
*/
int* rgb888_find_rectangles(FrameCHWSize frame_shape, uint8_t* data, int canny_thresh1, int canny_thresh2,float approx_epsilon_ratio,float area_min_ratio,float max_angle_cos,int gaussian_blur_size, int* ret_num) {
    int width = frame_shape.width;
    int height = frame_shape.height;

    // 构造 RGB 图像（RGB888 每像素3字节）
    cv::Mat rgb(height, width, CV_8UC3, data);

    // 转为灰度图
    cv::Mat gray;
    cv::cvtColor(rgb, gray, cv::COLOR_RGB2GRAY);

    // 高斯模糊降噪
    if (gaussian_blur_size > 1 && gaussian_blur_size % 2 == 1) {
        cv::GaussianBlur(gray, gray, cv::Size(gaussian_blur_size, gaussian_blur_size), 0);
    }

    // Canny 边缘检测
    cv::Mat edges;
    cv::Canny(gray, edges, canny_thresh1, canny_thresh2);

     // 查找外层轮廓
    std::vector<std::vector<cv::Point>> contours;
    cv::findContours(edges, contours, cv::RETR_EXTERNAL, cv::CHAIN_APPROX_SIMPLE);

    const double min_area = width * height * area_min_ratio;
    std::vector<cv::Rect> bounding_boxes;

    for (auto& contour : contours) {
        // 快速剪枝：小面积轮廓直接跳过
        if (cv::contourArea(contour) < min_area) continue;

        // 获取轮廓周长并近似为多边形
        double perimeter = cv::arcLength(contour, true);
        std::vector<cv::Point> approx;
        cv::approxPolyDP(contour, approx, perimeter * approx_epsilon_ratio, true);

        // 检查是否是4个点的凸多边形
        if (approx.size() != 4 || !cv::isContourConvex(approx)) continue;

        // 角度检查：判断是否接近矩形
        bool is_rect = true;
        auto angleCos = [](cv::Point pt1, cv::Point pt2, cv::Point pt0) {
            double dx1 = pt1.x - pt0.x, dy1 = pt1.y - pt0.y;
            double dx2 = pt2.x - pt0.x, dy2 = pt2.y - pt0.y;
            return (dx1 * dx2 + dy1 * dy2) /
                   (std::sqrt((dx1*dx1 + dy1*dy1) * (dx2*dx2 + dy2*dy2)) + 1e-10);
        };

        for (int i = 0; i < 4; ++i) {
            double cos_val = angleCos(
                approx[(i + 1) % 4],
                approx[(i + 3) % 4],
                approx[i]
            );
            if (std::abs(cos_val) > max_angle_cos) {
                is_rect = false;
                break;
            }
        }

        if (is_rect) {
            bounding_boxes.push_back(cv::boundingRect(approx));
        }
    }

    *ret_num = bounding_boxes.size();
    if (*ret_num == 0) return nullptr;

    int* ret = (int*)malloc(*ret_num * 4 * sizeof(int));
    if (!ret) {
        *ret_num = 0;
        return nullptr;
    }

    for (int i = 0; i < *ret_num; ++i) {
        ret[i * 4 + 0] = bounding_boxes[i].x;
        ret[i * 4 + 1] = bounding_boxes[i].y;
        ret[i * 4 + 2] = bounding_boxes[i].width;
        ret[i * 4 + 3] = bounding_boxes[i].height;
    }

    return ret;
}

// int* grayscale_find_lines_raw(FrameCHWSize frame_shape, uint8_t* data,int canny_thresh1, int canny_thresh2,int gaussian_blur_size,float rho, float theta,int hough_thresh,int* ret_num)
// {
//     int width = frame_shape.width;
//     int height = frame_shape.height;

//     // 1. 构造灰度图（不复制数据）
//     cv::Mat gray(height, width, CV_8UC1, data);

//     // 2. 可选高斯模糊
//     if (gaussian_blur_size > 1 && (gaussian_blur_size & 1)) {
//         cv::GaussianBlur(gray, gray, cv::Size(gaussian_blur_size, gaussian_blur_size), 0, 0, cv::BORDER_REPLICATE);
//     }

//     // 3. Canny 边缘检测
//     cv::Mat edges;
//     cv::Canny(gray, edges, canny_thresh1, canny_thresh2, 3, true);

//     // 4. 标准霍夫变换，返回 (rho, theta)
//     std::vector<cv::Vec2f> lines;
//     cv::HoughLines(edges, lines, rho, theta, hough_thresh);

//     // 5. 设置返回数量
//     *ret_num = lines.size();
//     if (*ret_num == 0) return nullptr;

//     // 6. 分配返回数组：每条线段 (x1, y1, x2, y2)
//     int* ret = (int*)malloc(*ret_num * 4 * sizeof(int));
//     if (!ret) {
//         *ret_num = 0;
//         return nullptr;
//     }

//     // 7. 将 (rho, theta) 转换为两端点 (x1, y1, x2, y2)，延伸至图像边界
//     for (int i = 0, j = 0; i < *ret_num; ++i, j += 4) {
//         float r = lines[i][0];
//         float t = lines[i][1];
//         double a = cos(t);
//         double b = sin(t);
//         double x0 = a * r;
//         double y0 = b * r;

//         // 使线段足够长（延伸到边界）
//         int x1 = cvRound(x0 + 1000 * (-b));
//         int y1 = cvRound(y0 + 1000 * (a));
//         int x2 = cvRound(x0 - 1000 * (-b));
//         int y2 = cvRound(y0 - 1000 * (a));

//         // 裁剪到图像边界内（可选）
//         // x1 = std::clamp(x1, 0, width - 1);
//         // y1 = std::clamp(y1, 0, height - 1);
//         // x2 = std::clamp(x2, 0, width - 1);
//         // y2 = std::clamp(y2, 0, height - 1);

//         ret[j + 0] = x1;
//         ret[j + 1] = y1;
//         ret[j + 2] = x2;
//         ret[j + 3] = y2;
//     }

//     return ret;
// }

#define fast_roundf(x) ((int)std::round(x))

int* grayscale_find_lines_raw(FrameCHWSize frame_shape, uint8_t* data,
                              int x_stride, int y_stride,
                              int sobel_thresh,
                              float rho_step, float theta_step,
                              int hough_thresh, int* ret_num) {
    const int width = frame_shape.width;
    const int height = frame_shape.height;
    const int diag_len = (int)std::sqrt(width * width + height * height);
    const int rho_size = diag_len * 2 / rho_step + 1;
    const int theta_size = (int)(CV_PI / theta_step) + 1;
    const int sobel_thresh2 = sobel_thresh * sobel_thresh;

    std::vector<int> acc(rho_size * theta_size, 0); // flat accumulator
    std::vector<float> sin_table(theta_size), cos_table(theta_size);
    for (int t = 0; t < theta_size; ++t) {
        float angle = t * theta_step;
        sin_table[t] = std::sin(angle);
        cos_table[t] = std::cos(angle);
    }

    cv::Mat gray(height, width, CV_8UC1, data);

    // 手写 Sobel + 跳步扫描
    for (int y = 1; y < height - 1; y += y_stride) {
        for (int x = 1 + (y % x_stride); x < width - 1; x += x_stride) {
            int gx =
                -gray.at<uint8_t>(y - 1, x - 1) + gray.at<uint8_t>(y - 1, x + 1) +
                -2 * gray.at<uint8_t>(y, x - 1) + 2 * gray.at<uint8_t>(y, x + 1) +
                -gray.at<uint8_t>(y + 1, x - 1) + gray.at<uint8_t>(y + 1, x + 1);
            int gy =
                -gray.at<uint8_t>(y - 1, x - 1) - 2 * gray.at<uint8_t>(y - 1, x) - gray.at<uint8_t>(y - 1, x + 1) +
                 gray.at<uint8_t>(y + 1, x - 1) + 2 * gray.at<uint8_t>(y + 1, x) + gray.at<uint8_t>(y + 1, x + 1);
            int mag2 = gx * gx + gy * gy;
            if (mag2 < sobel_thresh2) continue;

            float angle = std::atan2((float)gy, (float)gx);
            if (angle < 0) angle += CV_PI;

            int t_idx = (int)((angle + theta_step / 2) / theta_step);
            if (t_idx >= theta_size) t_idx = theta_size - 1;

            float r = x * cos_table[t_idx] + y * sin_table[t_idx];
            int r_idx = (int)((r + diag_len) / rho_step);
            if (r_idx >= 0 && r_idx < rho_size)
                acc[r_idx * theta_size + t_idx] += mag2;  // 权重为梯度强度平方
        }
    }

    // 非极大值抑制
    std::vector<cv::Vec2f> lines;
    for (int r = 1; r < rho_size - 1; ++r) {
        for (int t = 1; t < theta_size - 1; ++t) {
            int idx = r * theta_size + t;
            int val = acc[idx];
            if (val < hough_thresh) continue;

            bool is_max = true;
            for (int dr = -1; dr <= 1 && is_max; ++dr) {
                for (int dt = -1; dt <= 1; ++dt) {
                    if (dr == 0 && dt == 0) continue;
                    int n_idx = (r + dr) * theta_size + (t + dt);
                    if (acc[n_idx] > val) {
                        is_max = false;
                        break;
                    }
                }
            }

            if (is_max) {
                float r_val = r * rho_step - diag_len;
                float t_val = t * theta_step;
                lines.emplace_back(r_val, t_val);
            }
        }
    }

    *ret_num = lines.size();
    if (*ret_num == 0) return nullptr;

    int* ret = (int*)malloc(*ret_num * 4 * sizeof(int));
    if (!ret) {
        *ret_num = 0;
        return nullptr;
    }

    for (int i = 0, j = 0; i < *ret_num; ++i, j += 4) {
        float r = lines[i][0];
        float t = lines[i][1];
        float a = std::cos(t), b = std::sin(t);
        float x0 = a * r, y0 = b * r;
        int x1 = cvRound(x0 + 1000 * (-b));
        int y1 = cvRound(y0 + 1000 * (a));
        int x2 = cvRound(x0 - 1000 * (-b));
        int y2 = cvRound(y0 - 1000 * (a));
        ret[j + 0] = x1;
        ret[j + 1] = y1;
        ret[j + 2] = x2;
        ret[j + 3] = y2;
    }

    return ret;
}

int* grayscale_find_lines(FrameCHWSize frame_shape, uint8_t* data,int canny_thresh1, int canny_thresh2,int gaussian_blur_size,float rho, float theta,int hough_thresh, float min_line_length,float max_line_gap,int* ret_num)
{
    int width = frame_shape.width;
    int height = frame_shape.height;

    // 1. 直接构造灰度图（无拷贝）
    cv::Mat gray(height, width, CV_8UC1, data);

    // 2. 高斯模糊（仅在必要时执行，且用更快的边界模式）
    if (gaussian_blur_size > 1 && (gaussian_blur_size & 1)) {
        cv::GaussianBlur(gray, gray, cv::Size(gaussian_blur_size, gaussian_blur_size), 0, 0, cv::BORDER_REPLICATE);
    }

    // 3. Canny 边缘检测，使用 L2gradient 提高边缘检测精度
    cv::Mat edges;
    cv::Canny(gray, edges, canny_thresh1, canny_thresh2, 3, true);

    // 4. 使用概率霍夫变换检测直线
    std::vector<cv::Vec4i> lines;
    lines.reserve(256); // 提前分配内存，避免频繁扩容
    cv::HoughLinesP(edges, lines, rho, theta, hough_thresh, min_line_length, max_line_gap);

    // 5. 设置返回数量
    *ret_num = lines.size();
    if (*ret_num == 0) return nullptr;
    // 6. 分配返回数组并写入数据：x1, y1, x2, y2
    int* ret = (int*)malloc(*ret_num * 4 * sizeof(int));
    if(!ret){
        *ret_num = 0;
        return nullptr;
    }
    for (int i = 0, j = 0; i < *ret_num; ++i, j += 4) {
        ret[j + 0] = lines[i][0];
        ret[j + 1] = lines[i][1];
        ret[j + 2] = lines[i][2];
        ret[j + 3] = lines[i][3];
    }

    return ret;
}

int* grayscale_find_lines_sobel(FrameCHWSize frame_shape, uint8_t* data,int sobel_thresh,int gaussian_blur_size,
                                float rho, float theta,
                                int hough_thresh, float min_line_length,
                                float max_line_gap,
                                int* ret_num)
{
    int width = frame_shape.width;
    int height = frame_shape.height;

    // 1. 构造灰度图（无拷贝）
    cv::Mat gray(height, width, CV_8UC1, data);

    // 2. 高斯模糊（可选）
    if (gaussian_blur_size > 1 && (gaussian_blur_size & 1)) {
        cv::GaussianBlur(gray, gray, cv::Size(gaussian_blur_size, gaussian_blur_size), 0, 0, cv::BORDER_REPLICATE);
    }

    // 3. 使用 Sobel 计算 x 和 y 方向梯度
    cv::Mat grad_x, grad_y;
    cv::Sobel(gray, grad_x, CV_16S, 1, 0, 3, 1, 0, cv::BORDER_REPLICATE);
    cv::Sobel(gray, grad_y, CV_16S, 0, 1, 3, 1, 0, cv::BORDER_REPLICATE);

    // 4. 计算梯度幅值图（快速近似: |dx| + |dy|）
    cv::Mat abs_grad_x, abs_grad_y, edge;
    cv::convertScaleAbs(grad_x, abs_grad_x);
    cv::convertScaleAbs(grad_y, abs_grad_y);
    cv::add(abs_grad_x, abs_grad_y, edge);

    // 5. 二值化（阈值）
    cv::threshold(edge, edge, sobel_thresh, 255, cv::THRESH_BINARY);

    // 6. 霍夫变换检测直线
    std::vector<cv::Vec4i> lines;
    lines.reserve(256);
    cv::HoughLinesP(edge, lines, rho, theta, hough_thresh, min_line_length, max_line_gap);

    // 7. 输出结果
    *ret_num = lines.size();
    if (*ret_num == 0) return nullptr;

    int* ret = (int*)malloc(*ret_num * 4 * sizeof(int));
    if (!ret) {
        *ret_num = 0;
        return nullptr;
    }

    for (int i = 0, j = 0; i < *ret_num; ++i, j += 4) {
        ret[j + 0] = lines[i][0];
        ret[j + 1] = lines[i][1];
        ret[j + 2] = lines[i][2];
        ret[j + 3] = lines[i][3];
    }

    return ret;
}


int* grayscale_find_lines_no_hough(FrameCHWSize frame_shape, uint8_t* data,int canny_thresh1, int canny_thresh2,int gaussian_blur_size,float min_contour_len,int* ret_num)
{
    int width = frame_shape.width;
    int height = frame_shape.height;

    // 构造灰度图像（不拷贝）
    cv::Mat gray(height, width, CV_8UC1, data);

    // 高斯模糊
    if (gaussian_blur_size > 1 && (gaussian_blur_size & 1)) {
        cv::GaussianBlur(gray, gray, cv::Size(gaussian_blur_size, gaussian_blur_size), 0, 0, cv::BORDER_REPLICATE);
    }

    // Canny 边缘检测
    cv::Mat edges;
    cv::Canny(gray, edges, canny_thresh1, canny_thresh2, 3, true);

    // 提取轮廓
    std::vector<std::vector<cv::Point>> contours;
    cv::findContours(edges, contours, cv::RETR_EXTERNAL, cv::CHAIN_APPROX_NONE);

    std::vector<cv::Vec4i> segments;
    segments.reserve(128);

    for (const auto& contour : contours) {
        if (contour.size() < 10) continue; // 太短的跳过
        if (cv::arcLength(contour, false) < min_contour_len) continue;

        // 使用最小二乘拟合直线
        cv::Vec4f line;
        cv::fitLine(contour, line, cv::DIST_L2, 0, 0.01, 0.01);

        float vx = line[0], vy = line[1];
        float x0 = line[2], y0 = line[3];

        // 在拟合方向上延展线段长度（这里使用轮廓边界包围）
        cv::Rect bound = cv::boundingRect(contour);
        float len = std::max(bound.width, bound.height) / 2.0f;

        int x1 = std::round(x0 - vx * len);
        int y1 = std::round(y0 - vy * len);
        int x2 = std::round(x0 + vx * len);
        int y2 = std::round(y0 + vy * len);

        // 限制在线内图像区域内
        x1 = std::clamp(x1, 0, width - 1);
        y1 = std::clamp(y1, 0, height - 1);
        x2 = std::clamp(x2, 0, width - 1);
        y2 = std::clamp(y2, 0, height - 1);

        segments.emplace_back(cv::Vec4i(x1, y1, x2, y2));
    }

    *ret_num = segments.size();
    if (*ret_num == 0) return nullptr;

    int* ret = (int*)malloc(*ret_num * 4 * sizeof(int));
    if (!ret) {
        *ret_num = 0;
        return nullptr;
    }

    for (int i = 0; i < *ret_num; ++i) {
        ret[i * 4 + 0] = segments[i][0];
        ret[i * 4 + 1] = segments[i][1];
        ret[i * 4 + 2] = segments[i][2];
        ret[i * 4 + 3] = segments[i][3];
    }

    return ret;
}



int* rgb888_find_lines(FrameCHWSize frame_shape, uint8_t* data,int canny_thresh1, int canny_thresh2,int gaussian_blur_size,float rho, float theta,int hough_thresh, float min_line_length,float max_line_gap,int* ret_num)
{
    int width = frame_shape.width;
    int height = frame_shape.height;

    // 构造 RGB 图像（RGB888 每像素3字节）
    cv::Mat rgb(height, width, CV_8UC3, data);

    // 转为灰度图
    cv::Mat gray;
    cv::cvtColor(rgb, gray, cv::COLOR_RGB2GRAY);

    // 高斯模糊降噪
    if (gaussian_blur_size > 1 && gaussian_blur_size % 2 == 1) {
        cv::GaussianBlur(gray, gray, cv::Size(gaussian_blur_size, gaussian_blur_size), 0);
    }

    // Canny 边缘检测
    cv::Mat edges;
    cv::Canny(gray, edges, canny_thresh1, canny_thresh2);

    // 使用 HoughLinesP 检测直线
    std::vector<cv::Vec4i> lines;
    cv::HoughLinesP(edges, lines, rho, theta, hough_thresh, min_line_length, max_line_gap);

    *ret_num = lines.size();
    if (*ret_num == 0) return nullptr;
    // 分配返回数组 [x1, y1, x2, y2] * N
    int* ret = (int*)malloc(*ret_num * 4 * sizeof(int));
    if(!ret){
        *ret_num = 0;
        return nullptr;
    }
    for (int i = 0, j = 0; i < *ret_num; ++i, j += 4) {
        ret[j + 0] = lines[i][0];
        ret[j + 1] = lines[i][1];
        ret[j + 2] = lines[i][2];
        ret[j + 3] = lines[i][3];
    }
    return ret;
}


/**
 * @brief 灰度图像查找边缘
 * 
 * @param frame_shape 图像尺寸
 * @param data 图像数据
 * @param threshold1 第一个阈值
 * @param threshold2 第二个阈值
 * @param result 输出边缘图像数据
*/
void grayscale_find_edges(FrameCHWSize frame_shape, uint8_t* data,int threshold1, int threshold2,uint8_t* result) {
    int width = frame_shape.width;
    int height = frame_shape.height;
    // 构造原始灰度图像
    cv::Mat gray(height, width, CV_8UC1, data);

    // Canny边缘检测
    cv::Mat edges(height, width, CV_8UC1);
    cv::Canny(gray, edges, threshold1, threshold2);

    // 将 edges（单通道）拷贝回原图（覆盖原始内容）
    hal_rvv_memcpy(result, edges.data, (size_t)width * height);
}

/**
 * @brief 彩色图像查找边缘
 * 
 * @param frame_shape 图像尺寸
 * @param data 图像数据
 * @param threshold1 第一个阈值
 * @param threshold2 第二个阈值
 * @param result 输出边缘图像数据
*/
void rgb888_find_edges(FrameCHWSize frame_shape, uint8_t* data, int threshold1, int threshold2, uint8_t* result) {
    int width = frame_shape.width;
    int height = frame_shape.height;

    // 构造 RGB 图像（注意：RGB888 格式，即每像素 3 字节，顺序为 R, G, B）
    cv::Mat rgb(height, width, CV_8UC3, data);

    // 转换为灰度图
    cv::Mat gray;
    cv::cvtColor(rgb, gray, cv::COLOR_RGB2GRAY);

    // Canny 边缘检测
    cv::Mat edges;
    cv::Canny(gray, edges, threshold1, threshold2);

    // 拷贝结果到输出缓冲区（单通道）
    hal_rvv_memcpy(result, edges.data, (size_t)width * height);
}

/**
 * @brief 灰度图像二值化
 * 
 * @param frame_shape 图像尺寸
 * @param data 图像数据
 * @param thresh 阈值
 * @param maxval 最大值
 * @param result 输出二值化图像数据
*/
void grayscale_threshold_binary(FrameCHWSize frame_shape, uint8_t* data, int thresh, int maxval, uint8_t* result) {
    int width = frame_shape.width;
    int height = frame_shape.height;

    // 构造 灰度图
    cv::Mat gray(height, width, CV_8UC1, data);

    // 二值化（固定阈值）
    cv::Mat binary;
    cv::threshold(gray, binary, thresh, maxval, cv::THRESH_BINARY);

    // 拷贝结果到输出缓冲区（单通道，0或maxval）
    hal_rvv_memcpy(result, binary.data, (size_t)width * height);
}


/**
 * @brief 彩色图像二值化
 * 
 * @param frame_shape 图像尺寸
 * @param data 图像数据
 * @param thresh 阈值
 * @param maxval 最大值
 * @param result 输出二值化图像数据
*/
void rgb888_threshold_binary(FrameCHWSize frame_shape, uint8_t* data, int thresh, int maxval, uint8_t* result) {
    int width = frame_shape.width;
    int height = frame_shape.height;

    // 构造 RGB 图像（RGB888 格式，每像素3字节）
    cv::Mat rgb(height, width, CV_8UC3, data);

    // 转换为灰度图
    cv::Mat gray;
    cv::cvtColor(rgb, gray, cv::COLOR_RGB2GRAY);

    // 二值化（固定阈值）
    cv::Mat binary;
    cv::threshold(gray, binary, thresh, maxval, cv::THRESH_BINARY);

    // 拷贝结果到输出缓冲区（单通道，0或maxval）
    hal_rvv_memcpy(result, binary.data, (size_t)width * height);
}

/**
 * @brief RGB888 图像白平衡（灰度世界算法）
 * 
 * @param frame_shape 图像尺寸
 * @param data RGB888 原始图像数据
 * @param result 输出白平衡图像数据
 */
void rgb888_white_balance_gray_world(FrameCHWSize frame_shape, uint8_t* data, uint8_t* result) {
    int width = frame_shape.width;
    int height = frame_shape.height;

    // 构造 RGB 图像（RGB888 格式）
    cv::Mat rgb(height, width, CV_8UC3, data);

    // 拆分通道（OpenCV默认顺序是 R G B）
    std::vector<cv::Mat> channels(3);
    cv::split(rgb, channels); // channels[0]=R, [1]=G, [2]=B

    // 计算每个通道的平均值
    double avgR = cv::mean(channels[0])[0];
    double avgG = cv::mean(channels[1])[0];
    double avgB = cv::mean(channels[2])[0];

    // 灰度世界平均值
    double avgGray = (avgR + avgG + avgB) / 3.0;

    // 计算每个通道的增益系数
    double rGain = avgGray / avgR;
    double gGain = avgGray / avgG;
    double bGain = avgGray / avgB;

    // 应用增益
    channels[0] *= rGain;
    channels[1] *= gGain;
    channels[2] *= bGain;

    // 合并通道
    cv::Mat balanced;
    cv::merge(channels, balanced);

    // 转换回 8 位图像（防止溢出）
    cv::Mat clipped;
    balanced.convertTo(clipped, CV_8UC3);

    // 拷贝结果到输出缓冲区
    hal_rvv_memcpy(result, clipped.data, width * height * 3);
}

/**
 * @brief 快速白平衡：灰度世界算法（不使用 OpenCV）
 * 
 * @param frame_shape 图像尺寸
 * @param data RGB888 输入图像数据
 * @param result 输出图像数据（RGB888）
 */
void rgb888_white_balance_gray_world_fast(FrameCHWSize frame_shape, uint8_t* data, uint8_t* result) {
    int width = frame_shape.width;
    int height = frame_shape.height;
    int total_pixels = width * height;

    uint64_t sum_r = 0, sum_g = 0, sum_b = 0;

    // 首先计算 R/G/B 通道的总和
    for (int i = 0; i < total_pixels; i++) {
        sum_r += data[i * 3 + 0];
        sum_g += data[i * 3 + 1];
        sum_b += data[i * 3 + 2];
    }

    // 计算通道平均值
    double avg_r = sum_r / (double)total_pixels;
    double avg_g = sum_g / (double)total_pixels;
    double avg_b = sum_b / (double)total_pixels;
    double avg_gray = (avg_r + avg_g + avg_b) / 3.0;

    // 计算每个通道的增益
    double r_gain = avg_gray / avg_r;
    double g_gain = avg_gray / avg_g;
    double b_gain = avg_gray / avg_b;

    // 应用增益并写入输出图像
    for (int i = 0; i < total_pixels; i++) {
        int r = data[i * 3 + 0];
        int g = data[i * 3 + 1];
        int b = data[i * 3 + 2];

        // 增益校正，并裁剪到 [0, 255]
        result[i * 3 + 0] = std::min(255, std::max(0, int(r * r_gain)));
        result[i * 3 + 1] = std::min(255, std::max(0, int(g * g_gain)));
        result[i * 3 + 2] = std::min(255, std::max(0, int(b * b_gain)));
    }
}

/**
 * @brief 快速灰度世界白平衡（可调增益上限与亮度因子）
 *
 * @param frame_shape 图像尺寸
 * @param data        RGB888 输入图像数据
 * @param result      输出图像数据（RGB888）
 * @param gain_clip   增益上限（防止过曝），如 2.5
 * @param brightness_boost 亮度整体提升系数（默认 1.0，无提升）
 */
void rgb888_white_balance_gray_world_fast_ex(FrameCHWSize frame_shape, uint8_t* data, uint8_t* result,float gain_clip=2.5, float brightness_boost=1.05) {
    int width = frame_shape.width;
    int height = frame_shape.height;
    int total_pixels = width * height;

    uint64_t sum_r = 0, sum_g = 0, sum_b = 0;

    // 计算 R/G/B 总和
    for (int i = 0; i < total_pixels; i++) {
        sum_r += data[i * 3 + 0];
        sum_g += data[i * 3 + 1];
        sum_b += data[i * 3 + 2];
    }

    // 计算每个通道的平均值
    float avg_r = sum_r / (float)total_pixels;
    float avg_g = sum_g / (float)total_pixels;
    float avg_b = sum_b / (float)total_pixels;

    // 灰度平均值
    float avg_gray = (avg_r + avg_g + avg_b) / 3.0;

    // 计算增益，并裁剪到 gain_clip 范围
    float r_gain = std::min(gain_clip, avg_gray / avg_r);
    float g_gain = std::min(gain_clip, avg_gray / avg_g);
    float b_gain = std::min(gain_clip, avg_gray / avg_b);

    // 应用增益与亮度增强
    for (int i = 0; i < total_pixels; i++) {
        int r = data[i * 3 + 0];
        int g = data[i * 3 + 1];
        int b = data[i * 3 + 2];

        int r_out = int(r * r_gain * brightness_boost);
        int g_out = int(g * g_gain * brightness_boost);
        int b_out = int(b * b_gain * brightness_boost);

        result[i * 3 + 0] = std::min(255, std::max(0, r_out));
        result[i * 3 + 1] = std::min(255, std::max(0, g_out));
        result[i * 3 + 2] = std::min(255, std::max(0, b_out));
    }
}


void rgb888_white_balance_white_patch(FrameCHWSize frame_shape, uint8_t* data, uint8_t* result) {
    int width = frame_shape.width;
    int height = frame_shape.height;
    int total_pixels = width * height;

    std::vector<uint16_t> luminance(total_pixels);

    // Step 1: 计算亮度 Y = 0.299R + 0.587G + 0.114B，构建亮度排序表
    for (int i = 0; i < total_pixels; i++) {
        int r = data[i * 3 + 0];
        int g = data[i * 3 + 1];
        int b = data[i * 3 + 2];
        luminance[i] = static_cast<uint16_t>((77 * r + 150 * g + 29 * b) >> 8); // 整数逼近 Y
    }

    // Step 2: 选择 top 5% 最亮像素
    int top_n = total_pixels / 20;  // 5%
    std::vector<int> indices(total_pixels);
    for (int i = 0; i < total_pixels; i++) indices[i] = i;
    std::nth_element(indices.begin(), indices.begin() + top_n, indices.end(),
                     [&](int a, int b) { return luminance[a] > luminance[b]; });

    uint64_t sum_r = 0, sum_g = 0, sum_b = 0;
    for (int i = 0; i < top_n; i++) {
        int idx = indices[i];
        sum_r += data[idx * 3 + 0];
        sum_g += data[idx * 3 + 1];
        sum_b += data[idx * 3 + 2];
    }

    double avg_r = sum_r / (double)top_n;
    double avg_g = sum_g / (double)top_n;
    double avg_b = sum_b / (double)top_n;

    // Step 3: 以最高通道为基准白点（防止放大噪声）
    double max_avg = std::max({avg_r, avg_g, avg_b});
    double r_gain = max_avg / avg_r;
    double g_gain = max_avg / avg_g;
    double b_gain = max_avg / avg_b;

    // Step 4: 应用增益并写入结果
    for (int i = 0; i < total_pixels; i++) {
        int r = data[i * 3 + 0];
        int g = data[i * 3 + 1];
        int b = data[i * 3 + 2];
        result[i * 3 + 0] = std::min(255, std::max(0, int(r * r_gain)));
        result[i * 3 + 1] = std::min(255, std::max(0, int(g * g_gain)));
        result[i * 3 + 2] = std::min(255, std::max(0, int(b * b_gain)));
    }
}

/**
 * @brief 快速白点增益白平衡（带调节参数）
 * 
 * @param frame_shape 图像尺寸
 * @param data        RGB888 输入图像数据
 * @param result      输出图像数据
 * @param top_percent 亮度前百分比用于白点估计（建议 1.0 - 10.0）
 * @param gain_clip   增益最大值（防止过度校正，建议 2.0 - 3.0）
 * @param brightness_boost 最终结果乘上的亮度提升因子（建议 1.0 - 1.2）
 */
void rgb888_white_balance_white_patch_ex(FrameCHWSize frame_shape, uint8_t* data, uint8_t* result,float top_percent = 5.0f, float gain_clip = 3.0f, float brightness_boost = 1.0f)
{
    int width = frame_shape.width;
    int height = frame_shape.height;
    int total_pixels = width * height;
    int top_n = std::max(1, int(total_pixels * top_percent / 100.0f));

    std::vector<uint16_t> luminance(total_pixels);
    std::vector<int> indices(total_pixels);

    // Step 1: 计算亮度 Y（整数近似）
    for (int i = 0; i < total_pixels; i++) {
        int r = data[i * 3 + 0];
        int g = data[i * 3 + 1];
        int b = data[i * 3 + 2];
        luminance[i] = static_cast<uint16_t>((77 * r + 150 * g + 29 * b) >> 8);
        indices[i] = i;
    }

    // Step 2: 找 top_n 最亮像素
    std::nth_element(indices.begin(), indices.begin() + top_n, indices.end(),
        [&](int a, int b) { return luminance[a] > luminance[b]; });

    uint64_t sum_r = 0, sum_g = 0, sum_b = 0;
    for (int i = 0; i < top_n; i++) {
        int idx = indices[i];
        sum_r += data[idx * 3 + 0];
        sum_g += data[idx * 3 + 1];
        sum_b += data[idx * 3 + 2];
    }

    float avg_r = sum_r / (float)top_n;
    float avg_g = sum_g / (float)top_n;
    float avg_b = sum_b / (float)top_n;

    float max_avg = std::max({avg_r, avg_g, avg_b});
    float r_gain = std::min(gain_clip, max_avg / avg_r);
    float g_gain = std::min(gain_clip, max_avg / avg_g);
    float b_gain = std::min(gain_clip, max_avg / avg_b);

    // Step 3: 应用增益、亮度补偿、饱和裁剪
    for (int i = 0; i < total_pixels; i++) {
        int r = data[i * 3 + 0];
        int g = data[i * 3 + 1];
        int b = data[i * 3 + 2];

        r = std::min(255, std::max(0, int(r * r_gain * brightness_boost)));
        g = std::min(255, std::max(0, int(g * g_gain * brightness_boost)));
        b = std::min(255, std::max(0, int(b * b_gain * brightness_boost)));

        result[i * 3 + 0] = r;
        result[i * 3 + 1] = g;
        result[i * 3 + 2] = b;
    }
}


/**
 * @brief RGB888 图像白平衡（灰度世界算法，带可调强度）
 * 
 * @param frame_shape 图像尺寸
 * @param data RGB888 原始图像数据
 * @param alpha 增益调节强度，范围建议 0.0～1.0（0表示不调整，1表示完全灰度世界修正）
 * @param result 输出白平衡图像数据
 */
void rgb888_white_balance_gray_world_adjustable(FrameCHWSize frame_shape, uint8_t* data, float alpha, uint8_t* result) {
    int width = frame_shape.width;
    int height = frame_shape.height;

    // 构造 RGB 图像（RGB888 格式）
    cv::Mat rgb(height, width, CV_8UC3, data);

    // 拆分通道
    std::vector<cv::Mat> channels(3);
    cv::split(rgb, channels); // [0]=R, [1]=G, [2]=B

    // 通道平均值
    double avgR = cv::mean(channels[0])[0];
    double avgG = cv::mean(channels[1])[0];
    double avgB = cv::mean(channels[2])[0];

    // 灰度世界参考平均值
    double avgGray = (avgR + avgG + avgB) / 3.0;

    // 计算各通道目标增益
    double rGain = avgGray / avgR;
    double gGain = avgGray / avgG;
    double bGain = avgGray / avgB;

    // 应用 alpha 插值，alpha = 1.0 表示完全校正，alpha = 0.0 表示原图
    rGain = 1.0 + (rGain - 1.0) * alpha;
    gGain = 1.0 + (gGain - 1.0) * alpha;
    bGain = 1.0 + (bGain - 1.0) * alpha;

    // 应用增益
    channels[0] *= rGain;
    channels[1] *= gGain;
    channels[2] *= bGain;

    // 合并回图像
    cv::Mat balanced;
    cv::merge(channels, balanced);

    // 截断到 CV_8UC3
    cv::Mat clipped;
    balanced.convertTo(clipped, CV_8UC3);

    // 拷贝结果
    hal_rvv_memcpy(result, clipped.data, width * height * 3);
}

/**
 * @brief RGB888 图像曝光调整
 * 
 * @param frame_shape 图像尺寸
 * @param data RGB888 原始图像数据
 * @param exposure_gain 曝光增益因子，范围建议为 0.0 ~ 3.0（1.0 表示原始亮度）
 * @param result 输出调整后图像数据（RGB888）
 */
void rgb888_adjust_exposure(FrameCHWSize frame_shape, uint8_t* data, float exposure_gain, uint8_t* result) {
    int width = frame_shape.width;
    int height = frame_shape.height;

    // 构造 RGB 图像（RGB888 格式）
    cv::Mat rgb(height, width, CV_8UC3, data);

    // 转换为 float 类型做乘法
    cv::Mat rgb_float;
    rgb.convertTo(rgb_float, CV_32FC3);

    // 曝光增益乘法（可为 <1 变暗，>1 变亮）
    rgb_float *= exposure_gain;

    // 剪裁并转换回 8 位
    cv::Mat adjusted;
    rgb_float.convertTo(adjusted, CV_8UC3);

    // 拷贝结果数据
    hal_rvv_memcpy(result, adjusted.data, width * height * 3);
}

/**
 * @brief 快速调整RGB888图像曝光（乘以曝光增益，支持参数调节）
 * 
 * @param frame_shape 图像尺寸结构体
 * @param data 输入RGB888图像数据（长度 width*height*3）
 * @param exposure_gain 曝光增益，通常大于0，<1变暗，>1变亮
 * @param result 输出RGB888图像数据缓冲区（长度 width*height*3）
 */
void rgb888_adjust_exposure_fast(FrameCHWSize frame_shape, uint8_t* data, float exposure_gain, uint8_t* result) {
    int width = frame_shape.width;
    int height = frame_shape.height;
    int total_pixels = width * height;

    // 对每个像素的每个通道进行增益调整
    for (int i = 0; i < total_pixels; i++) {
        int base_idx = i * 3;

        // 计算新的通道值，并裁剪到0~255
        int r = static_cast<int>(data[base_idx + 0] * exposure_gain);
        int g = static_cast<int>(data[base_idx + 1] * exposure_gain);
        int b = static_cast<int>(data[base_idx + 2] * exposure_gain);

        result[base_idx + 0] = (r > 255) ? 255 : (r < 0 ? 0 : (uint8_t)r);
        result[base_idx + 1] = (g > 255) ? 255 : (g < 0 ? 0 : (uint8_t)g);
        result[base_idx + 2] = (b > 255) ? 255 : (b < 0 ? 0 : (uint8_t)b);
    }
}

static inline int clamp(int v, int low, int high) {
    return v < low ? low : (v > high ? high : v);
}



void rgb888_denoise(FrameCHWSize frame_shape, uint8_t* data, int method, int strength, uint8_t* result) {
    int width = frame_shape.width;
    int height = frame_shape.height;

    // 构造 RGB 图像（RGB888 格式）
    cv::Mat rgb(height, width, CV_8UC3, data);

    // 输出图像
    cv::Mat denoised;

    // 降噪方式选择
    switch (method) {
        case 0:  // 均值模糊（速度快，效果一般）
            cv::blur(rgb, denoised, cv::Size(strength, strength));
            break;

        case 1:  // 高斯模糊（边缘更柔和）
            cv::GaussianBlur(rgb, denoised, cv::Size(strength|1, strength|1), 0);
            break;

        case 2:  // 中值滤波（对椒盐噪声特别有效）
            cv::medianBlur(rgb, denoised, strength|1);
            break;

        case 3:  // 双边滤波（边缘保留最好，速度慢）
            cv::bilateralFilter(rgb, denoised, strength, strength * 2, strength / 2);
            break;

        default: // 默认使用高斯模糊
            cv::GaussianBlur(rgb, denoised, cv::Size(strength|1, strength|1), 0);
            break;
    }

    // 拷贝输出
    hal_rvv_memcpy(result, denoised.data, width * height * 3);
}

// 仅做均值滤波（Mean Blur）的函数
void rgb888_mean_blur(FrameCHWSize frame_shape, uint8_t* data, int kernel_size, uint8_t* result) {
    int width = frame_shape.width;
    int height = frame_shape.height;

    // 将输入数据构造成 OpenCV 的 RGB 图像
    cv::Mat rgb(height, width, CV_8UC3, data);

    // 存储输出的图像
    cv::Mat blurred;

    // 使用均值滤波，kernel_size 必须是正奇数
    int ksize = (kernel_size % 2 == 0) ? kernel_size + 1 : kernel_size;  // 确保为奇数
    cv::blur(rgb, blurred, cv::Size(ksize, ksize));

    // 拷贝结果到输出缓冲区
    hal_rvv_memcpy(result, blurred.data, width * height * 3);
}

void rgb888_mean_blur_fast(FrameCHWSize frame_shape, uint8_t* data, int kernel_size, uint8_t* result)
{
    int width = frame_shape.width;
    int height = frame_shape.height;
    int channels = frame_shape.channel;  // 应该是3

    int ksize = (kernel_size % 2 == 0) ? kernel_size + 1 : kernel_size;
    int khalf = ksize / 2;
    int window_area = ksize * ksize;

    // 分配积分图，uint32_t足够存储累加和
    // 三个通道分别计算积分图，尺寸：(height+1) * (width+1)，多1是方便计算
    uint32_t* integral_r = (uint32_t*)calloc((height + 1) * (width + 1), sizeof(uint32_t));
    uint32_t* integral_g = (uint32_t*)calloc((height + 1) * (width + 1), sizeof(uint32_t));
    uint32_t* integral_b = (uint32_t*)calloc((height + 1) * (width + 1), sizeof(uint32_t));

    // 计算积分图
    for (int y = 1; y <= height; y++) {
        uint32_t sum_r = 0, sum_g = 0, sum_b = 0;
        for (int x = 1; x <= width; x++) {
            int idx = ((y - 1) * width + (x - 1)) * 3;
            sum_r += data[idx + 0];
            sum_g += data[idx + 1];
            sum_b += data[idx + 2];

            integral_r[y * (width + 1) + x] = integral_r[(y - 1) * (width + 1) + x] + sum_r;
            integral_g[y * (width + 1) + x] = integral_g[(y - 1) * (width + 1) + x] + sum_g;
            integral_b[y * (width + 1) + x] = integral_b[(y - 1) * (width + 1) + x] + sum_b;
        }
    }

    // 使用积分图快速计算均值滤波
    for (int y = 0; y < height; y++) {
        int y1 = (y - khalf) < 0 ? 0 : y - khalf;
        int y2 = (y + khalf) >= height ? height - 1 : y + khalf;

        for (int x = 0; x < width; x++) {
            int x1 = (x - khalf) < 0 ? 0 : x - khalf;
            int x2 = (x + khalf) >= width ? width - 1 : x + khalf;

            int area = (y2 - y1 + 1) * (x2 - x1 + 1);

            // 积分图索引+1偏移
            int A = y1 * (width + 1) + x1;
            int B = y1 * (width + 1) + (x2 + 1);
            int C = (y2 + 1) * (width + 1) + x1;
            int D = (y2 + 1) * (width + 1) + (x2 + 1);

            uint32_t sum_r = integral_r[D] + integral_r[A] - integral_r[B] - integral_r[C];
            uint32_t sum_g = integral_g[D] + integral_g[A] - integral_g[B] - integral_g[C];
            uint32_t sum_b = integral_b[D] + integral_b[A] - integral_b[B] - integral_b[C];

            int out_idx = (y * width + x) * 3;
            result[out_idx + 0] = (uint8_t)(sum_r / area);
            result[out_idx + 1] = (uint8_t)(sum_g / area);
            result[out_idx + 2] = (uint8_t)(sum_b / area);
        }
    }

    free(integral_r);
    free(integral_g);
    free(integral_b);
}


void generate_gaussian_kernel_1d(int ksize, float sigma, std::vector<int>& kernel, int& kernel_sum) {
    int half = ksize / 2;
    kernel.resize(ksize);
    float sum = 0.0f;

    for (int i = -half; i <= half; ++i) {
        float val = std::exp(-(i * i) / (2.0f * sigma * sigma));
        kernel[i + half] = static_cast<int>(val * 1024); // 放大精度
        sum += val;
    }

    // 归一化
    kernel_sum = 0;
    for (int i = 0; i < ksize; ++i) {
        kernel_sum += kernel[i];
    }
}

void rgb888_gaussian_blur_fast(FrameCHWSize frame_shape, uint8_t* data, int kernel_size, uint8_t* result) {
    int width = frame_shape.width;
    int height = frame_shape.height;
    int channels = 3;
    int ksize = (kernel_size % 2 == 0) ? kernel_size + 1 : kernel_size;
    int khalf = ksize / 2;

    std::vector<int> kernel;
    int kernel_sum = 0;
    generate_gaussian_kernel_1d(ksize, kernel_size / 2.0f, kernel, kernel_sum);

    // 临时缓冲区
    std::vector<uint8_t> temp_buf(width * height * 3);

    // 第一阶段：横向卷积
    for (int y = 0; y < height; ++y) {
        for (int x = 0; x < width; ++x) {
            int sum_r = 0, sum_g = 0, sum_b = 0;

            for (int k = -khalf; k <= khalf; ++k) {
                int xx = std::clamp(x + k, 0, width - 1);
                int idx = (y * width + xx) * 3;
                int w = kernel[k + khalf];

                sum_r += data[idx + 0] * w;
                sum_g += data[idx + 1] * w;
                sum_b += data[idx + 2] * w;
            }

            int out_idx = (y * width + x) * 3;
            temp_buf[out_idx + 0] = sum_r / kernel_sum;
            temp_buf[out_idx + 1] = sum_g / kernel_sum;
            temp_buf[out_idx + 2] = sum_b / kernel_sum;
        }
    }

    // 第二阶段：纵向卷积
    for (int y = 0; y < height; ++y) {
        for (int x = 0; x < width; ++x) {
            int sum_r = 0, sum_g = 0, sum_b = 0;

            for (int k = -khalf; k <= khalf; ++k) {
                int yy = std::clamp(y + k, 0, height - 1);
                int idx = (yy * width + x) * 3;
                int w = kernel[k + khalf];

                sum_r += temp_buf[idx + 0] * w;
                sum_g += temp_buf[idx + 1] * w;
                sum_b += temp_buf[idx + 2] * w;
            }

            int out_idx = (y * width + x) * 3;
            result[out_idx + 0] = sum_r / kernel_sum;
            result[out_idx + 1] = sum_g / kernel_sum;
            result[out_idx + 2] = sum_b / kernel_sum;
        }
    }
}

inline uint8_t clamp(int v) {
    return v < 0 ? 0 : (v > 255 ? 255 : v);
}

/**
 * @brief 手动实现多种滤波降噪方式（支持 0~3 模式）
 * 
 * @param frame_shape 图像尺寸
 * @param data 输入 RGB888 图像数据
 * @param method 降噪方法（0-3）
 * @param strength 核大小（必须为奇数，建议 3, 5, 7）
 * @param result 输出图像缓冲区
 */
void rgb888_denoise_fast(FrameCHWSize frame_shape, uint8_t* data, int method, int strength, uint8_t* result) {
    int w = frame_shape.width;
    int h = frame_shape.height;
    int c = 3;
    int radius = strength / 2;

    float sigma2 = (strength * strength) / 9.0f;  // 用于高斯核或双边滤波

    for (int y = 0; y < h; y++) {
        for (int x = 0; x < w; x++) {
            int r_sum = 0, g_sum = 0, b_sum = 0;
            float wr_sum = 0, wg_sum = 0, wb_sum = 0;

            uint8_t r_vals[49], g_vals[49], b_vals[49]; // 中值缓存
            int val_idx = 0;

            uint8_t center_r = data[(y * w + x) * 3 + 0];
            uint8_t center_g = data[(y * w + x) * 3 + 1];
            uint8_t center_b = data[(y * w + x) * 3 + 2];

            for (int dy = -radius; dy <= radius; dy++) {
                int yy = y + dy;
                if (yy < 0 || yy >= h) continue;

                for (int dx = -radius; dx <= radius; dx++) {
                    int xx = x + dx;
                    if (xx < 0 || xx >= w) continue;

                    int idx = (yy * w + xx) * 3;
                    uint8_t r = data[idx + 0];
                    uint8_t g = data[idx + 1];
                    uint8_t b = data[idx + 2];

                    if (method == 0) {
                        // 均值模糊
                        r_sum += r; g_sum += g; b_sum += b;
                        val_idx++;
                    } else if (method == 1) {
                        // 高斯模糊（近似：基于距离计算权重）
                        float dist2 = dx * dx + dy * dy;
                        float weight = std::exp(-dist2 / (2 * sigma2));
                        wr_sum += r * weight;
                        wg_sum += g * weight;
                        wb_sum += b * weight;
                        val_idx += weight;
                    } else if (method == 2) {
                        // 中值滤波
                        if (val_idx < 49) {
                            r_vals[val_idx] = r;
                            g_vals[val_idx] = g;
                            b_vals[val_idx] = b;
                            val_idx++;
                        }
                    } else if (method == 3) {
                        // 双边滤波（近似）
                        float dist2 = dx * dx + dy * dy;
                        float color_dist2_r = (r - center_r) * (r - center_r);
                        float color_dist2_g = (g - center_g) * (g - center_g);
                        float color_dist2_b = (b - center_b) * (b - center_b);

                        float w_r = std::exp(-(dist2 + color_dist2_r) / (2 * sigma2));
                        float w_g = std::exp(-(dist2 + color_dist2_g) / (2 * sigma2));
                        float w_b = std::exp(-(dist2 + color_dist2_b) / (2 * sigma2));

                        wr_sum += r * w_r;
                        wg_sum += g * w_g;
                        wb_sum += b * w_b;

                        r_sum += w_r;
                        g_sum += w_g;
                        b_sum += w_b;
                    }
                }
            }

            int out_idx = (y * w + x) * 3;

            if (method == 0) {
                result[out_idx + 0] = r_sum / val_idx;
                result[out_idx + 1] = g_sum / val_idx;
                result[out_idx + 2] = b_sum / val_idx;
            } else if (method == 1) {
                result[out_idx + 0] = clamp(int(wr_sum / val_idx));
                result[out_idx + 1] = clamp(int(wg_sum / val_idx));
                result[out_idx + 2] = clamp(int(wb_sum / val_idx));
            } else if (method == 2) {
                std::sort(r_vals, r_vals + val_idx);
                std::sort(g_vals, g_vals + val_idx);
                std::sort(b_vals, b_vals + val_idx);
                result[out_idx + 0] = r_vals[val_idx / 2];
                result[out_idx + 1] = g_vals[val_idx / 2];
                result[out_idx + 2] = b_vals[val_idx / 2];
            } else if (method == 3) {
                result[out_idx + 0] = clamp(int(wr_sum / r_sum));
                result[out_idx + 1] = clamp(int(wg_sum / g_sum));
                result[out_idx + 2] = clamp(int(wb_sum / b_sum));
            }
        }
    }
}


/**
 * @brief RGB888 图像腐蚀（先转灰度并二值化，支持自定义或 Otsu 阈值）
 * 
 * @param frame_shape 图像尺寸
 * @param data RGB888 原始图像数据
 * @param kernel_size 腐蚀核尺寸（建议奇数）
 * @param iterations 腐蚀迭代次数
 * @param threshold_value 二值化阈值（0=使用Otsu，自定义则传1~255）
 * @param result 输出腐蚀后图像数据（二值图，单通道，大小为 W×H）
 */
void rgb888_erode(FrameCHWSize frame_shape, uint8_t* data, int kernel_size, int iterations, int threshold_value, uint8_t* result) {
    int width = frame_shape.width;
    int height = frame_shape.height;
    // 构造 RGB 图像（RGB888 格式）
    cv::Mat rgb(height, width, CV_8UC3, data);
    // 转换为灰度图
    cv::Mat gray;
    cv::cvtColor(rgb, gray, cv::COLOR_RGB2GRAY);  // 若为 BGR 输入请改为 COLOR_BGR2GRAY
    // 二值化（根据传入参数决定使用 Otsu 还是固定阈值）
    cv::Mat binary;
    if (threshold_value <= 0 || threshold_value > 255) {
        // Otsu 自适应
        cv::threshold(gray, binary, 0, 255, cv::THRESH_BINARY | cv::THRESH_OTSU);
    } else {
        // 固定阈值
        cv::threshold(gray, binary, threshold_value, 255, cv::THRESH_BINARY);
    }
    // 创建腐蚀核（必须是奇数）
    int ksize = kernel_size | 1;
    cv::Mat kernel = cv::getStructuringElement(cv::MORPH_RECT, cv::Size(ksize, ksize));

    // 执行腐蚀操作
    cv::Mat eroded;
    cv::erode(binary, eroded, kernel, cv::Point(-1, -1), iterations);

    // 拷贝输出结果（二值图，单通道）
    hal_rvv_memcpy(result, eroded.data, width * height);
}



/**
 * @brief RGB888 图像膨胀
 * 
 * @param frame_shape 图像尺寸
 * @param data RGB888 原始图像数据
 * @param kernel_size 膨胀核尺寸（建议奇数）
 * @param iterations 膨胀迭代次数
 * @param threshold_value 二值化阈值（0=使用Otsu，自定义则传1~255）
 * @param result 输出膨胀后图像数据（二值图，单通道）
 */
void rgb888_dilate(FrameCHWSize frame_shape, uint8_t* data, int kernel_size, int iterations, int threshold_value, uint8_t* result) {
    int width = frame_shape.width;
    int height = frame_shape.height;
    // 构造 RGB 图像（RGB888 格式）
    cv::Mat rgb(height, width, CV_8UC3, data);
    // 转换为灰度图
    cv::Mat gray;
    cv::cvtColor(rgb, gray, cv::COLOR_RGB2GRAY);  // 若为 BGR 输入请改为 COLOR_BGR2GRAY
    // 二值化（根据传入参数决定使用 Otsu 还是固定阈值）
    cv::Mat binary;
    if (threshold_value <= 0 || threshold_value > 255) {
        // Otsu 自适应
        cv::threshold(gray, binary, 0, 255, cv::THRESH_BINARY | cv::THRESH_OTSU);
    } else {
        // 固定阈值
        cv::threshold(gray, binary, threshold_value, 255, cv::THRESH_BINARY);
    }
    // 创建膨胀核（必须是奇数）
    int ksize = kernel_size | 1; // 保证为奇数
    cv::Mat kernel = cv::getStructuringElement(cv::MORPH_RECT, cv::Size(ksize, ksize));

    // 执行膨胀操作
    cv::Mat dilated;
    cv::dilate(binary, dilated, kernel, cv::Point(-1, -1), iterations);

    // 拷贝输出结果（二值图，单通道）
    hal_rvv_memcpy(result, dilated.data, width * height);
}


/**
 * @brief RGB888 图像开运算（先腐蚀后膨胀，去除小噪点）
 * 
 * @param frame_shape 图像尺寸
 * @param data RGB888 原始图像数据
 * @param kernel_size 结构元素尺寸（建议奇数）
 * @param iterations 迭代次数（每个操作的重复次数）
 * @param threshold_value 二值化阈值（0=Otsu自适应，1-255=固定阈值）
 * @param result 输出图像数据（二值图）
 */
void rgb888_open(FrameCHWSize frame_shape, uint8_t* data, int kernel_size, int iterations,int threshold_value, uint8_t* result) {
    int width = frame_shape.width;
    int height = frame_shape.height;
    // 构造 RGB 图像（RGB888 格式）
    cv::Mat rgb(height, width, CV_8UC3, data);
    // 转换为灰度图
    cv::Mat gray;
    cv::cvtColor(rgb, gray, cv::COLOR_RGB2GRAY);  // 若为 BGR 输入请改为 COLOR_BGR2GRAY
    // 二值化（根据传入参数决定使用 Otsu 还是固定阈值）
    cv::Mat binary;
    if (threshold_value <= 0 || threshold_value > 255) {
        // Otsu 自适应
        cv::threshold(gray, binary, 0, 255, cv::THRESH_BINARY | cv::THRESH_OTSU);
    } else {
        // 固定阈值
        cv::threshold(gray, binary, threshold_value, 255, cv::THRESH_BINARY);
    }

    // 创建结构元素（卷积核）
    int ksize = kernel_size | 1; // 强制为奇数
    cv::Mat kernel = cv::getStructuringElement(cv::MORPH_RECT, cv::Size(ksize, ksize));

    // 执行开运算（MORPH_OPEN = 腐蚀后膨胀）
    cv::Mat opened;
    cv::morphologyEx(binary, opened, cv::MORPH_OPEN, kernel, cv::Point(-1, -1), iterations);

    // 拷贝输出结果
    hal_rvv_memcpy(result, opened.data, width * height);
}

/**
 * @brief RGB888 图像闭运算（先膨胀后腐蚀，填补小孔）
 * 
 * @param frame_shape 图像尺寸
 * @param data RGB888 原始图像数据
 * @param kernel_size 结构元素尺寸（建议奇数）
 * @param iterations 迭代次数（每个操作的重复次数）
 * @param threshold_value 二值化阈值（0=Otsu自适应，1-255=固定阈值）
 * @param result 输出图像数据（二值图）
 */
void rgb888_close(FrameCHWSize frame_shape, uint8_t* data, int kernel_size, int iterations, int threshold_value, uint8_t* result) {
    int width = frame_shape.width;
    int height = frame_shape.height;

    // 构造 RGB 图像（RGB888 格式）
    cv::Mat rgb(height, width, CV_8UC3, data);
    // 转换为灰度图
    cv::Mat gray;
    cv::cvtColor(rgb, gray, cv::COLOR_RGB2GRAY);  // 若为 BGR 输入请改为 COLOR_BGR2GRAY
    // 二值化（根据传入参数决定使用 Otsu 还是固定阈值）
    cv::Mat binary;
    if (threshold_value <= 0 || threshold_value > 255) {
        // Otsu 自适应
        cv::threshold(gray, binary, 0, 255, cv::THRESH_BINARY | cv::THRESH_OTSU);
    } else {
        // 固定阈值
        cv::threshold(gray, binary, threshold_value, 255, cv::THRESH_BINARY);
    }

    // 创建结构元素（卷积核）
    int ksize = kernel_size | 1;  // 强制为奇数
    cv::Mat kernel = cv::getStructuringElement(cv::MORPH_RECT, cv::Size(ksize, ksize));

    // 执行闭运算（MORPH_CLOSE = 膨胀后腐蚀）
    cv::Mat closed;
    cv::morphologyEx(binary, closed, cv::MORPH_CLOSE, kernel, cv::Point(-1, -1), iterations);

    // 拷贝输出结果
    hal_rvv_memcpy(result, closed.data, width * height);
}

/**
 * @brief RGB888 图像形态学梯度（膨胀减去腐蚀结果，突出边缘）
 * 
 * @param frame_shape 图像尺寸
 * @param data RGB888 原始图像数据
 * @param kernel_size 结构元素尺寸（建议奇数）
 * @param iterations 迭代次数（每个操作的重复次数）
 * @param threshold_value 二值化阈值（0=Otsu自适应，1-255=固定阈值）
 * @param result 输出图像数据（RGB888）
 */
void rgb888_gradient(FrameCHWSize frame_shape, uint8_t* data, int kernel_size, int iterations, int threshold_value, uint8_t* result) {
    int width = frame_shape.width;
    int height = frame_shape.height;

    // 构造 RGB 图像（RGB888 格式）
    cv::Mat rgb(height, width, CV_8UC3, data);
    // 转换为灰度图
    cv::Mat gray;
    cv::cvtColor(rgb, gray, cv::COLOR_RGB2GRAY);  // 若为 BGR 输入请改为 COLOR_BGR2GRAY
    // 二值化（根据传入参数决定使用 Otsu 还是固定阈值）
    cv::Mat binary;
    if (threshold_value <= 0 || threshold_value > 255) {
        // Otsu 自适应
        cv::threshold(gray, binary, 0, 255, cv::THRESH_BINARY | cv::THRESH_OTSU);
    } else {
        // 固定阈值
        cv::threshold(gray, binary, threshold_value, 255, cv::THRESH_BINARY);
    }

    // 创建结构元素（卷积核）
    int ksize = kernel_size | 1;  // 强制为奇数
    cv::Mat kernel = cv::getStructuringElement(cv::MORPH_RECT, cv::Size(ksize, ksize));

    // 执行形态学梯度运算（膨胀 - 腐蚀）
    cv::Mat gradient;
    cv::morphologyEx(binary, gradient, cv::MORPH_GRADIENT, kernel, cv::Point(-1, -1), iterations);

    // 拷贝输出结果
    hal_rvv_memcpy(result, gradient.data, width * height);
}

/**
 * @brief RGB888 图像顶帽操作（Top-Hat，原图减去开运算结果）
 * 
 * @param frame_shape 图像尺寸
 * @param data RGB888 原始图像数据
 * @param kernel_size 结构元素尺寸（建议奇数）
 * @param iterations 迭代次数（每个操作的重复次数）
 * @param threshold_value 二值化阈值（0=Otsu自适应，1-255=固定阈值）
 * @param result 输出图像数据（二值图）
 */
void rgb888_tophat(FrameCHWSize frame_shape, uint8_t* data, int kernel_size, int iterations, int threshold_value, uint8_t* result) {
    int width = frame_shape.width;
    int height = frame_shape.height;

    // 构造 RGB 图像（RGB888 格式）
    cv::Mat rgb(height, width, CV_8UC3, data);
    // 转换为灰度图
    cv::Mat gray;
    cv::cvtColor(rgb, gray, cv::COLOR_RGB2GRAY);  // 若为 BGR 输入请改为 COLOR_BGR2GRAY
    // 二值化（根据传入参数决定使用 Otsu 还是固定阈值）
    cv::Mat binary;
    if (threshold_value <= 0 || threshold_value > 255) {
        // Otsu 自适应
        cv::threshold(gray, binary, 0, 255, cv::THRESH_BINARY | cv::THRESH_OTSU);
    } else {
        // 固定阈值
        cv::threshold(gray, binary, threshold_value, 255, cv::THRESH_BINARY);
    }

    // 创建结构元素（卷积核）
    int ksize = kernel_size | 1;  // 强制为奇数
    cv::Mat kernel = cv::getStructuringElement(cv::MORPH_RECT, cv::Size(ksize, ksize));

    // 执行顶帽操作（TopHat = 原图 - 开运算）
    cv::Mat tophat;
    cv::morphologyEx(binary, tophat, cv::MORPH_TOPHAT, kernel, cv::Point(-1, -1), iterations);

    // 拷贝输出结果
    hal_rvv_memcpy(result, tophat.data, width * height);
}

/**
 * @brief RGB888 图像黑帽操作（Black-Hat，闭运算结果减去原图）
 * 
 * @param frame_shape 图像尺寸
 * @param data RGB888 原始图像数据
 * @param kernel_size 结构元素尺寸（建议奇数）
 * @param iterations 迭代次数（每个操作的重复次数）
 * @param threshold_value 二值化阈值（0=Otsu自适应，1-255=固定阈值）
 * @param result 输出图像数据（二值图）
 */
void rgb888_blackhat(FrameCHWSize frame_shape, uint8_t* data, int kernel_size, int iterations, int threshold_value, uint8_t* result) {
    int width = frame_shape.width;
    int height = frame_shape.height;

    // 构造 RGB 图像（RGB888 格式）
    cv::Mat rgb(height, width, CV_8UC3, data);

    // 转换为灰度图
    cv::Mat gray;
    cv::cvtColor(rgb, gray, cv::COLOR_RGB2GRAY);  // 若为 BGR 输入请改为 COLOR_BGR2GRAY
    // 二值化（根据传入参数决定使用 Otsu 还是固定阈值）
    cv::Mat binary;
    if (threshold_value <= 0 || threshold_value > 255) {
        // Otsu 自适应
        cv::threshold(gray, binary, 0, 255, cv::THRESH_BINARY | cv::THRESH_OTSU);
    } else {
        // 固定阈值
        cv::threshold(gray, binary, threshold_value, 255, cv::THRESH_BINARY);
    }

    // 创建结构元素（卷积核）
    int ksize = kernel_size | 1;  // 强制为奇数
    cv::Mat kernel = cv::getStructuringElement(cv::MORPH_RECT, cv::Size(ksize, ksize));

    // 执行黑帽操作（BlackHat = 闭运算 - 原图）
    cv::Mat blackhat;
    cv::morphologyEx(binary, blackhat, cv::MORPH_BLACKHAT, kernel, cv::Point(-1, -1), iterations);

    // 拷贝输出结果
    hal_rvv_memcpy(result, blackhat.data, width * height);
}

/**
 * @brief 计算 RGB888 图像的颜色直方图（每通道 256 个 bin）
 * 
 * @param frame_shape 图像尺寸
 * @param data RGB888 原始图像数据
 * @param hist_r 输出 R 通道直方图（256 个 int 元素）
 * @param hist_g 输出 G 通道直方图（256 个 int 元素）
 * @param hist_b 输出 B 通道直方图（256 个 int 元素）
 */
void rgb888_calc_histogram(FrameCHWSize frame_shape, uint8_t* data, uint32_t* result) {
    int width = frame_shape.width;
    int height = frame_shape.height;

    cv::Mat rgb(height, width, CV_8UC3, data);
    cv::Mat bgr;
    cv::cvtColor(rgb, bgr, cv::COLOR_RGB2BGR);
    std::vector<cv::Mat> channels;
    cv::split(bgr, channels);

    if (channels.size() != 3) return;

    uint32_t* hist_b = result + 0;
    uint32_t* hist_g = result + 256;
    uint32_t* hist_r = result + 512;

    hal_rvv_memset(hist_b, 0, 256 * sizeof(uint32_t));
    hal_rvv_memset(hist_g, 0, 256 * sizeof(uint32_t));
    hal_rvv_memset(hist_r, 0, 256 * sizeof(uint32_t));

    for (int y = 0; y < height; ++y) {
        const uchar* ptr_b = channels[0].ptr<uchar>(y);
        const uchar* ptr_g = channels[1].ptr<uchar>(y);
        const uchar* ptr_r = channels[2].ptr<uchar>(y);
        for (int x = 0; x < width; ++x) {
            hist_b[ptr_b[x]]++;
            hist_g[ptr_g[x]]++;
            hist_r[ptr_r[x]]++;
        }
    }
}

int* grayscale_find_corners(FrameCHWSize frame_shape, uint8_t* data,int maxCorners, float qualityLevel, float minDistance,int* ret_num){
    int width = frame_shape.width;
    int height = frame_shape.height;

    // 构造 灰度 图像
    cv::Mat gray(height, width, CV_8UC1, data);
    // Shi-Tomasi角点检测
    std::vector<cv::Point2f> corners;
    cv::goodFeaturesToTrack(gray, corners, maxCorners, qualityLevel, minDistance);

    *ret_num = static_cast<int>(corners.size());
    if (*ret_num == 0) return nullptr;

    // 分配输出内存（每个角点2个int：x, y）
    int* ret = static_cast<int*>(malloc(*ret_num * 2 * sizeof(int)));
    for (int i = 0; i < *ret_num; ++i) {
        ret[i * 2 + 0] = cvRound(corners[i].x);
        ret[i * 2 + 1] = cvRound(corners[i].y);
    }

    return ret;
}

/**
 * @brief 彩色图像查找角点（不缩放图像，优化性能）
 * 
 * @param frame_shape 图像尺寸
 * @param data 图像数据（RGB888，每像素3字节）
 * @param maxCorners 最大角点数（建议100~500）
 * @param qualityLevel Shi-Tomasi角点质量因子（建议0.01~0.1）
 * @param minDistance 最小角点距离（像素，建议5~20）
 * @param ret_num 返回角点数量
 * @return int* 角点数组，每个角点包含 x, y 坐标（int），共 ret_num*2 个元素
 */
int* rgb888_find_corners(FrameCHWSize frame_shape, uint8_t* data,int maxCorners, float qualityLevel, float minDistance,int* ret_num)
{
    int width = frame_shape.width;
    int height = frame_shape.height;

    // 构造 RGB 图像
    cv::Mat rgb(height, width, CV_8UC3, data);

    // 转为灰度图
    cv::Mat gray;
    cv::cvtColor(rgb, gray, cv::COLOR_RGB2GRAY);

    // Shi-Tomasi角点检测
    std::vector<cv::Point2f> corners;
    cv::goodFeaturesToTrack(gray, corners, maxCorners, qualityLevel, minDistance);

    *ret_num = static_cast<int>(corners.size());
    if (*ret_num == 0) return nullptr;

    // 分配输出内存（每个角点2个int：x, y）
    int* ret = static_cast<int*>(malloc(*ret_num * 2 * sizeof(int)));
    for (int i = 0; i < *ret_num; ++i) {
        ret[i * 2 + 0] = cvRound(corners[i].x);
        ret[i * 2 + 1] = cvRound(corners[i].y);
    }

    return ret;
}

struct Corner {
    int x;
    int y;
    int score; // 用于排序
};

// FAST 16点偏移（保持不变）
const int FAST_OFFSETS[16][2] = {
    {0, -3}, {1, -3}, {2, -2}, {3, -1},
    {3, 0},  {3, 1},  {2, 2},  {1, 3},
    {0, 3},  {-1, 3}, {-2, 2}, {-3, 1},
    {-3, 0}, {-3, -1},{-2, -2},{-1, -3}
};

// 预计算偏移地址（以 byte 为单位），避免每次 y*w+x 计算
std::vector<int> precomputed_offsets;

// 初始化偏移地址（调用一次即可）
void init_fast_offsets(int w, int h) {
    precomputed_offsets.resize(16);
    for (int i = 0; i < 16; ++i) {
        int dx = FAST_OFFSETS[i][0];
        int dy = FAST_OFFSETS[i][1];
        precomputed_offsets[i] = dy * w + dx;
    }
}

// 快速 FAST 检测（使用 9-点连续检查）
inline bool is_corner_fast(const uint8_t* img, const std::vector<int>& offsets, uint8_t center, int threshold, int& score) {
    const uint8_t* p = img;
    int above[16], below[16];
    int n_above = 0, n_below = 0;

    // 预计算每个点是否亮/暗
    for (int i = 0; i < 16; ++i) {
        uint8_t val = p[offsets[i]];
        if (val > center + threshold) {
            above[i] = 1;
            n_above++;
        } else above[i] = 0;

        if (val < center - threshold) {
            below[i] = 1;
            n_below++;
        } else below[i] = 0;
    }

    if (n_above < 9 && n_below < 9) return false;

    // 检查是否存在连续 9 个 above 或 below
    auto has_n_consecutive = [](const int* pattern, int n) {
        int extended[32];
        for (int i = 0; i < 16; ++i) extended[i] = extended[i + 16] = pattern[i];
        int count = 0;
        for (int i = 0; i < 32; ++i) {
            if (extended[i]) count++;
            else count = 0;
            if (count >= n) return true;
        }
        return false;
    };

    bool bright = has_n_consecutive(above, 9);
    bool dark   = has_n_consecutive(below, 9);

    if (!bright && !dark) return false;

    // 计算 score：最大 threshold 差值（可简化为最小 |diff| 超出 threshold 的量）
    int min_diff = 255;
    if (bright) {
        for (int i = 0; i < 16; ++i) {
            if (above[i]) {
                int diff = img[offsets[i]] - center - threshold;
                if (diff < min_diff) min_diff = diff;
            }
        }
        score = min_diff + threshold; // 越大越强
    } else if (dark) {
        for (int i = 0; i < 16; ++i) {
            if (below[i]) {
                int diff = center - threshold - img[offsets[i]];
                if (diff < min_diff) min_diff = diff;
            }
        }
        score = min_diff + threshold;
    }

    return true;
}

// 优化版 FAST 检测
std::vector<Corner> fast_detect_optimized(uint8_t* img, int w, int h, int threshold) {
    std::vector<Corner> corners;
    corners.reserve(h * w / 100); // 预分配

    // 确保偏移已初始化
    static bool offsets_inited = false;
    static std::vector<int> local_offsets;
    if (!offsets_inited || local_offsets.size() != 16) {
        init_fast_offsets(w, h);
        local_offsets = precomputed_offsets;
        offsets_inited = true;
    }

    const uint8_t* base = img + 3 * w + 3; // 起始位置 (3,3)
    int stride = w;

    for (int y = 3; y < h - 3; ++y) {
        const uint8_t* row = base + (y - 3) * stride;
        for (int x = 3; x < w - 3; ++x) {
            const uint8_t* center_ptr = row + x;
            uint8_t center = *center_ptr;
            int score = 0;
            if (is_corner_fast(center_ptr, local_offsets, center, threshold, score)) {
                corners.push_back({x, y, score});
            }
        }
    }

    return corners;
}

// 非极大值抑制（NMS）：在局部窗口中保留最高分角点
std::vector<Corner> nms_corners(const std::vector<Corner>& corners, int w, int h, int radius = 7) {
    std::vector<std::vector<const Corner*>> grid((w + radius - 1) / radius, std::vector<const Corner*>((h + radius - 1) / radius));
    std::vector<Corner> kept;

    // 分桶
    for (const auto& c : corners) {
        int gx = c.x / radius;
        int gy = c.y / radius;
        if (gx >= 0 && gx < (int)grid.size() && gy >= 0 && gy < (int)grid[0].size()) {
            grid[gx][gy] = &c;
        }
    }

    // 对每个桶，检查邻居桶，保留局部最大值
    for (int gx = 0; gx < (int)grid.size(); ++gx) {
        for (int gy = 0; gy < (int)grid[0].size(); ++gy) {
            const Corner* best = nullptr;
            // 检查 3x3 邻域
            for (int dx = -1; dx <= 1; ++dx) {
                for (int dy = -1; dy <= 1; ++dy) {
                    int ngx = gx + dx;
                    int ngy = gy + dy;
                    if (ngy >= 0 && ngx >= 0 && ngx < (int)grid.size() && ngy < (int)grid[0].size()) {
                        const Corner* c = grid[ngx][ngy];
                        if (c && (!best || c->score > best->score)) {
                            best = c;
                        }
                    }
                }
            }
            if (best && (kept.empty() || !(best->x == kept.back().x && best->y == kept.back().y))) {
                kept.push_back(*best);
            }
        }
    }

    // 按分数排序
    std::sort(kept.begin(), kept.end(), [](const Corner& a, const Corner& b) {
        return a.score > b.score;
    });

    return kept;
}

// 主函数：优化版
int* rgb888_find_corners_fast(FrameCHWSize frame_shape, uint8_t* data, int maxCorners,
                              float qualityLevel, float minDistance, int* ret_num) {
    int width = frame_shape.width;
    int height = frame_shape.height;

    // RGB 转灰度
    std::vector<uint8_t> gray_data(width * height);
    const uint8_t* rgb_ptr = data;
    for (int i = 0; i < width * height; ++i, rgb_ptr += 3) {
        gray_data[i] = static_cast<uint8_t>((77 * rgb_ptr[0] + 150 * rgb_ptr[1] + 29 * rgb_ptr[2]) >> 8);
    }
    // FAST 阈值
    int fast_threshold = static_cast<int>(qualityLevel * 255);
    if (fast_threshold < 10) fast_threshold = 10;
    // FAST 检测
    std::vector<Corner> raw_corners = fast_detect_optimized(gray_data.data(), width, height, fast_threshold);

    if (raw_corners.empty()) {
        *ret_num = 0;
        return nullptr;
    }
    // NMS 抑制
    std::vector<Corner> nms_corners_list = nms_corners(raw_corners, width, height, static_cast<int>(minDistance));
    // 限制数量
    if ((int)nms_corners_list.size() > maxCorners) {
        nms_corners_list.resize(maxCorners);
    }

    *ret_num = static_cast<int>(nms_corners_list.size());
    if (*ret_num == 0) return nullptr;

    // 分配输出内存
    int* ret = static_cast<int*>(malloc(*ret_num * 2 * sizeof(int)));
    if (!ret) {
        *ret_num = 0;
        return nullptr;
    }

    for (int i = 0; i < *ret_num; ++i) {
        ret[i * 2 + 0] = nms_corners_list[i].x;
        ret[i * 2 + 1] = nms_corners_list[i].y;
    }

    return ret;
}

void save_image(const char* save_path,FrameCHWSize frame_shape,uint8_t* data){
    cv::Mat img(frame_shape.height, frame_shape.width, CV_8UC3, data);
    cv::cvtColor(img, img, cv::COLOR_RGB2BGR);
    cv::imwrite(save_path, img);
}

/**
 * @brief RGB888 图像畸变校正（去畸变）
 * 
 * @param frame_shape 图像尺寸（宽高）
 * @param data RGB888 原始图像数据
 * @param camera_matrix 相机内参（长度9的 float 数组，按行主序 3x3）
 * @param dist_coeffs 畸变系数（长度为5或8的 float 数组）
 * @param dist_len 畸变系数个数（5 或 8）
 * @param result 输出图像数据（去畸变 RGB888）
 */
void rgb888_undistort(FrameCHWSize frame_shape, uint8_t* data,float* camera_matrix, float* dist_coeffs, int dist_len,uint8_t* result) {
    int width = frame_shape.width;
    int height = frame_shape.height;
    // 构造 RGB 图像（RGB888 格式）
    cv::Mat rgb(height, width, CV_8UC3, data);
    // 构造相机内参矩阵 (3x3)
    cv::Mat cam_mat(3, 3, CV_32F);
    hal_rvv_memcpy(cam_mat.data, camera_matrix, 9 * sizeof(float));
    // 构造畸变系数矩阵（1xN）
    cv::Mat dist_mat(1, dist_len, CV_32F);
    hal_rvv_memcpy(dist_mat.data, dist_coeffs, dist_len * sizeof(float));
    // 去畸变图像
    cv::Mat undistorted;
    cv::undistort(rgb, undistorted, cam_mat, dist_mat);
    // 拷贝输出结果
    hal_rvv_memcpy(result, undistorted.data, width * height * 3);
}

void rgb888_undistort_new_cam_mat(FrameCHWSize frame_shape, uint8_t* data,float* camera_matrix, float* dist_coeffs,int dist_len, uint8_t* result) {
    int width = frame_shape.width;
    int height = frame_shape.height;

    // 原始图像（RGB888）
    cv::Mat rgb(height, width, CV_8UC3, data);

    // 相机矩阵
    cv::Mat cam_mat(3, 3, CV_32F);
    hal_rvv_memcpy(cam_mat.data, camera_matrix, 9 * sizeof(float));

    // 畸变系数
    cv::Mat dist_mat(1, dist_len, CV_32F);
    hal_rvv_memcpy(dist_mat.data, dist_coeffs, dist_len * sizeof(float));

    // 计算优化后的新相机矩阵（最大保留图像区域）
    cv::Mat new_cam_mat = cv::getOptimalNewCameraMatrix(
        cam_mat, dist_mat, cv::Size(width, height), 1.0, cv::Size(width, height), 0);

    // 去畸变图像
    cv::Mat undistorted;
    cv::undistort(rgb, undistorted, cam_mat, dist_mat, new_cam_mat);

    // 拷贝输出数据
    hal_rvv_memcpy(result, undistorted.data, width * height * 3);
}


static cv::Mat map1, map2;
static cv::Size last_size;
static bool map_initialized = false;

/**
 * @brief RGB888 图像畸变校正（高性能）
 * 
 * @param frame_shape 图像尺寸（宽高）
 * @param data RGB888 原始图像数据
 * @param camera_matrix 相机内参（长度9的 float 数组，按行主序 3x3）
 * @param dist_coeffs 畸变系数（长度为5或8的 float 数组）
 * @param dist_len 畸变系数个数（5 或 8）
 * @param result 输出图像数据（去畸变 RGB888）
 */
void rgb888_undistort_fast(FrameCHWSize frame_shape, uint8_t* data, float* camera_matrix, float* dist_coeffs, int dist_len, uint8_t* result) {
    int width = frame_shape.width;
    int height = frame_shape.height;
    cv::Size image_size(width, height);

    // 输入图像（不复制数据）
    cv::Mat rgb(height, width, CV_8UC3, data);

    // 相机矩阵
    cv::Mat cam_mat(3, 3, CV_32F, camera_matrix);
    // 畸变参数
    cv::Mat dist_mat(1, dist_len, CV_32F, dist_coeffs);

    // 如果尺寸改变或第一次调用，重新计算映射表
    if (!map_initialized || image_size != last_size) {
        cv::initUndistortRectifyMap(
            cam_mat, dist_mat, cv::Mat(), cam_mat,  // R = 空，newCameraMatrix = 原始相机矩阵
            image_size, CV_16SC2, map1, map2);
        last_size = image_size;
        map_initialized = true;
    }

    // remap 是多线程优化的，远快于 undistort
    cv::Mat undistorted;
    cv::remap(rgb, undistorted, map1, map2, cv::INTER_LINEAR);

    // 拷贝结果
    hal_rvv_memcpy(result, undistorted.data, width * height * 3);
}


void rgb888_undistort_new_cam_mat(FrameCHWSize frame_shape, uint8_t* data,int* roi, float* camera_matrix, float* dist_coeffs,int dist_len, uint8_t* result) {
    int width = frame_shape.width;
    int height = frame_shape.height;

    // 原始图像（RGB888）
    cv::Mat rgb(height, width, CV_8UC3, data);

    // 相机矩阵
    cv::Mat cam_mat(3, 3, CV_32F);
    hal_rvv_memcpy(cam_mat.data, camera_matrix, 9 * sizeof(float));

    // 畸变系数
    cv::Mat dist_mat(1, dist_len, CV_32F);
    hal_rvv_memcpy(dist_mat.data, dist_coeffs, dist_len * sizeof(float));

    // 计算优化后的新相机矩阵（最大保留图像区域）
    cv::Mat new_cam_mat = cv::getOptimalNewCameraMatrix(
        cam_mat, dist_mat, cv::Size(width, height), 1.0, cv::Size(width, height), 0);

    // 去畸变图像
    cv::Mat undistorted;
    cv::undistort(rgb, undistorted, cam_mat, dist_mat, new_cam_mat);

    // 拷贝输出数据
    hal_rvv_memcpy(result, undistorted.data, width * height * 3);
}

float rgb888_pnp_distance(FrameCHWSize frame_shape, uint8_t* data, int* roi,
                          float* camera_matrix, float* dist_coeffs, int dist_len,
                          float roi_width_real, float roi_height_real) {
    int width = frame_shape.width;
    int height = frame_shape.height;

    // 构建 RGB888 图像
    cv::Mat rgb(height, width, CV_8UC3, data);

    // 相机内参矩阵
    cv::Mat cam_mat(3, 3, CV_32F);
    hal_rvv_memcpy(cam_mat.data, camera_matrix, 9 * sizeof(float));

    // 畸变系数
    cv::Mat dist_mat(1, dist_len, CV_32F);
    hal_rvv_memcpy(dist_mat.data, dist_coeffs, dist_len * sizeof(float));

    // ROI 图像坐标
    int x = roi[0];
    int y = roi[1];
    int w = roi[2];
    int h = roi[3];

    // 使用实际物理尺寸构建 objectPoints（单位自定义，如 cm 或 m）
    std::vector<cv::Point3f> objectPoints = {
        {0, 0, 0},
        {roi_width_real, 0, 0},
        {roi_width_real, roi_height_real, 0},
        {0, roi_height_real, 0}
    };

    // ROI 的图像像素坐标（四角）
    std::vector<cv::Point2f> imagePoints = {
        {static_cast<float>(x), static_cast<float>(y)},
        {static_cast<float>(x + w), static_cast<float>(y)},
        {static_cast<float>(x + w), static_cast<float>(y + h)},
        {static_cast<float>(x), static_cast<float>(y + h)}
    };

    // 解算位姿
    cv::Mat rvec, tvec;
    bool ok = cv::solvePnP(objectPoints, imagePoints, cam_mat, dist_mat, rvec, tvec);

    if (ok && tvec.total() == 3) {
        return static_cast<float>(cv::norm(tvec));  // 返回目标到相机的距离（与输入尺寸单位一致）
    } else {
        return -1.0f; // 解算失败
    }
}

// 判断四边形是否接近矩形
bool isRectangle(const std::vector<cv::Point>& approx, double angle_tolerance = 10.0) {
    if (approx.size() != 4) return false;

    auto angle = [](cv::Point pt1, cv::Point pt2, cv::Point pt3) {
        cv::Point2f v1 = pt1 - pt2;
        cv::Point2f v2 = pt3 - pt2;
        float cos_angle = (v1.dot(v2)) / (cv::norm(v1) * cv::norm(v2));
        return std::acos(std::clamp(cos_angle, -1.0f, 1.0f)) * 180.0 / CV_PI;
    };

    for (int i = 0; i < 4; ++i) {
        double a = angle(approx[(i+3)%4], approx[i], approx[(i+1)%4]);
        if (std::abs(a - 90.0) > angle_tolerance) return false;
    }

    return true;
}

// 将 4 个角点顺时针排列（左上、右上、右下、左下）
std::vector<cv::Point2f> orderPointsClockwise(const std::vector<cv::Point2f>& pts) {
    std::vector<cv::Point2f> rect(4);
    std::vector<float> sum_pts, diff_pts;

    for (const auto& pt : pts) {
        sum_pts.push_back(pt.x + pt.y);
        diff_pts.push_back(pt.y - pt.x);
    }

    rect[0] = pts[std::min_element(sum_pts.begin(), sum_pts.end()) - sum_pts.begin()]; // top-left
    rect[2] = pts[std::max_element(sum_pts.begin(), sum_pts.end()) - sum_pts.begin()]; // bottom-right
    rect[1] = pts[std::min_element(diff_pts.begin(), diff_pts.end()) - diff_pts.begin()]; // top-right
    rect[3] = pts[std::max_element(diff_pts.begin(), diff_pts.end()) - diff_pts.begin()]; // bottom-left

    return rect;
}

float rgb888_pnp_distance_from_corners(FrameCHWSize frame_shape, uint8_t* data,
                                       float* camera_matrix, float* dist_coeffs, int dist_len,
                                       float obj_width_cm, float obj_height_cm,
                                       int* rects, int* corners) {
    int width = frame_shape.width;
    int height = frame_shape.height;

    // 构造 RGB 图像
    cv::Mat rgb(height, width, CV_8UC3, data);
    cv::Mat undistorted;

    // 相机参数
    cv::Mat cam_mat(3, 3, CV_32F, camera_matrix);
    cv::Mat dist_mat(1, dist_len, CV_32F, dist_coeffs);

    // 畸变校正
    cv::undistort(rgb, undistorted, cam_mat, dist_mat);

    // 灰度 + 预处理
    cv::Mat gray, blurred, edges;
    cv::cvtColor(undistorted, gray, cv::COLOR_BGR2GRAY);
    cv::GaussianBlur(gray, blurred, cv::Size(5, 5), 0);
    cv::Canny(blurred, edges, 50, 150);

    // 查找轮廓
    std::vector<std::vector<cv::Point>> contours;
    cv::findContours(edges, contours, cv::RETR_EXTERNAL, cv::CHAIN_APPROX_SIMPLE);

    std::vector<std::vector<cv::Point>> rectangles;
    for (const auto& cnt : contours) {
        if (cv::contourArea(cnt) < 1000) continue;

        std::vector<cv::Point> approx;
        cv::approxPolyDP(cnt, approx, 0.02 * cv::arcLength(cnt, true), true);
        if (isRectangle(approx)) {
            rectangles.push_back(approx);
        }
    }

    if (rectangles.empty()) return -1.0f;

    // 获取最大矩形
    auto largest_rect = *std::max_element(rectangles.begin(), rectangles.end(),
        [](const std::vector<cv::Point>& a, const std::vector<cv::Point>& b) {
            return cv::contourArea(a) < cv::contourArea(b);
        });

    // 获取最小外接矩形角点
    cv::RotatedRect box = cv::minAreaRect(largest_rect);
    cv::Point2f box_points[4];
    box.points(box_points);
    std::vector<cv::Point2f> img_pts = orderPointsClockwise({box_points, box_points + 4});

    // === 拷贝矩形 rects: x, y, w, h ===
    cv::Rect rect = box.boundingRect();
    if (rects) {
        rects[0] = rect.x;
        rects[1] = rect.y;
        rects[2] = rect.width;
        rects[3] = rect.height;
    }

    // === 拷贝角点 corners: [x0, y0, x1, y1, ..., x3, y3] ===
    if (corners) {
        for (int i = 0; i < 4; ++i) {
            corners[i * 2]     = static_cast<int>(img_pts[i].x);
            corners[i * 2 + 1] = static_cast<int>(img_pts[i].y);
        }
    }

    // 构造 3D 物体点
    std::vector<cv::Point3f> obj_pts = {
        {0, 0, 0},
        {obj_width_cm, 0, 0},
        {obj_width_cm, obj_height_cm, 0},
        {0, obj_height_cm, 0}
    };

    // PnP 解算
    cv::Mat rvec, tvec;
    bool ok = cv::solvePnP(obj_pts, img_pts, cam_mat, dist_mat, rvec, tvec);
    if (!ok || tvec.total() != 3) return -1.0f;

    return static_cast<float>(cv::norm(tvec));
}


/**
 * @brief 对 RGB888 图像中指定 ROI 区域进行透视变换
 * 
 * @param frame_shape     输入图像尺寸（CHW）
 * @param data            原始 RGB888 图像数据（HWC 格式，连续内存）
 * @param roi             ROI 区域坐标（int[4]，分别为 x, y, width, height）
 * @param dst_pts         目标变换点（float[8]，按顺时针顺序：左上、左下、右下、右上）
 * @param out_width       目标图像宽度
 * @param out_height      目标图像高度
 * @param result          透视变换后的 RGB888 图像输出指针（大小为 out_width * out_height * 3）
 */
void rgb888_perspective_transform(FrameCHWSize frame_shape, uint8_t* data,
                                  int roi[4], float dst_pts[8],
                                  int out_width, int out_height,
                                  uint8_t* result) {
    int width = frame_shape.width;
    int height = frame_shape.height;

    // 构造 OpenCV 图像
    cv::Mat rgb(height, width, CV_8UC3, data);

    // 解析 ROI
    int x = roi[0];
    int y = roi[1];
    int w = roi[2];
    int h = roi[3];
    cv::Rect roi_rect(x, y, w, h);
    cv::Mat roi_img = rgb(roi_rect);

    // 构造源点：ROI 内部的 4 个角点（顺时针）
    std::vector<cv::Point2f> src_pts = {
        {0.0f, 0.0f},
        {0.0f, static_cast<float>(h - 1)},
        {static_cast<float>(w - 1), static_cast<float>(h - 1)},
        {static_cast<float>(w - 1), 0.0f}
    };

    // 构造目标点（顺时针）
    std::vector<cv::Point2f> dst_points = {
        {dst_pts[0], dst_pts[1]},
        {dst_pts[2], dst_pts[3]},
        {dst_pts[4], dst_pts[5]},
        {dst_pts[6], dst_pts[7]}
    };

    // 获取透视变换矩阵
    cv::Mat M = cv::getPerspectiveTransform(src_pts, dst_points);

    // 执行透视变换
    cv::Mat warped;
    cv::warpPerspective(roi_img, warped, M, cv::Size(out_width, out_height));

    // 拷贝结果
    hal_rvv_memcpy(result, warped.data, out_width * out_height * 3);
}







