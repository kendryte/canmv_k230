#include <string>
#include <algorithm>
#include <new>
#include <sstream>
#include <array>
#include "postprocess.h"
#include <opencv2/opencv.hpp>
#include "clipper.h"

#include "hal_rvv_ops.h"


typedef struct ocr_det_res
{
    float meanx;
    float meany;
	cv::Point2f vertices[4];
    cv::Point2f ver_src[4];
    float score;
}ocr_det_res;

double distance(cv::Point p0, cv::Point p1)
{
    const double dx = (double)p0.x - p1.x;
    const double dy = (double)p0.y - p1.y;
    return sqrt(dx * dx + dy * dy);
}

void getBox(ocr_det_res& b, const std::vector<cv::Point>& contours)
{
    cv::RotatedRect minrect = cv::minAreaRect(contours);
    cv::Point2f vtx[4];
    minrect.points(vtx);
    for(int i = 0; i < 4; i++)
    {
        b.vertices[i].x = vtx[i].x;
        b.vertices[i].y = vtx[i].y;
    }
}

void unclip(const std::vector<cv::Point>& contours, std::vector<cv::Point>& con)
{
    ClipperLib::Path subj;
    ClipperLib::Paths solution;
    double dis = 0.0;
    for(int i = 0; i < contours.size(); i++)
        subj << ClipperLib::IntPoint(contours[i].x, contours[i].y);
    for(int i = 0; i < contours.size() - 1; i++)
        dis += distance(contours[i], contours[i+1]);
    // Degenerate contour (zero perimeter): dividing by dis would give a NaN
    // offset and an empty solution.  Fall back to the raw contour points so the
    // caller still gets a usable polygon instead of crashing.
    if (dis == 0.0) {
        con = contours;
        return;
    }
    double dis1 = (-1 * Area(subj)) * 1.5 / dis;
    ClipperLib::ClipperOffset co;
    co.AddPath(subj, ClipperLib::jtSquare, ClipperLib::etClosedPolygon);
    co.Execute(solution, dis1);
    // Execute can legally return an empty solution for degenerate/self-
    // intersecting polygons; guard the solution[0] access.
    if (solution.empty()) {
        con = contours;
        return;
    }
    ClipperLib::Path tmp = solution[0];
    for(int i = 0; i < tmp.size(); i++)
    {
        cv::Point p(tmp[i].X, tmp[i].Y);
        con.push_back(p);
    }
    for(int i = 0; i < con.size(); i++)
        subj << ClipperLib::IntPoint(con[i].x, con[i].y);
}

float boxScore(const cv::Mat& src, std::vector<cv::Point> contours, ocr_det_res& b, int w, int h, FrameSize frame_size,int input_width ,int input_height)
{
    int xmin = input_width;
    int xmax = 0;
    int ymin = input_height;
    int ymax = 0;
    for(int i = 0; i < contours.size(); i++)
    {
        xmin = std::floor((contours[i].x < xmin ? contours[i].x : xmin));
        xmax = std::ceil((contours[i].x > xmax ? contours[i].x : xmax));
        ymin = std::floor((contours[i].y < ymin ? contours[i].y : ymin));
        ymax = std::ceil((contours[i].y > ymax ? contours[i].y : ymax));
    }
    for(int i = 0; i < contours.size(); i++)
    {
        contours[i].x = contours[i].x - xmin;
        contours[i].y = contours[i].y - ymin;
    }
    std::vector<std::vector<cv::Point>> vec;
    vec.clear();
    vec.push_back(contours);
    float ratiow = 1.0 * input_width / frame_size.width;
    float ratioh = 1.0 * input_height / frame_size.height;
    b.meanx = ((1.0 * xmin + xmax) / 2 - w) / (input_width - 2 * w) * frame_size.width;
    b.meany = ((1.0 * ymin + ymax) / 2 - h) / (input_height - 2 * h) * frame_size.height;
    cv::Mat img = cv::Mat::zeros(ymax - ymin + 1, xmax - xmin + 1, CV_8UC1);
    cv::fillPoly(img, vec, cv::Scalar(1));
    return (float)cv::mean(src(cv::Rect(xmin, ymin, xmax-xmin+1, ymax-ymin+1)), img)[0];  
}

