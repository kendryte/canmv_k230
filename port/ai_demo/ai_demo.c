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
#include <stdint.h>
#include <string.h>
#include "py/compile.h"
#include "py/runtime.h"
#include "py/binary.h"
#include "py/obj.h"
#include "ndarray.h"
#include "ulab.h"
#include "ai_demo.h"
#include "aidemo_type.h"
#include "aidemo_wrap.h"

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
            invert_affine_transform(p_matrix,&info);
            size_t *mp_shape = m_new(size_t, ULAB_MAX_DIMS);
            int32_t *mp_stride = m_new(int32_t, ULAB_MAX_DIMS);
            for(int i=0; i<info.ndim_; i++)
            {
                mp_shape[ULAB_MAX_DIMS - 1-i] = (size_t)info.shape_[info.ndim_ - 1 - i];
                mp_stride[ULAB_MAX_DIMS - 1-i] = (int32_t)info.strides_[info.ndim_ - 1 - i];
            }
            ndarray_obj_t *matrix_inv = ndarray_new_ndarray(info.ndim_, mp_shape, mp_stride, info.dtype_);
            memcpy((void *)matrix_inv->origin, (void *)info.data_, matrix_inv->len * matrix_inv->itemsize);

            free(info.data_);
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
    memset(in_info.shape_,0,sizeof(size_t)*3);
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
    memset(in_info.shape_,0,sizeof(size_t)*3);
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
    mp_obj_list_t *results_mp_list = mp_obj_new_list(0, NULL);
    if(result->vec_len>0)
    {    
        size_t *bbox_shape = m_new(size_t, ULAB_MAX_DIMS);
        bbox_shape[2] = result->vec_len;
        bbox_shape[3] = sizeof(Bbox) / sizeof(float);
        ndarray_obj_t *bbox_obj = ndarray_new_ndarray(2, bbox_shape, NULL, NDARRAY_FLOAT);
        float *bbox_data = (float *)bbox_obj->array;
        memcpy(bbox_data,result->bbox,sizeof(Bbox) * result->vec_len);
        free(result->bbox);
        mp_obj_list_append(results_mp_list, bbox_obj);

        size_t *kps_shape = m_new(size_t, ULAB_MAX_DIMS);
        kps_shape[2] = result->vec_len;
        kps_shape[3] = sizeof(SparseLandmarks) / sizeof(float);
        ndarray_obj_t *kps_obj = ndarray_new_ndarray(2, kps_shape, NULL, NDARRAY_FLOAT);
        float *kps_data = (float *)kps_obj->array;
        memcpy(kps_data,result->sparse_kps,sizeof(SparseLandmarks) * result->vec_len);
        free(result->sparse_kps);
        mp_obj_list_append(results_mp_list, kps_obj);

        size_t *score_shape = m_new(size_t, ULAB_MAX_DIMS);
        score_shape[2] = result->vec_len;
        score_shape[3] = sizeof(float) / sizeof(float);
        ndarray_obj_t *score_obj = ndarray_new_ndarray(2, score_shape, NULL, NDARRAY_FLOAT);
        float *score_data = (float *)score_obj->array;
        memcpy(score_data,result->score,sizeof(float) * result->vec_len);
        free(result->score);
        mp_obj_list_append(results_mp_list, score_obj);
    }
    free(result);
    
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
    memset(in_info.shape_,0,sizeof(size_t)*3);
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
    memset(in_info.shape_,0,sizeof(size_t)*3);
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
    ndarray_obj_t *dest_obj_ndarray = MP_ROM_PTR(dest_obj);
    float *dest_obj_ndarray_tmp = dest_obj_ndarray->array;
    float *dest = (float *)malloc(dest_obj_ndarray->len * sizeof(float));
    for (int i = 0; i < dest_obj_ndarray->len; i++) 
    {
        dest[i] = dest_obj_ndarray_tmp[i];
    }

    mp_obj_list_t *ori_shape_list = MP_OBJ_TO_PTR(ori_shape_obj);
    mp_obj_list_t *tag_shape_list = MP_OBJ_TO_PTR(tag_shape_obj);
    FrameSize ori_shape;
    FrameSize tag_shape;

    ori_shape.height = mp_obj_get_int(ori_shape_list->items[0]);
    ori_shape.width = mp_obj_get_int(ori_shape_list->items[1]);
    tag_shape.height = mp_obj_get_int(tag_shape_list->items[0]);
    tag_shape.width = mp_obj_get_int(tag_shape_list->items[1]);

    float* mask =  mask_resize(dest, ori_shape, tag_shape);

    size_t ndarray_shape[4];
    ndarray_shape[2] = tag_shape.height;
    ndarray_shape[3] = tag_shape.width;
    ndarray_obj_t *mask_obj = ndarray_new_ndarray(2, ndarray_shape, NULL, NDARRAY_FLOAT);

    float *data = (float *)mask_obj->array;
    for (int i = 0 ; i < tag_shape.height * tag_shape.width; i++)
    {
        data[i] =  mask[i];
    }

    free(dest);
    free(mask);
    return MP_OBJ_FROM_PTR(mask_obj);
};

