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
#include <stddef.h>
#include "ide_dbg.h"

#include "hal_rvv_ops.h"

#if CONFIG_CANMV_IDE_SUPPORT

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>

#include "k_vb_comm.h"
#include "py/runtime.h"

#include "kd_display.h"

#include "mpi_gsdma_api.h"
#include "mpi_sys_api.h"
#include "mpi_vb_api.h"
#include "mpi_venc_api.h"

#include "py_modules.h"

/* Context for VENC resource management and caching */
typedef struct {
    int        inited;
    k_u32      chn_id;
    int        fd_acquired;
    int        chn_requested;
    int        pool_attached;
    int        chn_created;
    int        chn_started;
    int        frame_held;
    k_u32      pool_id; // Single pool for both VENC and output
    k_u32      width; // Cached Display width
    k_u32      height; // Cached Display height
    int        quality; // Cached Quality
    k_rotation rotation; // Cached Rotation state

    // Single output buffer (allocated from the same pool)
    k_vb_blk_handle output_block;
    k_u64           output_phys_addr;
    void*           output_virt_addr;
    size_t          output_size;

#define MAX_VENC_PACKS 64
    k_venc_pack static_packs[MAX_VENC_PACKS];
} ide_dbg_vo_wbc_ctx_t;

static ide_dbg_vo_wbc_ctx_t g_wbc_ctx = {
    .inited           = 0,
    .chn_id           = -1,
    .pool_id          = VB_INVALID_POOLID,
    .output_block     = VB_INVALID_HANDLE,
    .output_phys_addr = 0,
    .output_virt_addr = NULL,
    .output_size      = 0,
    .rotation         = K_VPU_ROTATION_0,
};

static int g_wbc_enable = 0;

// Heap-backed copy of the encoder output. FRAME_SIZE and FRAME_DUMP are
// serialized by the IDE task, so the buffer can be reused after each dump.
// Keep it outside g_wbc_ctx because encoder teardown must not invalidate it.
static void *g_wbc_snapshot_buffer = NULL;
static size_t g_wbc_snapshot_capacity = 0;

// Serializes the writeback encoder lifecycle across threads. The IDE task
// thread runs ide_dbg_vo_wbc_dump_and_encode() (driven by USBDBG_FRAME_SIZE)
// while the main thread can tear the encoder down via ide_dbg_vo_wbc_stop()
// during a soft reset. Without this lock the teardown destroys the VENC
// channel / VB pool while an encode is still reading from it (use-after-free).
// Held only across the encoder entry points; the helpers below assume it is
// already held by their caller, so they must never re-acquire it.
static pthread_mutex_t g_wbc_lock = PTHREAD_MUTEX_INITIALIZER;

static void wbc_release_frame(void)
{
    if (g_wbc_ctx.frame_held) {
        py_display_wbc_dump_relase();
        g_wbc_ctx.frame_held = 0;
    }
}

/**
 * @brief Cleanup initialized resources in reverse order
 * @note Caller must hold g_wbc_lock. On failure, dependent resources remain
 *       recorded so a later stop can retry safely.
 */
