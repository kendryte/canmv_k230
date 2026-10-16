#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <cstring>
#include <deque>
#include <mutex>
#include <new>
#include <pthread.h>
#include <sched.h>
#include <string>
#include <thread>
#include <vector>

#include "rtsp_player_logic.h"

#include <stdio.h>

#include "k_vo_comm.h"
#include "mpi_nonai_2d_api.h"
#include "mpi_sys_api.h"
#include "mpi_vb_api.h"
#include "mpi_vdec_api.h"
#include "multimedia_wrap.h"
#include "rtsp_client.h"

namespace {

constexpr int kDescribeWaitMs = 8000;
constexpr int kSendTimeoutMs = 30;
constexpr int kVdecGetTimeoutMs = 0;
constexpr int kInputBufNum = 8;
// A failed send is retried this long, draining decoded output in between.
// While catching up after a network pause VDEC can hold every input block for
// more than 20 ms; giving up then costs a whole GOP. Retrying only stalls the
// decode thread, the reader keeps filling the queue.
constexpr int kSendRetryMs = 500;
// The reader must never stop pulling the socket: on this lwIP stack that made
// TCP throughput fall below the stream rate. So the queue drops when full, and
// is sized to absorb a burst after a short network pause instead. AUs are
// stored at their real size, so this budget holds cache_count frames of a
// normal stream while one oversized IDR still fits.
constexpr int kDefaultBlockW = 1920;
constexpr int kDefaultBlockH = 1088;

static int align16(int value) {
    return (value + 15) & ~15;
}

static int even_ok(int value) {
    return value >= 0 && (value % 2) == 0;
}

struct AuSlot {
    std::vector<uint8_t> data;
    uint64_t pts = 0;
    bool key = false;
};

static k_u64 align_pool(k_u64 size) {
    return (size + 4095u) & ~4095ull;
}

}  // namespace

class KdRtspPlayer : public IOnVideoData, public IRtspClientEvent {
  public:
    KdRtspPlayer() = default;
    ~KdRtspPlayer() { deinit(); }

    int init(const char *url, int cache_count, int buffer_count, int out_width, int out_height);
    int start();
    int stop();
    void deinit();
    int video_size(int *width, int *height);
    int bind_info(int x, int y, int *width, int *height, int *mod_id, int *dev_id, int *chn_id, int *pix_format);
    int get_frame(int timeout_ms, RtspPlayerFrame **image);
    int check();

    void OnVideoType(VideoType type, uint8_t *extra_data, size_t extra_data_size) override;
    void OnVideoData(const uint8_t *data, size_t size, uint64_t timestamp, bool keyframe) override;
    void OnRtspClientEvent(int event) override;

  private:
    int open_locked();
    void close_session();
    void clear_queue_locked();
    int create_vdec();
    void destroy_vdec();
    int create_nonai(k_pixel_format fmt, k_u64 blk_size, int blk_cnt, int *chn, k_u32 *pool);
    void destroy_nonai(int *chn, k_u32 *pool);
    void release_rgb_locked();
    bool display_is_bound();
    void unbind_display();
    void decode_loop();
    int send_stream(const uint8_t *data, size_t size, uint64_t pts, k_s32 *vdec_ret);
    bool publish_display(k_video_frame_info *frame);
    void publish_rgb(k_video_frame_info *frame);
    void compact_rgb_locked(k_video_frame_info *frame, void *virt, k_u32 map_size);

    std::mutex mu_;
    std::condition_variable describe_cv_;
    std::condition_variable queue_cv_;
    std::condition_variable frame_cv_;

    KdRtspClient client_;
    bool client_inited_ = false;
    bool opened_ = false;
    bool inited_ = false;
    bool started_ = false;
    bool described_ = false;
    bool describe_failed_ = false;
    bool conn_failed_ = false;
    bool decode_run_ = false;
    bool need_idr_ = true;
    bool waiting_ = false;
    bool frame_ready_ = false;
    bool display_bound_ = false;

    std::string url_;
    int cache_count_ = 60;
    int buffer_count_ = 6;
    int out_w_ = 0;
    int out_h_ = 0;
    int codec_ = -1;
    int video_w_ = 0;
    int video_h_ = 0;
    size_t au_cap_ = (size_t)kDefaultBlockW * kDefaultBlockH;

    std::deque<AuSlot> queue_;
    size_t queue_bytes_ = 0;
    std::thread decode_thread_;

    bool vdec_ready_ = false;
    bool vdec_chn_held_ = false;
    k_u32 vdec_chn_ = 0;
    k_u32 input_pool_ = VB_INVALID_POOLID;
    k_u32 output_pool_ = VB_INVALID_POOLID;
    k_u64 input_blk_size_ = 0;

    int display_chn_ = -1;
    k_u32 display_pool_ = VB_INVALID_POOLID;
    int disp_x_ = 0;
    int disp_y_ = 0;
    int disp_w_ = 0;
    int disp_h_ = 0;

