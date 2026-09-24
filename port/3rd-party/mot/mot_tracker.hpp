/*
 * Generic multi-object tracking core for CanMV.
 *
 * Detection and appearance inference deliberately live outside this module.
 */
#pragma once

#include <cstddef>
#include <deque>
#include <string>
#include <vector>

namespace canmv::mot {

enum class Algorithm { ByteTrack, OCSort, DeepSort, BoTSort };
enum class TrackState { Tentative, Tracked, Lost, Removed };

struct Box {
    float x1 = 0;
    float y1 = 0;
    float x2 = 0;
    float y2 = 0;
};

struct Detection {
    Box box;
    float score = 0;
    int class_id = 0;
    std::vector<float> feature;
};

struct Result {
    int track_id = 0;
    int class_id = 0;
    Box box;
    float score = 0;
    TrackState state = TrackState::Tentative;
    int age = 0;
    int hits = 0;
    int time_since_update = 0;
};

struct Params {
    bool class_aware = true;
    int feature_dim = 0;
    int max_age = 30;
    int min_hits = 1;
    int nn_budget = 100;
    int delta_t = 3;
    float det_thresh = 0.3f;
    float track_high_thresh = 0.6f;
    float track_low_thresh = 0.1f;
    float new_track_thresh = 0.7f;
    float match_thresh = 0.8f;       // maximum association cost
    float second_match_thresh = 0.5f;
    float iou_threshold = 0.3f;
    float max_iou_distance = 0.7f;
    float max_cosine_distance = 0.2f;
    float proximity_thresh = 0.5f;
    float appearance_thresh = 0.25f;
    float inertia = 0.2f;
    float appearance_weight = 0.985f;
    bool use_byte = false;
    bool reid_enabled = false;
};

class Tracker {
public:
    Tracker(Algorithm algorithm, const Params &params);
    ~Tracker() = default;

    std::vector<Result> update(const std::vector<Detection> &detections);
    std::vector<Result> tracks(bool include_lost = false) const;
    void reset();
    int frame_id() const { return frame_id_; }
    int feature_dim() const { return params_.feature_dim; }
    Algorithm algorithm() const { return algorithm_; }

private:
    struct Track {
        int id = 0;
        int class_id = 0;
        int age = 1;
        int hits = 1;
        int hit_streak = 1;
        int time_since_update = 0;
        int start_frame = 0;
        float score = 0;
        TrackState state = TrackState::Tentative;
        Box box;
        Box previous_observation;
        float vx = 0;
        float vy = 0;
        float vw = 0;
        float vh = 0;
        std::deque<std::vector<float>> features;
        std::deque<Box> observations;
    };

    struct MatchResult {
        std::vector<std::pair<int, int>> matches;
        std::vector<int> unmatched_tracks;
        std::vector<int> unmatched_detections;
    };

    Algorithm algorithm_;
    Params params_;
    int frame_id_ = 0;
    int next_id_ = 1;
    std::vector<Track> active_;
    std::vector<Track> lost_;

    void predict(std::vector<Track> &tracks);
    Track make_track(const Detection &detection, bool confirmed);
    void apply_detection(Track &track, const Detection &detection, bool reactivate = false);
    void mark_missed(Track &track, bool tentative_deletes);
    void expire_lost();

    MatchResult associate(const std::vector<Track> &tracks,
                          const std::vector<Detection> &detections,
                          float max_cost, bool appearance, bool oc_direction) const;
    float association_cost(const Track &track, const Detection &detection,
                           bool appearance, bool oc_direction) const;

    std::vector<Result> update_byte(const std::vector<Detection> &detections, bool bot_sort);
    std::vector<Result> update_ocsort(const std::vector<Detection> &detections);
    std::vector<Result> update_deepsort(const std::vector<Detection> &detections);
};

const char *state_name(TrackState state);

} // namespace canmv::mot
