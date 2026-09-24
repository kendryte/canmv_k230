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
#include <stdio.h>
#include <stdlib.h>
#include <limits.h>
#include <stdint.h>
#include <string.h>
#include "py/compile.h"
#include "py/nlr.h"
#include "py/runtime.h"
#include "py/binary.h"
#include "py/obj.h"
#include "ndarray.h"
#include "ulab.h"
#include "ai_demo.h"
#include "aidemo_type.h"
#include "aidemo_wrap.h"
#include "aidemo_cleanup.h"
#include "aidemo_size.h"

typedef struct {
    float *input;
    float *output;
} aidemo_mask_resize_resource_t;

typedef struct {
    ArrayWrapperMat1 *items;
    int count;
    uint8_t *input;
} aidemo_ocr_resource_t;

typedef struct {
    YoloPoseInfo *items;
    int count;
} aidemo_yolo_pose_resource_t;

static void aidemo_free_mask_resize_resource(void *context)
{
    aidemo_mask_resize_resource_t *resource = context;
    mask_resize_free_output(resource->output);
    resource->output = NULL;
    free(resource->input);
    resource->input = NULL;
}

static void aidemo_free_ocr_resource(void *context)
{
    aidemo_ocr_resource_t *resource = context;
    ocr_rec_free_outputs(resource->items, resource->count);
    resource->items = NULL;
    free(resource->input);
    resource->input = NULL;
}

static void aidemo_free_yolo_pose_resource(void *context)
{
    aidemo_yolo_pose_resource_t *resource = context;
    yolo_pose_free_outputs(resource->items, resource->count);
    resource->items = NULL;
}

static size_t aidemo_image_size_or_raise(FrameSize frame_size, size_t channels)
{
    size_t size;
    if (!aidemo_checked_image_size(frame_size.width, frame_size.height, channels, &size)) {
        mp_raise_ValueError(MP_ERROR_TEXT("invalid image dimensions"));
    }
    return size;
}

static size_t aidemo_keypoint_count_or_raise(int keypoint_count, int keypoint_dimensions)
{
    if (keypoint_count <= 0 || keypoint_dimensions <= 0
        || keypoint_count > INT_MAX / keypoint_dimensions) {
        mp_raise_ValueError(MP_ERROR_TEXT("invalid keypoint dimensions"));
    }

    size_t count = (size_t)keypoint_count * (size_t)keypoint_dimensions;
    if (count > SIZE_MAX / sizeof(float)) {
        mp_raise_ValueError(MP_ERROR_TEXT("keypoint dimensions are too large"));
    }
    return count;
}

static bool aidemo_ndarray_is_contiguous(const ndarray_obj_t *ndarray)
{
    if (ndarray->ndim == 0 || ndarray->ndim > ULAB_MAX_DIMS) {
        return false;
    }

    size_t expected_stride = ndarray->itemsize;
    size_t first_dimension = ULAB_MAX_DIMS - ndarray->ndim;
    for (size_t i = ULAB_MAX_DIMS; i > first_dimension; --i) {
        size_t index = i - 1;
        if (ndarray->shape[index] == 0
            || ndarray->strides[index] < 0
            || (size_t)ndarray->strides[index] != expected_stride
            || expected_stride > SIZE_MAX / ndarray->shape[index]) {
            return false;
        }
        expected_stride *= ndarray->shape[index];
    }
    return true;
}

static ndarray_obj_t *aidemo_require_uint8_array(mp_obj_t object, size_t required_bytes)
{
    if (!mp_obj_is_type(object, &ulab_ndarray_type)) {
        mp_raise_TypeError(MP_ERROR_TEXT("expected uint8 ndarray"));
    }

    ndarray_obj_t *ndarray = MP_OBJ_TO_PTR(object);
    if (ndarray->dtype != NDARRAY_UINT8 || ndarray->itemsize != sizeof(uint8_t)) {
        mp_raise_TypeError(MP_ERROR_TEXT("expected uint8 ndarray"));
    }
    if (!aidemo_ndarray_is_contiguous(ndarray)) {
        mp_raise_ValueError(MP_ERROR_TEXT("ndarray must be contiguous"));
    }
    if (ndarray->array == NULL || ndarray->len < required_bytes) {
        mp_raise_ValueError(MP_ERROR_TEXT("ndarray buffer is too small"));
    }
    return ndarray;
}

STATIC ndarray_obj_t *aidemo_require_ndarray(mp_obj_t obj, uint8_t dtype) {
    if (!mp_obj_is_type(obj, &ulab_ndarray_type)) {
        mp_raise_TypeError(MP_ERROR_TEXT("expected ndarray"));
    }
    ndarray_obj_t *array = MP_OBJ_TO_PTR(obj);
    if (array->dtype != dtype || !aidemo_ndarray_is_contiguous(array)) {
        mp_raise_msg(&mp_type_ValueError, MP_ERROR_TEXT("invalid ndarray dtype or layout"));
    }
    return array;
}

STATIC mp_obj_list_t *aidemo_require_list(mp_obj_t obj, size_t min_len) {
    if (!mp_obj_is_type(obj, &mp_type_list)) {
        mp_raise_TypeError(MP_ERROR_TEXT("expected list"));
    }
    mp_obj_list_t *list = MP_OBJ_TO_PTR(obj);
    if (list->len < min_len) {
        mp_raise_msg(&mp_type_ValueError, MP_ERROR_TEXT("list is too short"));
    }
    return list;
}

STATIC FrameSize aidemo_frame_size_hw(mp_obj_t obj) {
    mp_obj_list_t *shape = aidemo_require_list(obj, 2);
    mp_int_t height = mp_obj_get_int(shape->items[0]);
    mp_int_t width = mp_obj_get_int(shape->items[1]);
    if (height <= 0 || width <= 0) {
        mp_raise_msg(&mp_type_ValueError, MP_ERROR_TEXT("shape values must be positive"));
    }
    if (width > INT_MAX || height > INT_MAX) {
        mp_raise_ValueError(MP_ERROR_TEXT("image dimensions are too large"));
    }
    FrameSize result = {width, height};
    return result;
}

STATIC mp_obj_t aidemo_yolo_det_results_to_list(const YoloDetInfo *outputs,
                                                size_t box_cnt) {
    mp_obj_list_t *result = mp_obj_new_list(3, NULL);
    mp_obj_list_t *boxes = mp_obj_new_list(box_cnt, NULL);
    mp_obj_list_t *ids = mp_obj_new_list(box_cnt, NULL);
    mp_obj_list_t *scores = mp_obj_new_list(box_cnt, NULL);
    result->items[0] = MP_OBJ_FROM_PTR(boxes);
    result->items[1] = MP_OBJ_FROM_PTR(ids);
    result->items[2] = MP_OBJ_FROM_PTR(scores);

    size_t box_shape[4] = {0};
    box_shape[3] = 4;
    for (size_t i = 0; i < box_cnt; ++i) {
        ndarray_obj_t *box =
            ndarray_new_ndarray(1, box_shape, NULL, NDARRAY_INT16);
        int16_t *box_data = (int16_t *)box->array;
        box_data[0] = outputs[i].x;
        box_data[1] = outputs[i].y;
        box_data[2] = outputs[i].w;
        box_data[3] = outputs[i].h;
        boxes->items[i] = MP_OBJ_FROM_PTR(box);
        ids->items[i] = mp_obj_new_int(outputs[i].index);
        scores->items[i] = mp_obj_new_float(outputs[i].confidence);
    }
    return MP_OBJ_FROM_PTR(result);
}

STATIC mp_obj_t aidemo_yolo_obb_results_to_list(const YoloObbInfo *outputs,
                                                size_t box_cnt) {
    mp_obj_list_t *result = mp_obj_new_list(3, NULL);
    mp_obj_list_t *boxes = mp_obj_new_list(box_cnt, NULL);
    mp_obj_list_t *ids = mp_obj_new_list(box_cnt, NULL);
    mp_obj_list_t *scores = mp_obj_new_list(box_cnt, NULL);
    result->items[0] = MP_OBJ_FROM_PTR(boxes);
    result->items[1] = MP_OBJ_FROM_PTR(ids);
    result->items[2] = MP_OBJ_FROM_PTR(scores);

    size_t box_shape[4] = {0};
    box_shape[3] = 8;
    for (size_t i = 0; i < box_cnt; ++i) {
        ndarray_obj_t *box =
            ndarray_new_ndarray(1, box_shape, NULL, NDARRAY_INT16);
        int16_t *box_data = (int16_t *)box->array;
        box_data[0] = outputs[i].x1;
        box_data[1] = outputs[i].y1;
        box_data[2] = outputs[i].x2;
        box_data[3] = outputs[i].y2;
        box_data[4] = outputs[i].x3;
        box_data[5] = outputs[i].y3;
        box_data[6] = outputs[i].x4;
        box_data[7] = outputs[i].y4;
        boxes->items[i] = MP_OBJ_FROM_PTR(box);
        ids->items[i] = mp_obj_new_int(outputs[i].index);
        scores->items[i] = mp_obj_new_float(outputs[i].confidence);
    }
    return MP_OBJ_FROM_PTR(result);
}

STATIC mp_obj_t aidemo_yolo_pose_results_to_list(const YoloPoseInfo *outputs,
                                                 size_t box_cnt, int kp_num,
                                                 int kp_dim) {
    mp_obj_list_t *result = mp_obj_new_list(4, NULL);
    mp_obj_list_t *boxes = mp_obj_new_list(box_cnt, NULL);
    mp_obj_list_t *ids = mp_obj_new_list(box_cnt, NULL);
    mp_obj_list_t *scores = mp_obj_new_list(box_cnt, NULL);
    mp_obj_list_t *keypoints = mp_obj_new_list(box_cnt, NULL);
    result->items[0] = MP_OBJ_FROM_PTR(boxes);
    result->items[1] = MP_OBJ_FROM_PTR(ids);
    result->items[2] = MP_OBJ_FROM_PTR(scores);
    result->items[3] = MP_OBJ_FROM_PTR(keypoints);

    size_t box_shape[4] = {0};
    size_t kps_shape[4] = {0};
    box_shape[3] = 4;
    kps_shape[3] = kp_num * kp_dim;
    for (size_t i = 0; i < box_cnt; ++i) {
        ndarray_obj_t *box =
            ndarray_new_ndarray(1, box_shape, NULL, NDARRAY_INT16);
        int16_t *box_data = (int16_t *)box->array;
        box_data[0] = outputs[i].x;
        box_data[1] = outputs[i].y;
        box_data[2] = outputs[i].w;
        box_data[3] = outputs[i].h;
        boxes->items[i] = MP_OBJ_FROM_PTR(box);
        ids->items[i] = mp_obj_new_int(outputs[i].index);
        scores->items[i] = mp_obj_new_float(outputs[i].confidence);

        ndarray_obj_t *kps =
            ndarray_new_ndarray(1, kps_shape, NULL, NDARRAY_FLOAT);
        memcpy(kps->array, outputs[i].kps,
               sizeof(float) * (size_t)kp_num * (size_t)kp_dim);
        keypoints->items[i] = MP_OBJ_FROM_PTR(kps);
    }
    return MP_OBJ_FROM_PTR(result);
}

//*****************************for cv*****************************
STATIC mp_obj_t aidemo_invert_affine_transform(mp_obj_t matrix_ndarray) 
{
    ndarray_obj_t *matrix = MP_ROM_PTR(matrix_ndarray);
    
    int start_shape_index = ULAB_MAX_DIMS - matrix->ndim;
    if(matrix->ndim==2 && matrix->shape[start_shape_index] == 2 && matrix->shape[start_shape_index+1]==3)
    {   
        char c_dtype = (char)matrix->dtype;
        if(c_dtype == 'f')
        {   
            float* p_matrix = (float*)matrix->array;
            cv_and_ndarray_convert_info info;
            if (!invert_affine_transform(p_matrix, &info)) {
                mp_raise_msg(&mp_type_MemoryError, MP_ERROR_TEXT("affine transform result allocation failed"));
            }
            aidemo_nlr_cleanup_t cleanup;
            aidemo_nlr_cleanup_push(&cleanup, cv_and_ndarray_convert_info_free, &info);
            size_t mp_shape[ULAB_MAX_DIMS] = {0};
            int32_t mp_stride[ULAB_MAX_DIMS] = {0};
            for(int i=0; i<info.ndim_; i++)
            {
                mp_shape[ULAB_MAX_DIMS - 1-i] = (size_t)info.shape_[info.ndim_ - 1 - i];
                mp_stride[ULAB_MAX_DIMS - 1-i] = (int32_t)info.strides_[info.ndim_ - 1 - i];
            }
            ndarray_obj_t *matrix_inv = ndarray_new_ndarray(info.ndim_, mp_shape, mp_stride, info.dtype_);
            hal_rvv_memcpy((void *)matrix_inv->origin, (void *)info.data_, matrix_inv->len * matrix_inv->itemsize);

            aidemo_nlr_cleanup_finish(&cleanup);
            return MP_OBJ_FROM_PTR(matrix_inv);
        }
        else
        {
            nlr_raise(mp_obj_new_exception_msg(&mp_type_AssertionError, MP_ERROR_TEXT("Error: Only float data types are supported in invert_affine_transform")));
        }
    }
    else
    {
        nlr_raise(mp_obj_new_exception_msg(&mp_type_AssertionError, MP_ERROR_TEXT("Error: Assertion failed (rows == 2 && cols == 3) in invert_affine_transform")));
    }
}
STATIC MP_DEFINE_CONST_FUN_OBJ_1(aidemo_invert_affine_transform_obj, aidemo_invert_affine_transform);

