/* Copyright (c) 2026, Canaan Bright Sight Co., Ltd
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are met:
 * 1. Redistributions of source code must retain the above copyright
 * notice, this list of conditions and the following disclaimer.
 * 2. Redistributions in binary form must reproduce the above copyright
 * notice, this list of conditions and the following disclaimer in the
 * documentation and/or other materials provided with the distribution.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND
 * CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES,
 * INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF
 * MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
 * DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
 * CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
 * SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
 * BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
 * SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
 * INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
 * WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
 * NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
 * OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 */
#include "generated/autoconf.h"

#include "kd_display.h"

#include "mpi_gsdma_api.h"
#include "mpi_sys_api.h"
#include "mpi_vb_api.h"

#include "py/mpprint.h"
#include "py/mpthread.h"
#include "py/obj.h"
#include "py/runtime.h"

#include "py_assert.h" // use openmv marco, PY_ASSERT_TYPE
#include "py_image.h"

#include "py_modules.h"

#include <errno.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define PY_PANEL_TYPE_VIRT     (300)
#define PY_PANEL_TYPE_DEBUGGER (301)
#define PY_PANEL_TYPE_ST7701   (302)
#define PY_PANEL_TYPE_HX8399   (303)
#define PY_PANEL_TYPE_ILI9806  (304)
#define PY_PANEL_TYPE_LT9611   (305)
#define PY_PANEL_TYPE_ILI9881  (306)
#define PY_PANEL_TYPE_NT35516  (307)
#define PY_PANEL_TYPE_NT35532  (308)
#define PY_PANEL_TYPE_GC9503   (309)
#define PY_PANEL_TYPE_ST7102   (310)
#define PY_PANEL_TYPE_AML020T  (311)
#define PY_PANEL_TYPE_JD9852   (312)

///////////////////////////////////////////////////////////////////////////////
// Py Panel Map ///////////////////////////////////////////////////////////////
///////////////////////////////////////////////////////////////////////////////
typedef struct _py_display_panel_map {
    int              py_type;
    int              width;
    int              height;
    k_connector_type type;
    int              fps;
    int              board_default; // 1 = entry used when user width/height are 0
} py_display_panel_map_t;

static const py_display_panel_map_t py_display_panel_map[] = {
    // Virtual and Debugger
    { PY_PANEL_TYPE_VIRT, 0, 0, VIRTUAL_DISPLAY_DEVICE, 0, 1 },
#if defined(CONFIG_MPP_ENABLE_DSI_DEBUGGER)
    { PY_PANEL_TYPE_DEBUGGER, 0, 0, DSI_DEBUGGER_DEVICE, 0, 1 },
#endif

    /* ST7701  */
    { PY_PANEL_TYPE_ST7701, 800, 480, ST7701_V1_MIPI_2LAN_480X800_30FPS, 0, 0 },
    { PY_PANEL_TYPE_ST7701, 480, 800, ST7701_V1_MIPI_2LAN_480X800_30FPS, 0, 0 },
    { PY_PANEL_TYPE_ST7701, 854, 480, ST7701_V1_MIPI_2LAN_480X854_30FPS, 0, 0 },
    { PY_PANEL_TYPE_ST7701, 480, 854, ST7701_V1_MIPI_2LAN_480X854_30FPS, 0, 0 },
    { PY_PANEL_TYPE_ST7701, 640, 480, ST7701_V1_MIPI_2LAN_480X640_30FPS, 0, 0 },
    { PY_PANEL_TYPE_ST7701, 480, 640, ST7701_V1_MIPI_2LAN_480X640_30FPS, 0, 0 },
    { PY_PANEL_TYPE_ST7701, 368, 544, ST7701_V1_MIPI_2LAN_368X544_60FPS, 0, 0 },
    { PY_PANEL_TYPE_ST7701, 544, 368, ST7701_V1_MIPI_2LAN_368X544_60FPS, 0, 0 },
#if defined(CONFIG_BOARD_K230D_CANMV_ATK_DNK230D) || defined(CONFIG_BOARD_K230_CANMV_YAHBOOM)
    { PY_PANEL_TYPE_ST7701, 640, 480, ST7701_V1_MIPI_2LAN_480X640_30FPS, 0, 1 },
#else
    { PY_PANEL_TYPE_ST7701, 800, 480, ST7701_V1_MIPI_2LAN_480X800_30FPS, 0, 1 },
#endif

    /* HX8399 */
    { PY_PANEL_TYPE_HX8399, 1920, 1080, HX8377_V2_MIPI_4LAN_1080X1920_30FPS, 0, 1 },
    { PY_PANEL_TYPE_HX8399, 1080, 1920, HX8377_V2_MIPI_4LAN_1080X1920_30FPS, 0, 0 },

    /* ILI9806 */
    { PY_PANEL_TYPE_ILI9806, 800, 480, ILI9806_MIPI_2LAN_480X800_30FPS, 0, 1 },
    { PY_PANEL_TYPE_ILI9806, 480, 800, ILI9806_MIPI_2LAN_480X800_30FPS, 0, 0 },

    /* LT9611 */
    { PY_PANEL_TYPE_LT9611, 1920, 1080, LT9611_MIPI_4LAN_1920X1080_60FPS, 60, 0 },
    { PY_PANEL_TYPE_LT9611, 1920, 1080, LT9611_MIPI_4LAN_1920X1080_30FPS, 0, 1 },
    { PY_PANEL_TYPE_LT9611, 1280, 720, LT9611_MIPI_4LAN_1280X720_60FPS, 60, 0 },
    { PY_PANEL_TYPE_LT9611, 1280, 720, LT9611_MIPI_4LAN_1280X720_50FPS, 50, 0 },
    { PY_PANEL_TYPE_LT9611, 1280, 720, LT9611_MIPI_4LAN_1280X720_30FPS, 30, 0 },
    { PY_PANEL_TYPE_LT9611, 640, 480, LT9611_MIPI_4LAN_640X480_60FPS, 0, 0 },

    /* ILI9881 */
    { PY_PANEL_TYPE_ILI9881, 1280, 800, ILI9881_MIPI_4LAN_800X1280_60FPS, 0, 1 },
    { PY_PANEL_TYPE_ILI9881, 800, 1280, ILI9881_MIPI_4LAN_800X1280_60FPS, 0, 0 },

    /* NT35516 */
    { PY_PANEL_TYPE_NT35516, 960, 536, NT35516_MIPI_2LAN_536X960_30FPS, 0, 1 },
    { PY_PANEL_TYPE_NT35516, 536, 960, NT35516_MIPI_2LAN_536X960_30FPS, 0, 0 },

    /* NT35532 */
    { PY_PANEL_TYPE_NT35532, 1920, 1080, NT35532_MIPI_2LAN_1080X1920_30FPS, 0, 1 },
    { PY_PANEL_TYPE_NT35532, 1080, 1920, NT35532_MIPI_2LAN_1080X1920_30FPS, 0, 0 },

    /* GC9503 */
    { PY_PANEL_TYPE_GC9503, 800, 480, GC9503_MIPI_2LAN_480X800_60FPS, 0, 1 },
    { PY_PANEL_TYPE_GC9503, 480, 800, GC9503_MIPI_2LAN_480X800_60FPS, 0, 0 },

    /* ST7102 */
    { PY_PANEL_TYPE_ST7102, 640, 480, ST7102_MIPI_2LAN_480X640_60FPS, 0, 1 },
    { PY_PANEL_TYPE_ST7102, 480, 640, ST7102_MIPI_2LAN_480X640_60FPS, 0, 0 },

    /* AML020T */
    { PY_PANEL_TYPE_AML020T, 480, 360, AML020T_MIPI_2LAN_480X360_30FPS, 0, 1 },
    { PY_PANEL_TYPE_AML020T, 480, 360, AML020T_MIPI_2LAN_480X360_30FPS, 0, 0 },

    /* JD9852 */
    { PY_PANEL_TYPE_JD9852, 320, 240, JD9852_MIPI_1LAN_240X320_60FPS, 0, 1 },
    { PY_PANEL_TYPE_JD9852, 240, 320, JD9852_MIPI_1LAN_240X320_60FPS, 0, 0 },
};