static k_s32 wbc_cleanup_resources(void)
{
    k_s32 ret;

    // Store chn_id locally before modifying it
    k_s32 chn_id_to_cleanup = g_wbc_ctx.chn_id;

    wbc_release_frame();

    // Stop and destroy VENC channel if chn_id is valid
    if (chn_id_to_cleanup != -1) {
        if (g_wbc_ctx.chn_started) {
            ret = kd_mpi_venc_stop_chn(chn_id_to_cleanup);
            if (ret != K_SUCCESS)
                return ret;
            g_wbc_ctx.chn_started = 0;
        }
        if (g_wbc_ctx.pool_attached) {
            ret = kd_mpi_venc_detach_vb_pool(chn_id_to_cleanup);
            if (ret != K_SUCCESS)
                return ret;
            g_wbc_ctx.pool_attached = 0;
        }
        if (g_wbc_ctx.chn_created) {
            ret = kd_mpi_venc_destroy_chn(chn_id_to_cleanup);
            if (ret != K_SUCCESS)
                return ret;
            g_wbc_ctx.chn_created = 0;
        }
        if (g_wbc_ctx.chn_requested) {
            ret = kd_mpi_venc_release_chn(chn_id_to_cleanup);
            if (ret != K_SUCCESS)
                return ret;
            g_wbc_ctx.chn_requested = 0;
        }
        g_wbc_ctx.chn_id = -1;
    }

    // Release output buffer
    if (g_wbc_ctx.output_virt_addr) {
        ret = kd_mpi_sys_munmap(g_wbc_ctx.output_virt_addr,
                                g_wbc_ctx.output_size);
        if (ret != K_SUCCESS)
            return ret;
        g_wbc_ctx.output_virt_addr = NULL;
    }

    if (g_wbc_ctx.output_block != VB_INVALID_HANDLE) {
        ret = kd_mpi_vb_release_block(g_wbc_ctx.output_block);
        if (ret != K_SUCCESS)
            return ret;
        g_wbc_ctx.output_block     = VB_INVALID_HANDLE;
        g_wbc_ctx.output_phys_addr = 0;
        g_wbc_ctx.output_size      = 0;
    }

    // Destroy VB pool if valid
    if (g_wbc_ctx.pool_id != VB_INVALID_POOLID) {
        ret = kd_mpi_vb_destory_pool(g_wbc_ctx.pool_id);
        if (ret != K_SUCCESS)
            return ret;
        g_wbc_ctx.pool_id = VB_INVALID_POOLID;
    }

    if (g_wbc_ctx.fd_acquired) {
        ret = kd_mpi_venc_release_fd();
        g_wbc_ctx.fd_acquired = 0;
        if (ret != K_SUCCESS)
            return ret;
    }

    // Reset all other state
    g_wbc_ctx.width    = 0;
    g_wbc_ctx.height   = 0;
    g_wbc_ctx.quality  = 0;
    g_wbc_ctx.rotation = K_VPU_ROTATION_0;
    hal_rvv_memset(g_wbc_ctx.static_packs, 0, sizeof(g_wbc_ctx.static_packs));

    return K_SUCCESS;
}

void ide_dbg_vo_wbc_start(int enable)
{
    if (enable) {
        ide_dbg_enable_vo_wbc();
    }

    pthread_mutex_lock(&g_wbc_lock);
    g_wbc_enable = enable;
    pthread_mutex_unlock(&g_wbc_lock);
}

/**
 * @brief Release VENC channel and return the ID to the system.
 */
void ide_dbg_vo_wbc_stop(void)
{
    // Take the lifecycle lock so we wait for any in-flight encode on the IDE
    // task thread to finish before destroying the channel/pool it reads from.
    pthread_mutex_lock(&g_wbc_lock);

    g_wbc_enable = 0;

    // Always cleanup resources regardless of inited flag
    // This handles partial initialization cases
    if (wbc_cleanup_resources() != K_SUCCESS)
        printf("ERROR: IDE WBC cleanup failed; resources retained\n");

    // Reset the inited flag after cleanup
    g_wbc_ctx.inited = 0;

    pthread_mutex_unlock(&g_wbc_lock);
}

/**
 * @brief Allocate output buffer from the same pool at init time
 */
static k_s32 wbc_alloc_output_buffer(k_u32 buffer_size)
{
    // Allocate output buffer from the same pool
    g_wbc_ctx.output_block = kd_mpi_vb_get_block(g_wbc_ctx.pool_id, buffer_size, NULL);
    if (g_wbc_ctx.output_block == VB_INVALID_HANDLE) {
        return -1;
    }

    g_wbc_ctx.output_phys_addr = kd_mpi_vb_handle_to_phyaddr(g_wbc_ctx.output_block);
    if (g_wbc_ctx.output_phys_addr == 0) {
        kd_mpi_vb_release_block(g_wbc_ctx.output_block);
        g_wbc_ctx.output_block = VB_INVALID_HANDLE;
        return -1;
    }

    g_wbc_ctx.output_size = buffer_size;

    // Map buffer to kernel space at init time (cached for CPU access)
    g_wbc_ctx.output_virt_addr = kd_mpi_sys_mmap_cached(g_wbc_ctx.output_phys_addr, buffer_size);
    if (!g_wbc_ctx.output_virt_addr) {
        kd_mpi_vb_release_block(g_wbc_ctx.output_block);
        g_wbc_ctx.output_block     = VB_INVALID_HANDLE;
        g_wbc_ctx.output_phys_addr = 0;
        g_wbc_ctx.output_size      = 0;
        return -1;
    }

    return 0;
}

