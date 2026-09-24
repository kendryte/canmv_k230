/* Copyright (c) 2026, Canaan Bright Sight Co., Ltd
 * SPDX-License-Identifier: BSD-3-Clause
 */
#include <math.h>
#include <stdbool.h>
#include <limits.h>
#include <stdint.h>
#include <string.h>

#include "py/obj.h"
#include "py/runtime.h"
#include "mot_bridge.h"

typedef struct {
    mp_obj_base_t base;
    mot_tracker_handle_t *tracker;
    bool xywh;
} mot_obj_t;

static bool parse_bbox_format(mp_obj_t value)
{
    const char *s = mp_obj_str_get_str(value);
    if (strcmp(s, "xyxy") == 0) return false;
    if (strcmp(s, "xywh") == 0) return true;
    mp_raise_ValueError(MP_ERROR_TEXT("bbox_format must be 'xyxy' or 'xywh'"));
}

static void check_probability(float value, const char *name)
{
    if (!isfinite(value) || value < 0.0f || value > 1.0f)
        mp_raise_msg_varg(&mp_type_ValueError,
                          MP_ERROR_TEXT("%s must be finite and in [0, 1]"), name);
}

// A NULL object lets static mp_arg_t tables represent a floating-point default
// without treating arbitrary values above one as percentages.
static float probability_arg(mp_obj_t value, float default_value)
{
    return value == MP_OBJ_NULL ? default_value : mp_obj_get_float(value);
}

static int scaled_track_buffer(mp_int_t track_buffer, mp_int_t frame_rate)
{
    if (track_buffer < 1 || frame_rate < 1)
        mp_raise_ValueError(MP_ERROR_TEXT("track_buffer and frame_rate must be positive"));
    if (track_buffer > INT_MAX || frame_rate > INT_MAX)
        mp_raise_ValueError(MP_ERROR_TEXT("track_buffer or frame_rate is out of range"));
    int64_t frames = (int64_t)track_buffer * (int64_t)frame_rate / 30;
    if (frames < 1 || frames > INT_MAX)
        mp_raise_ValueError(MP_ERROR_TEXT("scaled track_buffer is out of range"));
    return (int)frames;
}

static mot_obj_t *new_tracker(const mp_obj_type_t *type, mot_algorithm_t algorithm,
                              const mot_params_t *params, bool xywh)
{
    const char *error = NULL;
    mot_obj_t *self = m_new_obj_with_finaliser(mot_obj_t);
    self->base.type = type;
    self->xywh = xywh;
    self->tracker = mot_tracker_create(algorithm, params, &error);
    if (self->tracker == NULL) {
        if (error == NULL || strcmp(error, "cannot allocate tracker") == 0)
            mp_raise_msg(&mp_type_MemoryError, MP_ERROR_TEXT("cannot allocate tracker"));
        mp_raise_msg_varg(&mp_type_ValueError, MP_ERROR_TEXT("%s"), error);
    }
    return self;
}