STATIC MP_DEFINE_CONST_FUN_OBJ_3(aidemo_mask_resize_obj, aidemo_mask_resize);

STATIC mp_obj_t aidemo_ocr_rec_preprocess(mp_obj_t data_obj, mp_obj_t ori_shape_obj, mp_obj_t boxpoint8_obj) {
    ndarray_obj_t *data_obj_ndarray = MP_ROM_PTR(data_obj);
    uint8_t *data_obj_ndarray_tmp = data_obj_ndarray->array;
    uint8_t *data = (uint8_t *)malloc(data_obj_ndarray->len * sizeof(uint8_t));
    for (int i = 0; i < data_obj_ndarray->len; i++) 
    {
        data[i] = data_obj_ndarray_tmp[i];
    }

    mp_obj_list_t *ori_shape_list = MP_OBJ_TO_PTR(ori_shape_obj);
    FrameSize ori_shape;
    ori_shape.height = mp_obj_get_int(ori_shape_list->items[0]);
    ori_shape.width = mp_obj_get_int(ori_shape_list->items[1]);

    mp_obj_list_t *boxpoint8_list = MP_OBJ_TO_PTR(boxpoint8_obj);
    int box_cnt = boxpoint8_list->len;
    BoxPoint8 boxpoint8[box_cnt];
    for (int i = 0; i < boxpoint8_list->len; i++)
    {
        ndarray_obj_t *boxpoint8_ndarray = MP_ROM_PTR(boxpoint8_list->items[i]);
        float *boxpoint8_ndarray_tmp = boxpoint8_ndarray->array;
        for (int j = 0; j < 8; j++)
        {
            boxpoint8[i].points8[j] = boxpoint8_ndarray_tmp[j];
        }
    }

    ArrayWrapperMat1 *arrayWrapperMat1  = ocr_rec_pre_process(data, ori_shape, boxpoint8, box_cnt);

    mp_obj_list_t *results_mp_list = mp_obj_new_list(0, NULL);
    mp_obj_list_t *results_mp_list_array = mp_obj_new_list(0, NULL);
    mp_obj_list_t *results_mp_list_points = mp_obj_new_list(0, NULL);

    for (int i = 0; i < box_cnt; i++)
    {
        size_t ndarray_shape[4];
        ndarray_shape[0] = 1;
        ndarray_shape[1] = 1;
        ndarray_shape[2] = arrayWrapperMat1[i].framesize.height;
        ndarray_shape[3] = arrayWrapperMat1[i].framesize.width;
        ndarray_obj_t *crop_obj = ndarray_new_ndarray(4, ndarray_shape, NULL, NDARRAY_UINT8);
        uint8_t *crop_data = (uint8_t *)crop_obj->array;
        for (int j = 0 ; j < arrayWrapperMat1[i].framesize.height * arrayWrapperMat1[i].framesize.width; j++)
        {
            crop_data[j] =  arrayWrapperMat1[i].data[j];
        }
        mp_obj_list_append(results_mp_list_array, crop_obj);

        size_t point_shape[4];
        point_shape[3] = 8;
        ndarray_obj_t *point_obj = ndarray_new_ndarray(1, point_shape, NULL, NDARRAY_FLOAT);
        float *point_data = (float *)point_obj->array;
        for (int j = 0; j < 8; j++)
        {
            point_data[j] =  arrayWrapperMat1[i].coordinates[j];
        }
        mp_obj_list_append(results_mp_list_points, point_obj);
        free(arrayWrapperMat1[i].data);
    }
    mp_obj_list_append(results_mp_list, results_mp_list_array);
    mp_obj_list_append(results_mp_list, results_mp_list_points);
    free(arrayWrapperMat1);
    free(data);
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

    mp_obj_list_t *results_mp_list = mp_obj_new_list(0, NULL);
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
        mp_obj_list_append(results_mp_list, point_obj);
    }

    free(boxPoint8);
    return MP_OBJ_FROM_PTR(results_mp_list);
};

STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(aidemo_licence_det_postprocess_obj, 5, 5, aidemo_licence_det_postprocess);