static k_s32 ide_dbg_vo_wbc_init(const k_video_frame_info *probe_vf)
{
    k_s32              ret;
    k_u32              display_width, display_height;
    k_rotation         target_rot = K_VPU_ROTATION_0;

    // Cache Display Resolution and Quality (only once)
    ret = kd_display_get_resolution(&display_width, &display_height);
    if (ret != 0) {
        goto _err;
    }
    g_wbc_ctx.quality = py_display_wbc_quality();

    // If dimensions differ from display, check hardware rotation flags
    if (probe_vf->v_frame.width != display_width || probe_vf->v_frame.height != display_height) {
        k_vo_dev_attr vo_attr;
        if (kd_mpi_vo_get_dev_attr(&vo_attr) == 0) {
            if (vo_attr.dev_rot_flg & GDMA_ROTATE_DEGREE_90)
                target_rot = K_VPU_ROTATION_90;
            else if (vo_attr.dev_rot_flg & GDMA_ROTATE_DEGREE_180)
                target_rot = K_VPU_ROTATION_180;
            else if (vo_attr.dev_rot_flg & GDMA_ROTATE_DEGREE_270)
                target_rot = K_VPU_ROTATION_270;
        }
    }

    ret = kd_mpi_venc_acquire_fd();
    if (ret != K_SUCCESS)
        goto _err;
    g_wbc_ctx.fd_acquired = 1;

    // Request VENC channel dynamically
    ret = kd_mpi_venc_request_chn(&g_wbc_ctx.chn_id);
    if (ret != 0) {
        // Don't set chn_id to -1 here, cleanup will handle it
        goto _err;
    }
    g_wbc_ctx.chn_requested = 1;

    // Create single VB Pool for both VENC and output
    k_u32 blk_size = (display_width * display_height * 3 / 2);
    blk_size       = VB_ALIGN_UP(blk_size, 4096);

    // Create pool with 2 blocks: 1 for VENC, 1 for our output buffer
    g_wbc_ctx.pool_id = kd_mpi_vb_create_pool_ex(blk_size, 2, VB_REMAP_MODE_NOCACHE);
    if (g_wbc_ctx.pool_id == VB_INVALID_POOLID) {
        goto _err;
    }

    //  Allocate output buffer from the same pool
    ret = wbc_alloc_output_buffer(blk_size);
    if (ret != 0) {
        goto _err;
    }

    //  Setup VENC attributes
    k_venc_chn_attr attr;
    hal_rvv_memset(&attr, 0, sizeof(attr));
    attr.venc_attr.type = K_PT_JPEG;

    // Set input dimensions: Swap width/height if WBC is providing a rotated buffer
    if (target_rot == K_VPU_ROTATION_90 || target_rot == K_VPU_ROTATION_270) {
        attr.venc_attr.pic_width  = display_height;
        attr.venc_attr.pic_height = display_width;
    } else {
        attr.venc_attr.pic_width  = display_width;
        attr.venc_attr.pic_height = display_height;
    }

    g_wbc_ctx.width  = attr.venc_attr.pic_width;
    g_wbc_ctx.height = attr.venc_attr.pic_height;

    attr.rc_attr.rc_mode                    = K_VENC_RC_MODE_MJPEG_FIXQP;
    attr.rc_attr.mjpeg_fixqp.src_frame_rate = 30;
    attr.rc_attr.mjpeg_fixqp.dst_frame_rate = 30;
    attr.rc_attr.mjpeg_fixqp.q_factor       = g_wbc_ctx.quality;

    // venc hardware use only one buffer in pool.
    ret = kd_mpi_venc_attach_vb_pool_ex(g_wbc_ctx.chn_id, g_wbc_ctx.pool_id, 1);
    if (ret != 0) {
        goto _err;
    }
    g_wbc_ctx.pool_attached = 1;

    ret = kd_mpi_venc_create_chn(g_wbc_ctx.chn_id, &attr);
    if (ret != 0) {
        goto _err;
    }
    g_wbc_ctx.chn_created = 1;

    //  Apply rotation to the VENC channel
    if (target_rot != K_VPU_ROTATION_0) {
        ret = kd_mpi_venc_set_rotation(g_wbc_ctx.chn_id, target_rot);
        if (ret != K_SUCCESS)
            goto _err;
    }

    ret = kd_mpi_venc_start_chn(g_wbc_ctx.chn_id);
    if (ret != 0) {
        goto _err;
    }
    g_wbc_ctx.chn_started = 1;

    g_wbc_ctx.rotation = target_rot;
    g_wbc_ctx.inited   = 1;

    return 0;

_err:
    printf("ERROR: idg dbg vo wbc init failed\n");

    // Clean up any partially allocated resources
    ret = wbc_cleanup_resources();
    if (ret != K_SUCCESS)
        printf("ERROR: IDE WBC cleanup failed:0x%x; resources retained\n", ret);
    return -1;
}

