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
#include <math.h>
#include <string.h>
#include <opencv2/highgui.hpp>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp>
#include "aidemo_wrap.h"
#include "ai_rvv_kernels.h"

void from_numpy(cv_and_ndarray_convert_info *info,cv::Mat& mat_data);

int net_len_;
cv::Mat matrix_dst_for_osd_;

// 0: 'background'	1: 'skin'	2: 'nose'
// 3: 'eye_g'	4: 'l_eye'	5: 'r_eye'
// 6: 'l_brow'	7: 'r_brow'	8: 'l_ear'
// 9: 'r_ear'	10: 'mouth'	11: 'u_lip'
// 12: 'l_lip'	13: 'hair'	14: 'hat'
// 15: 'ear_r'	16: 'neck_l'	17: 'neck'
// 18: 'cloth'		
cv::Vec4b color_list_for_osd_pixel[] = {
	cv::Vec4b(255,220,20,60), //background， 注意：颜色顺序改为A-RGB
    cv::Vec4b(255,0,0,142),//skin
    cv::Vec4b(255,119,11,32), //nose
    cv::Vec4b(255,0,0,230), //eye_g
    cv::Vec4b(255,106,0,228),//l_eye
    cv::Vec4b(255,0,60,100), //r_eye
    cv::Vec4b(255,0,80,100), //l_brow
    cv::Vec4b(255,0,0,70), //r_brow
    cv::Vec4b(255,0,0,192), //l_ear
    cv::Vec4b(255,250,170,30), //r_ear
    cv::Vec4b(255,100,170,30), //mouth
    cv::Vec4b(255,220,220,0), //u_lip
    cv::Vec4b(255,175,116,175), //l_lip
    cv::Vec4b(255,250,0,30), //hair
    cv::Vec4b(255,165,42,42), //hat
    cv::Vec4b(255,255,77,255), //ear_r
    cv::Vec4b(255,0,226,252), //neck_l
    cv::Vec4b(255,182,182,255), //neck
    cv::Vec4b(255,0,82,0) //cloth
};

void get_affine_matrix_for_osd(Bbox& bbox)
{
    float factor = 2.7;
    float edge_size = net_len_;	
	float trans_distance = edge_size / 2.0;
	float height = bbox.h;
	float width = bbox.w;
	float center_x = bbox.x + bbox.w / 2.0 ;
	float center_y = bbox.y + bbox.h / 2.0 ;
	float maximum_edge = factor * (height > width ? height : width);
	float scale = edge_size * 2.0 / maximum_edge;
	float cx = trans_distance - scale * center_x;
	float cy = trans_distance - scale * center_y;
	matrix_dst_for_osd_ = cv::Mat::zeros(3, 3, CV_32FC1);
    matrix_dst_for_osd_.at<float>(0, 0) = scale;
    matrix_dst_for_osd_.at<float>(0, 1) = 0;
    matrix_dst_for_osd_.at<float>(0, 2) = cx;
    matrix_dst_for_osd_.at<float>(1, 0) = 0;
    matrix_dst_for_osd_.at<float>(1, 1) = scale;
    matrix_dst_for_osd_.at<float>(1, 2) = cy;
	matrix_dst_for_osd_.at<float>(2, 0) = 0;
	matrix_dst_for_osd_.at<float>(2, 1) = 0;
	matrix_dst_for_osd_.at<float>(2, 2) = 1;
}

void face_parse_post_process(cv_and_ndarray_convert_info* in_info,FrameSize* ai_img_shape,FrameSize* osd_img_shape,int net_len,Bbox* bbox,CHWSize* model_out_shape,float* p_outputs)
{
    cv::Mat src_img;
    from_numpy(in_info,src_img);

    int src_w = osd_img_shape->width;
    int src_h = osd_img_shape->height;	

	net_len_ = net_len;
	
	//1. get final affine matrix
	//1.1 get affine matrix for osd shape
	bbox->x = float(bbox->x)/ai_img_shape->width*src_w;
	bbox->y = float(bbox->y)/ai_img_shape->height*src_h;
	bbox->w = float(bbox->w)/ai_img_shape->width*src_w;
	bbox->h = float(bbox->h)/ai_img_shape->height*src_h;
	get_affine_matrix_for_osd(*bbox);
	
	//1.2 get invert affine matrix
	cv::Mat matrix_dst_inv_osd;
	cv::invert(matrix_dst_for_osd_,matrix_dst_inv_osd);
			
	//2.get net_image for output_shapes
	//frame_size.width
	cv::Mat net_image(model_out_shape->height,model_out_shape->width, CV_8UC4, cv::Scalar(0, 0, 0, 0));
	uint32_t packed_colors[sizeof(color_list_for_osd_pixel) /
	                       sizeof(color_list_for_osd_pixel[0])];
	packed_colors[0] = 0;
	for (size_t i = 1; i < sizeof(packed_colors) / sizeof(packed_colors[0]); ++i)
		memcpy(&packed_colors[i], &color_list_for_osd_pixel[i], sizeof(uint32_t));
	ai_rvv_hwc_argmax_color(
	    p_outputs, model_out_shape->height * model_out_shape->width,
	    model_out_shape->channel, packed_colors,
	    reinterpret_cast<uint32_t*>(net_image.data));

	//3.affine to osd shape
	cv::Mat matrix_for_warp = matrix_dst_inv_osd(cv::Rect(0,0,3,2));
	cv::Mat mask(src_h, src_w, CV_8UC4, cv::Scalar(0, 0, 0, 0));
	cv::warpAffine(net_image, mask, matrix_for_warp, cv::Size(src_w,src_h));
	src_img = src_img + mask;
}