    int rgb_chn_ = -1;
    k_u32 rgb_pool_ = VB_INVALID_POOLID;
    bool rgb_held_ = false;
    k_video_frame_info rgb_frame_{};
    void *rgb_virt_ = nullptr;
    k_u32 rgb_map_size_ = 0;
    RtspPlayerFrame rgb_view_{};
};

static std::mutex g_players_mu;
static std::vector<KdRtspPlayer *> g_players;
constexpr size_t kMaxRtspClients = 4;

void KdRtspPlayer::OnVideoType(VideoType type, uint8_t *extra_data, size_t extra_data_size) {
    std::lock_guard<std::mutex> lock(mu_);
    if (type == VideoTypeH264) {
        codec_ = 0;
    } else if (type == VideoTypeH265) {
        codec_ = 1;
    } else {
        codec_ = -1;
        describe_failed_ = true;
        describe_cv_.notify_all();
        return;
    }
    int w = 0;
    int h = 0;
    if (rtsp_player::parse_parameter_sets(codec_, extra_data, extra_data_size, &w, &h)) {
        video_w_ = w;
        video_h_ = h;
        size_t cap = (size_t)align16(w) * (size_t)align16(h);
        if (cap > au_cap_) {
            au_cap_ = cap;
        }
    }
    described_ = true;
    describe_failed_ = false;
    describe_cv_.notify_all();
    printf("rtsp_client: codec %s size %d x %d\n", codec_ == 0 ? "h264" : "h265", video_w_, video_h_);
}

void KdRtspPlayer::OnVideoData(const uint8_t *data, size_t size, uint64_t timestamp, bool keyframe) {
    int queued = 0;
    size_t queued_bytes = 0;
    int limit = 0;
    const char *latch = nullptr;
    {
        std::unique_lock<std::mutex> lock(mu_);
        queued = (int)queue_.size();
        queued_bytes = queue_bytes_;
        limit = cache_count_;
        // Drop until the next keyframe. The access unit that set need_idr_
        // already reported why. A full queue is kept until that keyframe.
        rtsp_player::AuDecision decision = rtsp_player::admit_access_unit(
            opened_, data, size, keyframe, need_idr_, queued, queued_bytes, limit, au_cap_);
        if (decision.ignore) {
            return;
        }
        latch = decision.latch;
        need_idr_ = decision.need_idr;
        if (!decision.drop) {
            if (decision.clear_queue) {
                clear_queue_locked();
            }
            AuSlot au;
            au.data.assign(data, data + size);
            au.pts = timestamp;
            au.key = keyframe;
            queue_bytes_ += size;
            queue_.push_back(std::move(au));
            queue_cv_.notify_one();
        }
    }
    if (latch != nullptr) {
        printf("rtsp_client: need idr: %s, queued %d/%d, %u/%u KB, au %u B\n",
               latch, queued, limit, (unsigned)(queued_bytes / 1024),
               (unsigned)(rtsp_player::kQueueBytes / 1024), (unsigned)size);
    }
}

void KdRtspPlayer::OnRtspClientEvent(int event) {
    std::lock_guard<std::mutex> lock(mu_);
    if (event != 0) {
        printf("rtsp_client: connection failed\n");
        conn_failed_ = true;
        describe_failed_ = true;
    } else {
        printf("rtsp_client: session closed\n");
        // After PLAY, the live555 thread reconnects and calls OnVideoType again.
        // Leave opened_ set: Open() does nothing while that thread is alive.
        // Before start(), this flag tells start() the session is not usable and
        // it must Close() first. A drop after start() is recovered by live555,
        // so do not fail a describe wait that is no longer running.
        if (!started_) {
            describe_failed_ = true;
        }
    }
    need_idr_ = true;
    clear_queue_locked();
    describe_cv_.notify_all();
    queue_cv_.notify_all();
    frame_cv_.notify_all();
}

void KdRtspPlayer::clear_queue_locked() {
    queue_.clear();
    queue_bytes_ = 0;
}

int KdRtspPlayer::open_locked() {
    if (!client_inited_) {
        RtspClientInitParam param;
        param.on_video_data = this;
        param.on_audio_data = nullptr;
        param.on_backchannel = nullptr;
        param.on_event = this;
        if (client_.Init(param) < 0) {
            printf("rtsp_client: KdRtspClient::Init failed\n");
            return -1;
        }
        client_inited_ = true;
    }
    described_ = false;
    describe_failed_ = false;
    if (client_.Open(url_.c_str()) < 0) {
        printf("rtsp_client: open failed\n");
        return -1;
    }
    opened_ = true;
    return 0;
}

void KdRtspPlayer::close_session() {
    {
        std::lock_guard<std::mutex> lock(mu_);
        if (!opened_) {
            return;
        }
        opened_ = false;
    }
    client_.Close();
}