#define MAP_SIZE (sizeof(py_display_panel_map) / sizeof(py_display_panel_map_t))

static const char* py_display_panel_name(int type)
{
    switch (type) {
    case PY_PANEL_TYPE_VIRT:
        return "Virt";
    case PY_PANEL_TYPE_DEBUGGER:
        return "Debugger";
    case PY_PANEL_TYPE_ST7701:
        return "ST7701";
    case PY_PANEL_TYPE_HX8399:
        return "HX8399";
    case PY_PANEL_TYPE_ILI9806:
        return "ILI9806";
    case PY_PANEL_TYPE_LT9611:
        return "LT9611";
    case PY_PANEL_TYPE_ILI9881:
        return "ILI9881";
    case PY_PANEL_TYPE_NT35516:
        return "NT35516";
    case PY_PANEL_TYPE_NT35532:
        return "NT35532";
    case PY_PANEL_TYPE_GC9503:
        return "GC9503";
    case PY_PANEL_TYPE_ST7102:
        return "ST7102";
    case PY_PANEL_TYPE_AML020T:
        return "AML020T";
    default:
        return "Unknown";
    }

    return "ERROR";
}

static int py_display_map_panel(py_display_panel_map_t* result, int type_in, int width_in, int height_in, int fps_in)
{
    int found = 0;

    const py_display_panel_map_t* curr_map = NULL;

    memset(result, 0, sizeof(*result));

    if (PY_PANEL_TYPE_VIRT > type_in) {
        result->type = type_in;

        return 0;
    }

    for (size_t i = 0; i < MAP_SIZE; i++) {
        curr_map = &py_display_panel_map[i];

        if (curr_map->py_type == type_in) {
            if (width_in != 0 && height_in != 0) {
                if (curr_map->width != width_in || curr_map->height != height_in) {
                    continue;
                }
            } else {
                if (curr_map->board_default == 0) {
                    continue;
                }
            }

            if ((0x00 != curr_map->fps) && (0x00 != fps_in) && (curr_map->fps != fps_in)) {
                continue;
            }

            found = 1;
            break;
        }
    }

    if (0x00 == found) {
        return -1;
    }

    memcpy(result, curr_map, sizeof(*curr_map));

    if (PY_PANEL_TYPE_VIRT == result->py_type) {
        result->width  = width_in ? width_in : 640;
        result->height = height_in ? height_in : 480;
        result->fps    = fps_in ? fps_in : 60;
    }

    return 0;
}

static int py_display_get_connector_resolution(k_connector_type type, int* widht, int* height)
{

    k_s32            ret;
    k_connector_info connector_info;

    memset(&connector_info, 0, sizeof(connector_info));
    if (K_SUCCESS != (ret = kd_mpi_get_connector_info(type, &connector_info))) {
        printf("[py_display]: failed to get connector info type=%d, ret=%d\n", type, ret);
        return -1;
    }

    if (widht) {
        *widht = connector_info.resolution.hdisplay;
    }

    if (height) {
        *height = connector_info.resolution.vdisplay;
    }

    return 0;
}

static int py_display_is_panel_rotated(k_connector_type type)
{
    k_u32 vo_width, vo_height;
    int   panel_width, panel_height;

    if (0x00 != py_display_get_connector_resolution(type, &panel_width, &panel_height)) {
        return -1;
    }

    if (0x00 != kd_display_get_resolution(&vo_width, &vo_height)) {
        return -1;
    }

    if ((panel_width == vo_width) && (panel_height == vo_height)) {
        return 0;
    }

    return 1;
}

static int py_display_vo_layer_pixl_format_bpp(k_pixel_format fmt)
{
    int bpp;

    switch (fmt) {
    case PIXEL_FORMAT_RGB_565: {
        bpp = 2;
    } break;
    case PIXEL_FORMAT_BGR_565: {
        bpp = 2;
    } break;
    case PIXEL_FORMAT_RGB_565_LE: {
        bpp = 2;
    } break;
    case PIXEL_FORMAT_BGR_565_LE: {
        bpp = 2;
    } break;
    case PIXEL_FORMAT_RGB_888: {
        bpp = 3;
    } break;
    case PIXEL_FORMAT_BGR_888: {
        bpp = 3;
    } break;
    case PIXEL_FORMAT_ABGR_8888: {
        bpp = 4;
    } break;
    case PIXEL_FORMAT_ARGB_8888: {
        bpp = 4;
    } break;
    case PIXEL_FORMAT_BGRA_8888: {
        bpp = 4;
    } break;
    case PIXEL_FORMAT_ABGR_4444: {
        bpp = 2;
    } break;
    case PIXEL_FORMAT_ARGB_4444: {
        bpp = 2;
    } break;
    case PIXEL_FORMAT_ARGB_1555: {
        bpp = 2;
    } break;
    case PIXEL_FORMAT_ABGR_1555: {
        bpp = 2;
    } break;
    case PIXEL_FORMAT_RGB_MONOCHROME_8BPP: {
        bpp = 1;
    } break;
    default: {
        bpp = 0; // invalid format
    } break;
    }

    return bpp;
}

///////////////////////////////////////////////////////////////////////////////
// Display Module Instance ////////////////////////////////////////////////////
///////////////////////////////////////////////////////////////////////////////
typedef struct _py_display_buffer {
    int                valid;
    k_s32              buffer_pool_id;
    void*              buffer_addr;
    size_t             buffer_size;
    k_vb_blk_handle    block_handle;
    k_video_frame_info vf_info;
} py_display_buffer_t;

static int py_display_alloc_single_buffer(py_display_buffer_t* buffer, k_s32 pool_id, k_u32 buffer_size);
static int py_display_free_single_buffer(py_display_buffer_t* buffer);

typedef struct _py_display_inst {
    int inited;

    int enable_wbc;
    int wbc_quality;
    int wbc_dumped;

    k_video_frame_info wbc_dumped_frame;

    int   rotated;
    int   osd_layer_num;
    k_s32 osd_layer_vb_pool_id;

    k_vo_layer_attr layer_attr[K_MAX_VO_LAYER_NR];
    k_mpp_chn       layer_bind[K_MAX_VO_LAYER_NR];
    int             layer_configed[K_MAX_VO_LAYER_NR];

    py_display_buffer_t share_buffer;
    py_display_buffer_t layer_buffer[K_MAX_VO_LAYER_NR];
} py_display_inst_t;

static py_display_inst_t py_display_inst = {
    .inited = 0,

    .enable_wbc = 0,
    .wbc_dumped = 0,

    .osd_layer_num = 0,
    .osd_layer_vb_pool_id = VB_INVALID_POOLID,

    .share_buffer = { .valid = 0 },
    .layer_buffer = {
        {.valid = 0},
        {.valid = 0},
        {.valid = 0},
        {.valid = 0},
        {.valid = 0},
        {.valid = 0},
        {.valid = 0},
        {.valid = 0},
    },
};

static pthread_mutex_t wbc_mutex = PTHREAD_MUTEX_INITIALIZER;

static int py_display_unbind_layer_inst(k_vo_layer_id layer)
{
    if ((K_MAX_VO_LAYER_NR <= layer) || (K_VO_LAYER_VIDEO0 >= layer)) {
        return -1;
    }

    k_mpp_chn bind_src, bind_dst = { K_ID_VO, 0, layer };

    if (0x00 != kd_mpi_sys_get_bind_by_dest(&bind_dst, &bind_src)) {
        return 0; // dest not binded.
    }

    return kd_mpi_sys_unbind(&bind_src, &bind_dst);
}