static void free_array_wrappers(ArrayWrapper *wrappers, int count)
{
    if (wrappers == nullptr) {
        return;
    }

    for (int i = 0; i < count; ++i) {
        free(wrappers[i].data);
        free(wrappers[i].dimensions);
    }

    free(wrappers);
}

std::array<size_t, 4> sort_indices(const std::array<cv::Point2f, 4>& points)
{
	std::array<size_t, 4> indices = {0, 1, 2, 3};
	std::sort(indices.begin(), indices.end(), [&points](size_t a, size_t b) {
		return points[a].x < points[b].x;
	});
	return indices;
}

void find_rectangle_vertices(const std::array<cv::Point2f, 4>& points, cv::Point2f& topLeft, cv::Point2f& topRight, cv::Point2f& bottomRight, cv::Point2f& bottomLeft)
{
    //先按照x排序,比较左右，再按照y比较上下
	auto sorted_x_id = sort_indices(points);

	if (points[sorted_x_id[0]].y < points[sorted_x_id[1]].y)
	{
		topLeft = points[sorted_x_id[0]];
		bottomLeft = points[sorted_x_id[1]];
	}
	else
	{
		topLeft = points[sorted_x_id[1]];
		bottomLeft = points[sorted_x_id[0]];
	}

	if (points[sorted_x_id[2]].y < points[sorted_x_id[3]].y)
	{
        bottomRight = points[sorted_x_id[3]];
		topRight = points[sorted_x_id[2]];

	}
	else
	{ 
        bottomRight = points[sorted_x_id[2]];
		topRight = points[sorted_x_id[3]];
	}
	
}


void expandRectangle(cv::Point2f& topLeft, cv::Point2f& topRight, cv::Point2f& bottomRight, cv::Point2f& bottomLeft, float scaleFactor_width,float scaleFactor_high, int maxWidth, int maxHeight) {
    // Calculate the center of the original rectangle

    cv::Point2f newTopLeft(scaleFactor_width * topLeft.x - (scaleFactor_width-1)*topRight.x, scaleFactor_high * topLeft.y - (scaleFactor_high-1)*bottomLeft.y);
    cv::Point2f newTopRight(scaleFactor_width * topRight.x - (scaleFactor_width-1)*topLeft.x, scaleFactor_high * topRight.y - (scaleFactor_high-1)*bottomRight.y);
    cv::Point2f newBottomRight(scaleFactor_width * bottomRight.x - (scaleFactor_width-1)*bottomLeft.x, scaleFactor_high * bottomRight.y - (scaleFactor_high-1)*topRight.y);
    cv::Point2f newBottomLeft(scaleFactor_width * bottomLeft.x - (scaleFactor_width-1)*bottomRight.x, scaleFactor_high * bottomLeft.y - (scaleFactor_high-1)*topLeft.y);

    // Check and adjust vertices to stay within specified boundaries
    if (newTopLeft.x < 0) newTopLeft.x = 0;
    if (newTopLeft.y < 0) newTopLeft.y = 0;
    if (newTopRight.x > maxWidth) newTopRight.x = maxWidth;
    if (newTopRight.y < 0) newTopRight.y = 0;
    if (newBottomRight.x > maxWidth) newBottomRight.x = maxWidth;
    if (newBottomRight.y > maxHeight) newBottomRight.y = maxHeight;
    if (newBottomLeft.x < 0) newBottomLeft.x = 0;
    if (newBottomLeft.y > maxHeight) newBottomLeft.y = maxHeight;

    // Update the input points with the adjusted vertices
    topLeft = newTopLeft;
    topRight = newTopRight;
    bottomRight = newBottomRight;
    bottomLeft = newBottomLeft;
    
}