static mp_obj_t mot_bytetrack_make_new(const mp_obj_type_t *type, size_t n_args,
                                       size_t n_kw, const mp_obj_t *all_args)
{
    enum { A_track_thresh, A_high_thresh, A_match_thresh, A_track_buffer,
           A_frame_rate, A_min_hits, A_class_aware, A_bbox_format };
    static const mp_arg_t allowed[] = {
        { MP_QSTR_track_thresh, MP_ARG_KW_ONLY | MP_ARG_OBJ, {.u_obj = MP_OBJ_NULL} },
        { MP_QSTR_high_thresh, MP_ARG_KW_ONLY | MP_ARG_OBJ, {.u_obj = MP_OBJ_NULL} },
        { MP_QSTR_match_thresh, MP_ARG_KW_ONLY | MP_ARG_OBJ, {.u_obj = MP_OBJ_NULL} },
        { MP_QSTR_track_buffer, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = 30} },
        { MP_QSTR_frame_rate, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = 30} },
        { MP_QSTR_min_hits, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = 1} },
        { MP_QSTR_class_aware, MP_ARG_KW_ONLY | MP_ARG_BOOL, {.u_bool = true} },
        { MP_QSTR_bbox_format, MP_ARG_KW_ONLY | MP_ARG_OBJ, {.u_obj = MP_OBJ_NEW_QSTR(MP_QSTR_xyxy)} },
    };
    mp_arg_check_num(n_args, n_kw, 0, 0, true);
    mp_map_t kw; mp_map_init_fixed_table(&kw, n_kw, all_args + n_args);
    mp_arg_val_t a[MP_ARRAY_SIZE(allowed)];
    mp_arg_parse_all(n_args, all_args, &kw, MP_ARRAY_SIZE(allowed), allowed, a);
    mot_params_t p = mot_default_params();
    p.track_low_thresh = 0.1f;
    p.track_high_thresh = probability_arg(a[A_track_thresh].u_obj, 0.5f);
    p.new_track_thresh = probability_arg(a[A_high_thresh].u_obj, 0.6f);
    p.match_thresh = probability_arg(a[A_match_thresh].u_obj, 0.8f);
    p.max_age = scaled_track_buffer(a[A_track_buffer].u_int, a[A_frame_rate].u_int);
    p.min_hits = a[A_min_hits].u_int;
    p.class_aware = a[A_class_aware].u_bool;
    check_probability(p.track_low_thresh, "track_thresh");
    check_probability(p.track_high_thresh, "track_thresh");
    check_probability(p.new_track_thresh, "high_thresh");
    check_probability(p.match_thresh, "match_thresh");
    if (p.track_low_thresh > p.track_high_thresh || p.new_track_thresh < p.track_high_thresh ||
        p.max_age < 1 || p.min_hits < 1)
        mp_raise_ValueError(MP_ERROR_TEXT("invalid ByteTrack thresholds or lifetime"));
    return MP_OBJ_FROM_PTR(new_tracker(type, MOT_ALGORITHM_BYTETRACK, &p,
                                       parse_bbox_format(a[A_bbox_format].u_obj)));
}

static mp_obj_t mot_ocsort_make_new(const mp_obj_type_t *type, size_t n_args,
                                    size_t n_kw, const mp_obj_t *all_args)
{
    enum { A_det_thresh, A_max_age, A_min_hits, A_iou_threshold, A_delta_t,
           A_inertia, A_use_byte, A_class_aware, A_bbox_format };
    static const mp_arg_t allowed[] = {
        { MP_QSTR_det_thresh, MP_ARG_KW_ONLY | MP_ARG_OBJ, {.u_obj = MP_OBJ_NULL} },
        { MP_QSTR_max_age, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = 30} },
        { MP_QSTR_min_hits, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = 3} },
        { MP_QSTR_iou_threshold, MP_ARG_KW_ONLY | MP_ARG_OBJ, {.u_obj = MP_OBJ_NULL} },
        { MP_QSTR_delta_t, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = 3} },
        { MP_QSTR_inertia, MP_ARG_KW_ONLY | MP_ARG_OBJ, {.u_obj = MP_OBJ_NULL} },
        { MP_QSTR_use_byte, MP_ARG_KW_ONLY | MP_ARG_BOOL, {.u_bool = false} },
        { MP_QSTR_class_aware, MP_ARG_KW_ONLY | MP_ARG_BOOL, {.u_bool = true} },
        { MP_QSTR_bbox_format, MP_ARG_KW_ONLY | MP_ARG_OBJ, {.u_obj = MP_OBJ_NEW_QSTR(MP_QSTR_xyxy)} },
    };
    mp_arg_check_num(n_args, n_kw, 0, 0, true);
    mp_map_t kw; mp_map_init_fixed_table(&kw, n_kw, all_args + n_args);
    mp_arg_val_t a[MP_ARRAY_SIZE(allowed)];
    mp_arg_parse_all(n_args, all_args, &kw, MP_ARRAY_SIZE(allowed), allowed, a);
    mot_params_t p = mot_default_params();
    p.det_thresh = probability_arg(a[A_det_thresh].u_obj, 0.3f);
    p.max_age = a[A_max_age].u_int; p.min_hits = a[A_min_hits].u_int;
    p.iou_threshold = probability_arg(a[A_iou_threshold].u_obj, 0.3f);
    p.delta_t = a[A_delta_t].u_int;
    p.inertia = probability_arg(a[A_inertia].u_obj, 0.2f);
    p.use_byte = a[A_use_byte].u_bool; p.class_aware = a[A_class_aware].u_bool;
    check_probability(p.det_thresh, "det_thresh");
    check_probability(p.iou_threshold, "iou_threshold");
    check_probability(p.inertia, "inertia");
    if (p.max_age < 1 || p.min_hits < 1 || p.delta_t < 1)
        mp_raise_ValueError(MP_ERROR_TEXT("age, hits, and delta_t must be positive"));
    return MP_OBJ_FROM_PTR(new_tracker(type, MOT_ALGORITHM_OCSORT, &p,
                                       parse_bbox_format(a[A_bbox_format].u_obj)));
}