/**
 * @brief High-speed dump and encode. Operates purely on cached state.
 * @note Caller must hold g_wbc_lock (see ide_dbg_vo_wbc_dump_and_encode).
 */
static int ide_dbg_vo_wbc_dump_and_encode_locked(void** buffer, size_t* buffer_size, uint32_t* image_width, uint32_t* image_height)
{
    k_s32 ret;

    if (!g_wbc_enable) {
        return -1;
    }

    if (!g_wbc_ctx.inited) {
        ret = wbc_cleanup_resources();
        if (ret != K_SUCCESS) {
            printf("ERROR: previous IDE WBC cleanup failed:0x%x\n", ret);
            return -1;
        }
    }

    // Dump the frame from WBC
    k_video_frame_info vf_info;
    if (py_display_wbc_dump(&vf_info, 1000, 1) != 0) {
        // printf("ide dbg vo wbc failed to dump WBC frame\n");
        return -1;
    }
    g_wbc_ctx.frame_held = 1;

    // Initialize once only
    if (!g_wbc_ctx.inited) {
        if (ide_dbg_vo_wbc_init(&vf_info) != 0) {
            wbc_release_frame();
            return -1;
        }
    }

    // Send to VENC
    if (kd_mpi_venc_send_frame(g_wbc_ctx.chn_id, &vf_info, 1000) != 0) {
        wbc_release_frame();

        printf("ide dbg vo wbc failed to send frame to VENC\n");
        return -1;
    }

    // NOTE: Do NOT release the WBC block here! VENC reads from it asynchronously.
    // We must hold the WBC block until kd_mpi_venc_get_stream() returns, which
    // guarantees the VPU has finished reading from the WBC buffer. Releasing early
    // allows the WBC ISR to reuse this block as a DMA write target while the VPU
    // is still reading, causing memory corruption.

    // Query VENC status first to get pack count
    k_venc_chn_status venc_status;
    hal_rvv_memset(&venc_status, 0, sizeof(venc_status));

    if (kd_mpi_venc_query_status(g_wbc_ctx.chn_id, &venc_status) != 0) {
        wbc_release_frame();

        printf("ide dbg vo wbc failed to query VENC status\n");
        return -1;
    }

    // Get stream from VENC using static packs
    k_venc_stream stream;
    hal_rvv_memset(&stream, 0, sizeof(stream));

    // Set pack_cnt based on status query
    stream.pack_cnt = (venc_status.cur_packs > 0) ? venc_status.cur_packs : 1;

    // IMPORTANT: Cap pack count to our static array size
    if (stream.pack_cnt > MAX_VENC_PACKS) {
        printf("ide dbg vo wbc warning: truncating packs from %d to %d\n", stream.pack_cnt, MAX_VENC_PACKS);
        stream.pack_cnt = MAX_VENC_PACKS;
    }

    // Use static memory instead of malloc
    stream.pack = g_wbc_ctx.static_packs;

    // Initialize pack array
    hal_rvv_memset(stream.pack, 0, sizeof(k_venc_pack) * stream.pack_cnt);

    if (kd_mpi_venc_get_stream(g_wbc_ctx.chn_id, &stream, 1000) != 0) {
        wbc_release_frame();

        printf("ide dbg vo wbc failed to get stream from VENC\n");
        return -1;
    }

    // VENC has finished reading the WBC buffer — safe to release now
    wbc_release_frame();

    // Check if we have valid packets
    if (stream.pack_cnt == 0 || stream.pack[0].phys_addr == 0) {
        // Still need to release stream even if it has no valid packets
        kd_mpi_venc_release_stream(g_wbc_ctx.chn_id, &stream);

        printf("ide dbg vo wbc no valid packets in stream\n");
        return -1;
    }

    // Calculate total length and copy data
    size_t total_len = 0;
    for (k_u32 i = 0; i < stream.pack_cnt && i < MAX_VENC_PACKS; i++) {
        if (stream.pack[i].phys_addr != 0) {
            total_len += stream.pack[i].len;
        }
    }

    if (0x00 == total_len) {
        kd_mpi_venc_release_stream(g_wbc_ctx.chn_id, &stream);

        printf("ide dbg vo wbc total length is 0\n");
        return -1;
    }

    // Check if buffer is large enough
    if (total_len > g_wbc_ctx.output_size) {
        kd_mpi_venc_release_stream(g_wbc_ctx.chn_id, &stream);

        printf("ide dbg vo wbc Output buffer too small: need %zu, have %zu\n", total_len, g_wbc_ctx.output_size);
        return -1;
    }

    // Copy data using DMA for each packet
    k_u64 dst_offset = 0;
    for (k_u32 i = 0; i < stream.pack_cnt && i < MAX_VENC_PACKS; i++) {
        if (stream.pack[i].len > 0 && stream.pack[i].phys_addr != 0) {
            kd_mpi_dma_memcpy((void*)(uintptr_t)(g_wbc_ctx.output_phys_addr + dst_offset),
                              (void*)(uintptr_t)stream.pack[i].phys_addr, stream.pack[i].len);
            dst_offset += stream.pack[i].len;
        }
    }

    // Invalidate cache
    kd_mpi_sys_mmz_invalidate_cache(g_wbc_ctx.output_phys_addr, g_wbc_ctx.output_virt_addr, total_len);

    // Return buffer info
    *buffer      = g_wbc_ctx.output_virt_addr;
    *buffer_size = total_len;

    *image_width  = g_wbc_ctx.width;
    *image_height = g_wbc_ctx.height;

    // Release stream
    kd_mpi_venc_release_stream(g_wbc_ctx.chn_id, &stream);

    // printf("%s->%d Success: encoded %zu bytes, %dx%d, packs=%d\n", __func__, __LINE__, total_len, *image_width,
    // *image_height,
    //        stream.pack_cnt);

    return 0;
}

