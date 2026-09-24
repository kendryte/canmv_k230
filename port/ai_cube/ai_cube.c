#include "py/compile.h"
#include "py/runtime.h"
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include "ndarray.h"
#include "postprocess.h"

STATIC ndarray_obj_t *aicube_require_ndarray(mp_obj_t obj, uint8_t dtype) {
    if (!mp_obj_is_type(obj, &ulab_ndarray_type)) {
        mp_raise_TypeError(MP_ERROR_TEXT("expected ndarray"));
    }
    ndarray_obj_t *array = MP_OBJ_TO_PTR(obj);
    if (array->dtype != dtype || !ndarray_is_dense(array)) {
        mp_raise_msg(&mp_type_ValueError, MP_ERROR_TEXT("invalid ndarray dtype or layout"));
    }
    return array;
}

STATIC mp_obj_list_t *aicube_require_list(mp_obj_t obj, size_t min_len) {
    if (!mp_obj_is_type(obj, &mp_type_list)) {
        mp_raise_TypeError(MP_ERROR_TEXT("expected list"));
    }
    mp_obj_list_t *list = MP_OBJ_TO_PTR(obj);
    if (list->len < min_len) {
        mp_raise_msg(&mp_type_ValueError, MP_ERROR_TEXT("list is too short"));
    }
    return list;
}

STATIC void aicube_require_positive_pair(mp_obj_list_t *shape) {
    if (mp_obj_get_int(shape->items[0]) <= 0 ||
        mp_obj_get_int(shape->items[1]) <= 0) {
        mp_raise_msg(&mp_type_ValueError, MP_ERROR_TEXT("shape values must be positive"));
    }
}

STATIC mp_obj_t aicube_detection_results_to_list(const ob_det_res *results,
                                                 size_t results_size) {
    mp_obj_list_t *mp_list = mp_obj_new_list(results_size, NULL);
    for (size_t i = 0; i < results_size; i++) {
        mp_obj_list_t *result = mp_obj_new_list(6, NULL);
        result->items[0] = mp_obj_new_int(results[i].label_index);
        result->items[1] = mp_obj_new_float(results[i].score);
        result->items[2] = mp_obj_new_int(results[i].x1);
        result->items[3] = mp_obj_new_int(results[i].y1);
        result->items[4] = mp_obj_new_int(results[i].x2);
        result->items[5] = mp_obj_new_int(results[i].y2);
        mp_list->items[i] = MP_OBJ_FROM_PTR(result);
    }
    return MP_OBJ_FROM_PTR(mp_list);
}