int KdRtspPlayer::init(const char *url, int cache_count, int buffer_count, int out_width, int out_height) {
    std::unique_lock<std::mutex> lock(mu_);
    if (started_) {
        return -1;
    }
    if (opened_) {
        lock.unlock();
        close_session();
        lock.lock();
    }
    url_ = url ? url : "";
    cache_count_ = cache_count;
    buffer_count_ = buffer_count;
    out_w_ = out_width;
    out_h_ = out_height;
    codec_ = -1;
    video_w_ = 0;
    video_h_ = 0;
    described_ = false;
    describe_failed_ = false;
    conn_failed_ = false;
    need_idr_ = true;
    clear_queue_locked();
    au_cap_ = (size_t)kDefaultBlockW * kDefaultBlockH;
    lock.unlock();
    if (open_locked() < 0) {
        return -1;
    }
    lock.lock();
    bool ok = describe_cv_.wait_for(lock, std::chrono::milliseconds(kDescribeWaitMs), [&] {
        return described_ || describe_failed_;
    });
    if (!ok || describe_failed_ || codec_ < 0) {
        lock.unlock();
        close_session();
        printf("rtsp_client: DESCRIBE failed\n");
        return -1;
    }
    if ((out_w_ > 0 || out_h_ > 0) &&
        (out_w_ <= 0 || out_h_ <= 0 || (out_w_ % 2) != 0 || (out_h_ % 2) != 0 ||
         out_w_ > video_w_ || out_h_ > video_h_)) {
        lock.unlock();
        close_session();
        printf("rtsp_client: output size %d x %d is not a downscale of %d x %d\n",
               out_w_, out_h_, video_w_, video_h_);
        return -1;
    }
    inited_ = true;
    return 0;
}

int KdRtspPlayer::create_nonai(k_pixel_format fmt, k_u64 blk_size, int blk_cnt, int *chn, k_u32 *pool) {
    k_u32 got = 0;
    if (kd_mpi_nonai_2d_request_chn(&got) != K_SUCCESS) {
        printf("rtsp_client: request nonai_2d failed\n");
        return -1;
    }
    k_u32 pool_id = kd_mpi_vb_create_pool_ex(align_pool(blk_size), blk_cnt, VB_REMAP_MODE_NOCACHE);
    if (pool_id == VB_INVALID_POOLID) {
        kd_mpi_nonai_2d_release_chn(got);
        printf("rtsp_client: nonai vb pool failed\n");
        return -1;
    }
    if (kd_mpi_nonai_2d_attach_vb_pool(got, pool_id) != K_SUCCESS) {
        kd_mpi_vb_destory_pool(pool_id);
        kd_mpi_nonai_2d_release_chn(got);
        printf("rtsp_client: nonai attach vb failed\n");
        return -1;
    }
    k_nonai_2d_chn_attr attr;
    memset(&attr, 0, sizeof(attr));
    attr.dst_fmt = fmt;
    attr.mode = K_NONAI_2D_CALC_MODE_CSC;
    if (kd_mpi_nonai_2d_create_chn(got, &attr) != K_SUCCESS ||
        kd_mpi_nonai_2d_start_chn(got) != K_SUCCESS) {
        kd_mpi_nonai_2d_detach_vb_pool(got);
        kd_mpi_nonai_2d_destroy_chn(got);
        kd_mpi_vb_destory_pool(pool_id);
        kd_mpi_nonai_2d_release_chn(got);
        printf("rtsp_client: nonai create/start failed\n");
        return -1;
    }
    *chn = (int)got;
    *pool = pool_id;
    return 0;
}

void KdRtspPlayer::destroy_nonai(int *chn, k_u32 *pool) {
    if (*chn >= 0) {
        kd_mpi_nonai_2d_stop_chn(*chn);
        kd_mpi_nonai_2d_detach_vb_pool(*chn);
        kd_mpi_nonai_2d_destroy_chn(*chn);
        kd_mpi_nonai_2d_release_chn(*chn);
        *chn = -1;
    }
    if (*pool != VB_INVALID_POOLID) {
        kd_mpi_vb_destory_pool(*pool);
        *pool = VB_INVALID_POOLID;
    }
}