static int py_display_bind_layer_inst(k_mpp_chn* src, k_vo_layer_id layer)
{
    k_mpp_chn bind_dst = { K_ID_VO, 0, layer };

    if ((K_MAX_VO_LAYER_NR <= layer) || (K_VO_LAYER_VIDEO0 >= layer)) {
        return -1;
    }

    // unbind layer
    py_display_unbind_layer_inst(layer);

    if (src) {
        if (K_SUCCESS != kd_mpi_sys_bind(src, &bind_dst)) {
            printf("bind vo layer failed\n");
            return -1;
        }

        k_mpp_chn* curr_bind_src = &py_display_inst.layer_bind[layer];

        memcpy(curr_bind_src, src, sizeof(k_mpp_chn));
    }

    return 0;
}

static int py_dispay_config_layer_inst(k_vo_layer_id layer, k_vo_layer_attr* attr)
{
    int              fmt_bpp = 0;
    k_vo_layer_attr* _attr   = attr;

    if ((K_MAX_VO_LAYER_NR <= layer) || (K_VO_LAYER_VIDEO0 >= layer)) {
        printf("[py_display] ERROR: Invalid layer ID: %d\n", layer);
        return -1;
    }

    // Phase 1: Buffering (Before Init)
    if (0x00 == py_display_inst.inited) {
        if (NULL == _attr) {
            printf("[py_display] ERROR: Layer %d config failed - attr is NULL before init\n", layer);
            return -1;
        }

        memcpy(&py_display_inst.layer_attr[layer], _attr, sizeof(k_vo_layer_attr));
        py_display_inst.layer_configed[layer] = 1;

        return 0;
    }

    // Phase 2: Execution (During or After Init)
    if (NULL == _attr) {
        if (!py_display_inst.layer_configed[layer]) {
            printf("[py_display] ERROR: Layer %d has no buffered config to apply\n", layer);
            return -1;
        }
        _attr = &py_display_inst.layer_attr[layer];
    }

    // Validate Format
    fmt_bpp = py_display_vo_layer_pixl_format_bpp(_attr->pixel_format);
    if (0x00 == fmt_bpp) {
        if (K_VO_LAYER_OSD0 <= layer) {
            printf("[py_display] ERROR: Invalid pixel format (0x%x) for OSD layer %d\n", _attr->pixel_format, layer);
            return -1;
        }
        if (PIXEL_FORMAT_YUV_SEMIPLANAR_420 != _attr->pixel_format) {
            printf("[py_display] ERROR: Video layer %d only supports YUV420SP (0x%x)\n", layer, _attr->pixel_format);
            return -1;
        }
    }

    // Hardware Operations
    k_s32 ret;

    // Disable before re-configuring
    ret = kd_display_layer_disable(layer);
    if (ret != 0) {
        printf("[py_display] WARNING: disable layer %d returned %d\n", layer, ret);
    }

    ret = kd_display_layer_set_attr(layer, _attr);
    if (0x00 != ret) {
        printf("[py_display] ERROR: set layer attr %d failed, ret=%d\n", layer, ret);
        return -1;
    }

    ret = kd_display_layer_enable(layer);
    if (0x00 != ret) {
        printf("[py_display] ERROR: enable layer %d failed, ret=%d\n", layer, ret);
        return -1;
    }

    if (&py_display_inst.layer_attr[layer] != _attr) {
        memcpy(&py_display_inst.layer_attr[layer], _attr, sizeof(k_vo_layer_attr));
    }

    py_display_inst.layer_configed[layer] = 1;

    return 0;
}

static int py_display_disable_layer_inst(k_vo_layer_id layer)
{
    if ((K_MAX_VO_LAYER_NR <= layer) || (K_VO_LAYER_VIDEO0 >= layer)) {
        return -1;
    }

    if (py_display_inst.layer_configed[layer]) {
        py_display_inst.layer_configed[layer] = 0;

        if (0x00 != kd_display_layer_disable(layer)) {
            printf("disable layer %d failed\n", layer);
            return -1;
        }

        py_display_free_single_buffer(&py_display_inst.layer_buffer[layer]);
    }

    return 0;
}

static int py_display_set_wbc_inst(int enable, int quality)
{
    pthread_mutex_lock(&wbc_mutex);

    if (enable == py_display_inst.enable_wbc) {
        pthread_mutex_unlock(&wbc_mutex);

        return 0;
    }
    py_display_inst.enable_wbc = enable;

    if (0 > quality) {
        quality = 50;
    }
    if (100 < quality) {
        quality = 90;
    }
    py_display_inst.wbc_quality = quality;

    if (enable) {
        if (0x00 != kd_display_wbc_configure()) {
            pthread_mutex_unlock(&wbc_mutex);

            printf("failed to config vo wbc\n");

            return -1;
        }

        if (0x00 != kd_display_wbc_enable()) {
            pthread_mutex_unlock(&wbc_mutex);

            printf("failed to enable vo wbc\n");

            return -1;
        }

        py_display_inst.wbc_dumped = 0;

        pthread_mutex_unlock(&wbc_mutex);

        return 0;
    } else {
        pthread_mutex_unlock(&wbc_mutex);

        usleep(500); // wait dump thread done.

        pthread_mutex_lock(&wbc_mutex);
    }

    if (py_display_inst.wbc_dumped) {
        kd_display_wbc_release_frame(&py_display_inst.wbc_dumped_frame);

        py_display_inst.wbc_dumped = 0;
    }

    pthread_mutex_unlock(&wbc_mutex);

    return kd_display_wbc_disable();
}

static int py_display_wbc_dump_inst(k_video_frame_info* info, int timeout_ms, int force)
{
    k_bool is_runing = K_FALSE;

    pthread_mutex_lock(&wbc_mutex);

    if (!py_display_inst.enable_wbc) {
        pthread_mutex_unlock(&wbc_mutex);

        return -1;
    }

    if (0x00 != kd_display_wbc_stats(&is_runing)) {
        pthread_mutex_unlock(&wbc_mutex);
        return -1;
    }

    if (!is_runing) {
        pthread_mutex_unlock(&wbc_mutex);
        return -1;
    }

    if (0x00 != kd_display_wbc_dump_frame(info, timeout_ms)) {
        pthread_mutex_unlock(&wbc_mutex);
        return -1;
    }

    if (py_display_inst.wbc_dumped) {
        kd_display_wbc_release_frame(&py_display_inst.wbc_dumped_frame);

        py_display_inst.wbc_dumped = 0;
    }

    py_display_inst.wbc_dumped = 1;
    memcpy(&py_display_inst.wbc_dumped_frame, info, sizeof(k_video_frame_info));

    pthread_mutex_unlock(&wbc_mutex);

    return 0;
}

static int py_display_wbc_dump_release_inst(void)
{
    pthread_mutex_lock(&wbc_mutex);

    if (py_display_inst.wbc_dumped) {
        kd_display_wbc_release_frame(&py_display_inst.wbc_dumped_frame);

        py_display_inst.wbc_dumped = 0;
    }
    pthread_mutex_unlock(&wbc_mutex);

    return 0;
}

