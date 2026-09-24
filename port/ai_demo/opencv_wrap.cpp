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
#include <opencv2/highgui.hpp>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp>
#include <limits>
#include "aidemo_wrap.h"

int get_dtype_for_cv(char dtype,int channels)
{
    switch (dtype)
    {
    case 'b':
        return CV_MAKETYPE(CV_8S,channels);
    case 'B':
        return CV_MAKETYPE(CV_8U,channels);
    case 'h':
        return CV_MAKETYPE(CV_16S,channels);
    case 'H':
        return CV_MAKETYPE(CV_16U,channels);
    case 'i':
        return CV_MAKETYPE(CV_32S,channels);
    case 'f':
        return CV_MAKETYPE(CV_32F,channels);
    case 'd':
        return CV_MAKETYPE(CV_64F,channels);
    default:
        throw std::runtime_error("Unsupported cv::mat data type.");
    }
}

char get_dtype_for_mp(int dtype)
{
    switch (dtype)
    {
    case CV_8S:
    case CV_8SC2:
    case CV_8SC3:
    case CV_8SC4:
        return 'b';
    case CV_8U:
    case CV_8UC2:
    case CV_8UC3:
    case CV_8UC4:
        return 'B';
    case CV_16S:
    case CV_16SC2:
    case CV_16SC3:
    case CV_16SC4:
        return 'h';
    case CV_16U:
    case CV_16UC2:
    case CV_16UC3:
    case CV_16UC4:
        return 'H';
    case CV_32S:
    case CV_32SC2:
    case CV_32SC3:
    case CV_32SC4:
        return 'i';
    case CV_32F:
    case CV_32FC2:
    case CV_32FC3:
    case CV_32FC4:
        return 'f';
    case CV_64F:
    case CV_64FC2:
    case CV_64FC3:
    case CV_64FC4:
        return 'd';
    default:
        throw std::runtime_error("Unsupported cv::mat data type.");
    }
}

void from_numpy(cv_and_ndarray_convert_info *info,cv::Mat& mat_data)
{   
    int cv_type;
    if (info->ndim_<=2)
        cv_type = get_dtype_for_cv(info->dtype_,1);
    else
        cv_type = get_dtype_for_cv(info->dtype_,info->shape_[2]);
    int height = info->shape_[0], width = info->shape_[1];
    mat_data = cv::Mat(height,width,cv_type,info->data_);
}

bool to_numpy(cv::Mat& mat_data, cv_and_ndarray_convert_info *info)
{
    info->data_ = nullptr;
    info->len_ = 0;
    info->dtype_ = get_dtype_for_mp(mat_data.type());
    hal_rvv_memset(info->shape_,0,sizeof(size_t)*3);
    info->shape_[0] = mat_data.rows;        //hwc
    info->shape_[1] = mat_data.cols;
    info->shape_[2] = mat_data.channels();

    hal_rvv_memset(info->strides_,0,sizeof(size_t)*3);
    int numpy_elem_size = mat_data.elemSize() / mat_data.channels();
    info->strides_[0] = numpy_elem_size * info->shape_[1] * info->shape_[2];
    info->strides_[1] = numpy_elem_size * info->shape_[2];
    info->strides_[2] = numpy_elem_size * 1;

    info->ndim_ = mat_data.dims;
    info->len_ = mat_data.total();
    size_t elem_size = mat_data.elemSize();
    if (elem_size != 0 && info->len_ > SIZE_MAX / elem_size) {
        info->data_ = NULL;
        return false;
    }
    size_t data_size = info->len_ * elem_size;
    info->data_ = (void *)malloc(data_size);
    if (info->data_ == NULL && data_size != 0) {
        return false;
    }
    if (data_size != 0) {
        hal_rvv_memcpy(info->data_, mat_data.data, data_size);
    }
    return true;
}

void cv_and_ndarray_convert_info_free(void *context)
{
    cv_and_ndarray_convert_info *info = static_cast<cv_and_ndarray_convert_info *>(context);
    if (info != NULL) {
        free(info->data_);
        info->data_ = NULL;
    }
}

bool invert_affine_transform(float *data,cv_and_ndarray_convert_info *info)
{
    info->data_ = nullptr;
    info->len_ = 0;
    try {
        cv::Mat matrix(2, 3, CV_32F,data);
        cv::Mat matrix_inv;
        cv::invertAffineTransform(matrix, matrix_inv);
        return to_numpy(matrix_inv,info);
    } catch (...) {
        return false;
    }
}

void draw_polylines(cv_and_ndarray_convert_info *in_info,generic_array *pts,bool is_closed,generic_array *color,int thickness,int line_type,int shift)
{
    cv::Mat src_img;
    from_numpy(in_info,src_img);

    std::vector<std::vector<cv::Point>> face_sub_part_point_set_outline;
    float* pts_data = (float*)(pts->data_);
    std::vector<cv::Point> face_sub_part_point_set;
    for(int i=0;i<pts->length_;i=i+2)
    {
        face_sub_part_point_set.push_back({int(pts_data[i]), int(pts_data[i+1])});
    }
    face_sub_part_point_set_outline.push_back(face_sub_part_point_set);

    uint8_t* draw_color = (uint8_t*)(color->data_);

    if(color->length_ == 3)
    {
        cv::Scalar scalar_bgr(draw_color[0], draw_color[1], draw_color[2]);
        cv::polylines(src_img, face_sub_part_point_set_outline, is_closed, scalar_bgr, thickness, line_type, shift);
    }
    else if(color->length_ == 4)
    {
        cv::Scalar scalar_bgra(draw_color[0], draw_color[1], draw_color[2],draw_color[3]);
        cv::polylines(src_img, face_sub_part_point_set_outline, is_closed, scalar_bgra, thickness, line_type, shift);
    }
    else
    {
        throw std::runtime_error("Unsupported color cv2::polylines.");
    }
}

void draw_contours(cv_and_ndarray_convert_info *in_info,generic_array *pts,int contour_idx,generic_array *color,int thickness,int line_type)
{
    cv::Mat src_img;
    from_numpy(in_info,src_img);

    std::vector<std::vector<cv::Point>> face_sub_part_point_set_outline;
    float* pts_data = (float*)(pts->data_);
    std::vector<cv::Point> face_sub_part_point_set;
	for(int i=0;i<pts->length_;i=i+2)
    {
        face_sub_part_point_set.push_back({int(pts_data[i]), int(pts_data[i+1])});
    }
    face_sub_part_point_set_outline.push_back(face_sub_part_point_set);

    uint8_t* draw_color = (uint8_t*)(color->data_);
    if(color->length_ == 3)
    {
        cv::Scalar scalar_bgr(draw_color[0], draw_color[1], draw_color[2]);
        cv::drawContours(src_img, face_sub_part_point_set_outline, contour_idx, scalar_bgr, thickness, line_type);
    }
    else if(color->length_ == 4)
    {
        cv::Scalar scalar_bgra(draw_color[0], draw_color[1], draw_color[2],draw_color[3]);
        cv::drawContours(src_img, face_sub_part_point_set_outline, contour_idx, scalar_bgra, thickness, line_type);
    }
    else
    {
        throw std::runtime_error("Unsupported color cv2::polylines.");
    }
}