int KdRtspPlayer::create_vdec() {
    if (!vdec_chn_held_) {
        k_u32 chn = 0;
        if (kd_mpi_vdec_request_chn(&chn) != K_SUCCESS) {
            printf("rtsp_client: no free vdec channel\n");
            return -1;
        }
        vdec_chn_ = chn;
        vdec_chn_held_ = true;
        printf("rtsp_client: vdec channel %u\n", vdec_chn_);
    }
    int width = video_w_ > 0 ? video_w_ : kDefaultBlockW;
    int height = video_h_ > 0 ? video_h_ : kDefaultBlockH;
    int pic_w = align16(width);
    int pic_h = align16(height);
    input_blk_size_ = (k_u64)pic_w * pic_h;
    if (input_blk_size_ < au_cap_) {
        input_blk_size_ = au_cap_;
    }

    k_vb_pool_config cfg;
    memset(&cfg, 0, sizeof(cfg));
    cfg.blk_cnt = kInputBufNum;
    cfg.blk_size = input_blk_size_;
    cfg.mode = VB_REMAP_MODE_NOCACHE;
    input_pool_ = kd_mpi_vb_create_pool(&cfg);
    if (input_pool_ == VB_INVALID_POOLID) {
        printf("rtsp_client: vdec input pool failed\n");
        destroy_vdec();
        return -1;
    }
    memset(&cfg, 0, sizeof(cfg));
    cfg.blk_cnt = buffer_count_;
    cfg.blk_size = (k_u64)pic_w * pic_h * 2;
    cfg.mode = VB_REMAP_MODE_NOCACHE;
    output_pool_ = kd_mpi_vb_create_pool(&cfg);
    if (output_pool_ == VB_INVALID_POOLID) {
        printf("rtsp_client: vdec output pool failed\n");
        destroy_vdec();
        return -1;
    }
    k_s32 ret = kd_mpi_vdec_attach_vb_pool(vdec_chn_, output_pool_);
    if (ret != K_SUCCESS) {
        printf("rtsp_client: attach vb pool failed %d\n", ret);
        destroy_vdec();
        return -1;
    }
    k_vdec_chn_attr attr;
    memset(&attr, 0, sizeof(attr));
    attr.pic_width = pic_w;
    attr.pic_height = pic_h;
    attr.stream_buf_size = (k_u32)input_blk_size_;
    attr.mode = K_VDEC_SEND_MODE_STREAM;
    attr.type = (codec_ == 1) ? K_PT_H265 : K_PT_H264;
    ret = kd_mpi_vdec_create_chn(vdec_chn_, &attr);
    if (ret != K_SUCCESS) {
        printf("rtsp_client: create vdec failed %d\n", ret);
        destroy_vdec();
        return -1;
    }
    if (out_w_ > 0 && out_h_ > 0 && (out_w_ != video_w_ || out_h_ != video_h_)) {
        k_vdec_downscale dsl;
        memset(&dsl, 0, sizeof(dsl));
        dsl.dsl_mode = K_VDEC_DSL_MODE_BY_SIZE;
        dsl.dsl_size.dsl_frame_width = (k_u32)out_w_;
        dsl.dsl_size.dsl_frame_height = (k_u32)out_h_;
        ret = kd_mpi_vdec_set_downscale(vdec_chn_, &dsl);
        if (ret != K_SUCCESS) {
            printf("rtsp_client: set downscale %dx%d failed %d\n", out_w_, out_h_, ret);
            kd_mpi_vdec_destroy_chn(vdec_chn_);
            destroy_vdec();
            return -1;
        }
        printf("rtsp_client: vdec downscale %d x %d -> %d x %d\n", video_w_, video_h_, out_w_, out_h_);
    }
    ret = kd_mpi_vdec_start_chn(vdec_chn_);
    if (ret != K_SUCCESS) {
        printf("rtsp_client: start vdec failed %d\n", ret);
        kd_mpi_vdec_destroy_chn(vdec_chn_);
        destroy_vdec();
        return -1;
    }
    vdec_ready_ = true;
    return 0;
}

void KdRtspPlayer::destroy_vdec() {
    if (vdec_ready_) {
        k_vb_blk_handle handle = kd_mpi_vb_get_block(input_pool_, input_blk_size_, NULL);
        if (handle != VB_INVALID_HANDLE) {
            k_vdec_stream stream;
            memset(&stream, 0, sizeof(stream));
            stream.end_of_stream = K_TRUE;
            stream.phy_addr = kd_mpi_vb_handle_to_phyaddr(handle);
            kd_mpi_vdec_send_stream(vdec_chn_, &stream, kSendTimeoutMs);
            kd_mpi_vb_release_block(handle);
            for (int i = 0; i < 20; ++i) {
                k_vdec_chn_status status;
                memset(&status, 0, sizeof(status));
                if (kd_mpi_vdec_query_status(vdec_chn_, &status) != K_SUCCESS ||
                    status.end_of_stream == K_TRUE) {
                    break;
                }
                k_video_frame_info frame;
                k_vdec_supplement_info supplement;
                memset(&frame, 0, sizeof(frame));
                memset(&supplement, 0, sizeof(supplement));
                if (kd_mpi_vdec_get_frame(vdec_chn_, &frame, &supplement, kSendTimeoutMs) == K_SUCCESS) {
                    kd_mpi_vdec_release_frame(vdec_chn_, &frame);
                }
            }
        }
        kd_mpi_vdec_stop_chn(vdec_chn_);
        kd_mpi_vdec_destroy_chn(vdec_chn_);
        vdec_ready_ = false;
    }
    if (vdec_chn_held_) {
        kd_mpi_vdec_detach_vb_pool(vdec_chn_);
    }
    if (output_pool_ != VB_INVALID_POOLID) {
        kd_mpi_vb_destory_pool(output_pool_);
        output_pool_ = VB_INVALID_POOLID;
    }
    if (input_pool_ != VB_INVALID_POOLID) {
        kd_mpi_vb_destory_pool(input_pool_);
        input_pool_ = VB_INVALID_POOLID;
    }
    if (vdec_chn_held_) {
        kd_mpi_vdec_release_chn(vdec_chn_);
        vdec_chn_held_ = false;
    }
}