//*****************************for object segment*****************************
STATIC mp_obj_t aidemo_segment_postprocess(size_t n_args, const mp_obj_t *args) {

    mp_obj_list_t *p_outputs_list = MP_OBJ_TO_PTR(args[0]);
    ndarray_obj_t *p_outputs_0_ndarray = MP_ROM_PTR(p_outputs_list->items[0]);
    float *data_0 = p_outputs_0_ndarray->array;
    
    ndarray_obj_t *p_outputs_1_ndarray = MP_ROM_PTR(p_outputs_list->items[1]);
    float *data_1 = p_outputs_1_ndarray->array;

    FrameSize frame_size;
    FrameSize kmodel_frame_size;
    FrameSize display_frame_size;
    float conf_thres;
    float nms_thres;
    float mask_thres;
    int box_cnt;

    mp_obj_list_t *frame_size_list = MP_OBJ_TO_PTR(args[1]);
    frame_size.height = mp_obj_get_int(frame_size_list->items[0]);
    frame_size.width = mp_obj_get_int(frame_size_list->items[1]);

    mp_obj_list_t *kmodel_frame_size_list = MP_OBJ_TO_PTR(args[2]);
    kmodel_frame_size.height = mp_obj_get_int(kmodel_frame_size_list->items[0]);
    kmodel_frame_size.width = mp_obj_get_int(kmodel_frame_size_list->items[1]);

    mp_obj_list_t *display_frame_size_list = MP_OBJ_TO_PTR(args[3]);
    display_frame_size.height = mp_obj_get_int(display_frame_size_list->items[0]);
    display_frame_size.width = mp_obj_get_int(display_frame_size_list->items[1]);

    conf_thres = mp_obj_get_float(args[4]);
    nms_thres = mp_obj_get_float(args[5]);
    mask_thres = mp_obj_get_float(args[6]);

    ndarray_obj_t *masks_results = MP_ROM_PTR(args[7]);
    uint8_t *masks_results_data = (uint8_t *)masks_results->array;

    SegOutputs segOutputs = object_seg_post_process(data_0, data_1, frame_size, kmodel_frame_size, display_frame_size, conf_thres, nms_thres, mask_thres, &box_cnt);

    mp_obj_list_t *results_mp_list = mp_obj_new_list(0, NULL);
    mp_obj_list_t *results_mp_list_boxes = mp_obj_new_list(0, NULL);
    mp_obj_list_t *results_mp_list_ids = mp_obj_new_list(0, NULL);
    mp_obj_list_t *results_mp_list_scores = mp_obj_new_list(0, NULL);
    
    for (int i = 0; i < display_frame_size.height * display_frame_size.width * 4; i++)
    {
        masks_results_data[i] = segOutputs.masks_results[i];
    }

    size_t ndarray_shape_box[4];
    ndarray_shape_box[3] = 4;
    for (int i = 0; i < box_cnt; i++)
    {
        ndarray_obj_t *box_obj = ndarray_new_ndarray(1, ndarray_shape_box, NULL, NDARRAY_INT16);
        int16_t *box_data = (int16_t *)box_obj->array;
        for (int j = 0; j < 4; j++)
        {
            box_data[j] = segOutputs.segOutput[i].box[j];
        }
        mp_obj_list_append(results_mp_list_boxes, box_obj);
        mp_obj_list_append(results_mp_list_ids, mp_obj_new_int(segOutputs.segOutput[i].id));
        mp_obj_list_append(results_mp_list_scores, mp_obj_new_float(segOutputs.segOutput[i].confidence));
    }
    mp_obj_list_append(results_mp_list, results_mp_list_boxes);
    mp_obj_list_append(results_mp_list, results_mp_list_ids);
    mp_obj_list_append(results_mp_list, results_mp_list_scores);


    free(segOutputs.masks_results);
    free(segOutputs.segOutput);
    return MP_OBJ_FROM_PTR(results_mp_list);
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

    mp_obj_list_t *results_mp_list = mp_obj_new_list(0, NULL);
    mp_obj_list_t *results_mp_list_boxes = mp_obj_new_list(0, NULL);
    mp_obj_list_t *results_mp_list_kpses = mp_obj_new_list(0, NULL);
    mp_obj_list_t *results_mp_list_confidences = mp_obj_new_list(0, NULL);

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

        mp_obj_list_append(results_mp_list_boxes, box_obj);
        mp_obj_list_append(results_mp_list_kpses, kps_obj);
        mp_obj_list_append(results_mp_list_confidences, mp_obj_new_float(personKPOutput[i].confidence));
    }
    mp_obj_list_append(results_mp_list, results_mp_list_boxes);
    mp_obj_list_append(results_mp_list, results_mp_list_kpses);
    mp_obj_list_append(results_mp_list, results_mp_list_confidences);


    free(personKPOutput);
    return MP_OBJ_FROM_PTR(results_mp_list);
};

STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(aidemo_person_kp_postprocess_obj, 5, 5, aidemo_person_kp_postprocess);