void warppersp(const cv::Mat& src, cv::Mat& dst, const ocr_det_res& b, std::array<cv::Point2f, 4>& vtd)
{
    cv::Mat rotation;
    std::array<cv::Point, 4> con;
    for (size_t i = 0; i < con.size(); ++i) con[i] = b.vertices[i];

    cv::Mat con_mat(4, 1, CV_32SC2, con.data());
    cv::RotatedRect minrect = cv::minAreaRect(con_mat);
    std::array<cv::Point2f, 4> vtx, vt;
    minrect.points(vtx.data());


    find_rectangle_vertices(vtx, vtd[0], vtd[1], vtd[2], vtd[3]);


    int maxWidth = src.cols;
    int maxHeight = src.rows;
    float scaleFactor_width = 1.025;
    float scaleFactor_higt = 1.15;

    expandRectangle(vtd[0], vtd[1], vtd[2], vtd[3],scaleFactor_width,scaleFactor_higt,maxWidth,maxHeight);


    float tmp_w = cv::norm(vtd[1]-vtd[0]);
    float tmp_h = cv::norm(vtd[2]-vtd[1]);
    float w = std::max(tmp_w,tmp_h);
    float h = std::min(tmp_w,tmp_h);

    vt[0].x = 0;
    vt[0].y = 0;
    vt[1].x = w;
    vt[1].y = 0;
    vt[2].x = w;
    vt[2].y = h;
    vt[3].x = 0;
    vt[3].y = h;//h
    rotation = cv::getPerspectiveTransform(vtd.data(), vt.data());

    cv::warpPerspective(src, dst, rotation, cv::Size(w, h));
}