int ide_dbg_vo_wbc_dump_and_encode(void** buffer, size_t* buffer_size, uint32_t* image_width, uint32_t* image_height)
{
    void *encoded_buffer = NULL;
    size_t encoded_size = 0;
    uint32_t encoded_width = 0;
    uint32_t encoded_height = 0;

    // Copy the encoded frame while holding the lifecycle lock. The encoder's
    // output buffer belongs to its VB pool and becomes invalid during a soft
    // reset; callers need an independently owned snapshot for FRAME_DUMP.
    pthread_mutex_lock(&g_wbc_lock);
    int ret = ide_dbg_vo_wbc_dump_and_encode_locked(
        &encoded_buffer, &encoded_size, &encoded_width, &encoded_height);
    if (ret == 0) {
        if (encoded_size == 0) {
            ret = -1;
        } else if (g_wbc_snapshot_capacity < encoded_size) {
            void *resized = realloc(g_wbc_snapshot_buffer, encoded_size);
            if (resized == NULL) {
                ret = -1;
            } else {
                g_wbc_snapshot_buffer = resized;
                g_wbc_snapshot_capacity = encoded_size;
            }
        }
        if (ret == 0) {
            hal_rvv_memcpy(g_wbc_snapshot_buffer, encoded_buffer, encoded_size);
        }
    }
    pthread_mutex_unlock(&g_wbc_lock);

    if (ret == 0) {
        *buffer = g_wbc_snapshot_buffer;
        *buffer_size = encoded_size;
        *image_width = encoded_width;
        *image_height = encoded_height;
    } else {
        *buffer = NULL;
        *buffer_size = 0;
        *image_width = 0;
        *image_height = 0;
    }
    return ret;
}

#endif // CONFIG_CANMV_IDE_SUPPORT