STATIC mp_obj_t aidemo_polylines(size_t n_args, const mp_obj_t *args) 
{
    ndarray_obj_t *mp_img = MP_ROM_PTR(args[0]);      //hwc
    cv_and_ndarray_convert_info in_info;    
    in_info.dtype_ = mp_img->dtype;
    in_info.ndim_ = mp_img->ndim;
    in_info.len_ = mp_img->len;
    hal_rvv_memset(in_info.shape_,0,sizeof(size_t)*3);
    for(int i=0; i<mp_img->ndim; i++)
    {
        in_info.shape_[in_info.ndim_ - 1 - i] = mp_img->shape[ULAB_MAX_DIMS - 1-i];
    }
    in_info.data_ = mp_img->array;

    ndarray_obj_t *mp_pts = MP_ROM_PTR(args[1]);      //nx2
    generic_array pts;
    pts.data_ = mp_pts->array;
    pts.length_ = mp_pts->len;          //only int

    bool is_closed = mp_obj_is_true(args[2]);
    ndarray_obj_t *mp_color = MP_OBJ_TO_PTR(args[3]);
    generic_array color;
    color.data_ = mp_color->array;
    color.length_ = mp_color->len;      //only int

    int thickness = 1;
    if (n_args > 4) {
        thickness = mp_obj_get_int(args[4]);
    }

    int line_type = 8;
    if (n_args > 5) {
        line_type = mp_obj_get_int(args[5]);
    }

    int shift = 0;
    if (n_args > 6) {
        shift = mp_obj_get_int(args[6]);
    }

    draw_polylines(&in_info,&pts,is_closed,&color,thickness,line_type,shift);

    return mp_const_none;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(aidemo_polylines_obj, 7, 7, aidemo_polylines);

STATIC mp_obj_t aidemo_contours(size_t n_args, const mp_obj_t *args) 
{
    ndarray_obj_t *mp_img = MP_ROM_PTR(args[0]);      //hwc
    cv_and_ndarray_convert_info in_info;    
    in_info.dtype_ = mp_img->dtype;
    in_info.ndim_ = mp_img->ndim;
    in_info.len_ = mp_img->len;
    hal_rvv_memset(in_info.shape_,0,sizeof(size_t)*3);
    for(int i=0; i<mp_img->ndim; i++)
    {
        in_info.shape_[in_info.ndim_ - 1 - i] = mp_img->shape[ULAB_MAX_DIMS - 1-i];
    }
    in_info.data_ = mp_img->array;

    ndarray_obj_t *mp_pts = MP_ROM_PTR(args[1]);      //nx2
    generic_array pts;
    pts.data_ = mp_pts->array;
    pts.length_ = mp_pts->len;          //only int

    int contour_idx = mp_obj_get_int(args[2]);
    ndarray_obj_t *mp_color = MP_OBJ_TO_PTR(args[3]);
    generic_array color;
    color.data_ = mp_color->array;
    color.length_ = mp_color->len;      //only int

    int thickness = 1;
    if (n_args > 4) {
        thickness = mp_obj_get_int(args[4]);
    }

    int line_type = 8;
    if (n_args > 5) {
        line_type = mp_obj_get_int(args[5]);
    }
    draw_contours(&in_info,&pts,contour_idx,&color,thickness,line_type);
    return mp_const_none;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(aidemo_contours_obj, 6, 6, aidemo_contours);

//*****************************for face det*****************************
STATIC mp_obj_t aidemo_face_det_post_process(size_t n_args, const mp_obj_t *args)
{
    float obj_thresh = mp_obj_get_float(args[0]);
    float nms_thresh = mp_obj_get_float(args[1]);
    int net_len = mp_obj_get_float(args[2]);
    ndarray_obj_t *mp_anchors = MP_ROM_PTR(args[3]);      //hwc
    float *anchors = (float*)mp_anchors->array;
    mp_obj_list_t *ori_shape_list = MP_OBJ_TO_PTR(args[4]);
    FrameSize frame_size;
    frame_size.width = mp_obj_get_int(ori_shape_list->items[0]);
    frame_size.height = mp_obj_get_int(ori_shape_list->items[1]);

    mp_obj_list_t *mp_outputs = MP_OBJ_TO_PTR(args[5]);
    float* p_outputs[9];
    for(int i=0;i<9;++i)
    {
        ndarray_obj_t *array_i = MP_ROM_PTR(mp_outputs->items[i]);
        p_outputs[i] =  (float*)(array_i->array);
    }

    FaceDetectionInfoVector* result = face_detetion_post_process(obj_thresh,nms_thresh,net_len,anchors,&frame_size,p_outputs);
    if (result == NULL) {
        mp_raise_msg(&mp_type_MemoryError, MP_ERROR_TEXT("face detection result allocation failed"));
    }

    aidemo_nlr_cleanup_t cleanup;
    aidemo_nlr_cleanup_push(&cleanup, face_detection_free_outputs, result);
    if (result->vec_len > 0
        && (result->bbox == NULL || result->sparse_kps == NULL || result->score == NULL)) {
        mp_raise_msg(&mp_type_MemoryError, MP_ERROR_TEXT("face detection result allocation failed"));
    }

    mp_obj_list_t *results_mp_list = mp_obj_new_list(0, NULL);
    if(result->vec_len>0)
    {    
        size_t bbox_shape[ULAB_MAX_DIMS] = {0};
        bbox_shape[2] = result->vec_len;
        bbox_shape[3] = sizeof(Bbox) / sizeof(float);
        ndarray_obj_t *bbox_obj = ndarray_new_ndarray(2, bbox_shape, NULL, NDARRAY_FLOAT);
        float *bbox_data = (float *)bbox_obj->array;
        hal_rvv_memcpy(bbox_data,result->bbox,sizeof(Bbox) * result->vec_len);
        mp_obj_list_append(results_mp_list, bbox_obj);

        size_t kps_shape[ULAB_MAX_DIMS] = {0};
        kps_shape[2] = result->vec_len;
        kps_shape[3] = sizeof(SparseLandmarks) / sizeof(float);
        ndarray_obj_t *kps_obj = ndarray_new_ndarray(2, kps_shape, NULL, NDARRAY_FLOAT);
        float *kps_data = (float *)kps_obj->array;
        hal_rvv_memcpy(kps_data,result->sparse_kps,sizeof(SparseLandmarks) * result->vec_len);
        mp_obj_list_append(results_mp_list, kps_obj);

        size_t score_shape[ULAB_MAX_DIMS] = {0};
        score_shape[2] = result->vec_len;
        score_shape[3] = sizeof(float) / sizeof(float);
        ndarray_obj_t *score_obj = ndarray_new_ndarray(2, score_shape, NULL, NDARRAY_FLOAT);
        float *score_data = (float *)score_obj->array;
        hal_rvv_memcpy(score_data,result->score,sizeof(float) * result->vec_len);
        mp_obj_list_append(results_mp_list, score_obj);
    }
    aidemo_nlr_cleanup_finish(&cleanup);
    
    return MP_OBJ_FROM_PTR(results_mp_list);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(aidemo_face_det_post_process_obj, 6, 6, aidemo_face_det_post_process);

//*****************************for face parse*****************************
STATIC mp_obj_t aidemo_face_parse_post_process(size_t n_args, const mp_obj_t *args)
{
    ndarray_obj_t *mp_img = MP_ROM_PTR(args[0]);      //hwc
    cv_and_ndarray_convert_info in_info;   
    in_info.dtype_ = mp_img->dtype;
    in_info.ndim_ = mp_img->ndim;
    in_info.len_ = mp_img->len;
    hal_rvv_memset(in_info.shape_,0,sizeof(size_t)*3);
    for(int i=0; i<mp_img->ndim; i++)
    {
        in_info.shape_[in_info.ndim_ - 1 - i] = mp_img->shape[ULAB_MAX_DIMS - 1-i];
    }
    in_info.data_ = mp_img->array;
    
    mp_obj_list_t *mp_ai_img_shape = MP_OBJ_TO_PTR(args[1]);
    FrameSize ai_img_shape;
    ai_img_shape.width = mp_obj_get_int(mp_ai_img_shape->items[0]);
    ai_img_shape.height = mp_obj_get_int(mp_ai_img_shape->items[1]);

    mp_obj_list_t *mp_osd_img_shape = MP_OBJ_TO_PTR(args[2]);
    FrameSize osd_img_shape;
    osd_img_shape.width = mp_obj_get_int(mp_osd_img_shape->items[0]);
    osd_img_shape.height = mp_obj_get_int(mp_osd_img_shape->items[1]);

    // int net_len = mp_obj_get_int(args[3]);
    int net_len = mp_obj_get_float(args[3]);

    mp_obj_list_t *mp_bbox = MP_OBJ_TO_PTR(args[4]);
    Bbox bbox;
    bbox.x = mp_obj_get_float(mp_bbox->items[0]);
    bbox.y = mp_obj_get_float(mp_bbox->items[1]);
    bbox.w = mp_obj_get_float(mp_bbox->items[2]);
    bbox.h = mp_obj_get_float(mp_bbox->items[3]);

    ndarray_obj_t *mp_outputs = MP_OBJ_TO_PTR(args[5]);
    float* p_outputs;
    p_outputs = (float*)(mp_outputs->array);
    CHWSize model_out_shape;
    model_out_shape.height = mp_outputs->shape[1];
    model_out_shape.width = mp_outputs->shape[2];
    model_out_shape.channel = mp_outputs->shape[3];

    face_parse_post_process(&in_info,&ai_img_shape,&osd_img_shape,net_len,&bbox,&model_out_shape,p_outputs);
    return mp_const_none;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(aidemo_face_parse_post_process_obj, 6, 6, aidemo_face_parse_post_process);

//*****************************for face mesh*****************************
STATIC mp_obj_t aidemo_face_mesh_post_process(mp_obj_t roi, mp_obj_t vertices)
{
    ndarray_obj_t *mp_roi = MP_ROM_PTR(roi);
    float *p_roi = (float*)(mp_roi->array);
    Bbox in_roi;
    in_roi.x = p_roi[0];
    in_roi.y = p_roi[1];
    in_roi.w = p_roi[2];
    in_roi.h = p_roi[3];

    ndarray_obj_t *mp_vertices = MP_ROM_PTR(vertices);
    generic_array in_vertices;
    in_vertices.data_ = mp_vertices->array;
    in_vertices.length_ = mp_vertices->len;
    
    face_mesh_post_process(in_roi,&in_vertices);
    return mp_const_none;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_2(aidemo_face_mesh_post_process_obj, aidemo_face_mesh_post_process);

STATIC mp_obj_t aidemo_face_draw_mesh(mp_obj_t img, mp_obj_t vertices)
{
    ndarray_obj_t *mp_img = MP_ROM_PTR(img);
    cv_and_ndarray_convert_info in_info;    
    in_info.dtype_ = mp_img->dtype;
    in_info.ndim_ = mp_img->ndim;
    in_info.len_ = mp_img->len;
    hal_rvv_memset(in_info.shape_,0,sizeof(size_t)*3);
    for(int i=0; i<mp_img->ndim; i++)
    {
        in_info.shape_[in_info.ndim_ - 1 - i] = mp_img->shape[ULAB_MAX_DIMS - 1-i];
    }
    in_info.data_ = mp_img->array;

    ndarray_obj_t *mp_vertices = MP_ROM_PTR(vertices);      
    generic_array vertices_array;
    vertices_array.data_ = mp_vertices->array;
    vertices_array.length_ = mp_vertices->len;         
    draw_mesh(&in_info, &vertices_array);
    return mp_const_none;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_2(aidemo_face_draw_mesh_obj, aidemo_face_draw_mesh);

//*****************************for ocr rec preprocess*****************************
STATIC mp_obj_t aidemo_mask_resize(mp_obj_t dest_obj, mp_obj_t ori_shape_obj, mp_obj_t tag_shape_obj) {
    ndarray_obj_t *dest_obj_ndarray = aidemo_require_ndarray(dest_obj, NDARRAY_FLOAT);
    float *dest = dest_obj_ndarray->array;
    aidemo_mask_resize_resource_t resources = { .input = NULL, .output = NULL };
    aidemo_nlr_cleanup_t cleanup;
    aidemo_nlr_cleanup_push(&cleanup, aidemo_free_mask_resize_resource, &resources);

    mp_obj_list_t *ori_shape_list = MP_OBJ_TO_PTR(ori_shape_obj);
    mp_obj_list_t *tag_shape_list = MP_OBJ_TO_PTR(tag_shape_obj);
    FrameSize ori_shape;
    FrameSize tag_shape;

    ori_shape.height = mp_obj_get_int(ori_shape_list->items[0]);
    ori_shape.width = mp_obj_get_int(ori_shape_list->items[1]);
    tag_shape.height = mp_obj_get_int(tag_shape_list->items[0]);
    tag_shape.width = mp_obj_get_int(tag_shape_list->items[1]);

    size_t ori_elements = aidemo_image_size_or_raise(ori_shape, 1);
    size_t result_len = aidemo_image_size_or_raise(tag_shape, 1);
    if (dest_obj_ndarray->len < ori_elements) {
        mp_raise_ValueError(MP_ERROR_TEXT("mask input buffer is too small"));
    }

    float* mask =  mask_resize(dest, ori_shape, tag_shape);
    resources.output = mask;
    if (mask == NULL) {
        mp_raise_msg(&mp_type_MemoryError, MP_ERROR_TEXT("mask resize result allocation failed"));
    }

    size_t ndarray_shape[4] = {0};
    ndarray_shape[2] = tag_shape.height;
    ndarray_shape[3] = tag_shape.width;
    ndarray_obj_t *mask_obj = ndarray_new_ndarray(2, ndarray_shape, NULL, NDARRAY_FLOAT);

    float *data = (float *)mask_obj->array;
    hal_rvv_memcpy(data, mask, result_len * sizeof(float));

    aidemo_nlr_cleanup_finish(&cleanup);
    return MP_OBJ_FROM_PTR(mask_obj);
};

STATIC MP_DEFINE_CONST_FUN_OBJ_3(aidemo_mask_resize_obj, aidemo_mask_resize);

STATIC mp_obj_t aidemo_ocr_rec_preprocess(mp_obj_t data_obj, mp_obj_t ori_shape_obj, mp_obj_t boxpoint8_obj) {
    ndarray_obj_t *data_obj_ndarray = aidemo_require_ndarray(data_obj, NDARRAY_UINT8);
    uint8_t *data = data_obj_ndarray->array;

    FrameSize ori_shape = aidemo_frame_size_hw(ori_shape_obj);
    size_t input_size = aidemo_image_size_or_raise(ori_shape, 3);
    if (data_obj_ndarray->len < input_size) {
        mp_raise_msg(&mp_type_ValueError, MP_ERROR_TEXT("OCR image buffer is too small"));
    }

    mp_obj_list_t *boxpoint8_list = aidemo_require_list(boxpoint8_obj, 0);
    if (boxpoint8_list->len > INT_MAX) {
        mp_raise_msg(&mp_type_ValueError, MP_ERROR_TEXT("too many OCR boxes"));
    }
    int box_cnt = boxpoint8_list->len;
    for (int i = 0; i < box_cnt; ++i) {
        ndarray_obj_t *box = aidemo_require_ndarray(boxpoint8_list->items[i], NDARRAY_FLOAT);
        if (box->len < 8) {
            mp_raise_msg(&mp_type_ValueError, MP_ERROR_TEXT("OCR box must contain 8 floats"));
        }
    }
    BoxPoint8 *boxpoint8 = NULL;
    if (box_cnt > 0) {
        boxpoint8 = (BoxPoint8 *)malloc((size_t)box_cnt * sizeof(BoxPoint8));
        if (boxpoint8 == NULL) {
            mp_raise_msg(&mp_type_MemoryError, MP_ERROR_TEXT("Memory allocation failed"));
        }
    }
    for (int i = 0; i < boxpoint8_list->len; i++)
    {
        ndarray_obj_t *boxpoint8_ndarray = MP_OBJ_TO_PTR(boxpoint8_list->items[i]);
        float *boxpoint8_ndarray_tmp = boxpoint8_ndarray->array;
        for (int j = 0; j < 8; j++)
        {
            boxpoint8[i].points8[j] = boxpoint8_ndarray_tmp[j];
        }
    }

    ArrayWrapperMat1 *arrayWrapperMat1  = ocr_rec_pre_process(data, ori_shape, boxpoint8, box_cnt);
    free(boxpoint8);
    if (box_cnt > 0 && arrayWrapperMat1 == NULL) {
        mp_raise_msg(&mp_type_MemoryError, MP_ERROR_TEXT("Memory allocation failed"));
    }

    aidemo_ocr_resource_t resources = {
        .items = arrayWrapperMat1, .count = box_cnt, .input = NULL,
    };
    aidemo_nlr_cleanup_t cleanup;
    aidemo_nlr_cleanup_push(&cleanup, aidemo_free_ocr_resource, &resources);
    mp_obj_list_t *results_mp_list = mp_obj_new_list(2, NULL);
    mp_obj_list_t *results_mp_list_array = mp_obj_new_list(box_cnt, NULL);
    mp_obj_list_t *results_mp_list_points = mp_obj_new_list(box_cnt, NULL);
    results_mp_list->items[0] = MP_OBJ_FROM_PTR(results_mp_list_array);
    results_mp_list->items[1] = MP_OBJ_FROM_PTR(results_mp_list_points);

    for (int i = 0; i < box_cnt; i++)
    {
        size_t ndarray_shape[4];
        ndarray_shape[0] = 1;
        ndarray_shape[1] = 1;
        ndarray_shape[2] = arrayWrapperMat1[i].framesize.height;
        ndarray_shape[3] = arrayWrapperMat1[i].framesize.width;
        ndarray_obj_t *crop_obj = ndarray_new_ndarray(4, ndarray_shape, NULL, NDARRAY_UINT8);
        uint8_t *crop_data = (uint8_t *)crop_obj->array;
        size_t crop_size = (size_t)arrayWrapperMat1[i].framesize.height *
                           arrayWrapperMat1[i].framesize.width;
        hal_rvv_memcpy(crop_data, arrayWrapperMat1[i].data, crop_size);
        results_mp_list_array->items[i] = MP_OBJ_FROM_PTR(crop_obj);

        size_t point_shape[4] = {0};
        point_shape[3] = 8;
        ndarray_obj_t *point_obj = ndarray_new_ndarray(1, point_shape, NULL, NDARRAY_FLOAT);
        float *point_data = (float *)point_obj->array;
        hal_rvv_memcpy(point_data, arrayWrapperMat1[i].coordinates,
                       sizeof(arrayWrapperMat1[i].coordinates));
        results_mp_list_points->items[i] = MP_OBJ_FROM_PTR(point_obj);
        free(arrayWrapperMat1[i].data);
        arrayWrapperMat1[i].data = NULL;
    }
    aidemo_nlr_cleanup_finish(&cleanup);
    return MP_OBJ_FROM_PTR(results_mp_list);
};

STATIC MP_DEFINE_CONST_FUN_OBJ_3(aidemo_ocr_rec_preprocess_obj, aidemo_ocr_rec_preprocess);

//*****************************for licence det*****************************
STATIC mp_obj_t aidemo_licence_det_postprocess(size_t n_args, const mp_obj_t *args) {

    FrameSize frame_size;
    FrameSize kmodel_frame_size;
    float obj_thresh;
    float nms_thresh;
    int box_cnt;

    mp_obj_list_t *p_outputs_list = MP_OBJ_TO_PTR(args[0]);
    ndarray_obj_t *p_outputs_0_ndarray = MP_ROM_PTR(p_outputs_list->items[0]);
    float *p_outputs_0 = p_outputs_0_ndarray->array;

    ndarray_obj_t *p_outputs_1_ndarray = MP_ROM_PTR(p_outputs_list->items[1]);
    float *p_outputs_1 = p_outputs_1_ndarray->array;

    ndarray_obj_t *p_outputs_2_ndarray = MP_ROM_PTR(p_outputs_list->items[2]);
    float *p_outputs_2 = p_outputs_2_ndarray->array;

    ndarray_obj_t *p_outputs_3_ndarray = MP_ROM_PTR(p_outputs_list->items[3]);
    float *p_outputs_3 = p_outputs_3_ndarray->array;

    ndarray_obj_t *p_outputs_4_ndarray = MP_ROM_PTR(p_outputs_list->items[4]);
    float *p_outputs_4 = p_outputs_4_ndarray->array;

    ndarray_obj_t *p_outputs_5_ndarray = MP_ROM_PTR(p_outputs_list->items[5]);
    float *p_outputs_5 = p_outputs_5_ndarray->array;

    ndarray_obj_t *p_outputs_6_ndarray = MP_ROM_PTR(p_outputs_list->items[6]);
    float *p_outputs_6= p_outputs_6_ndarray->array;

    ndarray_obj_t *p_outputs_7_ndarray = MP_ROM_PTR(p_outputs_list->items[7]);
    float *p_outputs_7 = p_outputs_7_ndarray->array;

    ndarray_obj_t *p_outputs_8_ndarray = MP_ROM_PTR(p_outputs_list->items[8]);
    float *p_outputs_8 = p_outputs_8_ndarray->array;


    mp_obj_list_t *frame_size_list = MP_OBJ_TO_PTR(args[1]);
    frame_size.height = mp_obj_get_int(frame_size_list->items[0]);
    frame_size.width = mp_obj_get_int(frame_size_list->items[1]);

    mp_obj_list_t *kmodel_frame_size_list = MP_OBJ_TO_PTR(args[2]);
    kmodel_frame_size.height = mp_obj_get_int(kmodel_frame_size_list->items[0]);
    kmodel_frame_size.width = mp_obj_get_int(kmodel_frame_size_list->items[1]);

    obj_thresh = mp_obj_get_float(args[3]);
    nms_thresh = mp_obj_get_float(args[4]);

    BoxPoint8* boxPoint8 =  licence_det_post_process(p_outputs_0, p_outputs_1, p_outputs_2, p_outputs_3, p_outputs_4, p_outputs_5, p_outputs_6, p_outputs_7, p_outputs_8, frame_size, kmodel_frame_size, obj_thresh, nms_thresh, &box_cnt);
    if (box_cnt < 0 || (box_cnt > 0 && boxPoint8 == NULL)) {
        mp_raise_msg(&mp_type_MemoryError, MP_ERROR_TEXT("licence detection result allocation failed"));
    }

    aidemo_nlr_cleanup_t cleanup;
    aidemo_nlr_cleanup_push(&cleanup, licence_det_free_outputs, boxPoint8);

    mp_obj_list_t *results_mp_list = mp_obj_new_list(box_cnt, NULL);
    size_t ndarray_shape[4];
    ndarray_shape[3] = 8;
    for (int i = 0; i < box_cnt; i++)
    {
        ndarray_obj_t *point_obj = ndarray_new_ndarray(1, ndarray_shape, NULL, NDARRAY_FLOAT);
        float *point_data = (float *)point_obj->array;
        for (int j = 0; j < 8; j++)
        {
            point_data[j] =  boxPoint8[i].points8[j];
        }
        results_mp_list->items[i] = MP_OBJ_FROM_PTR(point_obj);
    }

    aidemo_nlr_cleanup_finish(&cleanup);
    return MP_OBJ_FROM_PTR(results_mp_list);
};

STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(aidemo_licence_det_postprocess_obj, 5, 5, aidemo_licence_det_postprocess);

//*****************************for object segment*****************************
static bool aidemo_seg_outputs_are_valid(const SegOutputs *seg_outputs,
                                         int box_cnt,
                                         size_t masks_size)
{
    if (box_cnt < 0) {
        return false;
    }

    if (masks_size != 0 && seg_outputs->masks_results == NULL) {
        return false;
    }

    return box_cnt == 0 || seg_outputs->segOutput != NULL;
}

static mp_obj_t aidemo_seg_outputs_to_mp(SegOutputs *seg_outputs,
                                         int box_cnt,
                                         size_t masks_size,
                                         uint8_t *masks_results_data)
{
    mp_obj_list_t *results_mp_list = mp_obj_new_list(0, NULL);
    mp_obj_list_t *results_mp_list_boxes = mp_obj_new_list(0, NULL);
    mp_obj_list_t *results_mp_list_ids = mp_obj_new_list(0, NULL);
    mp_obj_list_t *results_mp_list_scores = mp_obj_new_list(0, NULL);

    if (masks_size != 0) {
        hal_rvv_memcpy(masks_results_data, seg_outputs->masks_results, masks_size);
    }

    size_t ndarray_shape_box[4] = {0, 0, 0, 4};
    for (int i = 0; i < box_cnt; i++) {
        ndarray_obj_t *box_obj = ndarray_new_ndarray(1, ndarray_shape_box, NULL, NDARRAY_INT16);
        int16_t *box_data = (int16_t *)box_obj->array;
        for (int j = 0; j < 4; j++) {
            box_data[j] = seg_outputs->segOutput[i].box[j];
        }
        mp_obj_list_append(results_mp_list_boxes, box_obj);
        mp_obj_list_append(results_mp_list_ids, mp_obj_new_int(seg_outputs->segOutput[i].id));
        mp_obj_list_append(results_mp_list_scores, mp_obj_new_float(seg_outputs->segOutput[i].confidence));
    }
    mp_obj_list_append(results_mp_list, results_mp_list_boxes);
    mp_obj_list_append(results_mp_list, results_mp_list_ids);
    mp_obj_list_append(results_mp_list, results_mp_list_scores);

    return MP_OBJ_FROM_PTR(results_mp_list);
}

STATIC mp_obj_t aidemo_segment_postprocess(size_t n_args, const mp_obj_t *args) {

    mp_obj_list_t *p_outputs_list = aidemo_require_list(args[0], 2);
    ndarray_obj_t *p_outputs_0_ndarray = aidemo_require_ndarray(p_outputs_list->items[0], NDARRAY_FLOAT);
    float *data_0 = p_outputs_0_ndarray->array;
    
    ndarray_obj_t *p_outputs_1_ndarray = aidemo_require_ndarray(p_outputs_list->items[1], NDARRAY_FLOAT);
    float *data_1 = p_outputs_1_ndarray->array;

    FrameSize frame_size;
    FrameSize kmodel_frame_size;
    FrameSize display_frame_size;
    float conf_thres;
    float nms_thres;
    float mask_thres;
    int box_cnt;

    frame_size = aidemo_frame_size_hw(args[1]);
    kmodel_frame_size = aidemo_frame_size_hw(args[2]);
    display_frame_size = aidemo_frame_size_hw(args[3]);

    conf_thres = mp_obj_get_float(args[4]);
    nms_thres = mp_obj_get_float(args[5]);
    mask_thres = mp_obj_get_float(args[6]);

    size_t masks_size = aidemo_image_size_or_raise(display_frame_size, 4);
    ndarray_obj_t *masks_results =
        aidemo_require_uint8_array(args[7], masks_size);
    uint8_t *masks_results_data = (uint8_t *)masks_results->array;

    SegOutputs segOutputs = object_seg_post_process_into(data_0, data_1, frame_size, kmodel_frame_size, display_frame_size, conf_thres, nms_thres, mask_thres, &box_cnt, masks_results_data);
    bool valid_output = aidemo_seg_outputs_are_valid(&segOutputs, box_cnt, masks_size);
    segOutputs.masks_results = NULL;  // The ndarray owns the borrowed mask.
    if (!valid_output) {
        object_seg_free_outputs(&segOutputs);
        mp_raise_msg(&mp_type_MemoryError, MP_ERROR_TEXT("segmentation result allocation failed"));
    }

    aidemo_nlr_cleanup_t cleanup;
    aidemo_nlr_cleanup_push(&cleanup, object_seg_free_outputs, &segOutputs);
    mp_obj_t result = aidemo_seg_outputs_to_mp(&segOutputs, box_cnt, 0, masks_results_data);
    aidemo_nlr_cleanup_finish(&cleanup);
    return result;
};

STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(aidemo_segment_postprocess_obj, 8, 8, aidemo_segment_postprocess);

//*****************************for person kp det*****************************
STATIC mp_obj_t aidemo_person_kp_postprocess(size_t n_args, const mp_obj_t *args) {

    ndarray_obj_t *p_outputs_ndarray = MP_ROM_PTR(args[0]);
    float *data = p_outputs_ndarray->array;
    

    FrameSize frame_size;
    FrameSize kmodel_frame_size;
    float obj_thresh;
    float nms_thresh;
    int box_cnt;

    mp_obj_list_t *frame_size_list = MP_OBJ_TO_PTR(args[1]);
    frame_size.height = mp_obj_get_int(frame_size_list->items[0]);
    frame_size.width = mp_obj_get_int(frame_size_list->items[1]);

    mp_obj_list_t *kmodel_frame_size_list = MP_OBJ_TO_PTR(args[2]);
    kmodel_frame_size.height = mp_obj_get_int(kmodel_frame_size_list->items[0]);
    kmodel_frame_size.width = mp_obj_get_int(kmodel_frame_size_list->items[1]);

    obj_thresh = mp_obj_get_float(args[3]);
    nms_thresh = mp_obj_get_float(args[4]);

    PersonKPOutput* personKPOutput = person_kp_postprocess(data, frame_size, kmodel_frame_size, obj_thresh, nms_thresh, &box_cnt);
    if (box_cnt < 0 || (box_cnt > 0 && personKPOutput == NULL)) {
        mp_raise_msg(&mp_type_MemoryError, MP_ERROR_TEXT("person keypoint result allocation failed"));
    }

    aidemo_nlr_cleanup_t cleanup;
    aidemo_nlr_cleanup_push(&cleanup, person_kp_free_outputs, personKPOutput);

    mp_obj_list_t *results_mp_list = mp_obj_new_list(3, NULL);
    mp_obj_list_t *results_mp_list_boxes = mp_obj_new_list(box_cnt, NULL);
    mp_obj_list_t *results_mp_list_kpses = mp_obj_new_list(box_cnt, NULL);
    mp_obj_list_t *results_mp_list_confidences = mp_obj_new_list(box_cnt, NULL);
    results_mp_list->items[0] = MP_OBJ_FROM_PTR(results_mp_list_boxes);
    results_mp_list->items[1] = MP_OBJ_FROM_PTR(results_mp_list_kpses);
    results_mp_list->items[2] = MP_OBJ_FROM_PTR(results_mp_list_confidences);

    size_t ndarray_shape_box[4];
    ndarray_shape_box[3] = 4;
    size_t ndarray_shape_kps[4];
    ndarray_shape_kps[2] = 17;
    ndarray_shape_kps[3] = 3;
    for (int i = 0; i < box_cnt; i++)
    {
        ndarray_obj_t *box_obj = ndarray_new_ndarray(1, ndarray_shape_box, NULL, NDARRAY_INT16);
        int16_t *box_data = (int16_t *)box_obj->array;
        for (int j = 0; j < 4; j++)
        {
            box_data[j] = personKPOutput[i].box[j];
        }

        ndarray_obj_t *kps_obj = ndarray_new_ndarray(2, ndarray_shape_kps, NULL, NDARRAY_FLOAT);
        float *kps_data = (float *)kps_obj->array;
        for (int j = 0; j < 17; j++)
        {
            for (int k = 0; k < 3; k++)
            {
                kps_data[j * 3 + k] = personKPOutput[i].kps[j][k];
            }
        }

        results_mp_list_boxes->items[i] = MP_OBJ_FROM_PTR(box_obj);
        results_mp_list_kpses->items[i] = MP_OBJ_FROM_PTR(kps_obj);
        results_mp_list_confidences->items[i] =
            mp_obj_new_float(personKPOutput[i].confidence);
    }


    aidemo_nlr_cleanup_finish(&cleanup);
    return MP_OBJ_FROM_PTR(results_mp_list);
};

STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(aidemo_person_kp_postprocess_obj, 5, 5, aidemo_person_kp_postprocess);

//*****************************for kws*****************************
STATIC mp_obj_t kws_feature_pipeline_create() {
    feature_pipeline* fp=feature_pipeline_create();
    if (fp == NULL) {
        mp_raise_msg(&mp_type_MemoryError, MP_ERROR_TEXT("Memory allocation failed"));
    }
    return MP_OBJ_FROM_PTR(fp);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_0(aidemo_kws_feature_pipeline_create_obj, kws_feature_pipeline_create);

STATIC mp_obj_t kws_feature_pipeline_destroy(mp_obj_t fp) {
    feature_pipeline *fp_ = MP_OBJ_TO_PTR(fp);
    release_preprocess_class(fp_);
    return mp_const_none;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_1(aidemo_kws_feature_pipeline_destroy_obj, kws_feature_pipeline_destroy);

STATIC mp_obj_t kws_preprocess(mp_obj_t fp,mp_obj_t wav_obj) {
    mp_obj_list_t *wav_list;
    size_t wav_length;
    size_t feats_length = 1 * 30 * 40;

    if (!mp_obj_is_type(wav_obj, &mp_type_list)) {
        mp_raise_msg(&mp_type_ValueError, MP_ERROR_TEXT("Invalid input"));
    }

    wav_list = MP_OBJ_TO_PTR(wav_obj);
    wav_length = wav_list->len;

    // 检查输入参数是否合法
    if (wav_length <= 0) {
        mp_raise_msg(&mp_type_ValueError, MP_ERROR_TEXT("Invalid input"));
        return mp_const_none;
    }
    // 分配内存来存储 wav 数组
    float* wav = (float *)malloc(wav_length * sizeof(float));
    if (wav == NULL) {
        mp_raise_msg(&mp_type_MemoryError, MP_ERROR_TEXT("Memory allocation failed"));
        return mp_const_none;
    }

    aidemo_malloc_pair_t resources = { .first = wav, .second = NULL };
    aidemo_nlr_cleanup_t cleanup;
    aidemo_nlr_cleanup_push(&cleanup, aidemo_free_malloc_pair, &resources);
    // 将 MicroPython 的列表转换为 C 数组
    for (size_t i = 0; i < wav_length; i++) {
        wav[i] =  mp_obj_get_float(wav_list->items[i]);
    }
    // 调用 C++ 函数
    feature_pipeline *fp_ = MP_OBJ_TO_PTR(fp);
    float *final_feats = (float *)malloc(feats_length * sizeof(float));
    resources.second = final_feats;
    if (final_feats == NULL) {
        mp_raise_msg(&mp_type_MemoryError, MP_ERROR_TEXT("Memory allocation failed"));
        return mp_const_none;
    }
    if (!wav_preprocess(fp_, wav, wav_length, final_feats)) {
        mp_raise_ValueError(MP_ERROR_TEXT("Insufficient audio data"));
    }
    // 释放 wav 数组内存
    free(wav);
    resources.first = NULL;
    // 创建 MicroPython 浮点数数组对象
    mp_obj_list_t *floats_array = mp_obj_new_list(feats_length, NULL);
    // 将 C++ 函数的浮点数数据逐个转换并存储在 MicroPython 浮点数数组中
    for (size_t i = 0; i < feats_length; i++) {
        floats_array->items[i] = mp_obj_new_float(final_feats[i]);
    }
    // 释放new的feats
    free(final_feats);
    resources.second = NULL;
    // 创建结果列表
    mp_obj_list_t *result = mp_obj_new_list(0, NULL);
    mp_obj_list_append(result, floats_array);
    mp_obj_list_append(result, MP_OBJ_NEW_SMALL_INT(feats_length));
    aidemo_nlr_cleanup_finish(&cleanup);
    return MP_OBJ_FROM_PTR(result);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_2(aidemo_kws_preprocess_obj, kws_preprocess);

STATIC mp_obj_t aidemo_eye_gaze_post_process(mp_obj_t outputs) 
{
    mp_obj_list_t *mp_outputs = MP_OBJ_TO_PTR(outputs);
    float* p_outputs[2];
    for(int i=0;i<2;++i)
    {
        ndarray_obj_t *array_i = MP_ROM_PTR(mp_outputs->items[i]);
        p_outputs[i] =  (float*)(array_i->array);
    }

    float pitch = 0,yaw = 0;
    eye_gaze_post_process(p_outputs,&pitch,&yaw);

    mp_obj_list_t *reuslts_mp_list = mp_obj_new_list(2, NULL);
    reuslts_mp_list->items[0] = mp_obj_new_float(pitch);
    reuslts_mp_list->items[1] = mp_obj_new_float(yaw);

    return MP_OBJ_FROM_PTR(reuslts_mp_list);
};
STATIC MP_DEFINE_CONST_FUN_OBJ_1(aidemo_eye_gaze_post_process_obj, aidemo_eye_gaze_post_process);

//*****************************for nanotracker*****************************
STATIC mp_obj_t aidemo_nanotracker_postprocess(size_t n_args, const mp_obj_t *args) {
    if (!mp_obj_is_type(args[0], &ulab_ndarray_type) ||
        !mp_obj_is_type(args[1], &ulab_ndarray_type)) {
        mp_raise_msg(&mp_type_TypeError, MP_ERROR_TEXT("outputs must be ndarrays"));
    }
    ndarray_obj_t *p_outputs_ndarray_0 = MP_ROM_PTR(args[0]);
    ndarray_obj_t *p_outputs_ndarray_1 = MP_ROM_PTR(args[1]);
    if (p_outputs_ndarray_0->dtype != NDARRAY_FLOAT ||
        p_outputs_ndarray_1->dtype != NDARRAY_FLOAT ||
        p_outputs_ndarray_0->len != 2 * 16 * 16 ||
        p_outputs_ndarray_1->len != 4 * 16 * 16 ||
        p_outputs_ndarray_0->ndim != 4 ||
        p_outputs_ndarray_1->ndim != 4 ||
        p_outputs_ndarray_0->shape[0] != 1 ||
        p_outputs_ndarray_0->shape[1] != 2 ||
        p_outputs_ndarray_0->shape[2] != 16 ||
        p_outputs_ndarray_0->shape[3] != 16 ||
        p_outputs_ndarray_1->shape[0] != 1 ||
        p_outputs_ndarray_1->shape[1] != 4 ||
        p_outputs_ndarray_1->shape[2] != 16 ||
        p_outputs_ndarray_1->shape[3] != 16 ||
        !ndarray_is_dense(p_outputs_ndarray_0) ||
        !ndarray_is_dense(p_outputs_ndarray_1)) {
        mp_raise_msg(&mp_type_ValueError, MP_ERROR_TEXT("invalid NanoTracker outputs"));
    }
    float *data_0 = p_outputs_ndarray_0->array;
    float *data_1 = p_outputs_ndarray_1->array;

    if (!mp_obj_is_type(args[2], &mp_type_list) ||
        !mp_obj_is_type(args[4], &mp_type_list)) {
        mp_raise_msg(&mp_type_TypeError, MP_ERROR_TEXT("sizes must be lists"));
    }
    FrameSize sensor_size;
    mp_obj_list_t *sensor_size_list = MP_OBJ_TO_PTR(args[2]);
    mp_obj_list_t *center_xy_wh_list = MP_OBJ_TO_PTR(args[4]);
    if (sensor_size_list->len < 2 || center_xy_wh_list->len < 4) {
        mp_raise_msg(&mp_type_ValueError, MP_ERROR_TEXT("invalid NanoTracker state"));
    }
    sensor_size.height = mp_obj_get_int(sensor_size_list->items[0]);
    sensor_size.width = mp_obj_get_int(sensor_size_list->items[1]);

    float obj_thresh;
    obj_thresh = mp_obj_get_float(args[3]);

    float center_xy_wh[4];
    center_xy_wh[0] = mp_obj_get_float(center_xy_wh_list->items[0]);
    center_xy_wh[1] = mp_obj_get_float(center_xy_wh_list->items[1]);
    center_xy_wh[2] = mp_obj_get_float(center_xy_wh_list->items[2]);
    center_xy_wh[3] = mp_obj_get_float(center_xy_wh_list->items[3]);

    int crop_size;
    crop_size = mp_obj_get_int(args[5]);

    float CONTEXT_AMOUNT;
    CONTEXT_AMOUNT = mp_obj_get_float(args[6]);
    if (sensor_size.width <= 0 || sensor_size.height <= 0 || crop_size <= 0 ||
        center_xy_wh[2] <= 0.0f || center_xy_wh[3] <= 0.0f ||
        CONTEXT_AMOUNT < 0.0f) {
        mp_raise_msg(&mp_type_ValueError, MP_ERROR_TEXT("invalid NanoTracker arguments"));
    }

    Tracker_box_center tracker_box_center;
    if (n_args == 8) {
        float scale_z = mp_obj_get_float(args[7]);
        if (!(scale_z > 0.0f)) {
            mp_raise_msg(&mp_type_ValueError, MP_ERROR_TEXT("invalid NanoTracker scale"));
        }
        tracker_box_center = nanotracker_post_process_with_scale(
            data_0, data_1, sensor_size, obj_thresh, center_xy_wh,
            crop_size, CONTEXT_AMOUNT, scale_z);
    } else {
        tracker_box_center = nanotracker_post_process(
            data_0, data_1, sensor_size, obj_thresh, center_xy_wh,
            crop_size, CONTEXT_AMOUNT);
    }

    mp_obj_list_t *results_mp_list = mp_obj_new_list(2, NULL);
    const size_t box_len = tracker_box_center.exist ? 5 : 0;
    const size_t center_len = tracker_box_center.exist ? 4 : 0;
    mp_obj_list_t *results_mp_list_box = mp_obj_new_list(box_len, NULL);
    mp_obj_list_t *results_mp_list_center =
        mp_obj_new_list(center_len, NULL);
    results_mp_list->items[0] = MP_OBJ_FROM_PTR(results_mp_list_box);
    results_mp_list->items[1] = MP_OBJ_FROM_PTR(results_mp_list_center);

    if (tracker_box_center.exist)
    {
        results_mp_list_box->items[0] = mp_obj_new_int(tracker_box_center.tracker_box.x);
        results_mp_list_box->items[1] = mp_obj_new_int(tracker_box_center.tracker_box.y);
        results_mp_list_box->items[2] = mp_obj_new_int(tracker_box_center.tracker_box.w);
        results_mp_list_box->items[3] = mp_obj_new_int(tracker_box_center.tracker_box.h);
        results_mp_list_box->items[4] = mp_obj_new_float(tracker_box_center.tracker_box.score);

        results_mp_list_center->items[0] = mp_obj_new_float(tracker_box_center.center_xy_wh[0]);
        results_mp_list_center->items[1] = mp_obj_new_float(tracker_box_center.center_xy_wh[1]);
        results_mp_list_center->items[2] = mp_obj_new_float(tracker_box_center.center_xy_wh[2]);
        results_mp_list_center->items[3] = mp_obj_new_float(tracker_box_center.center_xy_wh[3]);
    }

    return MP_OBJ_FROM_PTR(results_mp_list);
};

STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(aidemo_nanotracker_postprocess_obj, 7, 8, aidemo_nanotracker_postprocess);

//*****************************for tts_zh*****************************
STATIC mp_obj_t tts_zh_create(mp_obj_t dictfile,mp_obj_t phasefile,mp_obj_t mapfile) {
    const char* dictfile_=mp_obj_str_get_str(dictfile);
    const char* phasefile_=mp_obj_str_get_str(phasefile);
    const char* mapfile_=mp_obj_str_get_str(mapfile);
    TtsZh *ttszh_=ttszh_create();
    if (ttszh_ == NULL) {
        mp_raise_msg(&mp_type_MemoryError, MP_ERROR_TEXT("TTS creation failed"));
    }
    if (!ttszh_init_safe(ttszh_,dictfile_,phasefile_,mapfile_)) {
        ttszh_destroy(ttszh_);
        mp_raise_msg(&mp_type_ValueError, MP_ERROR_TEXT("TTS initialization failed"));
    }
    return MP_OBJ_FROM_PTR(ttszh_);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_3(aidemo_tts_zh_create_obj, tts_zh_create);

STATIC mp_obj_t tts_zh_destroy(mp_obj_t ttszh) {
    TtsZh *ttszh_ = MP_OBJ_TO_PTR(ttszh);
    ttszh_destroy(ttszh_);
    return mp_const_none;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_1(aidemo_tts_zh_destroy_obj, tts_zh_destroy);

STATIC mp_obj_t tts_zh_preprocess(mp_obj_t ttszh,mp_obj_t text) {
    TtsZh* ttszh_=MP_OBJ_TO_PTR(ttszh);
    const char* text_=mp_obj_str_get_str(text);
    TtsZhOutput* tts_zh_out=tts_zh_frontend_preprocess(ttszh_,text_); 
    if (tts_zh_out == NULL) {
        mp_raise_msg(&mp_type_MemoryError, MP_ERROR_TEXT("TTS preprocessing allocation failed"));
    }

    aidemo_nlr_cleanup_t cleanup;
    aidemo_nlr_cleanup_push(&cleanup, tts_zh_free_output, tts_zh_out);
    mp_obj_list_t *result_mp_list=mp_obj_new_list(0, NULL);
    // 创建 MicroPython 浮点数数组对象
    mp_obj_list_t *floats_array = mp_obj_new_list(0, NULL);
    mp_obj_list_t *int_array = mp_obj_new_list(0, NULL);
    // 将 C++ 函数的浮点数数据逐个转换并存储在 MicroPython 浮点数数组中
    for (size_t i = 0; i < tts_zh_out->size; i++) {
        mp_obj_list_append(floats_array, mp_obj_new_float(tts_zh_out->data[i]));
    }
    for (size_t i = 0; i < tts_zh_out->len_size; i++) {
        mp_obj_list_append(int_array, mp_obj_new_float(tts_zh_out->len_data[i]));
    }
    mp_obj_list_append(result_mp_list,floats_array);
    mp_obj_list_append(result_mp_list,int_array);
    aidemo_nlr_cleanup_finish(&cleanup);
    return MP_OBJ_FROM_PTR(result_mp_list);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_2(aidemo_tts_zh_preprocess_obj, tts_zh_preprocess);


STATIC mp_obj_t save_wav(size_t n_args, const mp_obj_t *args){
    if (!mp_obj_is_type(args[0], &mp_type_list)) {
        mp_raise_TypeError(MP_ERROR_TEXT("wav must be a list"));
    }
    mp_obj_list_t *wav_list = MP_OBJ_TO_PTR(args[0]);
    mp_int_t wav_length_int = mp_obj_get_int(args[1]);
    const char* wav_path=mp_obj_str_get_str(args[2]);
    mp_int_t sample_rate_int = mp_obj_get_int(args[3]);
    if (wav_length_int <= 0 || (size_t)wav_length_int > wav_list->len ||
        sample_rate_int <= 0 || (size_t)wav_length_int > SIZE_MAX / sizeof(float)) {
        mp_raise_msg(&mp_type_ValueError, MP_ERROR_TEXT("Invalid input"));
    }
    size_t wav_length = (size_t)wav_length_int;
    size_t sample_rate_ = (size_t)sample_rate_int;
    float* wav = (float *)malloc(wav_length * sizeof(float));
    if (wav == NULL) {
        mp_raise_msg(&mp_type_MemoryError, MP_ERROR_TEXT("Memory allocation failed"));
        return mp_const_none;
    }

    aidemo_malloc_resource_t wav_resource = { .ptr = wav };
    aidemo_nlr_cleanup_t cleanup;
    aidemo_nlr_cleanup_push(&cleanup, aidemo_free_malloc_resource, &wav_resource);
    // 将 MicroPython 的列表转换为 C 数组
    for (size_t i = 0; i < wav_length; i++) {
        wav[i] =  mp_obj_get_float(wav_list->items[i]);
    }
    tts_save_wav(wav,wav_length,wav_path,sample_rate_);
    aidemo_nlr_cleanup_finish(&cleanup);
    return mp_const_none;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(aidemo_save_wav_obj, 4, 4, save_wav);

//***********************************for body seg ******************/
STATIC mp_obj_t aidemo_body_seg_postprocess(size_t n_args, const mp_obj_t *args) {
    ndarray_obj_t *data_mp = aidemo_require_ndarray(args[0], NDARRAY_FLOAT);
    float *data = data_mp->array;
    int num_class = mp_obj_get_int(args[1]);
    FrameSize ori_shape = aidemo_frame_size_hw(args[2]);
    FrameSize dst_shape = aidemo_frame_size_hw(args[3]);

    ndarray_obj_t *data_1_mp=aidemo_require_ndarray(args[4], NDARRAY_UINT8);
    uint8_t *data_1=data_1_mp->array;
    if (num_class <= 0 || (size_t)num_class > SIZE_MAX / 4 ||
        data_1_mp->len < (size_t)num_class * 4) {
        mp_raise_msg(&mp_type_ValueError, MP_ERROR_TEXT("invalid class count or color buffer"));
    }
    size_t pixels = aidemo_image_size_or_raise(ori_shape, 1);
    (void)aidemo_image_size_or_raise(dst_shape, 4);
    if (pixels > SIZE_MAX / (size_t)num_class ||
        data_mp->len < pixels * (size_t)num_class) {
        mp_raise_ValueError(MP_ERROR_TEXT("segmentation input buffer is too small"));
    }

    size_t ndarray_shape[4] = {0};
    ndarray_shape[1] = dst_shape.height;
    ndarray_shape[2] = dst_shape.width;
    ndarray_shape[3] = 4;
    ndarray_obj_t *result_obj = ndarray_new_ndarray(3, ndarray_shape, NULL, NDARRAY_UINT8);

    uint8_t *result_data = (uint8_t *)result_obj->array;
    if (!body_seg_postprocess_into(data, num_class, ori_shape, dst_shape,
                                   data_1, result_data)) {
        mp_raise_msg(&mp_type_MemoryError,
                     MP_ERROR_TEXT("Body segmentation postprocess failed"));
    }
    return MP_OBJ_FROM_PTR(result_obj);
}

STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(aidemo_body_seg_postprocess_obj, 5, 5, aidemo_body_seg_postprocess);

//***********************************for yolo seg ******************/
STATIC mp_obj_t aidemo_yolov5_seg_postprocess(size_t n_args, const mp_obj_t *args) {
    ndarray_obj_t *data_mp_0 = aidemo_require_ndarray(args[0], NDARRAY_FLOAT);
    float *output0 = data_mp_0->array;

    ndarray_obj_t *data_mp_1 = aidemo_require_ndarray(args[1], NDARRAY_FLOAT);
    float *output1 = data_mp_1->array;

    int num_class = mp_obj_get_int(args[5]);
    if (num_class <= 0) mp_raise_msg(&mp_type_ValueError, MP_ERROR_TEXT("num_class must be positive"));

    float conf_thresh=mp_obj_get_float(args[6]);
    float nms_thresh=mp_obj_get_float(args[7]);
    float mask_thresh=mp_obj_get_float(args[8]);

    FrameSize frame_shape = aidemo_frame_size_hw(args[2]);
    FrameSize input_shape = aidemo_frame_size_hw(args[3]);
    FrameSize display_shape = aidemo_frame_size_hw(args[4]);

    int box_cnt;
    size_t masks_size = aidemo_image_size_or_raise(display_shape, 4);
    ndarray_obj_t *masks_results =
        aidemo_require_uint8_array(args[9], masks_size);
    uint8_t *masks_results_data = (uint8_t *)masks_results->array;

    SegOutputs segOutputs = yolov5_seg_postprocess_into(output0, output1, frame_shape, input_shape, display_shape,num_class, conf_thresh,nms_thresh,mask_thresh,&box_cnt, masks_results_data);
    bool valid_output = aidemo_seg_outputs_are_valid(&segOutputs, box_cnt, masks_size);
    segOutputs.masks_results = NULL;  // The ndarray owns the borrowed mask.
    if (!valid_output) {
        yolo_seg_free_outputs(&segOutputs);
        mp_raise_msg(&mp_type_MemoryError, MP_ERROR_TEXT("segmentation result allocation failed"));
    }

    aidemo_nlr_cleanup_t cleanup;
    aidemo_nlr_cleanup_push(&cleanup, yolo_seg_free_outputs, &segOutputs);
    mp_obj_t result = aidemo_seg_outputs_to_mp(&segOutputs, box_cnt, 0, masks_results_data);
    aidemo_nlr_cleanup_finish(&cleanup);
    return result;
}

STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(aidemo_yolov5_seg_postprocess_obj, 10, 10, aidemo_yolov5_seg_postprocess);


//***********************************for yolo seg ******************/
STATIC mp_obj_t aidemo_yolov8_seg_postprocess(size_t n_args, const mp_obj_t *args) {
    ndarray_obj_t *data_mp_0 = aidemo_require_ndarray(args[0], NDARRAY_FLOAT);
    float *output0 = data_mp_0->array;

    ndarray_obj_t *data_mp_1 = aidemo_require_ndarray(args[1], NDARRAY_FLOAT);
    float *output1 = data_mp_1->array;

    int num_class = mp_obj_get_int(args[5]);
    if (num_class <= 0) mp_raise_msg(&mp_type_ValueError, MP_ERROR_TEXT("num_class must be positive"));

    float conf_thresh=mp_obj_get_float(args[6]);
    float nms_thresh=mp_obj_get_float(args[7]);
    float mask_thresh=mp_obj_get_float(args[8]);

    FrameSize frame_shape = aidemo_frame_size_hw(args[2]);
    FrameSize input_shape = aidemo_frame_size_hw(args[3]);
    FrameSize display_shape = aidemo_frame_size_hw(args[4]);

    int box_cnt;
    size_t masks_size = aidemo_image_size_or_raise(display_shape, 4);
    ndarray_obj_t *masks_results =
        aidemo_require_uint8_array(args[9], masks_size);
    uint8_t *masks_results_data = (uint8_t *)masks_results->array;

    SegOutputs segOutputs = yolov8_seg_postprocess_into(output0, output1, frame_shape, input_shape, display_shape,num_class, conf_thresh,nms_thresh,mask_thresh,&box_cnt, masks_results_data);
    bool valid_output = aidemo_seg_outputs_are_valid(&segOutputs, box_cnt, masks_size);
    segOutputs.masks_results = NULL;  // The ndarray owns the borrowed mask.
    if (!valid_output) {
        yolo_seg_free_outputs(&segOutputs);
        mp_raise_msg(&mp_type_MemoryError, MP_ERROR_TEXT("segmentation result allocation failed"));
    }

    aidemo_nlr_cleanup_t cleanup;
    aidemo_nlr_cleanup_push(&cleanup, yolo_seg_free_outputs, &segOutputs);
    mp_obj_t result = aidemo_seg_outputs_to_mp(&segOutputs, box_cnt, 0, masks_results_data);
    aidemo_nlr_cleanup_finish(&cleanup);
    return result;
}

STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(aidemo_yolov8_seg_postprocess_obj, 10, 10, aidemo_yolov8_seg_postprocess);

STATIC mp_obj_t aidemo_yolo26_seg_postprocess(size_t n_args, const mp_obj_t *args) {
    ndarray_obj_t *data_mp_0 = aidemo_require_ndarray(args[0], NDARRAY_FLOAT);
    float *output0 = data_mp_0->array;

    ndarray_obj_t *data_mp_1 = aidemo_require_ndarray(args[1], NDARRAY_FLOAT);
    float *output1 = data_mp_1->array;

    int num_class = mp_obj_get_int(args[5]);
    if (num_class <= 0) mp_raise_msg(&mp_type_ValueError, MP_ERROR_TEXT("num_class must be positive"));

    float conf_thresh=mp_obj_get_float(args[6]);
    float mask_thresh=mp_obj_get_float(args[7]);

    FrameSize frame_shape = aidemo_frame_size_hw(args[2]);
    FrameSize input_shape = aidemo_frame_size_hw(args[3]);
    FrameSize display_shape = aidemo_frame_size_hw(args[4]);

    int box_cnt;
    size_t masks_size = aidemo_image_size_or_raise(display_shape, 4);
    ndarray_obj_t *masks_results =
        aidemo_require_uint8_array(args[8], masks_size);
    uint8_t *masks_results_data = (uint8_t *)masks_results->array;

    SegOutputs segOutputs = yolo26_seg_postprocess_into(output0, output1, frame_shape, input_shape, display_shape,num_class, conf_thresh,mask_thresh,&box_cnt, masks_results_data);
    bool valid_output = aidemo_seg_outputs_are_valid(&segOutputs, box_cnt, masks_size);
    segOutputs.masks_results = NULL;  // The ndarray owns the borrowed mask.
    if (!valid_output) {
        yolo_seg_free_outputs(&segOutputs);
        mp_raise_msg(&mp_type_MemoryError, MP_ERROR_TEXT("segmentation result allocation failed"));
    }

    aidemo_nlr_cleanup_t cleanup;
    aidemo_nlr_cleanup_push(&cleanup, yolo_seg_free_outputs, &segOutputs);
    mp_obj_t result = aidemo_seg_outputs_to_mp(&segOutputs, box_cnt, 0, masks_results_data);
    aidemo_nlr_cleanup_finish(&cleanup);
    return result;
}

STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(aidemo_yolo26_seg_postprocess_obj, 9, 9, aidemo_yolo26_seg_postprocess);

//***********************************for yolo det ******************/
STATIC mp_obj_t aidemo_yolov8_det_postprocess(size_t n_args, const mp_obj_t *args) {
    ndarray_obj_t *data_mp_0 = MP_ROM_PTR(args[0]);
    float *output0 = data_mp_0->array;

    mp_obj_list_t *frame_size_mp = MP_OBJ_TO_PTR(args[1]);
    mp_obj_list_t *kmodel_input_size_mp = MP_OBJ_TO_PTR(args[2]);
    mp_obj_list_t *display_size_mp = MP_OBJ_TO_PTR(args[3]);

    int num_class = mp_obj_get_int(args[4]);

    float conf_thresh=mp_obj_get_float(args[5]);
    float nms_thresh=mp_obj_get_float(args[6]);

    int max_box_cnt = mp_obj_get_int(args[7]);

    FrameSize frame_shape;
    FrameSize input_shape;
    FrameSize display_shape;

    frame_shape.height = mp_obj_get_int(frame_size_mp->items[0]);
    frame_shape.width = mp_obj_get_int(frame_size_mp->items[1]);
    input_shape.height = mp_obj_get_int(kmodel_input_size_mp->items[0]);
    input_shape.width = mp_obj_get_int(kmodel_input_size_mp->items[1]);
    display_shape.height = mp_obj_get_int(display_size_mp->items[0]);
    display_shape.width = mp_obj_get_int(display_size_mp->items[1]);

    int box_cnt;
    YoloDetInfo* yolo_det_res = yolov8_det_postprocess(output0, frame_shape, input_shape, display_shape,num_class, conf_thresh,nms_thresh,max_box_cnt,&box_cnt);
    if (box_cnt < 0 || (box_cnt > 0 && yolo_det_res == NULL)) {
        mp_raise_msg(&mp_type_MemoryError, MP_ERROR_TEXT("YOLO detection result allocation failed"));
    }

    aidemo_nlr_cleanup_t cleanup;
    aidemo_nlr_cleanup_push(&cleanup, yolo_det_free_outputs, yolo_det_res);

    mp_obj_t result = aidemo_yolo_det_results_to_list(yolo_det_res, box_cnt);
    aidemo_nlr_cleanup_finish(&cleanup);
    return result;
}

STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(aidemo_yolov8_det_postprocess_obj, 8, 8, aidemo_yolov8_det_postprocess);

//***********************************for yolo det ******************/
STATIC mp_obj_t aidemo_yolov5_det_postprocess(size_t n_args, const mp_obj_t *args) {
    ndarray_obj_t *data_mp_0 = MP_ROM_PTR(args[0]);
    float *output0 = data_mp_0->array;

    mp_obj_list_t *frame_size_mp = MP_OBJ_TO_PTR(args[1]);
    mp_obj_list_t *kmodel_input_size_mp = MP_OBJ_TO_PTR(args[2]);
    mp_obj_list_t *display_size_mp = MP_OBJ_TO_PTR(args[3]);

    int num_class = mp_obj_get_int(args[4]);

    float conf_thresh=mp_obj_get_float(args[5]);
    float nms_thresh=mp_obj_get_float(args[6]);

    int max_box_cnt = mp_obj_get_int(args[7]);

    FrameSize frame_shape;
    FrameSize input_shape;
    FrameSize display_shape;

    frame_shape.height = mp_obj_get_int(frame_size_mp->items[0]);
    frame_shape.width = mp_obj_get_int(frame_size_mp->items[1]);
    input_shape.height = mp_obj_get_int(kmodel_input_size_mp->items[0]);
    input_shape.width = mp_obj_get_int(kmodel_input_size_mp->items[1]);
    display_shape.height = mp_obj_get_int(display_size_mp->items[0]);
    display_shape.width = mp_obj_get_int(display_size_mp->items[1]);

    int box_cnt;
    YoloDetInfo* yolo_det_res = yolov5_det_postprocess(output0, frame_shape, input_shape, display_shape,num_class, conf_thresh,nms_thresh,max_box_cnt,&box_cnt);
    if (box_cnt < 0 || (box_cnt > 0 && yolo_det_res == NULL)) {
        mp_raise_msg(&mp_type_MemoryError, MP_ERROR_TEXT("YOLO detection result allocation failed"));
    }

    aidemo_nlr_cleanup_t cleanup;
    aidemo_nlr_cleanup_push(&cleanup, yolo_det_free_outputs, yolo_det_res);

    mp_obj_t result = aidemo_yolo_det_results_to_list(yolo_det_res, box_cnt);
    aidemo_nlr_cleanup_finish(&cleanup);
    return result;
}

STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(aidemo_yolov5_det_postprocess_obj, 8, 8, aidemo_yolov5_det_postprocess);

STATIC mp_obj_t aidemo_yolo26_det_postprocess(size_t n_args, const mp_obj_t *args) {
    ndarray_obj_t *data_mp_0 = MP_ROM_PTR(args[0]);
    float *output0 = data_mp_0->array;

    mp_obj_list_t *frame_size_mp = MP_OBJ_TO_PTR(args[1]);
    mp_obj_list_t *kmodel_input_size_mp = MP_OBJ_TO_PTR(args[2]);
    mp_obj_list_t *display_size_mp = MP_OBJ_TO_PTR(args[3]);

    int num_class = mp_obj_get_int(args[4]);

    float conf_thresh=mp_obj_get_float(args[5]);

    int max_box_cnt = mp_obj_get_int(args[6]);

    FrameSize frame_shape;
    FrameSize input_shape;
    FrameSize display_shape;

    frame_shape.height = mp_obj_get_int(frame_size_mp->items[0]);
    frame_shape.width = mp_obj_get_int(frame_size_mp->items[1]);
    input_shape.height = mp_obj_get_int(kmodel_input_size_mp->items[0]);
    input_shape.width = mp_obj_get_int(kmodel_input_size_mp->items[1]);
    display_shape.height = mp_obj_get_int(display_size_mp->items[0]);
    display_shape.width = mp_obj_get_int(display_size_mp->items[1]);

    int box_cnt;
    YoloDetInfo* yolo_det_res = yolo26_det_postprocess(output0, frame_shape, input_shape, display_shape,num_class, conf_thresh,max_box_cnt,&box_cnt);
    if (box_cnt < 0 || (box_cnt > 0 && yolo_det_res == NULL)) {
        mp_raise_msg(&mp_type_MemoryError, MP_ERROR_TEXT("YOLO detection result allocation failed"));
    }

    aidemo_nlr_cleanup_t cleanup;
    aidemo_nlr_cleanup_push(&cleanup, yolo_det_free_outputs, yolo_det_res);

    mp_obj_t result = aidemo_yolo_det_results_to_list(yolo_det_res, box_cnt);
    aidemo_nlr_cleanup_finish(&cleanup);
    return result;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(aidemo_yolo26_det_postprocess_obj, 7, 7, aidemo_yolo26_det_postprocess);

STATIC mp_obj_t aidemo_yolo_obb_postprocess(size_t n_args, const mp_obj_t *args) {
    ndarray_obj_t *data_mp_0 = MP_ROM_PTR(args[0]);
    float *output0 = data_mp_0->array;

    mp_obj_list_t *frame_size_mp = MP_OBJ_TO_PTR(args[1]);
    mp_obj_list_t *kmodel_input_size_mp = MP_OBJ_TO_PTR(args[2]);
    mp_obj_list_t *display_size_mp = MP_OBJ_TO_PTR(args[3]);

    int num_class = mp_obj_get_int(args[4]);

    float conf_thresh=mp_obj_get_float(args[5]);
    float nms_thresh=mp_obj_get_float(args[6]);

    int max_box_cnt = mp_obj_get_int(args[7]);

    FrameSize frame_shape;
    FrameSize input_shape;
    FrameSize display_shape;

    frame_shape.height = mp_obj_get_int(frame_size_mp->items[0]);
    frame_shape.width = mp_obj_get_int(frame_size_mp->items[1]);
    input_shape.height = mp_obj_get_int(kmodel_input_size_mp->items[0]);
    input_shape.width = mp_obj_get_int(kmodel_input_size_mp->items[1]);
    display_shape.height = mp_obj_get_int(display_size_mp->items[0]);
    display_shape.width = mp_obj_get_int(display_size_mp->items[1]);

    int box_cnt;
    YoloObbInfo* yolo_obb_res = yolo_obb_postprocess(output0, frame_shape, input_shape, display_shape,num_class, conf_thresh,nms_thresh,max_box_cnt,&box_cnt);
    if (box_cnt < 0 || (box_cnt > 0 && yolo_obb_res == NULL)) {
        mp_raise_msg(&mp_type_MemoryError, MP_ERROR_TEXT("YOLO OBB result allocation failed"));
    }

    aidemo_nlr_cleanup_t cleanup;
    aidemo_nlr_cleanup_push(&cleanup, yolo_obb_free_outputs, yolo_obb_res);

    mp_obj_t result = aidemo_yolo_obb_results_to_list(yolo_obb_res, box_cnt);
    aidemo_nlr_cleanup_finish(&cleanup);
    return result;
}

STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(aidemo_yolo_obb_postprocess_obj, 8, 8, aidemo_yolo_obb_postprocess);

STATIC mp_obj_t aidemo_yolo26_obb_postprocess(size_t n_args, const mp_obj_t *args) {
    ndarray_obj_t *data_mp_0 = MP_ROM_PTR(args[0]);
    float *output0 = data_mp_0->array;

    mp_obj_list_t *frame_size_mp = MP_OBJ_TO_PTR(args[1]);
    mp_obj_list_t *kmodel_input_size_mp = MP_OBJ_TO_PTR(args[2]);
    mp_obj_list_t *display_size_mp = MP_OBJ_TO_PTR(args[3]);

    int num_class = mp_obj_get_int(args[4]);

    float conf_thresh=mp_obj_get_float(args[5]);
    int max_box_cnt = mp_obj_get_int(args[6]);

    FrameSize frame_shape;
    FrameSize input_shape;
    FrameSize display_shape;

    frame_shape.height = mp_obj_get_int(frame_size_mp->items[0]);
    frame_shape.width = mp_obj_get_int(frame_size_mp->items[1]);
    input_shape.height = mp_obj_get_int(kmodel_input_size_mp->items[0]);
    input_shape.width = mp_obj_get_int(kmodel_input_size_mp->items[1]);
    display_shape.height = mp_obj_get_int(display_size_mp->items[0]);
    display_shape.width = mp_obj_get_int(display_size_mp->items[1]);

    int box_cnt;
    YoloObbInfo* yolo_obb_res = yolo26_obb_postprocess(output0, frame_shape, input_shape, display_shape,num_class, conf_thresh,max_box_cnt,&box_cnt);
    if (box_cnt < 0 || (box_cnt > 0 && yolo_obb_res == NULL)) {
        mp_raise_msg(&mp_type_MemoryError, MP_ERROR_TEXT("YOLO OBB result allocation failed"));
    }

    aidemo_nlr_cleanup_t cleanup;
    aidemo_nlr_cleanup_push(&cleanup, yolo_obb_free_outputs, yolo_obb_res);

    mp_obj_t result = aidemo_yolo_obb_results_to_list(yolo_obb_res, box_cnt);
    aidemo_nlr_cleanup_finish(&cleanup);
    return result;
}

STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(aidemo_yolo26_obb_postprocess_obj, 7, 7, aidemo_yolo26_obb_postprocess);

STATIC mp_obj_t aidemo_yolov8_pose_postprocess(size_t n_args, const mp_obj_t *args) {
    ndarray_obj_t *data_mp_0 = MP_ROM_PTR(args[0]);
    float *output0 = data_mp_0->array;

    mp_obj_list_t *frame_size_mp = MP_OBJ_TO_PTR(args[1]);
    mp_obj_list_t *kmodel_input_size_mp = MP_OBJ_TO_PTR(args[2]);
    mp_obj_list_t *display_size_mp = MP_OBJ_TO_PTR(args[3]);

    int num_class = mp_obj_get_int(args[4]);

    int kp_num = mp_obj_get_int(args[5]);

    int kp_dim = mp_obj_get_int(args[6]);
    (void)aidemo_keypoint_count_or_raise(kp_num, kp_dim);

    float conf_thresh=mp_obj_get_float(args[7]);
    float nms_thresh=mp_obj_get_float(args[8]);
    int max_box_cnt = mp_obj_get_int(args[9]);

    FrameSize frame_shape;
    FrameSize input_shape;
    FrameSize display_shape;

    frame_shape.height = mp_obj_get_int(frame_size_mp->items[0]);
    frame_shape.width = mp_obj_get_int(frame_size_mp->items[1]);
    input_shape.height = mp_obj_get_int(kmodel_input_size_mp->items[0]);
    input_shape.width = mp_obj_get_int(kmodel_input_size_mp->items[1]);
    display_shape.height = mp_obj_get_int(display_size_mp->items[0]);
    display_shape.width = mp_obj_get_int(display_size_mp->items[1]);

    int box_cnt;
    YoloPoseInfo* yolo_pose_res = yolov8_pose_postprocess(output0, frame_shape, input_shape, display_shape,num_class,kp_num,kp_dim, conf_thresh,nms_thresh,max_box_cnt,&box_cnt);
    if (box_cnt < 0 || (box_cnt > 0 && yolo_pose_res == NULL)) {
        mp_raise_msg(&mp_type_MemoryError, MP_ERROR_TEXT("YOLO pose result allocation failed"));
    }

    aidemo_yolo_pose_resource_t result_resource = {
        .items = yolo_pose_res,
        .count = box_cnt,
    };
    aidemo_nlr_cleanup_t cleanup;
    aidemo_nlr_cleanup_push(&cleanup, aidemo_free_yolo_pose_resource, &result_resource);

    mp_obj_t result = aidemo_yolo_pose_results_to_list(yolo_pose_res, box_cnt, kp_num, kp_dim);
    aidemo_nlr_cleanup_finish(&cleanup);
    return result;
}

STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(aidemo_yolov8_pose_postprocess_obj, 10, 10, aidemo_yolov8_pose_postprocess);

STATIC mp_obj_t aidemo_yolo26_pose_postprocess(size_t n_args, const mp_obj_t *args) {
    ndarray_obj_t *data_mp_0 = MP_ROM_PTR(args[0]);
    float *output0 = data_mp_0->array;

    mp_obj_list_t *frame_size_mp = MP_OBJ_TO_PTR(args[1]);
    mp_obj_list_t *kmodel_input_size_mp = MP_OBJ_TO_PTR(args[2]);
    mp_obj_list_t *display_size_mp = MP_OBJ_TO_PTR(args[3]);

    int num_class = mp_obj_get_int(args[4]);

    int kp_num = mp_obj_get_int(args[5]);

    int kp_dim = mp_obj_get_int(args[6]);
    (void)aidemo_keypoint_count_or_raise(kp_num, kp_dim);

    float conf_thresh=mp_obj_get_float(args[7]);
    int max_box_cnt = mp_obj_get_int(args[8]);

    FrameSize frame_shape;
    FrameSize input_shape;
    FrameSize display_shape;

    frame_shape.height = mp_obj_get_int(frame_size_mp->items[0]);
    frame_shape.width = mp_obj_get_int(frame_size_mp->items[1]);
    input_shape.height = mp_obj_get_int(kmodel_input_size_mp->items[0]);
    input_shape.width = mp_obj_get_int(kmodel_input_size_mp->items[1]);
    display_shape.height = mp_obj_get_int(display_size_mp->items[0]);
    display_shape.width = mp_obj_get_int(display_size_mp->items[1]);

    int box_cnt;
    YoloPoseInfo* yolo_pose_res = yolo26_pose_postprocess(output0, frame_shape, input_shape, display_shape,num_class,kp_num,kp_dim, conf_thresh,max_box_cnt,&box_cnt);
    if (box_cnt < 0 || (box_cnt > 0 && yolo_pose_res == NULL)) {
        mp_raise_msg(&mp_type_MemoryError, MP_ERROR_TEXT("YOLO pose result allocation failed"));
    }

    aidemo_yolo_pose_resource_t result_resource = {
        .items = yolo_pose_res,
        .count = box_cnt,
    };
    aidemo_nlr_cleanup_t cleanup;
    aidemo_nlr_cleanup_push(&cleanup, aidemo_free_yolo_pose_resource, &result_resource);

    mp_obj_t result = aidemo_yolo_pose_results_to_list(yolo_pose_res, box_cnt, kp_num, kp_dim);
    aidemo_nlr_cleanup_finish(&cleanup);
    return result;
}

STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(aidemo_yolo26_pose_postprocess_obj, 9, 9, aidemo_yolo26_pose_postprocess);


//*****************************for yunet postprocess*****************************
STATIC mp_obj_t aidemo_yunet_postprocess(size_t n_args, const mp_obj_t *args) {
    mp_obj_list_t *p_outputs_list = MP_OBJ_TO_PTR(args[0]);
    ndarray_obj_t *p_outputs_0_ndarray = MP_ROM_PTR(p_outputs_list->items[0]);
    float *data_0 = p_outputs_0_ndarray->array;
    ndarray_obj_t *p_outputs_1_ndarray = MP_ROM_PTR(p_outputs_list->items[1]);
    float *data_1 = p_outputs_1_ndarray->array;
    ndarray_obj_t *p_outputs_2_ndarray = MP_ROM_PTR(p_outputs_list->items[2]);
    float *data_2 = p_outputs_2_ndarray->array;
    ndarray_obj_t *p_outputs_3_ndarray = MP_ROM_PTR(p_outputs_list->items[3]);
    float *data_3 = p_outputs_3_ndarray->array;
    ndarray_obj_t *p_outputs_4_ndarray = MP_ROM_PTR(p_outputs_list->items[4]);
    float *data_4 = p_outputs_4_ndarray->array;
    ndarray_obj_t *p_outputs_5_ndarray = MP_ROM_PTR(p_outputs_list->items[5]);
    float *data_5 = p_outputs_5_ndarray->array;
    ndarray_obj_t *p_outputs_6_ndarray = MP_ROM_PTR(p_outputs_list->items[6]);
    float *data_6 = p_outputs_6_ndarray->array;
    ndarray_obj_t *p_outputs_7_ndarray = MP_ROM_PTR(p_outputs_list->items[7]);
    float *data_7 = p_outputs_7_ndarray->array;
    ndarray_obj_t *p_outputs_8_ndarray = MP_ROM_PTR(p_outputs_list->items[8]);
    float *data_8 = p_outputs_8_ndarray->array;
    ndarray_obj_t *p_outputs_9_ndarray = MP_ROM_PTR(p_outputs_list->items[9]);
    float *data_9 = p_outputs_9_ndarray->array;
    ndarray_obj_t *p_outputs_10_ndarray = MP_ROM_PTR(p_outputs_list->items[10]);
    float *data_10 = p_outputs_10_ndarray->array;
    ndarray_obj_t *p_outputs_11_ndarray = MP_ROM_PTR(p_outputs_list->items[11]);
    float *data_11 = p_outputs_11_ndarray->array;

    float *p_outputs[12];
    p_outputs[0] = data_0;
    p_outputs[1] = data_1;
    p_outputs[2] = data_2;
    p_outputs[3] = data_3;
    p_outputs[4] = data_4;
    p_outputs[5] = data_5;
    p_outputs[6] = data_6;
    p_outputs[7] = data_7;
    p_outputs[8] = data_8;
    p_outputs[9] = data_9;
    p_outputs[10] = data_10;
    p_outputs[11] = data_11;

    mp_obj_list_t *frame_size_mp = MP_OBJ_TO_PTR(args[1]);
    mp_obj_list_t *kmodel_input_size_mp = MP_OBJ_TO_PTR(args[2]);
    mp_obj_list_t *display_size_mp = MP_OBJ_TO_PTR(args[3]);
    mp_obj_list_t *strides_mp = MP_OBJ_TO_PTR(args[4]);

    float conf_thres = mp_obj_get_float(args[5]);
    float nms_thres = mp_obj_get_float(args[6]);
    int max_box_cnt = mp_obj_get_int(args[7]);
    int box_cnt;

    FrameSize frame_shape;
    FrameSize input_shape;
    FrameSize display_shape;

    frame_shape.height = mp_obj_get_int(frame_size_mp->items[0]);
    frame_shape.width = mp_obj_get_int(frame_size_mp->items[1]);
    input_shape.height = mp_obj_get_int(kmodel_input_size_mp->items[0]);
    input_shape.width = mp_obj_get_int(kmodel_input_size_mp->items[1]);
    display_shape.height = mp_obj_get_int(display_size_mp->items[0]);
    display_shape.width = mp_obj_get_int(display_size_mp->items[1]);

    int strides[strides_mp->len];
    for (int i = 0; i < strides_mp->len; i++) 
    {
        strides[i] = mp_obj_get_int(strides_mp->items[i]);
    }

    YUNetFaceDetInfo* yunet_face_det_res = yunet_postprocess(p_outputs, frame_shape, input_shape, display_shape, strides, conf_thres, nms_thres, max_box_cnt, &box_cnt);
    if (box_cnt < 0 || (box_cnt > 0 && yunet_face_det_res == NULL)) {
        mp_raise_msg(&mp_type_MemoryError, MP_ERROR_TEXT("YUNet result allocation failed"));
    }

    aidemo_nlr_cleanup_t cleanup;
    aidemo_nlr_cleanup_push(&cleanup, yunet_free_outputs, yunet_face_det_res);

    mp_obj_list_t *results_mp_list = mp_obj_new_list(2, NULL);
    mp_obj_list_t *results_mp_list_boxes = mp_obj_new_list(box_cnt, NULL);
    mp_obj_list_t *results_mp_list_scores = mp_obj_new_list(box_cnt, NULL);
    results_mp_list->items[0] = MP_OBJ_FROM_PTR(results_mp_list_boxes);
    results_mp_list->items[1] = MP_OBJ_FROM_PTR(results_mp_list_scores);

    size_t ndarray_shape_box[4];
    ndarray_shape_box[3] = 4;
    for (int i = 0; i < box_cnt; i++)
    {
        ndarray_obj_t *box_obj = ndarray_new_ndarray(1, ndarray_shape_box, NULL, NDARRAY_INT16);
        int16_t *box_data = (int16_t *)box_obj->array;
        box_data[0] = yunet_face_det_res[i].x;
        box_data[1] = yunet_face_det_res[i].y;
        box_data[2] = yunet_face_det_res[i].w;
        box_data[3] = yunet_face_det_res[i].h;
        results_mp_list_boxes->items[i] = MP_OBJ_FROM_PTR(box_obj);
        results_mp_list_scores->items[i] =
            mp_obj_new_float(yunet_face_det_res[i].score);
    }

    aidemo_nlr_cleanup_finish(&cleanup);
    return MP_OBJ_FROM_PTR(results_mp_list);
};
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(aidemo_yunet_postprocess_obj, 8, 8, aidemo_yunet_postprocess);

//*****************************for yolo license plate det postprocess*****************************
STATIC mp_obj_t aidemo_yolo_license_plate_det_postprocess(size_t n_args, const mp_obj_t *args) {
    ndarray_obj_t *data_mp_0 = MP_ROM_PTR(args[0]);
    float *output0 = data_mp_0->array;

    mp_obj_list_t *frame_size_mp = MP_OBJ_TO_PTR(args[1]);
    mp_obj_list_t *kmodel_input_size_mp = MP_OBJ_TO_PTR(args[2]);
    mp_obj_list_t *display_size_mp = MP_OBJ_TO_PTR(args[3]);

    float conf_thresh=mp_obj_get_float(args[4]);
    float nms_thresh=mp_obj_get_float(args[5]);

    int max_box_cnt = mp_obj_get_int(args[6]);

    FrameSize frame_shape;
    FrameSize input_shape;
    FrameSize display_shape;

    frame_shape.height = mp_obj_get_int(frame_size_mp->items[0]);
    frame_shape.width = mp_obj_get_int(frame_size_mp->items[1]);
    input_shape.height = mp_obj_get_int(kmodel_input_size_mp->items[0]);
    input_shape.width = mp_obj_get_int(kmodel_input_size_mp->items[1]);
    display_shape.height = mp_obj_get_int(display_size_mp->items[0]);
    display_shape.width = mp_obj_get_int(display_size_mp->items[1]);

    int box_cnt;
    YoloLicensePlateDetInfo* yolo_license_plate_det_res = yolo_license_plate_det_postprocess(output0, frame_shape, input_shape, display_shape,conf_thresh,nms_thresh,max_box_cnt,&box_cnt);
    if (box_cnt < 0 || (box_cnt > 0 && yolo_license_plate_det_res == NULL)) {
        mp_raise_msg(&mp_type_MemoryError, MP_ERROR_TEXT("licence plate result allocation failed"));
    }

    aidemo_nlr_cleanup_t cleanup;
    aidemo_nlr_cleanup_push(&cleanup, yolo_license_plate_det_free_outputs, yolo_license_plate_det_res);

    mp_obj_list_t *results_mp_list = mp_obj_new_list(3, NULL);
    mp_obj_list_t *results_mp_list_boxes = mp_obj_new_list(box_cnt, NULL);
    mp_obj_list_t *results_mp_list_kps = mp_obj_new_list(box_cnt, NULL);
    mp_obj_list_t *results_mp_list_scores = mp_obj_new_list(box_cnt, NULL);
    results_mp_list->items[0] = MP_OBJ_FROM_PTR(results_mp_list_kps);
    results_mp_list->items[1] = MP_OBJ_FROM_PTR(results_mp_list_boxes);
    results_mp_list->items[2] = MP_OBJ_FROM_PTR(results_mp_list_scores);

    size_t ndarray_shape_box[4];
    ndarray_shape_box[3] = 4;

    size_t ndarray_shape_kps[8];
    ndarray_shape_kps[3] = 8;
    for (int i = 0; i < box_cnt; i++)
    {
        ndarray_obj_t *box_obj = ndarray_new_ndarray(1, ndarray_shape_box, NULL, NDARRAY_FLOAT);
        float *box_data = (float *)box_obj->array;
        box_data[0] = yolo_license_plate_det_res[i].box_kps[0];
        box_data[1] = yolo_license_plate_det_res[i].box_kps[1];
        box_data[2] = yolo_license_plate_det_res[i].box_kps[2];
        box_data[3] = yolo_license_plate_det_res[i].box_kps[3];

        ndarray_obj_t *kps_obj = ndarray_new_ndarray(1, ndarray_shape_kps, NULL, NDARRAY_FLOAT);
        float *kps_data = (float *)kps_obj->array;
        kps_data[0] = yolo_license_plate_det_res[i].box_kps[4];
        kps_data[1] = yolo_license_plate_det_res[i].box_kps[5];
        kps_data[2] = yolo_license_plate_det_res[i].box_kps[6];
        kps_data[3] = yolo_license_plate_det_res[i].box_kps[7];
        kps_data[4] = yolo_license_plate_det_res[i].box_kps[8];
        kps_data[5] = yolo_license_plate_det_res[i].box_kps[9];
        kps_data[6] = yolo_license_plate_det_res[i].box_kps[10];
        kps_data[7] = yolo_license_plate_det_res[i].box_kps[11];
        results_mp_list_kps->items[i] = MP_OBJ_FROM_PTR(kps_obj);
        results_mp_list_boxes->items[i] = MP_OBJ_FROM_PTR(box_obj);
        results_mp_list_scores->items[i] =
            mp_obj_new_float(yolo_license_plate_det_res[i].score);
    }
    aidemo_nlr_cleanup_finish(&cleanup);
    return MP_OBJ_FROM_PTR(results_mp_list);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(aidemo_yolo_license_plate_det_postprocess_obj, 7, 7, aidemo_yolo_license_plate_det_postprocess);

STATIC mp_obj_t aidemo_opencv_grayscale_find_blobs(size_t n_args, const mp_obj_t *args)
{
    mp_obj_list_t *frame_size_mp = MP_OBJ_TO_PTR(args[0]);

    ndarray_obj_t *data = MP_ROM_PTR(args[1]); //hwc
    uint8_t* img_data = data->array;

    int threshold_min = mp_obj_get_int(args[2]);
    int threshold_max = mp_obj_get_int(args[3]);

    FrameSize frame_shape;
    frame_shape.height = mp_obj_get_int(frame_size_mp->items[0]);
    frame_shape.width = mp_obj_get_int(frame_size_mp->items[1]);

    int ret_num;

    int* ret=opencv_grayscale_findblobs(frame_shape,img_data,threshold_min,threshold_max,&ret_num);
    if (ret_num < 0 || (ret_num > 0 && ret == NULL)) {
        mp_raise_msg(&mp_type_MemoryError, MP_ERROR_TEXT("blob result allocation failed"));
    }

    aidemo_nlr_cleanup_t cleanup;
    aidemo_nlr_cleanup_push(&cleanup, opencv_grayscale_findblobs_free_outputs, ret);

    mp_obj_list_t *int_array = mp_obj_new_list(0, NULL);

    for (int i = 0; i < ret_num; i++)
    {
        mp_obj_list_append(int_array, mp_obj_new_int(ret[i*4+0]));
        mp_obj_list_append(int_array, mp_obj_new_int(ret[i*4+1]));
        mp_obj_list_append(int_array, mp_obj_new_int(ret[i*4+2]));
        mp_obj_list_append(int_array, mp_obj_new_int(ret[i*4+3]));
    }
    aidemo_nlr_cleanup_finish(&cleanup);
    return MP_OBJ_FROM_PTR(int_array);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(aidemo_opencv_grayscale_find_blobs_obj, 4, 4, aidemo_opencv_grayscale_find_blobs);

STATIC mp_obj_t aidemo_rgb888_compress(size_t n_args, const mp_obj_t *args)
{
    mp_obj_list_t *frame_size_mp = MP_OBJ_TO_PTR(args[0]);

    // 构造图像尺寸
    FrameSize frame_shape;
    frame_shape.height = mp_obj_get_int(frame_size_mp->items[0]);
    frame_shape.width  = mp_obj_get_int(frame_size_mp->items[1]);
    // 处理：JPEG 压缩
    int jpeg_quality = mp_obj_get_int(args[2]);
    size_t result_size = aidemo_image_size_or_raise(frame_shape, 3);
    ndarray_obj_t *data = aidemo_require_uint8_array(args[1], result_size);
    uint8_t *img_data = data->array;
    uint8_t* result=(uint8_t*)malloc(result_size);
    if (result_size != 0 && result == NULL) {
        mp_raise_msg(&mp_type_MemoryError, MP_ERROR_TEXT("JPEG result allocation failed"));
    }

    aidemo_malloc_resource_t result_resource = { .ptr = result };
    aidemo_nlr_cleanup_t cleanup;
    aidemo_nlr_cleanup_push(&cleanup, aidemo_free_malloc_resource, &result_resource);
    // 处理：JPEG 压缩
    if (data->len < result_size) {
        mp_raise_ValueError(MP_ERROR_TEXT("RGB image buffer is too small"));
    }
    if (!rgb888_compress_safe(frame_shape, img_data, jpeg_quality, result)) {
        mp_raise_ValueError(MP_ERROR_TEXT("RGB compression failed"));
    }
    // 构造返回的 numpy 对象（共享内存，不复制）
    size_t ndarray_shape[4] = {0};
    ndarray_shape[1] = frame_shape.height;
    ndarray_shape[2] = frame_shape.width;
    ndarray_shape[3] = 3;
    ndarray_obj_t *out = ndarray_new_ndarray(3, ndarray_shape, NULL, NDARRAY_UINT8);
    uint8_t *out_data = (uint8_t *)out->array;
    hal_rvv_memcpy(out_data, result, result_size);
    aidemo_nlr_cleanup_finish(&cleanup);
    return MP_OBJ_FROM_PTR(out);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(aidemo_rgb888_compress_obj, 3, 3, aidemo_rgb888_compress);
//| # Auto-generated CanMV stub docs. Edit the signatures/docstrings here.
//| module: aidemo
//| """CanMV aidemo module."""
//| def body_seg_postprocess(data_mp: Any, num_class: int, ori_shape_mp: Any, dst_shape_mp: Any, color: Any, /) -> Any:
//|     """Run body seg post-processing for aidemo."""
//| def contours(mp_img: Any, mp_pts: Any, contour_idx: int, mp_color: Any, thickness: int, line_type: int, /) -> Any:
//|     """Perform contours for aidemo."""
//| def eye_gaze_post_process(outputs: Any, /) -> Any:
//|     """Run eye gaze post-processing for aidemo."""
//| def face_det_post_process(obj_thresh: float, nms_thresh: float, net_len: float, mp_anchors: Any, ori_shape_list: Any, mp_outputs: Any, /) -> Any:
//|     """Run face det post-processing for aidemo."""
//| def face_draw_mesh(img: Any, vertices: Any, /) -> Any:
//|     """Perform face draw mesh for aidemo."""
//| def face_mesh_post_process(roi: Any, vertices: Any, /) -> Any:
//|     """Run face mesh post-processing for aidemo."""
//| def face_parse_post_process(mp_img: Any, mp_ai_img_shape: Any, mp_osd_img_shape: Any, net_len: int, mp_bbox: Any, mp_outputs: Any, /) -> Any:
//|     """Run face parse post-processing for aidemo."""
//| def invert_affine_transform(matrix_ndarray: Any, /) -> Any:
//|     """Perform invert affine transform for aidemo."""
//| def kws_fp_create() -> Any:
//|     """Perform kws fp create for aidemo."""
//| def kws_fp_destroy(fp: Any, /) -> Any:
//|     """Release resources held by aidemo."""
//| def kws_preprocess(fp: Any, wav: Any, /) -> Any:
//|     """Run kws preprocessing for aidemo."""
//| def licence_det_postprocess(p_outputs_list: Any, frame_size_list: Any, kmodel_frame_size_list: Any, obj_thresh: float, nms_thresh: float, /) -> Any:
//|     """Run licence det post-processing for aidemo."""
//| def mask_resize(dest: Any, ori_shape: Any, tag_shape: Any, /) -> Any:
//|     """Perform mask resize for aidemo."""
//| def nanotracker_postprocess(p_outputs_ndarray_0: Any, p_outputs_ndarray_1: Any, sensor_size_list: Any, obj_thresh: float, center_xy_wh_list: Any, crop_size: int, CONTEXT_AMOUNT: float, /) -> Any:
//|     """Run nanotracker post-processing for aidemo."""
//| def ocr_rec_preprocess(data: Any, ori_shape: Any, boxpoint8: Any, /) -> Any:
//|     """Run ocr rec preprocessing for aidemo."""
//| def opencv_grayscale_find_blobs(frame_size_mp: Any, data: Any, threshold_min: int, threshold_max: int, /) -> Any:
//|     """Perform opencv grayscale find blobs for aidemo."""
//| def person_kp_postprocess(p_outputs_ndarray: Any, frame_size_list: Any, kmodel_frame_size_list: Any, obj_thresh: float, nms_thresh: float, /) -> Any:
//|     """Run person kp post-processing for aidemo."""
//| def polylines(mp_img: Any, mp_pts: Any, is_closed: bool, mp_color: Any, thickness: int, line_type: int, shift: int, /) -> Any:
//|     """Perform polylines for aidemo."""
//| def rgb888_compress(frame_size_mp: Any, data: Any, jpeg_quality: int, /) -> Any:
//|     """Perform rgb888 compress for aidemo."""
//| def save_wav(wav_list: Any, wav_length: int, wav_path: str, sample_rate: Any, /) -> Any:
//|     """Save wav from aidemo."""
//| def segment_postprocess(p_outputs_list: Any, frame_size_list: Any, kmodel_frame_size_list: Any, display_frame_size_list: Any, conf_thres: float, nms_thres: float, mask_thres: float, masks_results: Any, /) -> Any:
//|     """Run segment post-processing for aidemo."""
//| def tts_zh_create(dictfile: Any, phasefile: Any, mapfile: Any, /) -> Any:
//|     """Perform tts zh create for aidemo."""
//| def tts_zh_destroy(ttszh: Any, /) -> Any:
//|     """Release resources held by aidemo."""
//| def tts_zh_preprocess(ttszh: Any, text: Any, /) -> Any:
//|     """Run tts zh preprocessing for aidemo."""
//| def yolo26_det_postprocess(data_mp_0: Any, frame_size_mp: Any, kmodel_input_size_mp: Any, display_size_mp: Any, num_class: int, conf_thresh: float, max_box_cnt: int, /) -> Any:
//|     """Run yolo26 det post-processing for aidemo."""
//| def yolo26_obb_postprocess(data_mp_0: Any, frame_size_mp: Any, kmodel_input_size_mp: Any, display_size_mp: Any, num_class: int, conf_thresh: float, max_box_cnt: int, /) -> Any:
//|     """Run yolo26 obb post-processing for aidemo."""
//| def yolo26_pose_postprocess(data_mp_0: Any, frame_size_mp: Any, kmodel_input_size_mp: Any, display_size_mp: Any, num_class: int, kp_num: int, kp_dim: int, conf_thresh: float, max_box_cnt: int, /) -> Any:
//|     """Run yolo26 pose post-processing for aidemo."""
//| def yolo26_seg_postprocess(data_mp_0: Any, data_mp_1: Any, frame_size_mp: Any, kmodel_input_size_mp: Any, display_size_mp: Any, num_class: int, conf_thresh: float, mask_thresh: float, masks_results: Any, /) -> Any:
//|     """Run yolo26 seg post-processing for aidemo."""
//| def yolo_license_plate_det_postprocess(data_mp_0: Any, frame_size_mp: Any, kmodel_input_size_mp: Any, display_size_mp: Any, conf_thresh: float, nms_thresh: float, max_box_cnt: int, /) -> Any:
//|     """Run yolo license plate det post-processing for aidemo."""
//| def yolo_obb_postprocess(data_mp_0: Any, frame_size_mp: Any, kmodel_input_size_mp: Any, display_size_mp: Any, num_class: int, conf_thresh: float, nms_thresh: float, max_box_cnt: int, /) -> Any:
//|     """Run yolo obb post-processing for aidemo."""
//| def yolov5_det_postprocess(data_mp_0: Any, frame_size_mp: Any, kmodel_input_size_mp: Any, display_size_mp: Any, num_class: int, conf_thresh: float, nms_thresh: float, max_box_cnt: int, /) -> Any:
//|     """Run yolov5 det post-processing for aidemo."""
//| def yolov5_seg_postprocess(data_mp_0: Any, data_mp_1: Any, frame_size_mp: Any, kmodel_input_size_mp: Any, display_size_mp: Any, num_class: int, conf_thresh: float, nms_thresh: float, mask_thresh: float, masks_results: Any, /) -> Any:
//|     """Run yolov5 seg post-processing for aidemo."""
//| def yolov8_det_postprocess(data_mp_0: Any, frame_size_mp: Any, kmodel_input_size_mp: Any, display_size_mp: Any, num_class: int, conf_thresh: float, nms_thresh: float, max_box_cnt: int, /) -> Any:
//|     """Run yolov8 det post-processing for aidemo."""
//| def yolov8_pose_postprocess(data_mp_0: Any, frame_size_mp: Any, kmodel_input_size_mp: Any, display_size_mp: Any, num_class: int, kp_num: int, kp_dim: int, conf_thresh: float, nms_thresh: float, max_box_cnt: int, /) -> Any:
//|     """Run yolov8 pose post-processing for aidemo."""
//| def yolov8_seg_postprocess(data_mp_0: Any, data_mp_1: Any, frame_size_mp: Any, kmodel_input_size_mp: Any, display_size_mp: Any, num_class: int, conf_thresh: float, nms_thresh: float, mask_thresh: float, masks_results: Any, /) -> Any:
//|     """Run yolov8 seg post-processing for aidemo."""
//| def yunet_postprocess(p_outputs_list: Any, frame_size_mp: Any, kmodel_input_size_mp: Any, display_size_mp: Any, strides_mp: Any, conf_thres: float, nms_thres: float, max_box_cnt: int, /) -> Any:
//|     """Run yunet post-processing for aidemo."""



STATIC const mp_rom_map_elem_t aidemo_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_aidemo) },
    { MP_ROM_QSTR(MP_QSTR_invert_affine_transform), MP_ROM_PTR(&aidemo_invert_affine_transform_obj) },
    { MP_ROM_QSTR(MP_QSTR_polylines), MP_ROM_PTR(&aidemo_polylines_obj) },
    { MP_ROM_QSTR(MP_QSTR_contours), MP_ROM_PTR(&aidemo_contours_obj) },
    { MP_ROM_QSTR(MP_QSTR_face_det_post_process), MP_ROM_PTR(&aidemo_face_det_post_process_obj) },
    { MP_ROM_QSTR(MP_QSTR_face_parse_post_process), MP_ROM_PTR(&aidemo_face_parse_post_process_obj) },
    { MP_ROM_QSTR(MP_QSTR_mask_resize), MP_ROM_PTR(&aidemo_mask_resize_obj) },
    { MP_ROM_QSTR(MP_QSTR_ocr_rec_preprocess), MP_ROM_PTR(&aidemo_ocr_rec_preprocess_obj) },
    { MP_ROM_QSTR(MP_QSTR_licence_det_postprocess), MP_ROM_PTR(&aidemo_licence_det_postprocess_obj) },
    { MP_ROM_QSTR(MP_QSTR_segment_postprocess), MP_ROM_PTR(&aidemo_segment_postprocess_obj) },
    { MP_ROM_QSTR(MP_QSTR_face_mesh_post_process), MP_ROM_PTR(&aidemo_face_mesh_post_process_obj) },
    { MP_ROM_QSTR(MP_QSTR_face_draw_mesh), MP_ROM_PTR(&aidemo_face_draw_mesh_obj) },
    { MP_ROM_QSTR(MP_QSTR_person_kp_postprocess), MP_ROM_PTR(&aidemo_person_kp_postprocess_obj) },
    { MP_ROM_QSTR(MP_QSTR_kws_fp_create), MP_ROM_PTR(&aidemo_kws_feature_pipeline_create_obj) },
    { MP_ROM_QSTR(MP_QSTR_kws_fp_destroy), MP_ROM_PTR(&aidemo_kws_feature_pipeline_destroy_obj) },
    { MP_ROM_QSTR(MP_QSTR_kws_preprocess), MP_ROM_PTR(&aidemo_kws_preprocess_obj) },
    { MP_ROM_QSTR(MP_QSTR_eye_gaze_post_process), MP_ROM_PTR(&aidemo_eye_gaze_post_process_obj) },
    { MP_ROM_QSTR(MP_QSTR_nanotracker_postprocess), MP_ROM_PTR(&aidemo_nanotracker_postprocess_obj) },
    { MP_ROM_QSTR(MP_QSTR_tts_zh_create), MP_ROM_PTR(&aidemo_tts_zh_create_obj) },
    { MP_ROM_QSTR(MP_QSTR_tts_zh_destroy), MP_ROM_PTR(&aidemo_tts_zh_destroy_obj) },
    { MP_ROM_QSTR(MP_QSTR_tts_zh_preprocess), MP_ROM_PTR(&aidemo_tts_zh_preprocess_obj) },
    { MP_ROM_QSTR(MP_QSTR_save_wav), MP_ROM_PTR(&aidemo_save_wav_obj) },
    { MP_ROM_QSTR(MP_QSTR_body_seg_postprocess), MP_ROM_PTR(&aidemo_body_seg_postprocess_obj) },
    { MP_ROM_QSTR(MP_QSTR_yolov5_seg_postprocess), MP_ROM_PTR(&aidemo_yolov5_seg_postprocess_obj) },
    { MP_ROM_QSTR(MP_QSTR_yolov8_seg_postprocess), MP_ROM_PTR(&aidemo_yolov8_seg_postprocess_obj) },
    { MP_ROM_QSTR(MP_QSTR_yolo26_seg_postprocess), MP_ROM_PTR(&aidemo_yolo26_seg_postprocess_obj) },
    { MP_ROM_QSTR(MP_QSTR_yolov8_det_postprocess), MP_ROM_PTR(&aidemo_yolov8_det_postprocess_obj) },
    { MP_ROM_QSTR(MP_QSTR_yolo26_det_postprocess), MP_ROM_PTR(&aidemo_yolo26_det_postprocess_obj) },
    { MP_ROM_QSTR(MP_QSTR_yolo_obb_postprocess), MP_ROM_PTR(&aidemo_yolo_obb_postprocess_obj) },
    { MP_ROM_QSTR(MP_QSTR_yolo26_obb_postprocess), MP_ROM_PTR(&aidemo_yolo26_obb_postprocess_obj) },
    { MP_ROM_QSTR(MP_QSTR_yolov5_det_postprocess), MP_ROM_PTR(&aidemo_yolov5_det_postprocess_obj) },
    { MP_ROM_QSTR(MP_QSTR_yolov8_pose_postprocess), MP_ROM_PTR(&aidemo_yolov8_pose_postprocess_obj) },
    { MP_ROM_QSTR(MP_QSTR_yolo26_pose_postprocess), MP_ROM_PTR(&aidemo_yolo26_pose_postprocess_obj) },
    { MP_ROM_QSTR(MP_QSTR_yunet_postprocess), MP_ROM_PTR(&aidemo_yunet_postprocess_obj) },
    { MP_ROM_QSTR(MP_QSTR_yolo_license_plate_det_postprocess), MP_ROM_PTR(&aidemo_yolo_license_plate_det_postprocess_obj) },
    { MP_ROM_QSTR(MP_QSTR_opencv_grayscale_find_blobs), MP_ROM_PTR(&aidemo_opencv_grayscale_find_blobs_obj) },
    { MP_ROM_QSTR(MP_QSTR_rgb888_compress), MP_ROM_PTR(&aidemo_rgb888_compress_obj) },
};

STATIC MP_DEFINE_CONST_DICT(aidemo_globals, aidemo_globals_table);

const mp_obj_module_t aidemo = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&aidemo_globals,
};

MP_REGISTER_EXTENSIBLE_MODULE(MP_QSTR_aidemo, aidemo);