STATIC mp_obj_t aicube_ocr_post_process(size_t n_args, const mp_obj_t *args) {

    ndarray_obj_t *data_mp_0 = aicube_require_ndarray(args[0], NDARRAY_FLOAT);
    ndarray_obj_t *data_mp_1 = aicube_require_ndarray(args[1], NDARRAY_UINT8);
    float *data_0 = data_mp_0->array;
    uint8_t *data_1 = data_mp_1->array;

    mp_obj_list_t *kmodel_frame_size_mp = aicube_require_list(args[2], 2);
    mp_obj_list_t *frame_size_mp = aicube_require_list(args[3], 2);
    aicube_require_positive_pair(kmodel_frame_size_mp);
    aicube_require_positive_pair(frame_size_mp);
    float threshold = mp_obj_get_float(args[4]);
    float box_thresh = mp_obj_get_float(args[5]);
    int results_size;
    FrameSize frame_size;
    FrameSize kmodel_frame_size;
    frame_size.width = mp_obj_get_int(frame_size_mp->items[0]);
    frame_size.height = mp_obj_get_int(frame_size_mp->items[1]);
    kmodel_frame_size.width = mp_obj_get_int(kmodel_frame_size_mp->items[0]);
    kmodel_frame_size.height = mp_obj_get_int(kmodel_frame_size_mp->items[1]);
    ArrayWrapper* results = ocr_post_process(frame_size, kmodel_frame_size,box_thresh,threshold, data_0, data_1,&results_size);

    // Free the C result (and its per-item buffers) even if an MP allocation
    // below raises (longjmp). Each item's data/dimensions are NULLed as they
    // are freed on the success path, so this cleanup never double-frees.
    nlr_buf_t nlr;
    if (nlr_push(&nlr) != 0) {
        if (results != NULL) {
            for (int i = 0; i < results_size; i++) {
                free(results[i].data);
                free(results[i].dimensions);
            }
            free(results);
        }
        nlr_jump(nlr.ret_val);
    }
    mp_obj_list_t *mp_list = mp_obj_new_list(results_size, NULL);
    for (size_t i = 0; i < results_size; i++) {
        mp_obj_list_t *result = mp_obj_new_list(2, NULL);
        size_t ndarray_shape[4];

        ndarray_shape[0] = 1;
        ndarray_shape[1] = results[i].dimensions[1];
        ndarray_shape[2] = results[i].dimensions[2];
        ndarray_shape[3] = results[i].dimensions[0];

        ndarray_obj_t *data_output = ndarray_new_ndarray(4, ndarray_shape, NULL, NDARRAY_UINT8);

        uint8_t *data = (uint8_t*)data_output->array;
        size_t data_size = (size_t)results[i].dimensions[0] *
                           results[i].dimensions[1] * results[i].dimensions[2];
        memcpy(data, results[i].data, data_size);
        

        result->items[0] = MP_OBJ_FROM_PTR(data_output);

        size_t ndarray_shape_1[4];

        ndarray_shape_1[3] = 8;

        ndarray_obj_t *data_output_1 = ndarray_new_ndarray(1, ndarray_shape_1, NULL, NDARRAY_FLOAT);

        float *coordinates = (float*)data_output_1->array;
        memcpy(coordinates, results[i].coordinates, sizeof(results[i].coordinates));
        result->items[1] = MP_OBJ_FROM_PTR(data_output_1);
 
        if (results[i].data != NULL) {
            free(results[i].data);
            results[i].data = NULL;
        }
        if (results[i].dimensions != NULL) {
            free(results[i].dimensions);
            results[i].dimensions = NULL;
        }

        mp_list->items[i] = MP_OBJ_FROM_PTR(result);
    }

    nlr_pop();
    free(results);
    return mp_list;
}

STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(aicube_ocr_post_process_obj, 6, 6, aicube_ocr_post_process);


STATIC mp_obj_t aicube_anchorbasedet_post_process(size_t n_args, const mp_obj_t *args) {


    ndarray_obj_t *data_mp_0 = aicube_require_ndarray(args[0], NDARRAY_FLOAT);
    ndarray_obj_t *data_mp_1 = aicube_require_ndarray(args[1], NDARRAY_FLOAT);
    ndarray_obj_t *data_mp_2 = aicube_require_ndarray(args[2], NDARRAY_FLOAT);

    float *data_0 = data_mp_0->array;
    float *data_1 = data_mp_1->array;
    float *data_2 = data_mp_2->array;

    mp_obj_list_t *kmodel_frame_size_mp = aicube_require_list(args[3], 2);
    mp_obj_list_t *frame_size_mp = aicube_require_list(args[4], 2);
    mp_obj_list_t *strides_mp = aicube_require_list(args[5], 3);
    int num_class = mp_obj_get_int(args[6]);
    float ob_det_thresh = mp_obj_get_float(args[7]);
    float ob_nms_thresh = mp_obj_get_float(args[8]);
    mp_obj_list_t *anchors_mp = aicube_require_list(args[9], 18);
    bool nms_option = mp_obj_is_true(args[10]);
    int results_size;

    aicube_require_positive_pair(kmodel_frame_size_mp);
    aicube_require_positive_pair(frame_size_mp);
    if (num_class <= 0) mp_raise_msg(&mp_type_ValueError, MP_ERROR_TEXT("num_class must be positive"));
    int strides[3];
    float anchors[18];

    FrameSize frame_size;
    FrameSize kmodel_frame_size;
    frame_size.width = mp_obj_get_int(frame_size_mp->items[0]);
    frame_size.height = mp_obj_get_int(frame_size_mp->items[1]);
    kmodel_frame_size.width = mp_obj_get_int(kmodel_frame_size_mp->items[0]);
    kmodel_frame_size.height = mp_obj_get_int(kmodel_frame_size_mp->items[1]);

    for (int i = 0; i < 3; i++)
    {
        strides[i] = mp_obj_get_int(strides_mp->items[i]);
        if (strides[i] <= 0) mp_raise_msg(&mp_type_ValueError, MP_ERROR_TEXT("strides must be positive"));
    }

    for (int i = 0; i < 18; i++)
    {
        anchors[i] = mp_obj_get_float(anchors_mp->items[i]);
    }

    ob_det_res *results = anchorbasedet_post_process(data_0, data_1, data_2, kmodel_frame_size, frame_size, strides, num_class, ob_det_thresh, ob_nms_thresh, anchors, nms_option, &results_size);

    // Free the C result even if aicube_detection_results_to_list raises
    // (longjmp) while building the MicroPython lists.
    nlr_buf_t nlr;
    if (nlr_push(&nlr) != 0) { free(results); nlr_jump(nlr.ret_val); }
    mp_obj_t mp_list =
        aicube_detection_results_to_list(results, (size_t)results_size);
    nlr_pop();
    free(results);
    return mp_list;
}

STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(aicube_anchorbasedet_post_process_obj, 11, 11, aicube_anchorbasedet_post_process);

STATIC mp_obj_t aicube_anchorfreedet_post_process(size_t n_args, const mp_obj_t *args) {

    ndarray_obj_t *data_mp_0 = aicube_require_ndarray(args[0], NDARRAY_FLOAT);
    ndarray_obj_t *data_mp_1 = aicube_require_ndarray(args[1], NDARRAY_FLOAT);
    ndarray_obj_t *data_mp_2 = aicube_require_ndarray(args[2], NDARRAY_FLOAT);

    float *data_0 = data_mp_0->array;
    float *data_1 = data_mp_1->array;
    float *data_2 = data_mp_2->array;

    mp_obj_list_t *kmodel_frame_size_mp = aicube_require_list(args[3], 2);
    mp_obj_list_t *frame_size_mp = aicube_require_list(args[4], 2);
    mp_obj_list_t *strides_mp = aicube_require_list(args[5], 3);
    int num_class = mp_obj_get_int(args[6]);
    float ob_det_thresh = mp_obj_get_float(args[7]);
    float ob_nms_thresh = mp_obj_get_float(args[8]);
    bool nms_option = mp_obj_is_true(args[9]);
    int results_size;

    aicube_require_positive_pair(kmodel_frame_size_mp);
    aicube_require_positive_pair(frame_size_mp);
    if (num_class <= 0) mp_raise_msg(&mp_type_ValueError, MP_ERROR_TEXT("num_class must be positive"));
    int strides[3];

    FrameSize frame_size;
    FrameSize kmodel_frame_size;
    frame_size.width = mp_obj_get_int(frame_size_mp->items[0]);
    frame_size.height = mp_obj_get_int(frame_size_mp->items[1]);
    kmodel_frame_size.width = mp_obj_get_int(kmodel_frame_size_mp->items[0]);
    kmodel_frame_size.height = mp_obj_get_int(kmodel_frame_size_mp->items[1]);

    for (int i = 0; i < 3; i++)
    {
        strides[i] = mp_obj_get_int(strides_mp->items[i]);
        if (strides[i] <= 0) mp_raise_msg(&mp_type_ValueError, MP_ERROR_TEXT("strides must be positive"));
    }

    ob_det_res *results = anchorfreedet_post_process(data_0, data_1, data_2, kmodel_frame_size, frame_size, strides, num_class, ob_det_thresh, ob_nms_thresh, nms_option, &results_size);

    // Free the C result even if aicube_detection_results_to_list raises
    // (longjmp) while building the MicroPython lists.
    nlr_buf_t nlr;
    if (nlr_push(&nlr) != 0) { free(results); nlr_jump(nlr.ret_val); }
    mp_obj_t mp_list =
        aicube_detection_results_to_list(results, (size_t)results_size);
    nlr_pop();
    free(results);
    return mp_list;
}

STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(aicube_anchorfreedet_post_process_obj, 10, 10, aicube_anchorfreedet_post_process);

STATIC mp_obj_t aicube_gfldet_post_process(size_t n_args, const mp_obj_t *args) {

    ndarray_obj_t *data_mp_0 = aicube_require_ndarray(args[0], NDARRAY_FLOAT);
    ndarray_obj_t *data_mp_1 = aicube_require_ndarray(args[1], NDARRAY_FLOAT);
    ndarray_obj_t *data_mp_2 = aicube_require_ndarray(args[2], NDARRAY_FLOAT);

    float *data_0 = data_mp_0->array;
    float *data_1 = data_mp_1->array;
    float *data_2 = data_mp_2->array;

    mp_obj_list_t *kmodel_frame_size_mp = aicube_require_list(args[3], 2);
    mp_obj_list_t *frame_size_mp = aicube_require_list(args[4], 2);
    mp_obj_list_t *strides_mp = aicube_require_list(args[5], 3);
    int num_class = mp_obj_get_int(args[6]);
    float ob_det_thresh = mp_obj_get_float(args[7]);
    float ob_nms_thresh = mp_obj_get_float(args[8]);
    bool nms_option = mp_obj_is_true(args[9]);
    int results_size;

    aicube_require_positive_pair(kmodel_frame_size_mp);
    aicube_require_positive_pair(frame_size_mp);
    if (num_class <= 0) mp_raise_msg(&mp_type_ValueError, MP_ERROR_TEXT("num_class must be positive"));
    int strides[3];

    FrameSize frame_size;
    FrameSize kmodel_frame_size;
    frame_size.width = mp_obj_get_int(frame_size_mp->items[0]);
    frame_size.height = mp_obj_get_int(frame_size_mp->items[1]);
    kmodel_frame_size.width = mp_obj_get_int(kmodel_frame_size_mp->items[0]);
    kmodel_frame_size.height = mp_obj_get_int(kmodel_frame_size_mp->items[1]);

    for (int i = 0; i < 3; i++)
    {
        strides[i] = mp_obj_get_int(strides_mp->items[i]);
        if (strides[i] <= 0) mp_raise_msg(&mp_type_ValueError, MP_ERROR_TEXT("strides must be positive"));
    }

    ob_det_res *results = gfldet_post_process(data_0, data_1, data_2, kmodel_frame_size, frame_size, strides, num_class, ob_det_thresh, ob_nms_thresh, nms_option, &results_size);

    // Free the C result even if aicube_detection_results_to_list raises
    // (longjmp) while building the MicroPython lists.
    nlr_buf_t nlr;
    if (nlr_push(&nlr) != 0) { free(results); nlr_jump(nlr.ret_val); }
    mp_obj_t mp_list =
        aicube_detection_results_to_list(results, (size_t)results_size);
    nlr_pop();
    free(results);
    return mp_list;
}

STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(aicube_gfldet_post_process_obj, 10, 10, aicube_gfldet_post_process);