static void py_display_deinit_inst(void)
{
    if (!py_display_inst.inited) {
        // Already deinitialized, nothing to do
        return;
    }

    // Disable WBC first
    py_display_set_wbc_inst(0, 0);

    // Store the inited flag locally before clearing it
    int was_inited = py_display_inst.inited;

    // Immediately mark as not initialized to prevent re-entry
    // but keep local copy for cleanup
    py_display_inst.inited = 0;

    // Only proceed with hardware cleanup if we were actually initialized
    if (was_inited) {
        // Unbind all layers first
        for (k_vo_layer_id layer = 0; layer < K_MAX_VO_LAYER_NR; layer++) {
            py_display_unbind_layer_inst(layer);
        }

        // Disable all configured layers
        for (k_vo_layer_id layer = 0; layer < K_MAX_VO_LAYER_NR; layer++) {
            if (py_display_inst.layer_configed[layer]) {
                // Attempt to disable, but continue even if fails
                kd_display_layer_disable(layer);
                py_display_inst.layer_configed[layer] = 0;
            }
        }

        // Deinitialize display hardware
        kd_display_deinit();

        // Free all layer buffers
        for (k_vo_layer_id layer = 0; layer < K_MAX_VO_LAYER_NR; layer++) {
            py_display_free_single_buffer(&py_display_inst.layer_buffer[layer]);
        }

        // Free shared buffer
        py_display_free_single_buffer(&py_display_inst.share_buffer);
    }

    // Clean up OSD VB pool if created
    if (VB_INVALID_POOLID != py_display_inst.osd_layer_vb_pool_id) {
        kd_mpi_vb_destory_pool(py_display_inst.osd_layer_vb_pool_id);
        py_display_inst.osd_layer_vb_pool_id = VB_INVALID_POOLID;
    }

    py_display_inst.osd_layer_num = 0;

    // Clear all configuration state
    memset(&py_display_inst.layer_bind, 0, sizeof(py_display_inst.layer_bind));
    memset(&py_display_inst.layer_attr, 0, sizeof(py_display_inst.layer_attr));
    memset(&py_display_inst.layer_configed, 0, sizeof(py_display_inst.layer_configed));
}

static int py_display_init_inst(int rotated, int osd_num, int enable_wbc, int wbc_quality)
{
    k_u64 buffer_size;
    k_u32 panel_width, panel_height;

    if (py_display_inst.inited) {
        printf("invalid status for display\n");

        py_display_deinit_inst();
    }

    if (0x00 != kd_display_get_resolution(&panel_width, &panel_height)) {
        printf("get display resolution failed\n");

        goto _failed;
    }
    buffer_size = VB_ALIGN_UP((panel_width * panel_height * 4), 4096);

    if (osd_num) {
        k_s32 osd_layer_vb_pool_id = kd_mpi_vb_create_pool_ex(buffer_size, osd_num, VB_REMAP_MODE_CACHED);

        if (VB_INVALID_POOLID == osd_layer_vb_pool_id) {
            printf("create vb pool for osd layer failed\n");

            goto _failed;
        }

        py_display_inst.osd_layer_vb_pool_id = osd_layer_vb_pool_id;
    }
    py_display_inst.rotated = rotated;
    py_display_inst.inited  = 1;

    py_display_set_wbc_inst(enable_wbc, wbc_quality);

    for (k_vo_layer_id layer = 0; layer < K_MAX_VO_LAYER_NR; layer++) {
        if (py_display_inst.layer_configed[layer]) {
            py_dispay_config_layer_inst(layer, NULL);
        }
    }

    return 0;

_failed:
    py_display_deinit_inst();

    return -1;
}
///////////////////////////////////////////////////////////////////////////////
// Display Layer Buffer ///////////////////////////////////////////////////////
///////////////////////////////////////////////////////////////////////////////
static int py_display_alloc_single_buffer(py_display_buffer_t* buffer, k_s32 pool_id, k_u32 buffer_size)
{
    if (!buffer || (VB_INVALID_POOLID == pool_id)) {
        return -1;
    }

    buffer->valid = 0;

    buffer->block_handle = kd_mpi_vb_get_block(pool_id, buffer_size, NULL);
    if (VB_INVALID_HANDLE == buffer->block_handle) {
        printf("alloc vo buffer failed, pool %d, size %d\n", pool_id, buffer_size);
        return -1;
    }

    buffer->buffer_pool_id               = pool_id;
    buffer->buffer_size                  = buffer_size;
    buffer->vf_info.v_frame.phys_addr[0] = kd_mpi_vb_handle_to_phyaddr(buffer->block_handle);
    buffer->buffer_addr                  = kd_mpi_sys_mmap_cached(buffer->vf_info.v_frame.phys_addr[0], buffer_size);

    if (!buffer->buffer_addr) {
        printf("Mmap failed\n");
        kd_mpi_vb_release_block(buffer->block_handle);
        buffer->block_handle = VB_INVALID_HANDLE;
        return -1;
    }

    buffer->valid = 1;

    return 0;
}

static int py_display_free_single_buffer(py_display_buffer_t* buffer)
{
    if (!buffer || (0x00 == buffer->valid)) {
        return -1;
    }

    if (buffer->buffer_addr) {
        kd_mpi_sys_munmap(buffer->buffer_addr, buffer->buffer_size);
        buffer->buffer_addr = NULL;
    }

    if (buffer->block_handle != VB_INVALID_HANDLE) {
        kd_mpi_vb_release_block(buffer->block_handle);
        buffer->block_handle = VB_INVALID_HANDLE;
    }

    buffer->valid = 0;

    return 0;
}

static int py_display_show_image_to_buffer(k_vo_layer_id layer, image_t* image, py_display_buffer_t* buffer,
                                           k_pixel_format pix_fmt, int bpp)
{
    k_u64  phy_addr = 0;
    size_t img_size;

    if (!buffer || !image || (0x00 == buffer->valid)) {
        return -1;
    }

    img_size = image_size(image);

    buffer->vf_info.mod_id               = K_ID_VO;
    buffer->vf_info.pool_id              = buffer->buffer_pool_id;
    buffer->vf_info.v_frame.width        = image->w;
    buffer->vf_info.v_frame.height       = image->h;
    buffer->vf_info.v_frame.stride[0]    = image->w * bpp;
    buffer->vf_info.v_frame.pixel_format = pix_fmt;

    phy_addr = buffer->vf_info.v_frame.phys_addr[0];

    if (img_size > buffer->buffer_size) {
        img_size = buffer->buffer_size;
    }

    memcpy(buffer->buffer_addr, image->data, img_size);
    kd_mpi_sys_mmz_flush_cache(phy_addr, buffer->buffer_addr, buffer->buffer_size);

    return kd_display_layer_push_frame(layer, &buffer->vf_info);
}

///////////////////////////////////////////////////////////////////////////////
// Public Display Functions ///////////////////////////////////////////////////
///////////////////////////////////////////////////////////////////////////////
int py_display_status(void) { return py_display_inst.inited; }

int py_display_wbc_status(void)
{
    k_bool is_runing = K_FALSE;

    if (!py_display_inst.inited || !py_display_inst.enable_wbc) {
        return 0;
    }

    if (0x00 != kd_display_wbc_stats(&is_runing)) {
        return 0;
    }

    return is_runing ? 1 : 0;
}

int py_display_wbc_quality(void)
{
    int quality;

    quality = py_display_inst.wbc_quality;

    return quality;
}

int py_display_wbc_dump(k_video_frame_info* vf_info, int timeout_ms, int force)
{
    return py_display_wbc_dump_inst(vf_info, timeout_ms, force);
}

int py_display_wbc_dump_relase(void) { return py_display_wbc_dump_release_inst(); }

void py_display_deinit(void) { py_display_deinit_inst(); }

///////////////////////////////////////////////////////////////////////////////
// Display Python Wrap ////////////////////////////////////////////////////////
///////////////////////////////////////////////////////////////////////////////
static void py_parse_array(mp_obj_t src_obj, size_t expected_len, mp_int_t* out)
{
    // If the object is None, you might want to handle it or throw error
    if (src_obj == mp_const_none) {
        mp_raise_ValueError(MP_ERROR_TEXT("Argument cannot be None"));
    }

    size_t    len;
    mp_obj_t* items;

    // This handles both list and tuple automatically
    mp_obj_get_array(src_obj, &len, &items);

    if (len != expected_len) {
        mp_raise_msg_varg(&mp_type_ValueError, MP_ERROR_TEXT("Expected %d values, got %d"), (int)expected_len, (int)len);
    }

    for (size_t i = 0; i < len; i++) {
        out[i] = mp_obj_get_int(items[i]);
    }
}

