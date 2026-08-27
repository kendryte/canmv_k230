#include "multimedia_wrap.h"
#include "rtsp_pusher.h"
#include "mpi_sys_api.h"

#include <algorithm>
#include <cstring>
#include <mutex>
#include <vector>

namespace {
std::mutex g_rtsp_pusher_mutex;
std::vector<KdRtspPusher *> g_rtsp_pusher;
}


KdRtspPusher * RtspPusher_create() {
    KdRtspPusher *pusher = new KdRtspPusher();
    std::lock_guard<std::mutex> lock(g_rtsp_pusher_mutex);
    g_rtsp_pusher.push_back(pusher);
    return pusher;
}

void RtspPusher_destroy(KdRtspPusher *p) {
    if (!p) {
        return;
    }

    {
        std::lock_guard<std::mutex> lock(g_rtsp_pusher_mutex);
        g_rtsp_pusher.erase(
            std::remove(g_rtsp_pusher.begin(), g_rtsp_pusher.end(), p),
            g_rtsp_pusher.end());
    }
    delete p;
}

void RtspPusher_DeInitAll(void) {
    std::lock_guard<std::mutex> lock(g_rtsp_pusher_mutex);
    for (KdRtspPusher *pusher : g_rtsp_pusher) {
        pusher->DeInit();
    }
}

int RtspPusher_Init(KdRtspPusher *p, int video_width, int video_height, const char *url, int fps, const char *transport) {
    RtspPusherInitParam param;
    param.video_width = video_width;
    param.video_height = video_height;
    param.video_fps = fps;

    if (url) {
        strncpy(param.sRtspUrl, url, sizeof(param.sRtspUrl) - 1);
        param.sRtspUrl[sizeof(param.sRtspUrl) - 1] = '\0';
    } else {
        param.sRtspUrl[0] = '\0';
    }

    if (transport) {
        strncpy(param.rtsp_transport, transport, sizeof(param.rtsp_transport) - 1);
        param.rtsp_transport[sizeof(param.rtsp_transport) - 1] = '\0';
    }

    param.on_event = nullptr;
    return p->Init(param);
}

void RtspPusher_DeInit(KdRtspPusher *p) {
    p->DeInit();
}

int RtspPusher_Open(KdRtspPusher *p) {
    return p->Open();
}

void RtspPusher_Close(KdRtspPusher *p) {
    p->Close();
}

int RtspPusher_PushVideoData(KdRtspPusher *p, const uint8_t *data, size_t size, bool key_frame, uint64_t timestamp) {
    return p->PushVideoData(data, size, key_frame, timestamp);
}

int RtspPusher_PushVideoHeader(KdRtspPusher *p, const uint8_t *data, size_t size) {
    return p->PushVideoHeader(data, size);
}