STATIC mp_obj_t aicube_seg_post_process(size_t n_args, const mp_obj_t *args) {
    ndarray_obj_t *data_mp = aicube_require_ndarray(args[0], NDARRAY_FLOAT);
    float *data = data_mp->array;
    int num_class = mp_obj_get_int(args[1]);
    mp_obj_list_t *ori_shape_mp = aicube_require_list(args[2], 2);
    mp_obj_list_t *dst_shape_mp = aicube_require_list(args[3], 2);
    aicube_require_positive_pair(ori_shape_mp);
    aicube_require_positive_pair(dst_shape_mp);
    if (num_class <= 0) mp_raise_msg(&mp_type_ValueError, MP_ERROR_TEXT("num_class must be positive"));

    FrameSize ori_shape;
    FrameSize dst_shape;

    ori_shape.height = mp_obj_get_int(ori_shape_mp->items[0]);
    ori_shape.width = mp_obj_get_int(ori_shape_mp->items[1]);
    dst_shape.height = mp_obj_get_int(dst_shape_mp->items[0]);
    dst_shape.width = mp_obj_get_int(dst_shape_mp->items[1]);

    size_t ndarray_shape[4];
    ndarray_shape[1] = dst_shape.height;
    ndarray_shape[2] = dst_shape.width;
    ndarray_shape[3] = 4;
    ndarray_obj_t *result_obj = ndarray_new_ndarray(3, ndarray_shape, NULL, NDARRAY_UINT8);

    uint8_t *result_data = (uint8_t *)result_obj->array;
    if (!seg_post_process_into(data, num_class, ori_shape, dst_shape,
                               result_data)) {
        mp_raise_msg(&mp_type_MemoryError,
                     MP_ERROR_TEXT("Segmentation postprocess failed"));
    }
    return MP_OBJ_FROM_PTR(result_obj);
}

STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(aicube_seg_post_process_obj, 4, 4, aicube_seg_post_process);
//| # Auto-generated CanMV stub docs. Edit the signatures/docstrings here.
//| module: aicube
//| """CanMV aicube module."""
//| def anchorbasedet_post_process(data_mp_0: Any, data_mp_1: Any, data_mp_2: Any, kmodel_frame_size_mp: Any, frame_size_mp: Any, strides_mp: Any, num_class: int, ob_det_thresh: float, ob_nms_thresh: float, anchors_mp: bool, nms_option: bool, /) -> Any:
//|     """Run anchorbasedet post-processing for aicube."""
//| def anchorfreedet_post_process(data_mp_0: Any, data_mp_1: int, data_mp_2: Any, kmodel_frame_size_mp: Any, frame_size_mp: Any, strides_mp: Any, num_class: int, ob_det_thresh: float, ob_nms_thresh: float, nms_option: bool, /) -> Any:
//|     """Run anchorfreedet post-processing for aicube."""
//| def gfldet_post_process(data_mp_0: Any, data_mp_1: int, data_mp_2: Any, kmodel_frame_size_mp: Any, frame_size_mp: Any, strides_mp: Any, num_class: int, ob_det_thresh: float, ob_nms_thresh: float, nms_option: bool, /) -> Any:
//|     """Run gfldet post-processing for aicube."""
//| def ocr_post_process(data_mp_0: Any, data_mp_1: Any, kmodel_frame_size_mp: Any, frame_size_mp: Any, threshold: float, box_thresh: float, /) -> Any:
//|     """Run ocr post-processing for aicube."""
//| def seg_post_process(data_mp: Any, num_class: int, ori_shape_mp: Any, dst_shape_mp: Any, /) -> Any:
//|     """Run seg post-processing for aicube."""


STATIC const mp_rom_map_elem_t aicube_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_aicube) },
    { MP_ROM_QSTR(MP_QSTR_ocr_post_process), MP_ROM_PTR(&aicube_ocr_post_process_obj) },
    { MP_ROM_QSTR(MP_QSTR_anchorbasedet_post_process), MP_ROM_PTR(&aicube_anchorbasedet_post_process_obj) },
    { MP_ROM_QSTR(MP_QSTR_anchorfreedet_post_process), MP_ROM_PTR(&aicube_anchorfreedet_post_process_obj) },
    { MP_ROM_QSTR(MP_QSTR_gfldet_post_process), MP_ROM_PTR(&aicube_gfldet_post_process_obj) },
    { MP_ROM_QSTR(MP_QSTR_seg_post_process), MP_ROM_PTR(&aicube_seg_post_process_obj) },
};

STATIC MP_DEFINE_CONST_DICT(aicube_globals, aicube_globals_table);

const mp_obj_module_t aicube = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&aicube_globals,
};

MP_REGISTER_EXTENSIBLE_MODULE(MP_QSTR_aicube, aicube);