void KdRtspPlayer::release_rgb_locked() {
    if (rgb_virt_ != nullptr) {
        kd_mpi_sys_munmap(rgb_virt_, rgb_map_size_);
        rgb_virt_ = nullptr;
        rgb_map_size_ = 0;
    }
    if (rgb_held_ && rgb_chn_ >= 0) {
        kd_mpi_nonai_2d_release_frame(rgb_chn_, &rgb_frame_);
        rgb_held_ = false;
    }
    memset(&rgb_view_, 0, sizeof(rgb_view_));
    frame_ready_ = false;
}

bool KdRtspPlayer::display_is_bound() {
    if (display_chn_ < 0) {
        return false;
    }
    for (int layer = K_VO_LAYER_VIDEO1; layer <= K_VO_LAYER_VIDEO3; layer++) {
        k_mpp_chn dest;
        k_mpp_chn src;
        memset(&dest, 0, sizeof(dest));
        memset(&src, 0, sizeof(src));
        dest.mod_id = K_ID_VO;
        dest.dev_id = 0;
        dest.chn_id = layer;
        if (kd_mpi_sys_get_bind_by_dest(&dest, &src) != K_SUCCESS) {
            continue;
        }
        if (src.mod_id == K_ID_NONAI_2D && src.dev_id == 0 && src.chn_id == display_chn_) {
            return true;
        }
    }
    return false;
}

void KdRtspPlayer::unbind_display() {
    if (display_chn_ < 0) {
        return;
    }
    for (int layer = K_VO_LAYER_VIDEO1; layer < K_MAX_VO_LAYER_NR; layer++) {
        k_mpp_chn dest;
        k_mpp_chn src;
        memset(&dest, 0, sizeof(dest));
        memset(&src, 0, sizeof(src));
        dest.mod_id = K_ID_VO;
        dest.dev_id = 0;
        dest.chn_id = layer;
        if (kd_mpi_sys_get_bind_by_dest(&dest, &src) != K_SUCCESS) {
            continue;
        }
        if (src.mod_id == K_ID_NONAI_2D && src.dev_id == 0 && src.chn_id == display_chn_) {
            kd_mpi_sys_unbind(&src, &dest);
        }
    }
    display_bound_ = false;
}

int KdRtspPlayer::start() {
    std::unique_lock<std::mutex> lock(mu_);
    if (!inited_ || started_ || codec_ < 0) {
        return -1;
    }
    if (video_w_ <= 0 || video_h_ <= 0) {
        printf("rtsp_client: video size unknown\n");
        return -1;
    }
    // opened_ stays true after a session-closed event. Reopen when that event
    // happened before the first PLAY, or when reconnect has given up. Close()
    // joins the idle live555 thread so the following Open() actually runs.
    bool reopen = rtsp_player::session_needs_reopen(opened_, describe_failed_, conn_failed_);
    lock.unlock();
    if (reopen) {
        close_session();
        if (open_locked() < 0) {
            return -1;
        }
    }
    lock.lock();
    if (reopen) {
        bool ok = describe_cv_.wait_for(lock, std::chrono::milliseconds(kDescribeWaitMs), [&] {
            return described_ || describe_failed_;
        });
        if (!ok || describe_failed_ || codec_ < 0) {
            lock.unlock();
            close_session();
            return -1;
        }
    }
    int rgb_w = (out_w_ > 0) ? out_w_ : video_w_;
    int rgb_h = (out_h_ > 0) ? out_h_ : video_h_;
    k_u64 rgb_size = (k_u64)align16(rgb_w) * align16(rgb_h) * 3;
    if (create_nonai(PIXEL_FORMAT_RGB_888_PLANAR, rgb_size, 2, &rgb_chn_, &rgb_pool_) < 0) {
        return -1;
    }
    if (create_vdec() < 0) {
        destroy_nonai(&rgb_chn_, &rgb_pool_);
        return -1;
    }
    clear_queue_locked();
    need_idr_ = true;
    conn_failed_ = false;
    display_bound_ = false;
    decode_run_ = true;
    started_ = true;
    decode_thread_ = std::thread([this] {
        // Smaller is higher. Stay ahead of MicroPython (25) and behind the
        // live555 reader (12), so a full AU copy cannot block the socket.
        struct sched_param param;
        param.sched_priority = 14;
        int sched_ret = pthread_setschedparam(pthread_self(), SCHED_FIFO, &param);
        if (sched_ret != 0) {
            printf("rtsp_client: decode priority 14 failed: %d\n", sched_ret);
        }
        decode_loop();
    });
    return 0;
}