//*****************************for kws*****************************
STATIC mp_obj_t kws_feature_pipeline_create() {
    feature_pipeline* fp=feature_pipeline_create();
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
    mp_obj_list_t *wav_list = MP_OBJ_TO_PTR(wav_obj);
    size_t wav_length = wav_list->len;
    size_t feats_length = 1 * 30 * 40;
    // 检查输入参数是否合法
    if (wav_list == NULL || wav_length <= 0) {
        mp_raise_msg(&mp_type_ValueError, MP_ERROR_TEXT("Invalid input"));
        return mp_const_none;
    }
    // 分配内存来存储 wav 数组
    float* wav = (float *)malloc(wav_length * sizeof(float));
    if (wav == NULL) {
        mp_raise_msg(&mp_type_MemoryError, MP_ERROR_TEXT("Memory allocation failed"));
        return mp_const_none;
    }
    // 将 MicroPython 的列表转换为 C 数组
    for (size_t i = 0; i < wav_length; i++) {
        wav[i] =  mp_obj_get_float(wav_list->items[i]);
    }
    // 调用 C++ 函数
    feature_pipeline *fp_ = MP_OBJ_TO_PTR(fp);
    float *final_feats = (float *)malloc(feats_length * sizeof(float));
    wav_preprocess(fp_, wav, wav_length, final_feats);
    // 释放 wav 数组内存
    free(wav);
    // 创建 MicroPython 浮点数数组对象
    mp_obj_list_t *floats_array = mp_obj_new_list(0, NULL);
    // 将 C++ 函数的浮点数数据逐个转换并存储在 MicroPython 浮点数数组中
    for (size_t i = 0; i < feats_length; i++) {
        mp_obj_list_append(floats_array, mp_obj_new_float(final_feats[i]));
    }
    // 释放new的feats
    free(final_feats);
    // 创建结果列表
    mp_obj_list_t *result = mp_obj_new_list(0, NULL);
    mp_obj_list_append(result, floats_array);
    mp_obj_list_append(result, MP_OBJ_NEW_SMALL_INT(feats_length));
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

    mp_obj_list_t *reuslts_mp_list = mp_obj_new_list(0, NULL);
    mp_obj_list_append(reuslts_mp_list, mp_obj_new_float(pitch));
    mp_obj_list_append(reuslts_mp_list, mp_obj_new_float(yaw));

    return MP_OBJ_FROM_PTR(reuslts_mp_list);
};
STATIC MP_DEFINE_CONST_FUN_OBJ_1(aidemo_eye_gaze_post_process_obj, aidemo_eye_gaze_post_process);

//*****************************for nanotracker*****************************
STATIC mp_obj_t aidemo_nanotracker_postprocess(size_t n_args, const mp_obj_t *args) {

    ndarray_obj_t *p_outputs_ndarray_0 = MP_ROM_PTR(args[0]);
    float *data_0 = p_outputs_ndarray_0->array;

    ndarray_obj_t *p_outputs_ndarray_1 = MP_ROM_PTR(args[1]);
    float *data_1 = p_outputs_ndarray_1->array;
    

    FrameSize sensor_size;
    mp_obj_list_t *sensor_size_list = MP_OBJ_TO_PTR(args[2]);
    sensor_size.height = mp_obj_get_int(sensor_size_list->items[0]);
    sensor_size.width = mp_obj_get_int(sensor_size_list->items[1]);

    float obj_thresh;
    obj_thresh = mp_obj_get_float(args[3]);

    float center_xy_wh[4];
    mp_obj_list_t *center_xy_wh_list = MP_OBJ_TO_PTR(args[4]);
    center_xy_wh[0] = mp_obj_get_float(center_xy_wh_list->items[0]);
    center_xy_wh[1] = mp_obj_get_float(center_xy_wh_list->items[1]);
    center_xy_wh[2] = mp_obj_get_float(center_xy_wh_list->items[2]);
    center_xy_wh[3] = mp_obj_get_float(center_xy_wh_list->items[3]);

    int crop_size;
    crop_size = mp_obj_get_int(args[5]);

    float CONTEXT_AMOUNT;
    CONTEXT_AMOUNT = mp_obj_get_float(args[6]);

    Tracker_box_center tracker_box_center = nanotracker_post_process(data_0, data_1, sensor_size, obj_thresh, center_xy_wh, crop_size, CONTEXT_AMOUNT);

    mp_obj_list_t *results_mp_list = mp_obj_new_list(0, NULL);
    mp_obj_list_t *results_mp_list_box = mp_obj_new_list(0, NULL);
    mp_obj_list_t *results_mp_list_center = mp_obj_new_list(0, NULL);

    if (tracker_box_center.exist)
    {
        mp_obj_list_append(results_mp_list_box, mp_obj_new_int(tracker_box_center.tracker_box.x));
        mp_obj_list_append(results_mp_list_box, mp_obj_new_int(tracker_box_center.tracker_box.y));
        mp_obj_list_append(results_mp_list_box, mp_obj_new_int(tracker_box_center.tracker_box.w));
        mp_obj_list_append(results_mp_list_box, mp_obj_new_int(tracker_box_center.tracker_box.h));
        mp_obj_list_append(results_mp_list_box, mp_obj_new_float(tracker_box_center.tracker_box.score));

        mp_obj_list_append(results_mp_list_center, mp_obj_new_float(tracker_box_center.center_xy_wh[0]));
        mp_obj_list_append(results_mp_list_center, mp_obj_new_float(tracker_box_center.center_xy_wh[1]));
        mp_obj_list_append(results_mp_list_center, mp_obj_new_float(tracker_box_center.center_xy_wh[2]));
        mp_obj_list_append(results_mp_list_center, mp_obj_new_float(tracker_box_center.center_xy_wh[3]));
    }
    mp_obj_list_append(results_mp_list, results_mp_list_box);
    mp_obj_list_append(results_mp_list, results_mp_list_center);

    return MP_OBJ_FROM_PTR(results_mp_list);
};

STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(aidemo_nanotracker_postprocess_obj, 7, 7, aidemo_nanotracker_postprocess);

//*****************************for tts_zh*****************************
STATIC mp_obj_t tts_zh_create(mp_obj_t dictfile,mp_obj_t phasefile,mp_obj_t mapfile) {
    TtsZh *ttszh_=ttszh_create();
    const char* dictfile_=mp_obj_str_get_str(dictfile);
    const char* phasefile_=mp_obj_str_get_str(phasefile);
    const char* mapfile_=mp_obj_str_get_str(mapfile);
    ttszh_init(ttszh_,dictfile_,phasefile_,mapfile_);
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
    return MP_OBJ_FROM_PTR(result_mp_list);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_2(aidemo_tts_zh_preprocess_obj, tts_zh_preprocess);


STATIC mp_obj_t save_wav(size_t n_args, const mp_obj_t *args){
    mp_obj_list_t *wav_list = MP_OBJ_TO_PTR(args[0]);
    size_t wav_length = mp_obj_get_int(args[1]);
    const char* wav_path=mp_obj_str_get_str(args[2]);
    size_t sample_rate_ = mp_obj_get_int(args[4]);
    if (wav_list == NULL || wav_length <= 0) {
        mp_raise_msg(&mp_type_ValueError, MP_ERROR_TEXT("Invalid input"));
        return mp_const_none;
    }
    // 分配内存来存储 wav 数组
    float* wav = (float *)malloc(wav_length * sizeof(float));
    if (wav == NULL) {
        mp_raise_msg(&mp_type_MemoryError, MP_ERROR_TEXT("Memory allocation failed"));
        return mp_const_none;
    }
    // 将 MicroPython 的列表转换为 C 数组
    for (size_t i = 0; i < wav_length; i++) {
        wav[i] =  mp_obj_get_float(wav_list->items[i]);
    }
    tts_save_wav(wav,wav_length,wav_path,sample_rate_);
    // 释放 wav 数组内存
    free(wav);
    return mp_const_none;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(aidemo_save_wav_obj, 4, 4, save_wav);

//***********************************for body seg ******************/
STATIC mp_obj_t aidemo_body_seg_postprocess(size_t n_args, const mp_obj_t *args) {
    ndarray_obj_t *data_mp = MP_ROM_PTR(args[0]);
    float *data = data_mp->array;
    int num_class = mp_obj_get_int(args[1]);
    mp_obj_list_t *ori_shape_mp = MP_OBJ_TO_PTR(args[2]);
    mp_obj_list_t *dst_shape_mp = MP_OBJ_TO_PTR(args[3]);

    ndarray_obj_t *data_1_mp=MP_ROM_PTR(args[5]);
    uint8_t *data_1=data_1_mp->array;

    FrameSize ori_shape;
    FrameSize dst_shape;

    ori_shape.height = mp_obj_get_int(ori_shape_mp->items[0]);
    ori_shape.width = mp_obj_get_int(ori_shape_mp->items[1]);
    dst_shape.height = mp_obj_get_int(dst_shape_mp->items[0]);
    dst_shape.width = mp_obj_get_int(dst_shape_mp->items[1]);

    uint8_t *result = body_seg_postprocess(data, num_class, ori_shape, dst_shape, data_1);

    size_t ndarray_shape[4];
    ndarray_shape[1] = dst_shape.height;
    ndarray_shape[2] = dst_shape.width;
    ndarray_shape[3] = 4;
    ndarray_obj_t *result_obj = ndarray_new_ndarray(3, ndarray_shape, NULL, NDARRAY_UINT8);

    uint8_t *result_data = (uint8_t *)result_obj->array;
    for (int i=0; i<dst_shape.height*dst_shape.width*4; i++)
    {
        result_data[i] = result[i];
    }

    free(result);
    return MP_OBJ_FROM_PTR(result_obj);
}

STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(aidemo_body_seg_postprocess_obj, 5, 5, aidemo_body_seg_postprocess);

//***********************************for yolo seg ******************/
STATIC mp_obj_t aidemo_yolov5_seg_postprocess(size_t n_args, const mp_obj_t *args) {
    ndarray_obj_t *data_mp_0 = MP_ROM_PTR(args[0]);
    float *output0 = data_mp_0->array;

    ndarray_obj_t *data_mp_1 = MP_ROM_PTR(args[1]);
    float *output1 = data_mp_1->array;

    mp_obj_list_t *frame_size_mp = MP_OBJ_TO_PTR(args[2]);
    mp_obj_list_t *kmodel_input_size_mp = MP_OBJ_TO_PTR(args[3]);
    mp_obj_list_t *display_size_mp = MP_OBJ_TO_PTR(args[4]);

    int num_class = mp_obj_get_int(args[5]);

    float conf_thresh=mp_obj_get_float(args[6]);
    float nms_thresh=mp_obj_get_float(args[7]);
    float mask_thresh=mp_obj_get_float(args[8]);

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
    ndarray_obj_t *masks_results = MP_ROM_PTR(args[9]);
    uint8_t *masks_results_data = (uint8_t *)masks_results->array;

    SegOutputs segOutputs = yolov5_seg_postprocess(output0, output1, frame_shape, input_shape, display_shape,num_class, conf_thresh,nms_thresh,mask_thresh,&box_cnt);

    mp_obj_list_t *results_mp_list = mp_obj_new_list(0, NULL);
    mp_obj_list_t *results_mp_list_boxes = mp_obj_new_list(0, NULL);
    mp_obj_list_t *results_mp_list_ids = mp_obj_new_list(0, NULL);
    mp_obj_list_t *results_mp_list_scores = mp_obj_new_list(0, NULL);
    
    for (int i = 0; i < display_shape.height * display_shape.width * 4; i++)
    {
        masks_results_data[i] = segOutputs.masks_results[i];
    }

    size_t ndarray_shape_box[4];
    ndarray_shape_box[3] = 4;
    for (int i = 0; i < box_cnt; i++)
    {
        ndarray_obj_t *box_obj = ndarray_new_ndarray(1, ndarray_shape_box, NULL, NDARRAY_INT16);
        int16_t *box_data = (int16_t *)box_obj->array;
        for (int j = 0; j < 4; j++)
        {
            box_data[j] = segOutputs.segOutput[i].box[j];
        }
        mp_obj_list_append(results_mp_list_boxes, box_obj);
        mp_obj_list_append(results_mp_list_ids, mp_obj_new_int(segOutputs.segOutput[i].id));
        mp_obj_list_append(results_mp_list_scores, mp_obj_new_float(segOutputs.segOutput[i].confidence));
    }
    mp_obj_list_append(results_mp_list, results_mp_list_boxes);
    mp_obj_list_append(results_mp_list, results_mp_list_ids);
    mp_obj_list_append(results_mp_list, results_mp_list_scores);


    free(segOutputs.masks_results);
    free(segOutputs.segOutput);
    return MP_OBJ_FROM_PTR(results_mp_list);
}

STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(aidemo_yolov5_seg_postprocess_obj, 10, 10, aidemo_yolov5_seg_postprocess);


//***********************************for yolo seg ******************/
STATIC mp_obj_t aidemo_yolov8_seg_postprocess(size_t n_args, const mp_obj_t *args) {
    ndarray_obj_t *data_mp_0 = MP_ROM_PTR(args[0]);
    float *output0 = data_mp_0->array;

    ndarray_obj_t *data_mp_1 = MP_ROM_PTR(args[1]);
    float *output1 = data_mp_1->array;

    mp_obj_list_t *frame_size_mp = MP_OBJ_TO_PTR(args[2]);
    mp_obj_list_t *kmodel_input_size_mp = MP_OBJ_TO_PTR(args[3]);
    mp_obj_list_t *display_size_mp = MP_OBJ_TO_PTR(args[4]);

    int num_class = mp_obj_get_int(args[5]);

    float conf_thresh=mp_obj_get_float(args[6]);
    float nms_thresh=mp_obj_get_float(args[7]);
    float mask_thresh=mp_obj_get_float(args[8]);

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
    ndarray_obj_t *masks_results = MP_ROM_PTR(args[9]);
    uint8_t *masks_results_data = (uint8_t *)masks_results->array;

    SegOutputs segOutputs = yolov8_seg_postprocess(output0, output1, frame_shape, input_shape, display_shape,num_class, conf_thresh,nms_thresh,mask_thresh,&box_cnt);

    mp_obj_list_t *results_mp_list = mp_obj_new_list(0, NULL);
    mp_obj_list_t *results_mp_list_boxes = mp_obj_new_list(0, NULL);
    mp_obj_list_t *results_mp_list_ids = mp_obj_new_list(0, NULL);
    mp_obj_list_t *results_mp_list_scores = mp_obj_new_list(0, NULL);
    
    for (int i = 0; i < display_shape.height * display_shape.width * 4; i++)
    {
        masks_results_data[i] = segOutputs.masks_results[i];
    }

    size_t ndarray_shape_box[4];
    ndarray_shape_box[3] = 4;
    for (int i = 0; i < box_cnt; i++)
    {
        ndarray_obj_t *box_obj = ndarray_new_ndarray(1, ndarray_shape_box, NULL, NDARRAY_INT16);
        int16_t *box_data = (int16_t *)box_obj->array;
        for (int j = 0; j < 4; j++)
        {
            box_data[j] = segOutputs.segOutput[i].box[j];
        }
        mp_obj_list_append(results_mp_list_boxes, box_obj);
        mp_obj_list_append(results_mp_list_ids, mp_obj_new_int(segOutputs.segOutput[i].id));
        mp_obj_list_append(results_mp_list_scores, mp_obj_new_float(segOutputs.segOutput[i].confidence));
    }
    mp_obj_list_append(results_mp_list, results_mp_list_boxes);
    mp_obj_list_append(results_mp_list, results_mp_list_ids);
    mp_obj_list_append(results_mp_list, results_mp_list_scores);


    free(segOutputs.masks_results);
    free(segOutputs.segOutput);
    return MP_OBJ_FROM_PTR(results_mp_list);
}

STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(aidemo_yolov8_seg_postprocess_obj, 10, 10, aidemo_yolov8_seg_postprocess);

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

    mp_obj_list_t *results_mp_list = mp_obj_new_list(0, NULL);
    mp_obj_list_t *results_mp_list_boxes = mp_obj_new_list(0, NULL);
    mp_obj_list_t *results_mp_list_ids = mp_obj_new_list(0, NULL);
    mp_obj_list_t *results_mp_list_scores = mp_obj_new_list(0, NULL);

    size_t ndarray_shape_box[4];
    ndarray_shape_box[3] = 4;
    for (int i = 0; i < box_cnt; i++)
    {
        ndarray_obj_t *box_obj = ndarray_new_ndarray(1, ndarray_shape_box, NULL, NDARRAY_INT16);
        int16_t *box_data = (int16_t *)box_obj->array;
        box_data[0] = yolo_det_res[i].x;
        box_data[1] = yolo_det_res[i].y;
        box_data[2] = yolo_det_res[i].w;
        box_data[3] = yolo_det_res[i].h;
        mp_obj_list_append(results_mp_list_boxes, box_obj);
        mp_obj_list_append(results_mp_list_ids, mp_obj_new_int(yolo_det_res[i].index));
        mp_obj_list_append(results_mp_list_scores, mp_obj_new_float(yolo_det_res[i].confidence));
    }
    mp_obj_list_append(results_mp_list, results_mp_list_boxes);
    mp_obj_list_append(results_mp_list, results_mp_list_ids);
    mp_obj_list_append(results_mp_list, results_mp_list_scores);

    free(yolo_det_res);
    return MP_OBJ_FROM_PTR(results_mp_list);
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

    mp_obj_list_t *results_mp_list = mp_obj_new_list(0, NULL);
    mp_obj_list_t *results_mp_list_boxes = mp_obj_new_list(0, NULL);
    mp_obj_list_t *results_mp_list_ids = mp_obj_new_list(0, NULL);
    mp_obj_list_t *results_mp_list_scores = mp_obj_new_list(0, NULL);

    size_t ndarray_shape_box[4];
    ndarray_shape_box[3] = 4;
    for (int i = 0; i < box_cnt; i++)
    {
        ndarray_obj_t *box_obj = ndarray_new_ndarray(1, ndarray_shape_box, NULL, NDARRAY_INT16);
        int16_t *box_data = (int16_t *)box_obj->array;
        box_data[0] = yolo_det_res[i].x;
        box_data[1] = yolo_det_res[i].y;
        box_data[2] = yolo_det_res[i].w;
        box_data[3] = yolo_det_res[i].h;
        mp_obj_list_append(results_mp_list_boxes, box_obj);
        mp_obj_list_append(results_mp_list_ids, mp_obj_new_int(yolo_det_res[i].index));
        mp_obj_list_append(results_mp_list_scores, mp_obj_new_float(yolo_det_res[i].confidence));
    }
    mp_obj_list_append(results_mp_list, results_mp_list_boxes);
    mp_obj_list_append(results_mp_list, results_mp_list_ids);
    mp_obj_list_append(results_mp_list, results_mp_list_scores);

    free(yolo_det_res);
    return MP_OBJ_FROM_PTR(results_mp_list);
}

STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(aidemo_yolov5_det_postprocess_obj, 8, 8, aidemo_yolov5_det_postprocess);

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

    mp_obj_list_t *results_mp_list = mp_obj_new_list(0, NULL);
    mp_obj_list_t *results_mp_list_boxes = mp_obj_new_list(0, NULL);
    mp_obj_list_t *results_mp_list_ids = mp_obj_new_list(0, NULL);
    mp_obj_list_t *results_mp_list_scores = mp_obj_new_list(0, NULL);

    size_t ndarray_shape_box[8];
    ndarray_shape_box[3] = 8;
    for (int i = 0; i < box_cnt; i++)
    {
        ndarray_obj_t *box_obj = ndarray_new_ndarray(1, ndarray_shape_box, NULL, NDARRAY_INT16);
        int16_t *box_data = (int16_t *)box_obj->array;
        box_data[0] = yolo_obb_res[i].x1;
        box_data[1] = yolo_obb_res[i].y1;
        box_data[2] = yolo_obb_res[i].x2;
        box_data[3] = yolo_obb_res[i].y2;
        box_data[4] = yolo_obb_res[i].x3;
        box_data[5] = yolo_obb_res[i].y3;
        box_data[6] = yolo_obb_res[i].x4;
        box_data[7] = yolo_obb_res[i].y4;
        mp_obj_list_append(results_mp_list_boxes, box_obj);
        mp_obj_list_append(results_mp_list_ids, mp_obj_new_int(yolo_obb_res[i].index));
        mp_obj_list_append(results_mp_list_scores, mp_obj_new_float(yolo_obb_res[i].confidence));
    }
    mp_obj_list_append(results_mp_list, results_mp_list_boxes);
    mp_obj_list_append(results_mp_list, results_mp_list_ids);
    mp_obj_list_append(results_mp_list, results_mp_list_scores);

    free(yolo_obb_res);
    return MP_OBJ_FROM_PTR(results_mp_list);
}

STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(aidemo_yolo_obb_postprocess_obj, 8, 8, aidemo_yolo_obb_postprocess);

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

    mp_obj_list_t *results_mp_list = mp_obj_new_list(0, NULL);
    mp_obj_list_t *results_mp_list_boxes = mp_obj_new_list(0, NULL);
    mp_obj_list_t *results_mp_list_scores = mp_obj_new_list(0, NULL);

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
        mp_obj_list_append(results_mp_list_boxes, box_obj);
        mp_obj_list_append(results_mp_list_scores, mp_obj_new_float(yunet_face_det_res[i].score));
    }
    mp_obj_list_append(results_mp_list, results_mp_list_boxes);
    mp_obj_list_append(results_mp_list, results_mp_list_scores);

    free(yunet_face_det_res);
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
    mp_obj_list_t *results_mp_list = mp_obj_new_list(0, NULL);
    mp_obj_list_t *results_mp_list_boxes = mp_obj_new_list(0, NULL);
    mp_obj_list_t *results_mp_list_kps = mp_obj_new_list(0, NULL);
    mp_obj_list_t *results_mp_list_scores = mp_obj_new_list(0, NULL);

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
        mp_obj_list_append(results_mp_list_kps, kps_obj);
        mp_obj_list_append(results_mp_list_boxes, box_obj);
        mp_obj_list_append(results_mp_list_scores, mp_obj_new_float(yolo_license_plate_det_res[i].score));
    }
    mp_obj_list_append(results_mp_list, results_mp_list_kps);
    mp_obj_list_append(results_mp_list, results_mp_list_boxes);
    mp_obj_list_append(results_mp_list, results_mp_list_scores);
    free(yolo_license_plate_det_res);
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

    mp_obj_list_t *int_array = mp_obj_new_list(0, NULL);

    for (int i = 0; i < ret_num; i++)
    {
        mp_obj_list_append(int_array, mp_obj_new_int(ret[i*4+0]));
        mp_obj_list_append(int_array, mp_obj_new_int(ret[i*4+1]));
        mp_obj_list_append(int_array, mp_obj_new_int(ret[i*4+2]));
        mp_obj_list_append(int_array, mp_obj_new_int(ret[i*4+3]));
    }
    free(ret);
    return MP_OBJ_FROM_PTR(int_array);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(aidemo_opencv_grayscale_find_blobs_obj, 4, 4, aidemo_opencv_grayscale_find_blobs);

