#pragma once

#include <cstddef>
#include <cstdint>
#include <vector>

// RTSP player logic called by rtsp_player.cpp.

namespace rtsp_player {

constexpr size_t kQueueBytes = 4 * 1024 * 1024;

class Bits {
  public:
    Bits(const uint8_t *data, size_t size) : data_(data), size_(size) {}

    bool ok() const { return ok_; }

    uint32_t u(int n) {
        uint32_t v = 0;
        for (int i = 0; i < n; i++) {
            if (bit_ >= size_ * 8) {
                ok_ = false;
                return 0;
            }
            v = (v << 1) | ((data_[bit_ >> 3] >> (7 - (bit_ & 7))) & 1);
            bit_++;
        }
        return v;
    }

    uint32_t ue() {
        int zeros = 0;
        while (u(1) == 0) {
            zeros++;
            if (zeros > 31 || !ok_) {
                ok_ = false;
                return 0;
            }
        }
        return ((1u << zeros) - 1u) + (zeros ? u(zeros) : 0);
    }

    int32_t se() {
        uint32_t v = ue();
        return (v & 1u) ? (int32_t)((v + 1u) / 2u) : -(int32_t)(v / 2u);
    }

  private:
    const uint8_t *data_;
    size_t size_;
    size_t bit_ = 0;
    bool ok_ = true;
};

inline std::vector<uint8_t> rbsp_from_nal(const uint8_t *nal, size_t size) {
    std::vector<uint8_t> out;
    out.reserve(size);
    for (size_t i = 0; i < size; i++) {
        if (i + 2 < size && nal[i] == 0 && nal[i + 1] == 0 && nal[i + 2] == 3) {
            out.push_back(0);
            out.push_back(0);
            i += 2;
        } else {
            out.push_back(nal[i]);
        }
    }
    return out;
}

inline void skip_scaling_list(Bits *br, int size) {
    int last = 8;
    int next = 8;
    for (int j = 0; j < size; j++) {
        if (next != 0) {
            int delta = br->se();
            next = (last + delta + 256) % 256;
        }
        last = (next == 0) ? last : next;
    }
}

inline bool parse_h264_sps(const uint8_t *nal, size_t size, int *width, int *height) {
    std::vector<uint8_t> rbsp = rbsp_from_nal(nal, size);
    if (rbsp.size() < 4) {
        return false;
    }
    Bits br(rbsp.data(), rbsp.size());
    if ((br.u(8) & 0x1f) != 7) {
        return false;
    }
    uint32_t profile = br.u(8);
    br.u(8);
    br.u(8);
    br.ue();
    uint32_t chroma = 1;
    if (profile == 100 || profile == 110 || profile == 122 || profile == 244 ||
        profile == 44 || profile == 83 || profile == 86 || profile == 118 ||
        profile == 128 || profile == 138 || profile == 139 || profile == 134 ||
        profile == 135) {
        chroma = br.ue();
        if (chroma == 3) {
            br.u(1);
        }
        br.ue();
        br.ue();
        br.u(1);
        if (br.u(1)) {
            int count = (chroma != 3) ? 8 : 12;
            for (int i = 0; i < count; i++) {
                if (br.u(1)) {
                    skip_scaling_list(&br, (i < 6) ? 16 : 64);
                }
            }
        }
    }
    br.ue();
    uint32_t poc = br.ue();
    if (poc == 0) {
        br.ue();
    } else if (poc == 1) {
        br.u(1);
        br.se();
        br.se();
        uint32_t cycles = br.ue();
        for (uint32_t i = 0; i < cycles; i++) {
            br.se();
        }
    }
    br.ue();
    br.u(1);
    int w = (int)(br.ue() + 1) * 16;
    int map_h = (int)(br.ue() + 1);
    int frame_only = (int)br.u(1);
    if (!frame_only) {
        br.u(1);
    }
    br.u(1);
    int h = (2 - frame_only) * map_h * 16;
    if (br.u(1)) {
        int crop_l = (int)br.ue();
        int crop_r = (int)br.ue();
        int crop_t = (int)br.ue();
        int crop_b = (int)br.ue();
        // SubWidthC / SubHeightC. CropUnitY is SubHeightC * (2 - frame_mbs_only),
        // applied below. 4:2:0 is (2, 2). 4:2:2 is (2, 1): SubHeightC is 1.
        int cx = 1;
        int cy = 1;
        if (chroma == 1) {
            cx = 2;
            cy = 2;
        } else if (chroma == 2) {
            cx = 2;
            cy = 1;
        } else if (chroma == 3) {
            cx = 1;
            cy = 1;
        }
        w -= (crop_l + crop_r) * cx;
        h -= (crop_t + crop_b) * cy * (2 - frame_only);
    }
    if (!br.ok() || w <= 0 || h <= 0) {
        return false;
    }
    *width = w;
    *height = h;
    return true;
}

inline void skip_h265_profile(Bits *br, int max_sub_layers) {
    br->u(2 + 1 + 5);
    br->u(32);
    br->u(48);
    br->u(8);
    uint8_t sub_profile[8];
    uint8_t sub_level[8];
    for (int i = 0; i < max_sub_layers; i++) {
        sub_profile[i] = (uint8_t)br->u(1);
        sub_level[i] = (uint8_t)br->u(1);
    }
    if (max_sub_layers > 0) {
        for (int i = max_sub_layers; i < 8; i++) {
            br->u(2);
        }
    }
    for (int i = 0; i < max_sub_layers; i++) {
        if (sub_profile[i]) {
            br->u(2 + 1 + 5);
            br->u(32);
            br->u(48);
            br->u(8);
        }
        if (sub_level[i]) {
            br->u(8);
        }
    }
}

inline bool parse_h265_sps(const uint8_t *nal, size_t size, int *width, int *height) {
    std::vector<uint8_t> rbsp = rbsp_from_nal(nal, size);
    if (rbsp.size() < 4) {
        return false;
    }
    Bits br(rbsp.data(), rbsp.size());
    uint32_t nal_type = (br.u(16) >> 9) & 0x3f;
    if (nal_type != 33) {
        return false;
    }
    br.u(4);
    int max_sub_layers = (int)br.u(3);
    br.u(1);
    skip_h265_profile(&br, max_sub_layers);
    br.ue();
    uint32_t chroma = br.ue();
    if (chroma == 3) {
        br.u(1);
    }
    int w = (int)br.ue();
    int h = (int)br.ue();
    if (br.u(1)) {
        int sub_w = 1;
        int sub_h = 1;
        if (chroma == 1) {
            sub_w = 2;
            sub_h = 2;
        } else if (chroma == 2) {
            sub_w = 2;
            sub_h = 1;
        }
        int left = (int)br.ue();
        int right = (int)br.ue();
        int top = (int)br.ue();
        int bottom = (int)br.ue();
        w -= (left + right) * sub_w;
        h -= (top + bottom) * sub_h;
    }
    if (!br.ok() || w <= 0 || h <= 0) {
        return false;
    }
    *width = w;
    *height = h;
    return true;
}

inline bool nal_at(const uint8_t *data, size_t size, size_t i, int *start_len) {
    if (i + 3 < size && data[i] == 0 && data[i + 1] == 0 && data[i + 2] == 1) {
        *start_len = 3;
        return true;
    }
    if (i + 4 <= size && data[i] == 0 && data[i + 1] == 0 && data[i + 2] == 0 && data[i + 3] == 1) {
        *start_len = 4;
        return true;
    }
    return false;
}

inline bool parse_parameter_sets(int codec, const uint8_t *data, size_t size, int *width, int *height) {
    if (data == nullptr || size == 0) {
        return false;
    }
    size_t i = 0;
    bool found_start = false;
    while (i + 3 < size) {
        int start_len = 0;
        if (!nal_at(data, size, i, &start_len)) {
            i++;
            continue;
        }
        found_start = true;
        size_t nal = i + start_len;
        size_t next = nal;
        while (next + 3 < size && !nal_at(data, size, next, &start_len)) {
            next++;
        }
        if (next + 3 >= size) {
            next = size;
        }
        bool ok = false;
        if (codec == 0) {
            ok = parse_h264_sps(data + nal, next - nal, width, height);
        } else {
            ok = parse_h265_sps(data + nal, next - nal, width, height);
        }
        if (ok) {
            return true;
        }
        i = next;
    }
    if (!found_start) {
        if (codec == 0) {
            return parse_h264_sps(data, size, width, height);
        }
        return parse_h265_sps(data, size, width, height);
    }
    return false;
}

// True when start() must Close() and Open() again. A healthy session keeps
// opened set and both failure flags clear. Event 0 before the first PLAY, and
// event 1 after reconnect gives up, set a failure flag while opened stays
// true: the live555 thread is still inside Open(), and another Open() is a
// no-op until that thread is joined.
inline bool session_needs_reopen(bool opened, bool describe_failed, bool conn_failed) {
    return !opened || describe_failed || conn_failed;
}

// Decision applied by KdRtspPlayer::OnVideoData. ignore leaves the queue and
// need_idr untouched. A dropped AU still updates need_idr. Only a non-oversized
// keyframe clears need_idr; a full queue is discarded only when that keyframe
// is accepted.
struct AuDecision {
    bool ignore = false;
    bool drop = true;
    bool clear_queue = false;
    bool need_idr = true;
    const char *latch = nullptr;
};

inline AuDecision admit_access_unit(bool opened, const uint8_t *data, size_t size, bool keyframe,
                                    bool need_idr, int queued, size_t queued_bytes, int cache_count,
                                    size_t au_cap) {
    AuDecision decision;
    decision.need_idr = need_idr;
    if (!opened || data == nullptr || size == 0) {
        decision.ignore = true;
        return decision;
    }
    bool full = queued >= cache_count || queued_bytes + size > kQueueBytes;
    if (size > au_cap) {
        if (!need_idr) {
            decision.latch = "au too big";
        }
        decision.need_idr = true;
        decision.drop = true;
    } else if (need_idr && !keyframe) {
        decision.drop = true;
    } else if (full && !keyframe) {
        if (!need_idr) {
            decision.latch = "queue full";
        }
        decision.need_idr = true;
        decision.drop = true;
    } else if (full) {
        decision.clear_queue = true;
        decision.drop = false;
        decision.need_idr = false;
    } else {
        decision.drop = false;
        if (keyframe) {
            decision.need_idr = false;
        }
    }
    return decision;
}

}  // namespace rtsp_player