int KdRtspPlayer::stop() {
    std::unique_lock<std::mutex> lock(mu_);
    if (!started_) {
        return 0;
    }
    decode_run_ = false;
    started_ = false;
    queue_cv_.notify_all();
    frame_cv_.notify_all();
    lock.unlock();
    if (decode_thread_.joinable()) {
        decode_thread_.join();
    }
    close_session();
    lock.lock();
    release_rgb_locked();
    destroy_nonai(&rgb_chn_, &rgb_pool_);
    destroy_vdec();
    clear_queue_locked();
    waiting_ = false;
    conn_failed_ = false;
    return 0;
}

void KdRtspPlayer::deinit() {
    stop();
    std::lock_guard<std::mutex> lock(mu_);
    unbind_display();
    destroy_nonai(&display_chn_, &display_pool_);
    disp_w_ = 0;
    disp_h_ = 0;
    inited_ = false;
    described_ = false;
    if (client_inited_) {
        client_.DeInit();
        client_inited_ = false;
    }
    opened_ = false;
}

int KdRtspPlayer::video_size(int *width, int *height) {
    std::lock_guard<std::mutex> lock(mu_);
    *width = video_w_;
    *height = video_h_;
    return 0;
}

int KdRtspPlayer::bind_info(int x, int y, int *width_io, int *height_io, int *mod_id, int *dev_id,
                            int *chn_id, int *pix_format) {
    int width = *width_io;
    int height = *height_io;
    std::lock_guard<std::mutex> lock(mu_);
    if (!inited_ || video_w_ <= 0 || video_h_ <= 0) {
        return -1;
    }
    if (started_) {
        return -1;
    }
    if (!even_ok(x) || !even_ok(y)) {
        return -1;
    }
    if (width == 0) {
        width = out_w_ > 0 ? out_w_ : video_w_;
    }
    if (height == 0) {
        height = out_h_ > 0 ? out_h_ : video_h_;
    }
    if (width <= 0 || height <= 0 || !even_ok(width) || !even_ok(height)) {
        return -1;
    }
    unbind_display();
    destroy_nonai(&display_chn_, &display_pool_);
    k_u64 nv12_size = (k_u64)width * height * 3 / 2;
    if (create_nonai(PIXEL_FORMAT_YUV_SEMIPLANAR_420, nv12_size, 4, &display_chn_, &display_pool_) < 0) {
        return -1;
    }
    disp_x_ = x;
    disp_y_ = y;
    disp_w_ = width;
    disp_h_ = height;
    display_bound_ = false;
    *mod_id = K_ID_NONAI_2D;
    *dev_id = 0;
    *chn_id = display_chn_;
    *pix_format = PIXEL_FORMAT_YUV_SEMIPLANAR_420;
    *width_io = width;
    *height_io = height;
    return 0;
}

int KdRtspPlayer::check() {
    std::lock_guard<std::mutex> lock(mu_);
    return conn_failed_ ? -3 : 0;
}

int KdRtspPlayer::get_frame(int timeout_ms, RtspPlayerFrame **image) {
    std::unique_lock<std::mutex> lock(mu_);
    if (conn_failed_) {
        return -3;
    }
    if (!started_) {
        return -2;
    }
    if (!frame_ready_) {
        waiting_ = true;
        bool ok = frame_cv_.wait_for(lock, std::chrono::milliseconds(timeout_ms), [&] {
            return frame_ready_ || !started_ || conn_failed_;
        });
        waiting_ = false;
        if (conn_failed_) {
            return -3;
        }
        if (!started_) {
            return -2;
        }
        if (!ok || !frame_ready_) {
            return 1;
        }
    }
    frame_ready_ = false;
    // rgb_view_ borrows the only mapped RGB buffer. The next get_frame() that
    // waits, and stop()/deinit(), unmap it. The caller must finish reading
    // before either of those.
    *image = &rgb_view_;
    return 0;
}

// 0 sent, -1 no input block, -2 mmap failed, -3 kd_mpi_vdec_send_stream
// failed (its code goes to *vdec_ret).
int KdRtspPlayer::send_stream(const uint8_t *data, size_t size, uint64_t pts, k_s32 *vdec_ret) {
    *vdec_ret = K_SUCCESS;
    k_vb_blk_handle handle = kd_mpi_vb_get_block(input_pool_, input_blk_size_, NULL);
    if (handle == VB_INVALID_HANDLE) {
        return -1;
    }
    k_u64 phys = kd_mpi_vb_handle_to_phyaddr(handle);
    void *virt = kd_mpi_sys_mmap(phys, (k_u32)input_blk_size_);
    if (virt == nullptr) {
        kd_mpi_vb_release_block(handle);
        return -2;
    }
    memcpy(virt, data, size);
    kd_mpi_sys_munmap(virt, (k_u32)input_blk_size_);

    k_vdec_stream stream;
    memset(&stream, 0, sizeof(stream));
    stream.len = (k_u32)size;
    stream.pts = pts;
    stream.phy_addr = phys;
    stream.end_of_stream = K_FALSE;
    k_s32 ret = kd_mpi_vdec_send_stream(vdec_chn_, &stream, kSendTimeoutMs);
    kd_mpi_vb_release_block(handle);
    *vdec_ret = ret;
    return ret == K_SUCCESS ? 0 : -3;
}