/**
@staticmethod
Display.init(type, width = 0, height = 0, fps = 0, flag = 0, osd_num = 1, to_ide = False, quality = 90);
*/
static mp_obj_t py_display_init_wrap(mp_uint_t n_args, const mp_obj_t* pos_args, mp_map_t* kw_args)
{
    enum { ARG_type, ARG_width, ARG_height, ARG_fps, ARG_flag, ARG_osd_num, ARG_to_ide, ARG_quality };
    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_type, MP_ARG_INT | MP_ARG_REQUIRED, { .u_int = -1 } },
        { MP_QSTR_width, MP_ARG_INT, { .u_int = 0 } },
        { MP_QSTR_height, MP_ARG_INT, { .u_int = 0 } },
        { MP_QSTR_fps, MP_ARG_INT, { .u_int = 60 } },
        { MP_QSTR_flag, MP_ARG_INT, { .u_int = 0 } },

        { MP_QSTR_osd_num, MP_ARG_INT, { .u_int = 1 } },

        { MP_QSTR_to_ide, MP_ARG_BOOL, { .u_bool = false } },
        { MP_QSTR_quality, MP_ARG_INT, { .u_int = 90 } },
    };
    mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all(n_args, pos_args, kw_args, MP_ARRAY_SIZE(allowed_args), allowed_args, args);

    py_display_panel_map_t panel_map;

    int arg_type = args[ARG_type].u_int;
    if (0 > arg_type) {
        mp_raise_ValueError(MP_ERROR_TEXT("invalid type\n"));
    }

    int arg_width  = args[ARG_width].u_int;
    int arg_height = args[ARG_height].u_int;
    int arg_fps    = args[ARG_fps].u_int;

    if (0x00 != py_display_map_panel(&panel_map, arg_type, arg_width, arg_height, arg_fps)) {
        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("%s not support %dx%d@%d"), py_display_panel_name(arg_type),
                          arg_width, arg_height, arg_fps);
    }

    py_display_deinit_inst();

    int arg_flag = args[ARG_flag].u_int;

    if (0x00 != kd_display_init_ex(panel_map.type, panel_map.width, panel_map.height, arg_flag, panel_map.fps)) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("init panel failed"));
    }

    int arg_osd_num = args[ARG_osd_num].u_int;

    int rotated = py_display_is_panel_rotated(panel_map.type);

    if (0x01 == rotated) {
        printf("panel is rotated, we only need one osd buffer\n");

        if (arg_osd_num) {
            arg_osd_num = 1;
        }
    }

    bool arg_enable_wbc  = args[ARG_to_ide].u_bool;
    int  arg_wbc_quality = args[ARG_quality].u_int;

    if (0x00 != py_display_init_inst(rotated, arg_osd_num, arg_enable_wbc, arg_wbc_quality)) {
        kd_display_deinit();

        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("init display failed"));
    }

    extern void ide_dbg_vo_wbc_start(int enable);
    ide_dbg_vo_wbc_start(arg_enable_wbc);

    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_KW(py_display_init_obj, 1, py_display_init_wrap);
static MP_DEFINE_CONST_STATICMETHOD_OBJ(py_display_init_method, MP_ROM_PTR(&py_display_init_obj));

/*
@staticmethod
Display.deinit();
*/
static mp_obj_t py_display_deinit_wrap(void)
{
    py_display_deinit_inst();

    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(py_display_deinit_obj, py_display_deinit_wrap);
static MP_DEFINE_CONST_STATICMETHOD_OBJ(py_display_deinit_method, MP_ROM_PTR(&py_display_deinit_obj));

/**
@staticmethod
Display.config_layer(layer, rect, pix_format, alpha, flag)
*/
static mp_obj_t py_display_config_layer_wrap(mp_uint_t n_args, const mp_obj_t* pos_args, mp_map_t* kw_args)
{
    enum { ARG_rect, ARG_pix_format, ARG_layer, ARG_alpha, ARG_flag };
    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_rect, MP_ARG_OBJ | MP_ARG_KW_ONLY, { .u_obj = mp_const_none } }, // (x, y, w, h)
        { MP_QSTR_pix_format, MP_ARG_INT | MP_ARG_KW_ONLY, { .u_int = -1 } }, // @k_pixel_format
        { MP_QSTR_layer, MP_ARG_INT | MP_ARG_KW_ONLY, { .u_int = -1 } }, // VIDEO0 ... OSD3

        { MP_QSTR_alpha, MP_ARG_INT | MP_ARG_KW_ONLY, { .u_int = 255 } }, // 0 ... 255
        { MP_QSTR_flag, MP_ARG_INT | MP_ARG_KW_ONLY, { .u_int = 0 } }, // @k_gdma_rotation_e
    };
    mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all(n_args, pos_args, kw_args, MP_ARRAY_SIZE(allowed_args), allowed_args, args);

    k_vo_layer_attr attr;
    memset(&attr, 0x00, sizeof(attr));

    // parse arg rect
    mp_int_t rect_arr[4];
    mp_obj_t arg_rect = args[ARG_rect].u_obj;

    py_parse_array(arg_rect, 4, &rect_arr[0]);

    attr.position.x      = rect_arr[0];
    attr.position.y      = rect_arr[1];
    attr.img_size.width  = rect_arr[2];
    attr.img_size.height = rect_arr[3];

    // parse arg pix_format
    int arg_pixel_format = args[ARG_pix_format].u_int;
    attr.pixel_format    = arg_pixel_format; // will check is valid when config layer

    // parse arg layer
    k_vo_layer_id arg_layer = args[ARG_layer].u_int;

    /* video0 currently can not use it. */
    if ((K_VO_LAYER_VIDEO0 >= arg_layer) || (K_MAX_VO_LAYER_NR <= arg_layer)) {
        mp_raise_ValueError(MP_ERROR_TEXT("invalid bind layer"));
    }
    attr.layer_id = arg_layer;

    // parse arg alpha
    int arg_alpha = args[ARG_alpha].u_int;

    if ((0 > arg_alpha)) {
        arg_alpha = 0;
    }

    if (255 < arg_alpha) {
        arg_alpha = 255;
    }

    attr.global_alpha = arg_alpha;

    // parse arg flag
    int arg_flag = args[ARG_flag].u_int;
    attr.func    = arg_flag;

    attr.rot_buf_nr  = 2;
    attr.rot_buf_bpp = 4;

    if (0x00 != py_dispay_config_layer_inst(arg_layer, &attr)) {
        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("vo bind config layer failed."));
    }

    return mp_obj_new_int(arg_layer);
}
static MP_DEFINE_CONST_FUN_OBJ_KW(py_display_config_layer_obj, 0, py_display_config_layer_wrap);
static MP_DEFINE_CONST_STATICMETHOD_OBJ(py_display_config_layer_method, MP_ROM_PTR(&py_display_config_layer_obj));

/**
@staticmethod
Display.disable_layer(layer)

@staticmethod
Display._disable_layer(layer)
*/
static mp_obj_t py_display_disable_layer_wrap(mp_obj_t arg)
{
    k_vo_layer_id arg_layer = mp_obj_get_int(arg);

    if ((K_VO_LAYER_VIDEO0 >= arg_layer) || (K_MAX_VO_LAYER_NR <= arg_layer)) {
        mp_raise_ValueError(MP_ERROR_TEXT("invalid layer"));
    }

    if (0x00 != py_display_disable_layer_inst(arg_layer)) {
        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("disable layer failed"));
    }

    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(py_display_disable_layer_obj, py_display_disable_layer_wrap);