ArrayWrapper* ocr_post_process(FrameSize frame_size,FrameSize kmodel_frame_size,float box_thresh,float threshold, float *data_0, uint8_t *data_1, int* results_size)
{   
    int input_width=kmodel_frame_size.width;
    int input_height=kmodel_frame_size.height;
    int h;
    int w;
    int row = frame_size.height;
    int col = frame_size.width;
    float ratio_w = 1.0 * input_width / col;
    float ratio_h = 1.0 * input_height / row;
    float ratio = std::min(ratio_h, ratio_w);
    int unpad_w = (int)round(col * ratio);
    int unpad_h = (int)round(row * ratio);

    if (results_size != nullptr) {
        *results_size = 0;
    }

    w = std::max(0, (input_width - unpad_w) / 2);
    h = std::max(0, (input_height - unpad_h) / 2);



    // Owned across the whole routine so the catch(...) at the end can release
    // them: this function is called across a C ABI boundary, so letting a cv::
    // / STL exception propagate into C would be undefined behaviour.
    ocr_det_res* b = nullptr;
    ArrayWrapper* arrayWrapper = nullptr;
    int l = 0;
    int num_result = 0;
    try {
    cv::Mat img_src = cv::Mat(row , col, CV_8UC3, data_1);
    cv::Mat src(input_height, input_width, CV_32FC1, data_0);
    cv::Mat mask(src > threshold);
    std::vector<std::vector<cv::Point>> contours;
    std::vector<cv::Vec4i> hierarchy;
    cv::findContours(mask, contours, hierarchy, cv::RETR_LIST, cv::CHAIN_APPROX_SIMPLE);

    int num = contours.size();
    std::vector<int> list_num;

    b = new (std::nothrow) ocr_det_res[num];
    if (b == nullptr) {
        return nullptr;
    }

    for(int i = 0; i < num; i++)
    {   
        std::vector<cv::Point> con;
        cv::Mat crop;
        if(contours[i].size() < 4)
            continue;
        getBox(b[i], contours[i]);
        unclip(contours[i], con);
        getBox(b[i], con);
        float score = boxScore(src, contours[i], b[i], w, h, frame_size,input_width ,input_height);
        if (score < box_thresh)
            continue;
        b[i].score = score;
        for(int m = 0; m < 4; m++)
        {
            b[i].vertices[m].x = std::max(std::min((int)b[i].vertices[m].x, input_width), 0);
            b[i].vertices[m].y = std::max(std::min((int)b[i].vertices[m].y, input_height), 0);
            b[i].vertices[m].x = b[i].vertices[m].x / unpad_w * frame_size.width;
            b[i].vertices[m].y = b[i].vertices[m].y  / unpad_h * frame_size.height;
            b[i].ver_src[m].x = b[i].vertices[m].x;
            b[i].ver_src[m].y = b[i].vertices[m].y;
            b[i].vertices[m].x = std::max((float)0, std::min(b[i].vertices[m].x, (float)frame_size.width));
            b[i].vertices[m].y = std::max((float)0, std::min(b[i].vertices[m].y, (float)frame_size.height));
        }


        l+=1;
        list_num.push_back(i);
    }
    if (l == 0) {
        delete[] b;
        b = nullptr;
        return nullptr;
    }

    arrayWrapper = (ArrayWrapper*)calloc((size_t)l, sizeof(ArrayWrapper));
    if (arrayWrapper == nullptr) {
        delete[] b;
        b = nullptr;
        return nullptr;
    }

     for (auto &i: list_num) 
    {   
        std::array<cv::Point2f, 4> sort_vtd;
        std::vector<cv::Point> vec;
        std::array<cv::Point2f, 4> ver, vtd;
        cv::Mat crop;
        warppersp(img_src, crop, b[i], sort_vtd);
        size_t crop_size = crop.total() * crop.channels() * sizeof(uint8_t);
        // A degenerate (zero-size) crop must be skipped, not treated as an
        // allocation failure: malloc(0) may return NULL and would otherwise
        // discard every valid result.
        if (crop_size == 0) {
            continue;
        }
        arrayWrapper[num_result].data = (uint8_t*)malloc(crop_size);
        arrayWrapper[num_result].dimensions=(int*)malloc(3*sizeof(int));
        if ((arrayWrapper[num_result].data == nullptr) || (arrayWrapper[num_result].dimensions == nullptr)) {
            delete[] b;
            b = nullptr;
            free_array_wrappers(arrayWrapper, l);
            arrayWrapper = nullptr;
            return nullptr;
        }
        
        uint8_t* matData = crop.ptr<uint8_t>(); // 获取cv::Mat的数据指针
        hal_rvv_memcpy(arrayWrapper[num_result].data, matData, crop_size); // 复制数据

        
        arrayWrapper[num_result].dimensions[0] = crop.channels();
        arrayWrapper[num_result].dimensions[1] = crop.rows;
        arrayWrapper[num_result].dimensions[2] = crop.cols;
        
        


        crop.release();
        vec.clear();
        for(int j = 0; j < 4; j++)
        {
            cv::Point tmp = b[i].vertices[j];
            vec.push_back(tmp);
        }
        cv::RotatedRect rect = minAreaRect(vec);
        rect.points(ver.data());
        int maxWidth = frame_size.width;
        int maxHeight = frame_size.height;
        float scaleFactor_width = 1.025;
        float scaleFactor_higt = 1.15;
        find_rectangle_vertices(ver, vtd[0], vtd[1], vtd[2], vtd[3]);
        expandRectangle(vtd[0], vtd[1], vtd[2], vtd[3],scaleFactor_width,scaleFactor_higt,maxWidth,maxHeight);
        for (int j = 0; j < 4; j++) {
            arrayWrapper[num_result].coordinates[2 * j] = vtd[j].x;
            arrayWrapper[num_result].coordinates[2 * j + 1] = vtd[j].y;
        }
        num_result+=1;
    }
    delete[] b;
    b = nullptr;
    if (results_size != nullptr) {
        *results_size = num_result;
    }
    return arrayWrapper;
    } catch (...) {
        // Never let a C++/OpenCV exception cross the C ABI boundary: release
        // everything owned so far and report zero results.
        delete[] b;
        free_array_wrappers(arrayWrapper, l);
        if (results_size != nullptr) {
            *results_size = 0;
        }
        return nullptr;
    }
}