static mp_obj_t mot_deepsort_make_new(const mp_obj_type_t *type, size_t n_args,
                                      size_t n_kw, const mp_obj_t *all_args)
{
    enum { A_feature_dim, A_max_cosine_distance, A_nn_budget, A_max_iou_distance,
           A_max_age, A_n_init, A_class_aware, A_bbox_format };
    static const mp_arg_t allowed[] = {
        { MP_QSTR_feature_dim, MP_ARG_KW_ONLY | MP_ARG_REQUIRED | MP_ARG_INT, {.u_int = 0} },
        { MP_QSTR_max_cosine_distance, MP_ARG_KW_ONLY | MP_ARG_OBJ, {.u_obj = MP_OBJ_NULL} },
        { MP_QSTR_nn_budget, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = 100} },
        { MP_QSTR_max_iou_distance, MP_ARG_KW_ONLY | MP_ARG_OBJ, {.u_obj = MP_OBJ_NULL} },
        { MP_QSTR_max_age, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = 30} },
        { MP_QSTR_n_init, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = 3} },
        { MP_QSTR_class_aware, MP_ARG_KW_ONLY | MP_ARG_BOOL, {.u_bool = true} },
        { MP_QSTR_bbox_format, MP_ARG_KW_ONLY | MP_ARG_OBJ, {.u_obj = MP_OBJ_NEW_QSTR(MP_QSTR_xyxy)} },
    };
    mp_arg_check_num(n_args, n_kw, 0, 0, true);
    mp_map_t kw; mp_map_init_fixed_table(&kw, n_kw, all_args + n_args);
    mp_arg_val_t a[MP_ARRAY_SIZE(allowed)];
    mp_arg_parse_all(n_args, all_args, &kw, MP_ARRAY_SIZE(allowed), allowed, a);
    mot_params_t p = mot_default_params();
    p.feature_dim = a[A_feature_dim].u_int;
    p.max_cosine_distance = probability_arg(a[A_max_cosine_distance].u_obj, 0.2f);
    p.nn_budget = a[A_nn_budget].u_int;
    p.max_iou_distance = probability_arg(a[A_max_iou_distance].u_obj, 0.7f);
    p.max_age = a[A_max_age].u_int; p.min_hits = a[A_n_init].u_int;
    p.class_aware = a[A_class_aware].u_bool;
    check_probability(p.max_cosine_distance, "max_cosine_distance");
    check_probability(p.max_iou_distance, "max_iou_distance");
    if (p.feature_dim < 1 || p.nn_budget < 1 || p.max_age < 1 || p.min_hits < 1)
        mp_raise_ValueError(MP_ERROR_TEXT("feature_dim, budget, age, and n_init must be positive"));
    return MP_OBJ_FROM_PTR(new_tracker(type, MOT_ALGORITHM_DEEPSORT, &p,
                                       parse_bbox_format(a[A_bbox_format].u_obj)));
}