static MP_DEFINE_CONST_STATICMETHOD_OBJ(py_display_disable_layer_method, MP_ROM_PTR(&py_display_disable_layer_obj));

/*
@staticmethod
Display.bind_layer(src, layer, pix_format, rect = None, alpha = 255, flag = 0)
*/
static mp_obj_t py_display_bind_layer_wrap(mp_uint_t n_args, const mp_obj_t* pos_args, mp_map_t* kw_args)
{
    mp_obj_t arg_src = mp_const_none;

    // We create a local map structure to handle potential modifications
    mp_map_t local_kw_args;
    if (kw_args != NULL) {
        // Shallow copy the map structure.
        // Note: the table inside may still be fixed, so we use a safe approach.
        local_kw_args = *kw_args;
    }

    // 1. "Eat" the src argument
    if (n_args > 0) {
        arg_src = pos_args[0];
        pos_args++;
        n_args--;
    } else if (kw_args != NULL) {
        mp_map_elem_t* elem = mp_map_lookup(kw_args, MP_OBJ_NEW_QSTR(MP_QSTR_src), MP_MAP_LOOKUP);
        if (elem != NULL) {
            arg_src = elem->value;

            // Instead of REMOVE_IF_FOUND (which crashes), we create a new map
            // without 'src' to pass to the next function.
            mp_map_init(&local_kw_args, kw_args->used - 1);
            for (size_t i = 0; i < kw_args->alloc; i++) {
                if (MP_MAP_SLOT_IS_FILLED(kw_args, i) && kw_args->table[i].key != MP_OBJ_NEW_QSTR(MP_QSTR_src)) {
                    mp_map_lookup(&local_kw_args, kw_args->table[i].key, MP_MAP_LOOKUP_ADD_IF_NOT_FOUND)->value
                        = kw_args->table[i].value;
                }
            }
            kw_args = &local_kw_args;
        }
    }

    if (arg_src == mp_const_none) {
        mp_raise_TypeError(MP_ERROR_TEXT("bind_layer requires src argument"));
    }

    // 2. Parse src array
    k_mpp_chn bind_src;
    mp_int_t  bind_arr[3];
    py_parse_array(arg_src, 3, &bind_arr[0]);
    bind_src.mod_id = bind_arr[0];
    bind_src.dev_id = bind_arr[1];
    bind_src.chn_id = bind_arr[2];

    // 3. Call config_layer with the cleaned map
    mp_obj_t layer_obj = py_display_config_layer_wrap(n_args, pos_args, kw_args);
    int      arg_layer = mp_obj_get_int(layer_obj);

    // 4. Bind
    if (0x00 != py_display_bind_layer_inst(&bind_src, arg_layer)) {
        py_display_disable_layer_inst(arg_layer);
        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("vo bind layer failed."));
    }

    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_KW(py_display_bind_layer_obj, 0, py_display_bind_layer_wrap);
static MP_DEFINE_CONST_STATICMETHOD_OBJ(py_display_bind_layer_method, MP_ROM_PTR(&py_display_bind_layer_obj));

/**
@staticmethod
Display.unbind_layer(layer)
*/
static mp_obj_t py_display_unbind_layer(mp_obj_t arg)
{
    int arg_layer = mp_obj_get_int(arg);

    if ((K_VO_LAYER_VIDEO0 >= arg_layer) || (K_MAX_VO_LAYER_NR <= arg_layer)) {
        mp_raise_ValueError(MP_ERROR_TEXT("invalid bind layer"));
    }

    if (0x00 != py_display_unbind_layer_inst(arg_layer)) {
        mp_printf(&mp_plat_print, "unbind layer failed\n");

        return mp_const_false;
    }

    return mp_const_true;
}
static MP_DEFINE_CONST_FUN_OBJ_1(py_display_unbind_layer_obj, py_display_unbind_layer);
static MP_DEFINE_CONST_STATICMETHOD_OBJ(py_display_unbind_layer_method, MP_ROM_PTR(&py_display_unbind_layer_obj));

static inline void py_display_get_resolution(k_u32* width, k_u32* height)
{
    if (0x00 != kd_display_get_resolution(width, height)) {
        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("get vo resolution failed"));
    }
}

static inline void py_display_get_layer_resolution(k_vo_layer_id layer, k_u32* width, k_u32* height)
{
    k_vo_layer_attr attr;

    if ((K_VO_LAYER_VIDEO0 >= layer) || (K_MAX_VO_LAYER_NR <= layer)) {
        mp_raise_ValueError(MP_ERROR_TEXT("invalid layer"));
    }

    if (K_SUCCESS != kd_display_layer_get_attr(layer, &attr)) {
        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("get layer attr failed"));
    }

    if (width) {
        *width = attr.img_size.width;
    }

    if (height) {
        *height = attr.img_size.height;
    }
}

/**
@staticmethod
Display.width(layer = None)
*/
static mp_obj_t py_display_width_wrap(size_t n, const mp_obj_t* args)
{
    k_u32 width = 0, height = 0;

    if (0x00 == n) {
        py_display_get_resolution(&width, &height);
    } else {
        int arg_layer = mp_obj_get_int(args[0]);

        py_display_get_layer_resolution(arg_layer, &width, &height);
    }

    return mp_obj_new_int_from_uint(width);
}
static MP_DEFINE_CONST_FUN_OBJ_VAR(py_display_width_obj, 0, py_display_width_wrap);
static MP_DEFINE_CONST_STATICMETHOD_OBJ(py_display_width_method, MP_ROM_PTR(&py_display_width_obj));

/**
@staticmethod
Display.height(layer = None)
*/
static mp_obj_t py_display_height_wrap(size_t n, const mp_obj_t* args)
{
    k_u32 width = 0, height = 0;

    if (0x00 == n) {
        py_display_get_resolution(&width, &height);
    } else {
        int arg_layer = mp_obj_get_int(args[0]);

        py_display_get_layer_resolution(arg_layer, &width, &height);
    }

    return mp_obj_new_int_from_uint(height);
}
static MP_DEFINE_CONST_FUN_OBJ_VAR(py_display_height_obj, 0, py_display_height_wrap);
static MP_DEFINE_CONST_STATICMETHOD_OBJ(py_display_height_method, MP_ROM_PTR(&py_display_height_obj));

/**
@staticmethod
Display.fps()
*/
static mp_obj_t py_display_fps_wrap(void)
{
    int fps = 0;

    k_connector_info info;

    if (0x00 != kd_display_get_connector_info(&info)) {
        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("get fps but not init display"));
    }

    if (VIRTUAL_DISPLAY_DEVICE == info.type) {
        fps = info.resolution.pclk;
    } else {
        k_u32 pclk = info.resolution.pclk;
        k_u32 ht   = info.resolution.htotal;
        k_u32 vt   = info.resolution.vtotal;

        fps = (k_u64)(pclk * 1000) / ht / vt;
    }

    fps = (fps > 200) ? 0 : fps;

    return mp_obj_new_int_from_uint(fps);
}
static MP_DEFINE_CONST_FUN_OBJ_0(py_display_fps_obj, py_display_fps_wrap);
static MP_DEFINE_CONST_STATICMETHOD_OBJ(py_display_fps_method, MP_ROM_PTR(&py_display_fps_obj));