bool KdRtspPlayer::publish_display(k_video_frame_info *frame) {
    if (display_chn_ < 0) {
        return false;
    }
    if (!display_bound_) {
        display_bound_ = display_is_bound();
    }
    if (!display_bound_) {
        return false;
    }
    k_video_frame *src = &frame->v_frame;
    int sw = (int)src->width;
    int sh = (int)src->height;
    if (sw == disp_w_ && sh == disp_h_) {
        return kd_mpi_nonai_2d_send_frame(display_chn_, frame, kSendTimeoutMs) == K_SUCCESS;
    }
    return false;
}

void KdRtspPlayer::compact_rgb_locked(k_video_frame_info *frame, void *virt, k_u32 map_size) {
    k_u32 plane = frame->v_frame.width * frame->v_frame.height;
    uint8_t *base = (uint8_t *)virt;
    k_u64 y = frame->v_frame.phys_addr[0];
    auto move_plane = [&](int idx, k_u32 dst_off) {
        k_u64 phys = frame->v_frame.phys_addr[idx];
        if (phys == 0 || y == 0 || phys < y) {
            return;
        }
        k_u64 off = phys - y;
        if (off == dst_off) {
            return;
        }
        if (off + plane > map_size || (k_u64)dst_off + plane > map_size) {
            return;
        }
        memmove(base + dst_off, base + off, plane);
    };
    move_plane(1, plane);
    move_plane(2, plane * 2);
}

void KdRtspPlayer::publish_rgb(k_video_frame_info *frame) {
    bool want = false;
    {
        std::lock_guard<std::mutex> lock(mu_);
        // One outstanding RGB. The decode thread is higher priority than
        // MicroPython, so it can run again before get_frame() reads view->data.
        // Replacing the buffer here unmaps that pointer and the main thread
        // takes a load page fault.
        want = waiting_ && !frame_ready_;
    }
    if (!want || rgb_chn_ < 0) {
        return;
    }
    if (kd_mpi_nonai_2d_send_frame(rgb_chn_, frame, kSendTimeoutMs) != K_SUCCESS) {
        return;
    }
    k_video_frame_info out;
    memset(&out, 0, sizeof(out));
    if (kd_mpi_nonai_2d_get_frame(rgb_chn_, &out, kSendTimeoutMs) != K_SUCCESS) {
        return;
    }
    k_u32 plane = out.v_frame.width * out.v_frame.height;
    k_u32 map_size = plane * 3;
    if (out.v_frame.phys_addr[2] > out.v_frame.phys_addr[0]) {
        k_u64 span = out.v_frame.phys_addr[2] - out.v_frame.phys_addr[0] + plane;
        if (span > map_size && span < 64u * 1024u * 1024u) {
            map_size = (k_u32)span;
        }
    }
    void *virt = kd_mpi_sys_mmap_cached(out.v_frame.phys_addr[0], map_size);
    if (virt == nullptr) {
        kd_mpi_nonai_2d_release_frame(rgb_chn_, &out);
        return;
    }
    compact_rgb_locked(&out, virt, map_size);
    std::lock_guard<std::mutex> lock(mu_);
    if (!waiting_ || frame_ready_) {
        kd_mpi_sys_munmap(virt, map_size);
        kd_mpi_nonai_2d_release_frame(rgb_chn_, &out);
        return;
    }
    release_rgb_locked();
    rgb_frame_ = out;
    rgb_virt_ = virt;
    rgb_map_size_ = map_size;
    rgb_held_ = true;
    if (video_w_ <= 0 || video_h_ <= 0) {
        video_w_ = (int)out.v_frame.width;
        video_h_ = (int)out.v_frame.height;
    }
    memset(&rgb_view_, 0, sizeof(rgb_view_));
    rgb_view_.width = (int)out.v_frame.width;
    rgb_view_.height = (int)out.v_frame.height;
    rgb_view_.data = virt;
    rgb_view_.phy_addr = out.v_frame.phys_addr[0];
    rgb_view_.size = plane * 3;
    rgb_view_.pool_id = out.pool_id;
    frame_ready_ = true;
    frame_cv_.notify_all();
}