static mp_obj_t mot_botsort_make_new(const mp_obj_type_t *type, size_t n_args,
                                     size_t n_kw, const mp_obj_t *all_args)
{
    enum { A_feature_dim, A_reid_enabled, A_track_high_thresh, A_track_low_thresh,
           A_new_track_thresh, A_track_buffer, A_match_thresh, A_proximity_thresh,
           A_appearance_thresh, A_appearance_weight, A_frame_rate, A_min_hits,
           A_class_aware, A_bbox_format };
    static const mp_arg_t allowed[] = {
        { MP_QSTR_feature_dim, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = 0} },
        { MP_QSTR_reid_enabled, MP_ARG_KW_ONLY | MP_ARG_BOOL, {.u_bool = false} },
        { MP_QSTR_track_high_thresh, MP_ARG_KW_ONLY | MP_ARG_OBJ, {.u_obj = MP_OBJ_NULL} },
        { MP_QSTR_track_low_thresh, MP_ARG_KW_ONLY | MP_ARG_OBJ, {.u_obj = MP_OBJ_NULL} },
        { MP_QSTR_new_track_thresh, MP_ARG_KW_ONLY | MP_ARG_OBJ, {.u_obj = MP_OBJ_NULL} },
        { MP_QSTR_track_buffer, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = 30} },
        { MP_QSTR_match_thresh, MP_ARG_KW_ONLY | MP_ARG_OBJ, {.u_obj = MP_OBJ_NULL} },
        { MP_QSTR_proximity_thresh, MP_ARG_KW_ONLY | MP_ARG_OBJ, {.u_obj = MP_OBJ_NULL} },
        { MP_QSTR_appearance_thresh, MP_ARG_KW_ONLY | MP_ARG_OBJ, {.u_obj = MP_OBJ_NULL} },
        { MP_QSTR_appearance_weight, MP_ARG_KW_ONLY | MP_ARG_OBJ, {.u_obj = MP_OBJ_NULL} },
        { MP_QSTR_frame_rate, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = 30} },
        { MP_QSTR_min_hits, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = 1} },
        { MP_QSTR_class_aware, MP_ARG_KW_ONLY | MP_ARG_BOOL, {.u_bool = true} },
        { MP_QSTR_bbox_format, MP_ARG_KW_ONLY | MP_ARG_OBJ, {.u_obj = MP_OBJ_NEW_QSTR(MP_QSTR_xyxy)} },
    };
    mp_arg_check_num(n_args, n_kw, 0, 0, true);
    mp_map_t kw; mp_map_init_fixed_table(&kw, n_kw, all_args + n_args);
    mp_arg_val_t a[MP_ARRAY_SIZE(allowed)];
    mp_arg_parse_all(n_args, all_args, &kw, MP_ARRAY_SIZE(allowed), allowed, a);
    mot_params_t p = mot_default_params();
    p.feature_dim = a[A_feature_dim].u_int; p.reid_enabled = a[A_reid_enabled].u_bool;
    if (!p.reid_enabled) p.feature_dim = 0;
    p.track_high_thresh = probability_arg(a[A_track_high_thresh].u_obj, 0.6f);
    p.track_low_thresh = probability_arg(a[A_track_low_thresh].u_obj, 0.1f);
    p.new_track_thresh = probability_arg(a[A_new_track_thresh].u_obj, 0.7f);
    p.max_age = scaled_track_buffer(a[A_track_buffer].u_int, a[A_frame_rate].u_int);
    p.match_thresh = probability_arg(a[A_match_thresh].u_obj, 0.7f);
    p.proximity_thresh = probability_arg(a[A_proximity_thresh].u_obj, 0.5f);
    p.appearance_thresh = probability_arg(a[A_appearance_thresh].u_obj, 0.25f);
    p.appearance_weight = probability_arg(a[A_appearance_weight].u_obj, 0.985f);
    p.min_hits = a[A_min_hits].u_int; p.class_aware = a[A_class_aware].u_bool;
    check_probability(p.track_high_thresh, "track_high_thresh");
    check_probability(p.track_low_thresh, "track_low_thresh");
    check_probability(p.new_track_thresh, "new_track_thresh");
    check_probability(p.match_thresh, "match_thresh");
    check_probability(p.proximity_thresh, "proximity_thresh");
    check_probability(p.appearance_thresh, "appearance_thresh");
    check_probability(p.appearance_weight, "appearance_weight");
    if (p.track_low_thresh > p.track_high_thresh ||
        p.new_track_thresh < p.track_high_thresh ||
        p.max_age < 1 || p.min_hits < 1 ||
        (p.reid_enabled && p.feature_dim < 1))
        mp_raise_ValueError(MP_ERROR_TEXT("invalid BoTSORT parameters"));
    return MP_OBJ_FROM_PTR(new_tracker(type, MOT_ALGORITHM_BOTSORT, &p,
                                       parse_bbox_format(a[A_bbox_format].u_obj)));
}

