#ifndef MULTIMEDIA_WRAP_H
#define MULTIMEDIA_WRAP_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>

typedef struct KdRtspServer KdRtspServer;
typedef struct SessionAttr SessionAttr;

typedef struct KdRtspPusher KdRtspPusher;

typedef struct KdRtspPlayer KdRtspPlayer;

typedef struct {
    int width;
    int height;
    void *data;
    uint64_t phy_addr;
    uint32_t size;
    uint32_t pool_id;
} RtspPlayerFrame;

#ifdef __cplusplus
extern "C" {
#endif

KdRtspServer * RtspServer_create();
void RtspServer_destroy(KdRtspServer *p);
void RtspServer_DeInitAll(void);
int RtspServer_Init(KdRtspServer *p, int port);
void RtspServer_DeInit(KdRtspServer *p);
int RtspServer_CreateSession(KdRtspServer *p, const char *session_name, const SessionAttr *session_attr);
int RtspServer_DestroySession(KdRtspServer *p, const char *session_name);
char* RtspServer_GetRtspUrl(KdRtspServer *p, const char *session_name);
void RtspServer_Start(KdRtspServer *p);
void RtspServer_Stop(KdRtspServer *p);
int RtspServer_SendVideoData(KdRtspServer *p, const char *session_name, const uint8_t *data, size_t size, uint64_t timestamp);
int RtspServer_SendAudioData(KdRtspServer *p, const char *session_name, const uint8_t *data, size_t size, uint64_t timestamp);
int RtspServer_SendVideoData_Byphyaddr(KdRtspServer *p, const char *session_name, uint64_t phy_addr, size_t size, uint64_t timestamp);
int RtspServer_SendAudioData_Byphyaddr(KdRtspServer *p, const char *session_name, uint64_t phy_addr, size_t size, uint64_t timestamp);
char* RtspServer_Test(KdRtspServer *p);


KdRtspPusher * RtspPusher_create();
void RtspPusher_destroy(KdRtspPusher *p);
void RtspPusher_DeInitAll(void);
int RtspPusher_Init(KdRtspPusher *p, int video_width, int video_height, const char *url, int fps, const char *transport);
void RtspPusher_DeInit(KdRtspPusher *p);
int RtspPusher_Open(KdRtspPusher *p);
void RtspPusher_Close(KdRtspPusher *p);
int RtspPusher_PushVideoData(KdRtspPusher *p, const uint8_t *data, size_t size, bool key_frame, uint64_t timestamp);
int RtspPusher_PushVideoHeader(KdRtspPusher *p, const uint8_t *data, size_t size);

KdRtspPlayer *RtspPlayer_create(void);
int RtspPlayer_count(void);
void RtspPlayer_destroy(KdRtspPlayer *player);
void RtspPlayer_DeInitAll(void);
int RtspPlayer_init(KdRtspPlayer *player, const char *url, int cache_count, int buffer_count,
                    int out_width, int out_height);
int RtspPlayer_start(KdRtspPlayer *player);
int RtspPlayer_stop(KdRtspPlayer *player);
void RtspPlayer_deinit(KdRtspPlayer *player);
int RtspPlayer_video_size(KdRtspPlayer *player, int *width, int *height);
int RtspPlayer_bind_info(KdRtspPlayer *player, int x, int y, int *width, int *height,
                         int *mod_id, int *dev_id, int *chn_id, int *pix_format);
int RtspPlayer_get_frame(KdRtspPlayer *player, int timeout_ms, void **image);
int RtspPlayer_check(KdRtspPlayer *player);

#ifdef __cplusplus
}
#endif

#endif