void KdRtspPlayer::decode_loop() {
    while (true) {
        std::vector<AuSlot> batch;
        {
            std::unique_lock<std::mutex> lock(mu_);
            queue_cv_.wait(lock, [&] { return !queue_.empty() || !decode_run_; });
            if (!decode_run_ && queue_.empty()) {
                return;
            }
            batch.reserve(queue_.size());
            for (AuSlot &au : queue_) {
                batch.push_back(std::move(au));
            }
            clear_queue_locked();
        }
        k_vdec_supplement_info supplement;
        auto drain_output = [&]() {
            while (true) {
                k_video_frame_info frame;
                memset(&frame, 0, sizeof(frame));
                memset(&supplement, 0, sizeof(supplement));
                if (kd_mpi_vdec_get_frame(vdec_chn_, &frame, &supplement, kVdecGetTimeoutMs) != K_SUCCESS) {
                    break;
                }
                // get_frame keeps returning the same buffer until release_frame.
                // Release only after this frame has been handed off, then the next
                // get returns the following picture.
                publish_rgb(&frame);
                publish_display(&frame);
                kd_mpi_vdec_release_frame(vdec_chn_, &frame);
            }
        };
        for (size_t i = 0; i < batch.size(); ++i) {
            AuSlot &au = batch[i];
            int sent = -1;
            k_s32 vdec_ret = K_SUCCESS;
            auto send_from = std::chrono::steady_clock::now();
            long long send_ms = 0;
            // Out of input blocks means VDEC still holds earlier streams.
            // Wait for it rather than throwing the rest of the batch away.
            // VDEC only frees input once it has an output buffer to decode
            // into, so release finished pictures between attempts.
            while (true) {
                sent = send_stream(au.data.data(), au.data.size(), au.pts, &vdec_ret);
                send_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
                    std::chrono::steady_clock::now() - send_from).count();
                if (sent == 0 || send_ms >= kSendRetryMs) {
                    break;
                }
                {
                    std::lock_guard<std::mutex> lock(mu_);
                    if (!decode_run_) {
                        break;
                    }
                }
                drain_output();
                std::this_thread::sleep_for(std::chrono::milliseconds(5));
            }
            if (sent != 0) {
                int lost = (int)(batch.size() - i);
                bool was_clear = false;
                {
                    std::lock_guard<std::mutex> lock(mu_);
                    was_clear = !need_idr_;
                    need_idr_ = true;
                }
                const char *step = sent == -1 ? "no input block"
                                 : sent == -2 ? "mmap failed"
                                 : "vdec send failed";
                printf("rtsp_client: need idr: %s (ret 0x%x)%s, au %u B, key %d, "
                       "send %lld ms, batch %d/%d, lost %d\n",
                       step, (unsigned)vdec_ret, was_clear ? "" : " while waiting",
                       (unsigned)au.data.size(), au.key ? 1 : 0, send_ms,
                       (int)i + 1, (int)batch.size(), lost);
                break;
            }
        }
        drain_output();
        {
            std::lock_guard<std::mutex> lock(mu_);
            if (!decode_run_ && queue_.empty()) {
                return;
            }
        }
    }
}

extern "C" {

int RtspPlayer_count(void) {
    std::lock_guard<std::mutex> lock(g_players_mu);
    return (int)g_players.size();
}

KdRtspPlayer *RtspPlayer_create(void) {
    std::lock_guard<std::mutex> lock(g_players_mu);
    if (g_players.size() >= kMaxRtspClients) {
        printf("rtsp_client: at most %u clients\n", (unsigned)kMaxRtspClients);
        return nullptr;
    }
    KdRtspPlayer *player = new (std::nothrow) KdRtspPlayer();
    if (player == nullptr) {
        return nullptr;
    }
    g_players.push_back(player);
    return player;
}

void RtspPlayer_destroy(KdRtspPlayer *player) {
    if (player == nullptr) {
        return;
    }
    player->deinit();
    {
        std::lock_guard<std::mutex> lock(g_players_mu);
        for (auto it = g_players.begin(); it != g_players.end(); ++it) {
            if (*it == player) {
                g_players.erase(it);
                break;
            }
        }
    }
    delete player;
}

void RtspPlayer_DeInitAll(void) {
    std::lock_guard<std::mutex> lock(g_players_mu);
    for (KdRtspPlayer *player : g_players) {
        player->deinit();
    }
}

int RtspPlayer_init(KdRtspPlayer *player, const char *url, int cache_count, int buffer_count,
                    int out_width, int out_height) {
    return player->init(url, cache_count, buffer_count, out_width, out_height);
}

int RtspPlayer_start(KdRtspPlayer *player) {
    return player->start();
}

int RtspPlayer_stop(KdRtspPlayer *player) {
    return player->stop();
}

void RtspPlayer_deinit(KdRtspPlayer *player) {
    if (player != nullptr) {
        player->deinit();
    }
}

int RtspPlayer_video_size(KdRtspPlayer *player, int *width, int *height) {
    return player->video_size(width, height);
}

int RtspPlayer_bind_info(KdRtspPlayer *player, int x, int y, int *width, int *height,
                         int *mod_id, int *dev_id, int *chn_id, int *pix_format) {
    return player->bind_info(x, y, width, height, mod_id, dev_id, chn_id, pix_format);
}

int RtspPlayer_check(KdRtspPlayer *player) {
    return player->check();
}

int RtspPlayer_get_frame(KdRtspPlayer *player, int timeout_ms, void **image) {
    RtspPlayerFrame *out = nullptr;
    int ret = player->get_frame(timeout_ms, &out);
    if (ret == 0) {
        *image = out;
    }
    return ret;
}

}  // extern "C"