static mot_obj_t *get_open(mp_obj_t self_in)
{
    mot_obj_t *self = MP_OBJ_TO_PTR(self_in);
    if (self->tracker == NULL) mp_raise_ValueError(MP_ERROR_TEXT("tracker is closed"));
    return self;
}

static mot_detection_t *parse_detections(mot_obj_t *self, mp_obj_t boxes_obj,
                                          mp_obj_t scores_obj, mp_obj_t classes_obj,
                                          mp_obj_t features_obj, size_t *out_count,
                                          float **out_features)
{
    size_t count, score_count, class_count;
    mp_obj_t *boxes, *scores, *classes;
    mp_obj_get_array(boxes_obj, &count, &boxes);
    mp_obj_get_array(scores_obj, &score_count, &scores);
    mp_obj_get_array(classes_obj, &class_count, &classes);
    if (score_count != count || class_count != count)
        mp_raise_ValueError(MP_ERROR_TEXT("boxes, scores, and class_ids must have equal length"));

    const int feature_dim = mot_tracker_feature_dim(self->tracker);
    const bool features_required = mot_tracker_features_required(self->tracker);
    size_t feature_count = 0;
    mp_obj_t *features = NULL;
    if (features_obj != mp_const_none) mp_obj_get_array(features_obj, &feature_count, &features);
    if (count > 0 && features_required && features_obj == mp_const_none)
        mp_raise_ValueError(MP_ERROR_TEXT("features are required for this tracker"));
    if (features_obj != mp_const_none && feature_count != count)
        mp_raise_ValueError(MP_ERROR_TEXT("features must have one row per detection"));
    if (features_obj != mp_const_none && feature_dim <= 0)
        mp_raise_ValueError(MP_ERROR_TEXT("this tracker does not accept features"));

    mot_detection_t *out = count ? m_new(mot_detection_t, count) : NULL;
    float *feature_data = (count && feature_dim > 0) ? m_new(float, count * feature_dim) : NULL;
    for (size_t i = 0; i < count; ++i) {
        size_t box_count;
        mp_obj_t *box_values;
        mp_obj_get_array(boxes[i], &box_count, &box_values);
        if (box_count != 4) mp_raise_ValueError(MP_ERROR_TEXT("each box must contain four values"));
        float v[4];
        for (int k = 0; k < 4; ++k) {
            v[k] = mp_obj_get_float(box_values[k]);
            if (!isfinite(v[k])) mp_raise_ValueError(MP_ERROR_TEXT("box values must be finite"));
        }
        out[i].x1 = v[0]; out[i].y1 = v[1];
        out[i].x2 = self->xywh ? v[0] + v[2] : v[2];
        out[i].y2 = self->xywh ? v[1] + v[3] : v[3];
        if (out[i].x2 <= out[i].x1 || out[i].y2 <= out[i].y1)
            mp_raise_ValueError(MP_ERROR_TEXT("box width and height must be positive"));
        out[i].score = mp_obj_get_float(scores[i]);
        check_probability(out[i].score, "score");
        out[i].class_id = mp_obj_get_int(classes[i]);
        if (out[i].class_id < 0) mp_raise_ValueError(MP_ERROR_TEXT("class_ids must be non-negative"));
        out[i].feature = NULL; out[i].feature_dim = 0;
        if (features_obj != mp_const_none) {
            size_t dim;
            mp_obj_t *row;
            mp_obj_get_array(features[i], &dim, &row);
            if (dim != (size_t)feature_dim)
                mp_raise_ValueError(MP_ERROR_TEXT("feature row has wrong dimension"));
            double norm = 0.0;
            float *destination = feature_data + i * feature_dim;
            for (size_t k = 0; k < dim; ++k) {
                destination[k] = mp_obj_get_float(row[k]);
                if (!isfinite(destination[k])) mp_raise_ValueError(MP_ERROR_TEXT("features must be finite"));
                norm += (double)destination[k] * destination[k];
            }
            if (norm <= 1.0e-12) mp_raise_ValueError(MP_ERROR_TEXT("feature vectors must have non-zero norm"));
            out[i].feature = destination; out[i].feature_dim = dim;
        }
    }
    *out_count = count;
    *out_features = feature_data;
    return out;
}