static k_pixel_format map_omv_image_to_pixel_format(pixformat_t fmt)
{
    k_pixel_format pix_fmt;

    switch (fmt) {
    case PIXFORMAT_GRAYSCALE:
        pix_fmt = PIXEL_FORMAT_RGB_MONOCHROME_8BPP;
        break;
    case PIXFORMAT_RGB565:
        pix_fmt = PIXEL_FORMAT_RGB_565_LE;
        break;
    case PIXFORMAT_ARGB8888:
        pix_fmt = PIXEL_FORMAT_ARGB_8888;
        break;
    case PIXFORMAT_ABGR8888:
        pix_fmt = PIXEL_FORMAT_ABGR_8888;
        break;
    case PIXFORMAT_RGBA8888:
        pix_fmt = PIXEL_FORMAT_BGRA_8888;
        break;
    case PIXFORMAT_BGRA8888:
        pix_fmt = PIXEL_FORMAT_BGRA_8888;
        break;
    case PIXFORMAT_RGB888:
        pix_fmt = PIXEL_FORMAT_RGB_888;
        break;
    case PIXFORMAT_BGR888:
        pix_fmt = PIXEL_FORMAT_BGR_888;
        break;
    default:
        pix_fmt = PIXEL_FORMAT_BUTT;
        break;
    }

    return pix_fmt;
}

/*
@staticmethod
Display.show_image(img, x = 0, y = 0, layer = Display.LAYER_OSD0, alpha = None, flag = 0)
*/
static mp_obj_t py_display_show_image_wrap(mp_uint_t n_args, const mp_obj_t* pos_args, mp_map_t* kw_args)
{
    enum { ARG_img, ARG_x, ARG_y, ARG_layer, ARG_alpha, ARG_flag };
    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_img, MP_ARG_OBJ | MP_ARG_REQUIRED, { .u_obj = mp_const_none } },
        { MP_QSTR_x, MP_ARG_INT, { .u_int = 0 } },
        { MP_QSTR_y, MP_ARG_INT, { .u_int = 0 } },
        { MP_QSTR_layer, MP_ARG_INT, { .u_int = K_VO_LAYER_OSD0 } },
        { MP_QSTR_alpha, MP_ARG_OBJ, { .u_obj = mp_const_none } },
        { MP_QSTR_flag, MP_ARG_INT, { .u_int = 0 } }, // removed.
    };
    mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all(n_args, pos_args, kw_args, MP_ARRAY_SIZE(allowed_args), allowed_args, args);

    if (!py_display_status()) {
        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("show image without init"));
    }

    image_t* arg_img = (image_t*)py_image_cobj(args[ARG_img].u_obj);

    k_pixel_format pix_fmt     = map_omv_image_to_pixel_format(arg_img->pixfmt);
    int            pix_fmt_bpp = py_display_vo_layer_pixl_format_bpp(pix_fmt);

    if ((PIXEL_FORMAT_BUTT == pix_fmt) || (0x00 == pix_fmt_bpp)) {
        mp_raise_msg_varg(&mp_type_ValueError, MP_ERROR_TEXT("unsupport image format %d"), arg_img->pixfmt);
    }

    k_u32 arg_x = args[ARG_x].u_int;
    k_u32 arg_y = args[ARG_y].u_int;

    int img_width  = arg_img->w;
    int img_height = arg_img->h;

    k_u32 panel_width = 0, panel_height = 0;
    py_display_get_resolution(&panel_width, &panel_height);

    if (((arg_x + img_width) > panel_width) || ((arg_y + img_height) > panel_height)) {
        mp_raise_msg_varg(&mp_type_ValueError, MP_ERROR_TEXT("image exceed the panel resolution"));
    }

    k_vo_layer_id arg_layer = args[ARG_layer].u_int;

    if ((K_VO_LAYER_OSD0 > arg_layer) || (K_MAX_VO_LAYER_NR <= arg_layer)) {
        mp_raise_ValueError(MP_ERROR_TEXT("invalid layer"));
    }

    int      arg_alpha     = -1;
    mp_obj_t arg_alpha_obj = args[ARG_alpha].u_obj;

    if (mp_const_none != arg_alpha_obj) {
        arg_alpha = mp_obj_get_int(arg_alpha_obj);

        if (0 > arg_alpha) {
            arg_alpha = 0;
        }
        if (255 < arg_alpha) {
            arg_alpha = 255;
        }
    }

    int arg_flag = args[ARG_flag].u_int;

    k_vo_layer_attr attr;

    if (0x00 == py_display_inst.layer_configed[arg_layer]) {
        attr.layer_id        = arg_layer;
        attr.position.x      = arg_x;
        attr.position.y      = arg_y;
        attr.img_size.width  = img_width;
        attr.img_size.height = img_height;
        attr.pixel_format    = pix_fmt;
        attr.func            = arg_flag;
        attr.global_alpha    = arg_alpha;
        attr.rot_buf_nr      = 2;
        attr.rot_buf_bpp     = 4;

        arg_flag = 0; // eat this arg

        if (0x00 != py_dispay_config_layer_inst(arg_layer, &attr)) {
            mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("config layer attr failed"));
        }
    }

    py_display_buffer_t* buffer = NULL;

    if (py_display_inst.rotated) {
        buffer = &py_display_inst.share_buffer;
    } else {
        buffer = &py_display_inst.layer_buffer[arg_layer];
    }

    if (0x00 == buffer->valid) {
        if (0x00
            != py_display_alloc_single_buffer(buffer, py_display_inst.osd_layer_vb_pool_id,
                                              pix_fmt_bpp * img_width * img_height)) {
            mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("alloc layer buffer failed"));
        }
    }

    k_vo_layer_attr* layer_attr = &py_display_inst.layer_attr[arg_layer];

    memset(&attr, 0x00, sizeof(attr));

    if (0x00 != kd_display_layer_get_attr(arg_layer, &attr)) {
        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("get vo layer attr failed"));
    }

    if ((attr.position.x != arg_x) || (attr.position.y != arg_y)) {
        if (0x00 != kd_display_layer_update_position(arg_layer, arg_x, arg_y)) {
            mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("set vo layer attr failed 1"));
        }
        layer_attr->position.x = arg_x;
        layer_attr->position.y = arg_y;
    }

    if ((attr.img_size.width != img_width) || (attr.img_size.height != img_height)) {
        if (0x00 != kd_display_layer_update_layer_image_size(arg_layer, img_width, img_height)) {
            mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("set vo layer attr failed 2"));
        }
        layer_attr->img_size.width  = img_width;
        layer_attr->img_size.height = img_height;
    }

    if (attr.pixel_format != pix_fmt) {
        if (0x00 != kd_display_layer_update_pixel_format(arg_layer, pix_fmt)) {
            mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("set vo layer attr failed 3"));
        }
        layer_attr->pixel_format = pix_fmt;
    }

    if ((-1 != arg_alpha) && (attr.global_alpha != arg_alpha)) {
        if (0x00 != kd_display_layer_update_alpha(arg_layer, arg_alpha)) {
            mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("set vo layer attr failed 4"));
        }
        layer_attr->global_alpha = arg_alpha;
    }

    if ((0 != arg_flag) && (attr.func != arg_flag)) {
        mp_printf(&mp_plat_print, "not support change flag\n");
    }

    if (0x00 != py_display_show_image_to_buffer(arg_layer, arg_img, buffer, pix_fmt, pix_fmt_bpp)) {
        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("show image failed"));
    }

    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_KW(py_display_show_image_obj, 1, py_display_show_image_wrap);
static MP_DEFINE_CONST_STATICMETHOD_OBJ(py_display_show_image_method, MP_ROM_PTR(&py_display_show_image_obj));

/**
@staticmethod
Display.writeback() // query stats
Display.writeback(enable = True/False) // set stats
*/
static mp_obj_t py_display_wbc_wrap(size_t n, const mp_obj_t* args)
{
    if (0x00 == n) {
        // query stats
        int stats = py_display_wbc_status();

        return stats ? mp_const_true : mp_const_false;
    }

    int new_stats = mp_obj_get_int(args[0]);

    if (0x00 == py_display_status()) {
        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("set wbc stats but not init display"));
    }

    int quality = py_display_wbc_quality();

    if (0x00 != py_display_set_wbc_inst(new_stats, quality)) {
        return mp_const_false;
    }

    return mp_const_true;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR(py_display_wbc_obj, 0, py_display_wbc_wrap);
