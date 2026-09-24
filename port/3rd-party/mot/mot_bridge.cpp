#include "mot_bridge.h"
#include "mot_tracker.hpp"

#include <new>
#include <string>
#include <vector>

using namespace canmv::mot;

struct mot_tracker_handle {
    Tracker *tracker = nullptr;
    Algorithm algorithm = Algorithm::ByteTrack;
    std::vector<Result> latest;
    std::string error;
};

static Algorithm convert_algorithm(mot_algorithm_t value)
{
    switch (value) {
    case MOT_ALGORITHM_OCSORT: return Algorithm::OCSort;
    case MOT_ALGORITHM_DEEPSORT: return Algorithm::DeepSort;
    case MOT_ALGORITHM_BOTSORT: return Algorithm::BoTSort;
    default: return Algorithm::ByteTrack;
    }
}

static Params convert_params(const mot_params_t &p)
{
    Params out;
    out.class_aware = p.class_aware; out.feature_dim = p.feature_dim;
    out.max_age = p.max_age; out.min_hits = p.min_hits;
    out.nn_budget = p.nn_budget; out.delta_t = p.delta_t;
    out.det_thresh = p.det_thresh; out.track_high_thresh = p.track_high_thresh;
    out.track_low_thresh = p.track_low_thresh; out.new_track_thresh = p.new_track_thresh;
    out.match_thresh = p.match_thresh; out.second_match_thresh = p.second_match_thresh;
    out.iou_threshold = p.iou_threshold; out.max_iou_distance = p.max_iou_distance;
    out.max_cosine_distance = p.max_cosine_distance; out.proximity_thresh = p.proximity_thresh;
    out.appearance_thresh = p.appearance_thresh; out.inertia = p.inertia;
    out.appearance_weight = p.appearance_weight; out.use_byte = p.use_byte;
    out.reid_enabled = p.reid_enabled;
    return out;
}

extern "C" mot_params_t mot_default_params(void)
{
    Params p;
    return {p.class_aware, p.feature_dim, p.max_age, p.min_hits, p.nn_budget, p.delta_t,
            p.det_thresh, p.track_high_thresh, p.track_low_thresh, p.new_track_thresh,
            p.match_thresh, p.second_match_thresh, p.iou_threshold, p.max_iou_distance,
            p.max_cosine_distance, p.proximity_thresh, p.appearance_thresh, p.inertia,
            p.appearance_weight, p.use_byte, p.reid_enabled};
}

extern "C" mot_tracker_handle_t *mot_tracker_create(mot_algorithm_t algorithm,
                                                       const mot_params_t *params,
                                                       const char **error)
{
    static const char *memory_error = "cannot allocate tracker";
    static std::string create_error;
    if (error) *error = nullptr;
    auto *handle = new (std::nothrow) mot_tracker_handle;
    if (!handle) { if (error) *error = memory_error; return nullptr; }
    try {
        handle->algorithm = convert_algorithm(algorithm);
        handle->tracker = new Tracker(handle->algorithm, convert_params(*params));
    } catch (const std::bad_alloc &) {
        if (error) *error = memory_error;
        delete handle;
        return nullptr;
    } catch (const std::exception &e) {
        create_error = e.what();
        if (error) *error = create_error.c_str();
        delete handle;
        return nullptr;
    } catch (...) {
        if (error) *error = memory_error;
        delete handle;
        return nullptr;
    }
    return handle;
}

extern "C" void mot_tracker_destroy(mot_tracker_handle_t *handle)
{
    if (!handle) return;
    delete handle->tracker;
    delete handle;
}

extern "C" void mot_tracker_reset(mot_tracker_handle_t *handle)
{
    handle->tracker->reset(); handle->latest.clear();
}

extern "C" int mot_tracker_frame_id(const mot_tracker_handle_t *handle)
{
    return handle->tracker->frame_id();
}

extern "C" int mot_tracker_feature_dim(const mot_tracker_handle_t *handle)
{
    return handle->tracker->feature_dim();
}

extern "C" bool mot_tracker_features_required(const mot_tracker_handle_t *handle)
{
    return handle->algorithm == Algorithm::DeepSort ||
           (handle->algorithm == Algorithm::BoTSort && handle->tracker->feature_dim() > 0);
}

extern "C" const char *mot_tracker_update(mot_tracker_handle_t *handle,
                                            const mot_detection_t *input, size_t count)
{
    try {
        std::vector<Detection> detections;
        detections.reserve(count);
        for (size_t i = 0; i < count; ++i) {
            Detection d;
            d.box = {input[i].x1, input[i].y1, input[i].x2, input[i].y2};
            d.score = input[i].score; d.class_id = input[i].class_id;
            if (input[i].feature && input[i].feature_dim)
                d.feature.assign(input[i].feature, input[i].feature + input[i].feature_dim);
            detections.push_back(std::move(d));
        }
        handle->latest = handle->tracker->update(detections);
        return nullptr;
    } catch (const std::exception &e) {
        handle->error = e.what(); return handle->error.c_str();
    } catch (...) {
        handle->error = "tracker update failed"; return handle->error.c_str();
    }
}

extern "C" size_t mot_tracker_results(const mot_tracker_handle_t *handle, bool include_lost,
                                        mot_result_t *output, size_t capacity)
{
    std::vector<Result> values = include_lost ? handle->tracker->tracks(true) : handle->latest;
    if (!output) return values.size();
    const size_t count = values.size() < capacity ? values.size() : capacity;
    for (size_t i = 0; i < count; ++i) {
        const Result &r = values[i];
        output[i] = {r.track_id, r.class_id, r.box.x1, r.box.y1, r.box.x2, r.box.y2,
                     r.score, state_name(r.state), r.age, r.hits, r.time_since_update};
    }
    return count;
}