static mp_obj_t result_list(mot_obj_t *self, bool include_lost)
{
    size_t count = mot_tracker_results(self->tracker, include_lost, NULL, 0);
    mot_result_t *results = count ? m_new(mot_result_t, count) : NULL;
    mot_tracker_results(self->tracker, include_lost, results, count);
    mp_obj_t list = mp_obj_new_list(0, NULL);
    for (size_t i = 0; i < count; ++i) {
        const mot_result_t *r = &results[i];
        mp_obj_t dict = mp_obj_new_dict(8);
        mp_obj_t bbox_items[4] = {
            mp_obj_new_float(r->x1), mp_obj_new_float(r->y1),
            mp_obj_new_float(self->xywh ? r->x2 - r->x1 : r->x2),
            mp_obj_new_float(self->xywh ? r->y2 - r->y1 : r->y2),
        };
        mp_obj_dict_store(dict, MP_OBJ_NEW_QSTR(MP_QSTR_track_id), mp_obj_new_int(r->track_id));
        mp_obj_dict_store(dict, MP_OBJ_NEW_QSTR(MP_QSTR_class_id), mp_obj_new_int(r->class_id));
        mp_obj_dict_store(dict, MP_OBJ_NEW_QSTR(MP_QSTR_bbox), mp_obj_new_tuple(4, bbox_items));
        mp_obj_dict_store(dict, MP_OBJ_NEW_QSTR(MP_QSTR_score), mp_obj_new_float(r->score));
        mp_obj_dict_store(dict, MP_OBJ_NEW_QSTR(MP_QSTR_state), mp_obj_new_str(r->state, strlen(r->state)));
        mp_obj_dict_store(dict, MP_OBJ_NEW_QSTR(MP_QSTR_age), mp_obj_new_int(r->age));
        mp_obj_dict_store(dict, MP_OBJ_NEW_QSTR(MP_QSTR_hits), mp_obj_new_int(r->hits));
        mp_obj_dict_store(dict, MP_OBJ_NEW_QSTR(MP_QSTR_time_since_update), mp_obj_new_int(r->time_since_update));
        mp_obj_list_append(list, dict);
    }
    if (results != NULL) m_del(mot_result_t, results, count);
    return list;
}

static mp_obj_t mot_update(size_t n_args, const mp_obj_t *args)
{
    mot_obj_t *self = get_open(args[0]);
    mp_obj_t features = n_args == 5 ? args[4] : mp_const_none;
    size_t count = 0;
    float *feature_data = NULL;
    mot_detection_t *detections = parse_detections(self, args[1], args[2], args[3],
                                                    features, &count, &feature_data);
    const char *error = mot_tracker_update(self->tracker, detections, count);
    if (feature_data != NULL) m_del(float, feature_data, count * mot_tracker_feature_dim(self->tracker));
    if (detections != NULL) m_del(mot_detection_t, detections, count);
    if (error != NULL)
        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("%s"), error);
    return result_list(self, false);
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(mot_update_obj, 4, 5, mot_update);