static MP_DEFINE_CONST_STATICMETHOD_OBJ(py_display_wbc_method, MP_ROM_PTR(&py_display_wbc_obj));

/**
@staticmethod
Display.writeback_dump(timeout=1000) // dump a frame
*/
static mp_obj_t py_display_wbc_dump_wrap(size_t n, const mp_obj_t* args)
{
    int timeout_ms = 1000;

    k_video_frame_info info;

    if (0x01 <= n) {
        timeout_ms = mp_obj_get_int(args[0]);
    }

    MP_THREAD_GIL_EXIT();
    if (0x00 != py_display_wbc_dump(&info, timeout_ms, 0)) {
        MP_THREAD_GIL_ENTER();

        mp_printf(&mp_plat_print, "wbc dump failed");

        return mp_const_none;
    }

    return py_video_frame_info_from_struct(&info);
}
static MP_DEFINE_CONST_FUN_OBJ_VAR(py_display_wbc_dump_obj, 0, py_display_wbc_dump_wrap);
static MP_DEFINE_CONST_STATICMETHOD_OBJ(py_display_wbc_dump_method, MP_ROM_PTR(&py_display_wbc_dump_obj));

static const mp_rom_map_elem_t display_locals_dict_table[] = {
    { MP_ROM_QSTR(MP_QSTR_init), MP_ROM_PTR(&py_display_init_method) },
    { MP_ROM_QSTR(MP_QSTR_deinit), MP_ROM_PTR(&py_display_deinit_method) },

    { MP_ROM_QSTR(MP_QSTR_bind_layer), MP_ROM_PTR(&py_display_bind_layer_method) },
    { MP_ROM_QSTR(MP_QSTR_unbind_layer), MP_ROM_PTR(&py_display_unbind_layer_method) },

    { MP_ROM_QSTR(MP_QSTR_width), MP_ROM_PTR(&py_display_width_method) },
    { MP_ROM_QSTR(MP_QSTR_height), MP_ROM_PTR(&py_display_height_method) },
    { MP_ROM_QSTR(MP_QSTR_fps), MP_ROM_PTR(&py_display_fps_method) },

    { MP_ROM_QSTR(MP_QSTR_config_layer), MP_ROM_PTR(&py_display_config_layer_method) },
    { MP_ROM_QSTR(MP_QSTR_disable_layer), MP_ROM_PTR(&py_display_disable_layer_method) },
    { MP_ROM_QSTR(MP_QSTR__disable_layer), MP_ROM_PTR(&py_display_disable_layer_method) },

    { MP_ROM_QSTR(MP_QSTR_show_image), MP_ROM_PTR(&py_display_show_image_method) },

    { MP_ROM_QSTR(MP_QSTR_writeback), MP_ROM_PTR(&py_display_wbc_method) },
    { MP_ROM_QSTR(MP_QSTR_writeback_dump), MP_ROM_PTR(&py_display_wbc_dump_method) },

    /* panel type */
    { MP_ROM_QSTR(MP_QSTR_VIRT), MP_ROM_INT(PY_PANEL_TYPE_VIRT) },
    { MP_ROM_QSTR(MP_QSTR_DEBUGGER), MP_ROM_INT(PY_PANEL_TYPE_DEBUGGER) },
    { MP_ROM_QSTR(MP_QSTR_ST7701), MP_ROM_INT(PY_PANEL_TYPE_ST7701) },
    { MP_ROM_QSTR(MP_QSTR_HX8399), MP_ROM_INT(PY_PANEL_TYPE_HX8399) },
    { MP_ROM_QSTR(MP_QSTR_ILI9806), MP_ROM_INT(PY_PANEL_TYPE_ILI9806) },
    { MP_ROM_QSTR(MP_QSTR_LT9611), MP_ROM_INT(PY_PANEL_TYPE_LT9611) },
    { MP_ROM_QSTR(MP_QSTR_ILI9881), MP_ROM_INT(PY_PANEL_TYPE_ILI9881) },
    { MP_ROM_QSTR(MP_QSTR_NT35516), MP_ROM_INT(PY_PANEL_TYPE_NT35516) },
    { MP_ROM_QSTR(MP_QSTR_NT35532), MP_ROM_INT(PY_PANEL_TYPE_NT35532) },
    { MP_ROM_QSTR(MP_QSTR_GC9503), MP_ROM_INT(PY_PANEL_TYPE_GC9503) },
    { MP_ROM_QSTR(MP_QSTR_ST7102), MP_ROM_INT(PY_PANEL_TYPE_ST7102) },
    { MP_ROM_QSTR(MP_QSTR_AML020T), MP_ROM_INT(PY_PANEL_TYPE_AML020T) },
    { MP_ROM_QSTR(MP_QSTR_JD9852), MP_ROM_INT(PY_PANEL_TYPE_JD9852) },

    /* layer */
    { MP_ROM_QSTR(MP_QSTR_LAYER_VIDEO1), MP_ROM_INT(K_VO_LAYER_VIDEO1) },
    { MP_ROM_QSTR(MP_QSTR_LAYER_VIDEO2), MP_ROM_INT(K_VO_LAYER_VIDEO2) },
    { MP_ROM_QSTR(MP_QSTR_LAYER_VIDEO3), MP_ROM_INT(K_VO_LAYER_VIDEO3) },
    { MP_ROM_QSTR(MP_QSTR_LAYER_OSD0), MP_ROM_INT(K_VO_LAYER_OSD0) },
    { MP_ROM_QSTR(MP_QSTR_LAYER_OSD1), MP_ROM_INT(K_VO_LAYER_OSD1) },
    { MP_ROM_QSTR(MP_QSTR_LAYER_OSD2), MP_ROM_INT(K_VO_LAYER_OSD2) },
    { MP_ROM_QSTR(MP_QSTR_LAYER_OSD3), MP_ROM_INT(K_VO_LAYER_OSD3) },

    /* rotate flag */
    { MP_ROM_QSTR(MP_QSTR_FLAG_ROTATION_NONE), MP_ROM_INT(0) },
    { MP_ROM_QSTR(MP_QSTR_FLAG_ROTATION_0), MP_ROM_INT(GDMA_ROTATE_DEGREE_0) },
    { MP_ROM_QSTR(MP_QSTR_FLAG_ROTATION_90), MP_ROM_INT(GDMA_ROTATE_DEGREE_90) },
    { MP_ROM_QSTR(MP_QSTR_FLAG_ROTATION_180), MP_ROM_INT(GDMA_ROTATE_DEGREE_180) },
    { MP_ROM_QSTR(MP_QSTR_FLAG_ROTATION_270), MP_ROM_INT(GDMA_ROTATE_DEGREE_270) },
    { MP_ROM_QSTR(MP_QSTR_FLAG_MIRROR_NONE), MP_ROM_INT(0) },
    { MP_ROM_QSTR(MP_QSTR_FLAG_MIRROR_HOR), MP_ROM_INT(GDMA_ROTATE_MIRROR_HOR) },
    { MP_ROM_QSTR(MP_QSTR_FLAG_MIRROR_VER), MP_ROM_INT(GDMA_ROTATE_MIRROR_VER) },
    { MP_ROM_QSTR(MP_QSTR_FLAG_MIRROR_BOTH), MP_ROM_INT(GDMA_ROTATE_MIRROR_HOR | GDMA_ROTATE_MIRROR_VER) },
};
static MP_DEFINE_CONST_DICT(display_locals_dict, display_locals_dict_table);

/* clang-format off */
MP_DEFINE_CONST_OBJ_TYPE(
    py_media_display_type,
    MP_QSTR_DISPLAY,
    MP_TYPE_FLAG_NONE,
    locals_dict, &display_locals_dict
);
/* clang-format on */