STATIC mp_obj_t aidemo_rgb888_compress(size_t n_args, const mp_obj_t *args)
{
    mp_obj_list_t *frame_size_mp = MP_OBJ_TO_PTR(args[0]);
    ndarray_obj_t *data = MP_ROM_PTR(args[1]); // hwc
    uint8_t *img_data = data->array;

    // 构造图像尺寸
    FrameSize frame_shape;
    frame_shape.height = mp_obj_get_int(frame_size_mp->items[0]);
    frame_shape.width  = mp_obj_get_int(frame_size_mp->items[1]);
    // 处理：JPEG 压缩
    int jpeg_quality = mp_obj_get_int(args[2]);
    uint8_t* result=(uint8_t*)malloc(frame_shape.width*frame_shape.height*3);
    // 处理：JPEG 压缩
    rgb888_compress(frame_shape, img_data, jpeg_quality, result);
    // 构造返回的 numpy 对象（共享内存，不复制）
    size_t ndarray_shape[4];
    ndarray_shape[1] = frame_shape.height;
    ndarray_shape[2] = frame_shape.width;
    ndarray_shape[3] = 3;
    ndarray_obj_t *out = ndarray_new_ndarray(3, ndarray_shape, NULL, NDARRAY_UINT8);
    uint8_t *out_data = (uint8_t *)out->array;
    memcpy(out_data, result, frame_shape.width * frame_shape.height * 3);
    free(result);
    return MP_OBJ_FROM_PTR(out);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(aidemo_rgb888_compress_obj, 3, 3, aidemo_rgb888_compress);


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
    { MP_ROM_QSTR(MP_QSTR_yolov8_det_postprocess), MP_ROM_PTR(&aidemo_yolov8_det_postprocess_obj) },
    { MP_ROM_QSTR(MP_QSTR_yolo_obb_postprocess), MP_ROM_PTR(&aidemo_yolo_obb_postprocess_obj) },
    { MP_ROM_QSTR(MP_QSTR_yolov5_det_postprocess), MP_ROM_PTR(&aidemo_yolov5_det_postprocess_obj) },
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