static mp_obj_t mot_tracks(size_t n_args, const mp_obj_t *pos_args, mp_map_t *kw_args)
{
    enum { A_include_lost };
    static const mp_arg_t allowed[] = {
        { MP_QSTR_include_lost, MP_ARG_KW_ONLY | MP_ARG_BOOL, {.u_bool = false} },
    };
    mp_arg_val_t a[MP_ARRAY_SIZE(allowed)];
    mp_arg_parse_all(n_args - 1, pos_args + 1, kw_args, MP_ARRAY_SIZE(allowed), allowed, a);
    mot_obj_t *self = get_open(pos_args[0]);
    return result_list(self, a[A_include_lost].u_bool);
}
static MP_DEFINE_CONST_FUN_OBJ_KW(mot_tracks_obj, 1, mot_tracks);

static mp_obj_t mot_reset(mp_obj_t self_in)
{
    mot_tracker_reset(get_open(self_in)->tracker);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(mot_reset_obj, mot_reset);

static mp_obj_t mot_frame_id(mp_obj_t self_in)
{
    return mp_obj_new_int(mot_tracker_frame_id(get_open(self_in)->tracker));
}
static MP_DEFINE_CONST_FUN_OBJ_1(mot_frame_id_obj, mot_frame_id);

static mp_obj_t mot_close(mp_obj_t self_in)
{
    mot_obj_t *self = MP_OBJ_TO_PTR(self_in);
    mot_tracker_destroy(self->tracker);
    self->tracker = NULL;
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(mot_close_obj, mot_close);

static const mp_rom_map_elem_t mot_locals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___del__), MP_ROM_PTR(&mot_close_obj) },
    { MP_ROM_QSTR(MP_QSTR_close), MP_ROM_PTR(&mot_close_obj) },
    { MP_ROM_QSTR(MP_QSTR_update), MP_ROM_PTR(&mot_update_obj) },
    { MP_ROM_QSTR(MP_QSTR_tracks), MP_ROM_PTR(&mot_tracks_obj) },
    { MP_ROM_QSTR(MP_QSTR_reset), MP_ROM_PTR(&mot_reset_obj) },
    { MP_ROM_QSTR(MP_QSTR_frame_id), MP_ROM_PTR(&mot_frame_id_obj) },
};
static MP_DEFINE_CONST_DICT(mot_locals, mot_locals_table);

MP_DEFINE_CONST_OBJ_TYPE(mot_bytetrack_type, MP_QSTR_ByteTrack, MP_TYPE_FLAG_NONE,
                         make_new, mot_bytetrack_make_new, locals_dict, &mot_locals);
MP_DEFINE_CONST_OBJ_TYPE(mot_ocsort_type, MP_QSTR_OCSort, MP_TYPE_FLAG_NONE,
                         make_new, mot_ocsort_make_new, locals_dict, &mot_locals);
MP_DEFINE_CONST_OBJ_TYPE(mot_deepsort_type, MP_QSTR_DeepSort, MP_TYPE_FLAG_NONE,
                         make_new, mot_deepsort_make_new, locals_dict, &mot_locals);
MP_DEFINE_CONST_OBJ_TYPE(mot_botsort_type, MP_QSTR_BoTSort, MP_TYPE_FLAG_NONE,
                         make_new, mot_botsort_make_new, locals_dict, &mot_locals);

static const mp_rom_map_elem_t mot_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_mot) },
    { MP_ROM_QSTR(MP_QSTR_ByteTrack), MP_ROM_PTR(&mot_bytetrack_type) },
    { MP_ROM_QSTR(MP_QSTR_OCSort), MP_ROM_PTR(&mot_ocsort_type) },
    { MP_ROM_QSTR(MP_QSTR_DeepSort), MP_ROM_PTR(&mot_deepsort_type) },
    { MP_ROM_QSTR(MP_QSTR_BoTSort), MP_ROM_PTR(&mot_botsort_type) },
};
static MP_DEFINE_CONST_DICT(mot_module_globals, mot_module_globals_table);

const mp_obj_module_t mot_module = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&mot_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR_mot, mot_module);
