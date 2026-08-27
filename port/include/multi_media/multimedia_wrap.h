#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>

typedef struct KdRtspServer KdRtspServer;
typedef struct SessionAttr SessionAttr;

typedef struct KdRtspPusher KdRtspPusher;

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

#ifdef __cplusplus
}
#endif
