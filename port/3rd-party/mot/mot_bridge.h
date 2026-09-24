#pragma once

#include <stdbool.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    MOT_ALGORITHM_BYTETRACK,
    MOT_ALGORITHM_OCSORT,
    MOT_ALGORITHM_DEEPSORT,
    MOT_ALGORITHM_BOTSORT,
} mot_algorithm_t;

typedef struct {
    bool class_aware;
    int feature_dim, max_age, min_hits, nn_budget, delta_t;
    float det_thresh, track_high_thresh, track_low_thresh, new_track_thresh;
    float match_thresh, second_match_thresh, iou_threshold;
    float max_iou_distance, max_cosine_distance;
    float proximity_thresh, appearance_thresh, inertia, appearance_weight;
    bool use_byte, reid_enabled;
} mot_params_t;

typedef struct {
    float x1, y1, x2, y2;
    float score;
    int class_id;
    const float *feature;
    size_t feature_dim;
} mot_detection_t;

typedef struct {
    int track_id, class_id;
    float x1, y1, x2, y2, score;
    const char *state;
    int age, hits, time_since_update;
} mot_result_t;

typedef struct mot_tracker_handle mot_tracker_handle_t;

mot_params_t mot_default_params(void);
mot_tracker_handle_t *mot_tracker_create(mot_algorithm_t algorithm,
                                          const mot_params_t *params,
                                          const char **error);
void mot_tracker_destroy(mot_tracker_handle_t *handle);
void mot_tracker_reset(mot_tracker_handle_t *handle);
int mot_tracker_frame_id(const mot_tracker_handle_t *handle);
int mot_tracker_feature_dim(const mot_tracker_handle_t *handle);
bool mot_tracker_features_required(const mot_tracker_handle_t *handle);
const char *mot_tracker_update(mot_tracker_handle_t *handle,
                               const mot_detection_t *detections, size_t count);
size_t mot_tracker_results(const mot_tracker_handle_t *handle, bool include_lost,
                           mot_result_t *results, size_t capacity);

#ifdef __cplusplus
}
#endif
