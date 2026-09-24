#include "mot_tracker.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <numeric>
#include <stdexcept>

namespace canmv::mot {
namespace {

constexpr float kInvalidCost = 1.0e6f;

float width(const Box &b) { return std::max(0.0f, b.x2 - b.x1); }
float height(const Box &b) { return std::max(0.0f, b.y2 - b.y1); }
float center_x(const Box &b) { return (b.x1 + b.x2) * 0.5f; }
float center_y(const Box &b) { return (b.y1 + b.y2) * 0.5f; }

float iou(const Box &a, const Box &b)
{
    const float x1 = std::max(a.x1, b.x1);
    const float y1 = std::max(a.y1, b.y1);
    const float x2 = std::min(a.x2, b.x2);
    const float y2 = std::min(a.y2, b.y2);
    const float intersection = std::max(0.0f, x2 - x1) * std::max(0.0f, y2 - y1);
    const float total = width(a) * height(a) + width(b) * height(b) - intersection;
    return total > 0.0f ? intersection / total : 0.0f;
}

float cosine_distance(const std::vector<float> &a, const std::vector<float> &b)
{
    if (a.empty() || a.size() != b.size()) {
        return 1.0f;
    }
    double dot = 0.0;
    double aa = 0.0;
    double bb = 0.0;
    for (size_t i = 0; i < a.size(); ++i) {
        dot += static_cast<double>(a[i]) * b[i];
        aa += static_cast<double>(a[i]) * a[i];
        bb += static_cast<double>(b[i]) * b[i];
    }
    if (aa <= 1.0e-12 || bb <= 1.0e-12) {
        return 1.0f;
    }
    const float similarity = static_cast<float>(dot / std::sqrt(aa * bb));
    return 1.0f - std::clamp(similarity, -1.0f, 1.0f);
}

// Rectangular minimum-cost assignment. Padding represents unmatched rows/columns.
std::vector<int> hungarian(const std::vector<std::vector<float>> &cost, float unmatched_cost)
{
    const int rows = static_cast<int>(cost.size());
    const int cols = rows == 0 ? 0 : static_cast<int>(cost.front().size());
    const int n = std::max(rows, cols);
    if (n == 0) {
        return {};
    }
    std::vector<double> u(n + 1), v(n + 1);
    std::vector<int> p(n + 1), way(n + 1);
    for (int i = 1; i <= n; ++i) {
        p[0] = i;
        int j0 = 0;
        std::vector<double> minv(n + 1, std::numeric_limits<double>::infinity());
        std::vector<char> used(n + 1, false);
        do {
            used[j0] = true;
            const int i0 = p[j0];
            double delta = std::numeric_limits<double>::infinity();
            int j1 = 0;
            for (int j = 1; j <= n; ++j) {
                if (used[j]) continue;
                const double cell = (i0 <= rows && j <= cols) ? cost[i0 - 1][j - 1] : unmatched_cost;
                const double cur = cell - u[i0] - v[j];
                if (cur < minv[j]) { minv[j] = cur; way[j] = j0; }
                if (minv[j] < delta) { delta = minv[j]; j1 = j; }
            }
            for (int j = 0; j <= n; ++j) {
                if (used[j]) { u[p[j]] += delta; v[j] -= delta; }
                else minv[j] -= delta;
            }
            j0 = j1;
        } while (p[j0] != 0);
        do {
            const int j1 = way[j0];
            p[j0] = p[j1];
            j0 = j1;
        } while (j0 != 0);
    }
    std::vector<int> assignment(rows, -1);
    for (int j = 1; j <= n; ++j) {
        if (p[j] >= 1 && p[j] <= rows && j <= cols) assignment[p[j] - 1] = j - 1;
    }
    return assignment;
}

template <typename T>
std::vector<T> select_items(const std::vector<T> &items, const std::vector<int> &indices)
{
    std::vector<T> out;
    out.reserve(indices.size());
    for (int i : indices) out.push_back(items[static_cast<size_t>(i)]);
    return out;
}

} // namespace

const char *state_name(TrackState state)
{
    switch (state) {
    case TrackState::Tentative: return "tentative";
    case TrackState::Tracked: return "tracked";
    case TrackState::Lost: return "lost";
    case TrackState::Removed: return "removed";
    }
    return "unknown";
}

Tracker::Tracker(Algorithm algorithm, const Params &params) : algorithm_(algorithm), params_(params)
{
    if (params_.max_age < 1 || params_.min_hits < 1 || params_.nn_budget < 1)
        throw std::invalid_argument("age, hits, and budget must be positive");
    if ((algorithm_ == Algorithm::DeepSort || (algorithm_ == Algorithm::BoTSort && params_.reid_enabled)) &&
        params_.feature_dim <= 0)
        throw std::invalid_argument("feature_dim must be positive when appearance matching is enabled");
}

void Tracker::reset()
{
    frame_id_ = 0;
    next_id_ = 1;
    active_.clear();
    lost_.clear();
}

void Tracker::predict(std::vector<Track> &tracks)
{
    for (Track &t : tracks) {
        t.box.x1 += t.vx - t.vw * 0.5f;
        t.box.x2 += t.vx + t.vw * 0.5f;
        t.box.y1 += t.vy - t.vh * 0.5f;
        t.box.y2 += t.vy + t.vh * 0.5f;
        if (width(t.box) <= 1.0e-3f || height(t.box) <= 1.0e-3f) t.box = t.previous_observation;
        ++t.age;
        ++t.time_since_update;
        if (t.time_since_update > 0) t.hit_streak = 0;
    }
}

Tracker::Track Tracker::make_track(const Detection &d, bool confirmed)
{
    Track t;
    t.id = next_id_++;
    t.class_id = d.class_id;
    t.start_frame = frame_id_;
    t.score = d.score;
    t.box = d.box;
    t.previous_observation = d.box;
    t.observations.push_back(d.box);
    t.state = confirmed ? TrackState::Tracked : TrackState::Tentative;
    if (!d.feature.empty()) t.features.push_back(d.feature);
    return t;
}

void Tracker::apply_detection(Track &t, const Detection &d, bool reactivate)
{
    const Box *velocity_origin = &t.previous_observation;
    int velocity_steps = 1;
    if (algorithm_ == Algorithm::OCSort && !t.observations.empty()) {
        velocity_steps = std::min(params_.delta_t, static_cast<int>(t.observations.size()));
        velocity_origin = &t.observations[t.observations.size() - velocity_steps];
    }
    const float scale = 1.0f / velocity_steps;
    t.vx = 0.8f * t.vx + 0.2f * (center_x(d.box) - center_x(*velocity_origin)) * scale;
    t.vy = 0.8f * t.vy + 0.2f * (center_y(d.box) - center_y(*velocity_origin)) * scale;
    t.vw = 0.8f * t.vw + 0.2f * (width(d.box) - width(*velocity_origin)) * scale;
    t.vh = 0.8f * t.vh + 0.2f * (height(d.box) - height(*velocity_origin)) * scale;
    t.previous_observation = d.box;
    t.observations.push_back(d.box);
    while (static_cast<int>(t.observations.size()) > params_.delta_t + 1) t.observations.pop_front();
    t.box = d.box;
    t.score = d.score;
    t.class_id = d.class_id;
    t.time_since_update = 0;
    ++t.hits;
    ++t.hit_streak;
    if (reactivate || t.state == TrackState::Lost || t.hits >= params_.min_hits) t.state = TrackState::Tracked;
    if (!d.feature.empty()) {
        t.features.push_back(d.feature);
        while (static_cast<int>(t.features.size()) > params_.nn_budget) t.features.pop_front();
    }
}

void Tracker::mark_missed(Track &t, bool tentative_deletes)
{
    if (tentative_deletes && t.state == TrackState::Tentative) t.state = TrackState::Removed;
    else t.state = TrackState::Lost;
}

void Tracker::expire_lost()
{
    lost_.erase(std::remove_if(lost_.begin(), lost_.end(), [&](Track &t) {
        if (t.time_since_update > params_.max_age) { t.state = TrackState::Removed; return true; }
        return false;
    }), lost_.end());
}

float Tracker::association_cost(const Track &t, const Detection &d, bool appearance, bool oc_direction) const
{
    if (params_.class_aware && t.class_id != d.class_id) return kInvalidCost;
    const float iou_cost = 1.0f - iou(t.box, d.box);
    // BoT-SORT first fuses detector confidence with IoU similarity.
    float cost = algorithm_ == Algorithm::BoTSort
                     ? 1.0f - (1.0f - iou_cost) * d.score
                     : iou_cost;
    if (oc_direction && (std::fabs(t.vx) + std::fabs(t.vy)) > 1.0e-4f) {
        const float dx = center_x(d.box) - center_x(t.previous_observation);
        const float dy = center_y(d.box) - center_y(t.previous_observation);
        const float a = std::sqrt(t.vx * t.vx + t.vy * t.vy);
        const float b = std::sqrt(dx * dx + dy * dy);
        const float direction_penalty = b > 1.0e-4f ? 0.5f * (1.0f - std::clamp((t.vx * dx + t.vy * dy) / (a * b), -1.0f, 1.0f)) : 0.0f;
        cost += params_.inertia * direction_penalty;
    }
    if (appearance) {
        float appearance_cost = 1.0f;
        for (const auto &f : t.features) appearance_cost = std::min(appearance_cost, cosine_distance(f, d.feature));
        if (algorithm_ == Algorithm::BoTSort) {
            if (1.0f - iou_cost < params_.proximity_thresh ||
                appearance_cost > params_.appearance_thresh) {
                appearance_cost = 1.0f;
            }
            // The reference port fuses embedding and motion first, then uses
            // its IoU/embedding min rule (max for near-identical boxes).
            appearance_cost = params_.appearance_weight * appearance_cost +
                              (1.0f - params_.appearance_weight) * iou_cost;
            cost = cost < 0.1f ? std::max(cost, appearance_cost)
                               : std::min(cost, appearance_cost);
        } else {
            if (appearance_cost > params_.max_cosine_distance) return kInvalidCost;
            cost = appearance_cost;
        }
    }
    return cost;
}

Tracker::MatchResult Tracker::associate(const std::vector<Track> &tracks,
                                        const std::vector<Detection> &detections,
                                        float max_cost, bool appearance, bool oc_direction) const
{
    MatchResult out;
    if (tracks.empty()) {
        out.unmatched_detections.resize(detections.size());
        std::iota(out.unmatched_detections.begin(), out.unmatched_detections.end(), 0);
        return out;
    }
    if (detections.empty()) {
        out.unmatched_tracks.resize(tracks.size());
        std::iota(out.unmatched_tracks.begin(), out.unmatched_tracks.end(), 0);
        return out;
    }
    std::vector<std::vector<float>> costs(tracks.size(), std::vector<float>(detections.size()));
    for (size_t i = 0; i < tracks.size(); ++i)
        for (size_t j = 0; j < detections.size(); ++j)
            costs[i][j] = association_cost(tracks[i], detections[j], appearance, oc_direction);
    const std::vector<int> assigned = hungarian(costs, max_cost + 1.0e-3f);
    std::vector<char> used(detections.size(), false);
    for (size_t i = 0; i < tracks.size(); ++i) {
        const int j = assigned[i];
        if (j >= 0 && costs[i][static_cast<size_t>(j)] <= max_cost) {
            out.matches.emplace_back(static_cast<int>(i), j);
            used[static_cast<size_t>(j)] = true;
        } else out.unmatched_tracks.push_back(static_cast<int>(i));
    }
    for (size_t j = 0; j < detections.size(); ++j) if (!used[j]) out.unmatched_detections.push_back(static_cast<int>(j));
    return out;
}

std::vector<Result> Tracker::update(const std::vector<Detection> &detections)
{
    ++frame_id_;
    switch (algorithm_) {
    case Algorithm::ByteTrack: return update_byte(detections, false);
    case Algorithm::BoTSort: return update_byte(detections, true);
    case Algorithm::OCSort: return update_ocsort(detections);
    case Algorithm::DeepSort: return update_deepsort(detections);
    }
    return {};
}

std::vector<Result> Tracker::update_byte(const std::vector<Detection> &detections, bool bot_sort)
{
    predict(active_);
    predict(lost_);
    std::vector<Detection> high, low;
    for (const auto &d : detections) {
        if (d.score >= params_.track_high_thresh) high.push_back(d);
        else if (d.score >= params_.track_low_thresh) low.push_back(d);
    }

    // Official ByteTrack keeps one-frame/unconfirmed tracks out of the main
    // active+lost pool and gives them a separate association pass.
    std::vector<Track> confirmed, unconfirmed;
    for (Track &t : active_) {
        if (t.state == TrackState::Tentative) unconfirmed.push_back(std::move(t));
        else confirmed.push_back(std::move(t));
    }
    std::vector<Track> pool = confirmed;
    pool.insert(pool.end(), lost_.begin(), lost_.end());
    const bool use_features = bot_sort && params_.reid_enabled;
    MatchResult first = associate(pool, high, params_.match_thresh, use_features, false);
    std::vector<Track> next_active, next_lost;
    std::vector<char> high_used(high.size(), false);
    for (auto [ti, di] : first.matches) {
        Track t = pool[static_cast<size_t>(ti)];
        apply_detection(t, high[static_cast<size_t>(di)], t.state == TrackState::Lost);
        next_active.push_back(std::move(t));
        high_used[static_cast<size_t>(di)] = true;
    }

    std::vector<Track> unmatched_confirmed;
    for (int ti : first.unmatched_tracks) {
        Track t = pool[static_cast<size_t>(ti)];
        if (t.state == TrackState::Lost) next_lost.push_back(std::move(t));
        else unmatched_confirmed.push_back(std::move(t));
    }
    MatchResult second = associate(unmatched_confirmed, low, params_.second_match_thresh, false, false);
    for (auto [ti, di] : second.matches) {
        Track t = unmatched_confirmed[static_cast<size_t>(ti)];
        apply_detection(t, low[static_cast<size_t>(di)]);
        next_active.push_back(std::move(t));
    }
    for (int ti : second.unmatched_tracks) {
        Track t = unmatched_confirmed[static_cast<size_t>(ti)];
        mark_missed(t, false);
        next_lost.push_back(std::move(t));
    }

    std::vector<Detection> remaining_high;
    std::vector<int> remaining_original;
    for (size_t i = 0; i < high.size(); ++i) if (!high_used[i]) {
        remaining_high.push_back(high[i]);
        remaining_original.push_back(static_cast<int>(i));
    }
    MatchResult tentative_match = associate(unconfirmed, remaining_high,
                                             std::min(0.7f, params_.match_thresh),
                                             use_features, false);
    for (auto [ti, di] : tentative_match.matches) {
        Track t = unconfirmed[static_cast<size_t>(ti)];
        apply_detection(t, remaining_high[static_cast<size_t>(di)]);
        next_active.push_back(std::move(t));
        high_used[static_cast<size_t>(remaining_original[static_cast<size_t>(di)])] = true;
    }
    // Unmatched tentative tracks are deliberately dropped, as in ByteTrack.
    for (size_t i = 0; i < high.size(); ++i) if (!high_used[i] && high[i].score >= params_.new_track_thresh)
        next_active.push_back(make_track(high[i], params_.min_hits <= 1));

    active_ = std::move(next_active);
    lost_ = std::move(next_lost);
    expire_lost();
    return tracks(false);
}

std::vector<Result> Tracker::update_ocsort(const std::vector<Detection> &detections)
{
    predict(active_);
    predict(lost_);
    std::vector<Detection> accepted, low;
    for (const auto &d : detections) {
        if (d.score >= params_.det_thresh) accepted.push_back(d);
        else if (params_.use_byte && d.score >= params_.track_low_thresh) low.push_back(d);
    }
    std::vector<Track> pool = active_;
    pool.insert(pool.end(), lost_.begin(), lost_.end());
    MatchResult first = associate(pool, accepted, 1.0f - params_.iou_threshold, false, true);
    std::vector<Track> next_active, next_lost;
    std::vector<char> detection_used(accepted.size(), false);
    for (auto [ti, di] : first.matches) {
        Track t = pool[static_cast<size_t>(ti)];
        apply_detection(t, accepted[static_cast<size_t>(di)], t.state == TrackState::Lost);
        next_active.push_back(std::move(t));
        detection_used[static_cast<size_t>(di)] = true;
    }

    std::vector<Track> remaining_tracks;
    for (int ti : first.unmatched_tracks) remaining_tracks.push_back(pool[static_cast<size_t>(ti)]);
    std::vector<Detection> remaining_detections;
    std::vector<int> remaining_detection_indices;
    for (size_t i = 0; i < accepted.size(); ++i) if (!detection_used[i]) {
        remaining_detections.push_back(accepted[i]);
        remaining_detection_indices.push_back(static_cast<int>(i));
    }

    // Observation-centric recovery: compare unmatched detections with the last
    // real observation, rather than only the extrapolated state.
    std::vector<Track> observation_tracks = remaining_tracks;
    for (Track &t : observation_tracks) t.box = t.previous_observation;
    MatchResult recovery = associate(observation_tracks, remaining_detections,
                                     1.0f - params_.iou_threshold, false, false);
    std::vector<char> remaining_track_used(remaining_tracks.size(), false);
    for (auto [ti, di] : recovery.matches) {
        Track t = remaining_tracks[static_cast<size_t>(ti)];
        const int original_detection = remaining_detection_indices[static_cast<size_t>(di)];
        apply_detection(t, accepted[static_cast<size_t>(original_detection)], t.state == TrackState::Lost);
        next_active.push_back(std::move(t));
        remaining_track_used[static_cast<size_t>(ti)] = true;
        detection_used[static_cast<size_t>(original_detection)] = true;
    }

    std::vector<Track> spatial_unmatched;
    for (size_t i = 0; i < remaining_tracks.size(); ++i) if (!remaining_track_used[i])
        spatial_unmatched.push_back(std::move(remaining_tracks[i]));
    if (params_.use_byte && !low.empty()) {
        MatchResult second = associate(spatial_unmatched, low,
                                       1.0f - params_.iou_threshold, false, false);
        std::vector<char> matched_track(spatial_unmatched.size(), false);
        for (auto [ti, di] : second.matches) {
            Track t = spatial_unmatched[static_cast<size_t>(ti)];
            apply_detection(t, low[static_cast<size_t>(di)], t.state == TrackState::Lost);
            next_active.push_back(std::move(t));
            matched_track[static_cast<size_t>(ti)] = true;
        }
        for (size_t i = 0; i < spatial_unmatched.size(); ++i) if (!matched_track[i]) {
            Track t = std::move(spatial_unmatched[i]);
            if (t.state != TrackState::Lost) mark_missed(t, false);
            next_lost.push_back(std::move(t));
        }
    } else {
        for (Track &t : spatial_unmatched) {
            if (t.state != TrackState::Lost) mark_missed(t, false);
            next_lost.push_back(std::move(t));
        }
    }
    for (size_t i = 0; i < accepted.size(); ++i) if (!detection_used[i])
        next_active.push_back(make_track(accepted[i], params_.min_hits <= 1 || frame_id_ <= params_.min_hits));
    active_ = std::move(next_active);
    lost_ = std::move(next_lost);
    expire_lost();
    return tracks(false);
}

std::vector<Result> Tracker::update_deepsort(const std::vector<Detection> &detections)
{
    predict(active_);
    std::vector<int> confirmed_indices, tentative_indices;
    for (size_t i = 0; i < active_.size(); ++i) {
        if (active_[i].state == TrackState::Tracked) confirmed_indices.push_back(static_cast<int>(i));
        else tentative_indices.push_back(static_cast<int>(i));
    }

    // DeepSORT matching cascade gives recently observed confirmed tracks first
    // choice of detections, preventing old tracks from stealing a current one.
    std::vector<int> remaining_detections(detections.size());
    std::iota(remaining_detections.begin(), remaining_detections.end(), 0);
    std::vector<char> track_used(active_.size(), false), detection_used(detections.size(), false);
    std::vector<Track> next_active;
    for (int level = 1; level <= params_.max_age && !remaining_detections.empty(); ++level) {
        std::vector<int> level_tracks;
        for (int index : confirmed_indices)
            if (!track_used[static_cast<size_t>(index)] && active_[static_cast<size_t>(index)].time_since_update == level)
                level_tracks.push_back(index);
        if (level_tracks.empty()) continue;
        std::vector<Track> candidates = select_items(active_, level_tracks);
        std::vector<Detection> candidate_detections = select_items(detections, remaining_detections);
        MatchResult level_match = associate(candidates, candidate_detections,
                                            params_.max_cosine_distance, true, false);
        for (auto [ti, di] : level_match.matches) {
            const int original_track = level_tracks[static_cast<size_t>(ti)];
            const int original_detection = remaining_detections[static_cast<size_t>(di)];
            Track t = active_[static_cast<size_t>(original_track)];
            apply_detection(t, detections[static_cast<size_t>(original_detection)]);
            next_active.push_back(std::move(t));
            track_used[static_cast<size_t>(original_track)] = true;
            detection_used[static_cast<size_t>(original_detection)] = true;
        }
        std::vector<int> next_remaining;
        for (int index : remaining_detections) if (!detection_used[static_cast<size_t>(index)])
            next_remaining.push_back(index);
        remaining_detections = std::move(next_remaining);
    }

    // Tentative tracks and confirmed tracks missed for only one frame use the
    // IoU fallback, matching the official DeepSORT ordering.
    std::vector<int> iou_original;
    for (int index : tentative_indices) if (!track_used[static_cast<size_t>(index)]) iou_original.push_back(index);
    for (int index : confirmed_indices)
        if (!track_used[static_cast<size_t>(index)] && active_[static_cast<size_t>(index)].time_since_update == 1)
            iou_original.push_back(index);
    std::vector<Track> iou_tracks = select_items(active_, iou_original);
    std::vector<Detection> remaining = select_items(detections, remaining_detections);
    MatchResult spatial = associate(iou_tracks, remaining, params_.max_iou_distance, false, false);
    for (auto [ti, di] : spatial.matches) {
        const int original_track = iou_original[static_cast<size_t>(ti)];
        const int original_detection = remaining_detections[static_cast<size_t>(di)];
        Track t = active_[static_cast<size_t>(original_track)];
        apply_detection(t, detections[static_cast<size_t>(original_detection)]);
        next_active.push_back(std::move(t));
        track_used[static_cast<size_t>(original_track)] = true;
        detection_used[static_cast<size_t>(original_detection)] = true;
    }

    for (size_t i = 0; i < active_.size(); ++i) if (!track_used[i]) {
        Track t = active_[i];
        if (t.state == TrackState::Tentative || t.time_since_update > params_.max_age) {
            t.state = TrackState::Removed;
        } else {
            t.state = TrackState::Tracked;
        }
        if (t.state != TrackState::Removed) next_active.push_back(std::move(t));
    }
    for (size_t i = 0; i < detections.size(); ++i) if (!detection_used[i])
        next_active.push_back(make_track(detections[i], params_.min_hits <= 1));
    active_ = std::move(next_active);
    return tracks(false);
}

std::vector<Result> Tracker::tracks(bool include_lost) const
{
    std::vector<Result> out;
    auto append = [&](const std::vector<Track> &source, bool visible_only) {
        for (const Track &t : source) {
            if (visible_only && t.time_since_update != 0) continue;
            if (t.state == TrackState::Removed) continue;
            out.push_back({t.id, t.class_id, t.box, t.score, t.state, t.age, t.hits, t.time_since_update});
        }
    };
    append(active_, !include_lost);
    if (include_lost) append(lost_, false);
    return out;
}

} // namespace canmv::mot
