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
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
 * AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
 * IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
 * ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
 * LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
 * CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
 * SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
 * INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
 * CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
 * ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
 * POSSIBILITY OF SUCH DAMAGE.
 */

#include <pthread.h>
#include <stdint.h>
#include <stdio.h>

#include "hal_rvv_ops.h"
#include "py/mpthread.h"
#include "py/obj.h"
#include "py/runtime.h"

#include "k_module.h"
#include "mpi_sys_api.h"
#include "mpi_vb_api.h"
#include "mpi_venc_api.h"

#include "py_image.h"
#include "py_modules.h"

#define MJPEG_MAX_PACKS 64
#define MJPEG_VPU_PAGE_SIZE 4096U

typedef struct {
    mp_obj_base_t base;
    pthread_mutex_t mutex;

    int closed;
    int quality;
    int chn_id;
    int fd_acquired;
    int chn_requested;
    int pool_attached;
    int chn_created;
    int chn_started;
    int width;
    int height;
    k_pixel_format pixel_format;

    k_s32 output_pool_id;
    size_t output_block_size;

    k_s32 input_pool_id;
    k_vb_blk_handle input_block;
    k_u64 input_phys_addr;
    void* input_virt_addr;
    size_t input_block_size;
    size_t input_data_size;

    k_venc_pack packs[MJPEG_MAX_PACKS];
} py_media_mjpeg_encoder_obj_t;

typedef struct {
    image_t* image;
    k_video_frame_info frame_info;
    k_pixel_format pixel_format;
    size_t data_size;
    size_t plane_offset[3];
    int staged;
} mjpeg_input_t;

static void mjpeg_encoder_lock(py_media_mjpeg_encoder_obj_t* self)
{
    MP_THREAD_GIL_EXIT();
    while (pthread_mutex_lock(&self->mutex) != 0) { }
    MP_THREAD_GIL_ENTER();
}

static void mjpeg_encoder_unlock(py_media_mjpeg_encoder_obj_t* self) { pthread_mutex_unlock(&self->mutex); }

static int mjpeg_output_block_size(int width, int height, size_t* block_size)
{
    uint64_t pixel_count = (uint64_t)width * height;
    uint64_t output_size = (pixel_count * 3 + 1) / 2;

    if (output_size > SIZE_MAX - (MJPEG_VPU_PAGE_SIZE - 1)) {
        return -1;
    }
    *block_size = VB_ALIGN_UP((size_t)output_size, MJPEG_VPU_PAGE_SIZE);
    return 0;
}

static k_s32 mjpeg_encoder_cleanup_locked(py_media_mjpeg_encoder_obj_t* self)
{
    k_s32 ret;

    if (self->chn_id >= 0) {
        if (self->chn_started) {
            ret = kd_mpi_venc_stop_chn(self->chn_id);
            if (ret != K_SUCCESS)
                return ret;
            self->chn_started = 0;
        }
        if (self->pool_attached) {
            ret = kd_mpi_venc_detach_vb_pool(self->chn_id);
            if (ret != K_SUCCESS)
                return ret;
            self->pool_attached = 0;
        }
        if (self->chn_created) {
            ret = kd_mpi_venc_destroy_chn(self->chn_id);
            if (ret != K_SUCCESS)
                return ret;
            self->chn_created = 0;
        }
        if (self->chn_requested) {
            ret = kd_mpi_venc_release_chn(self->chn_id);
            if (ret != K_SUCCESS)
                return ret;
            self->chn_requested = 0;
        }
        self->chn_id = -1;
    }

    if (self->fd_acquired) {
        ret = kd_mpi_venc_release_fd();
        self->fd_acquired = 0;
        if (ret != K_SUCCESS)
            return ret;
    }

    self->width = 0;
    self->height = 0;
    self->pixel_format = PIXEL_FORMAT_BUTT;

    if (self->output_pool_id != VB_INVALID_POOLID) {
        ret = kd_mpi_vb_destory_pool(self->output_pool_id);
        if (ret != K_SUCCESS)
            return ret;
        self->output_pool_id = VB_INVALID_POOLID;
    }
    self->output_block_size = 0;

    if (self->input_virt_addr != NULL) {
        ret = kd_mpi_sys_munmap(self->input_virt_addr,
                                self->input_block_size);
        if (ret != K_SUCCESS)
            return ret;
        self->input_virt_addr = NULL;
    }
    if (self->input_block != VB_INVALID_HANDLE) {
        ret = kd_mpi_vb_release_block(self->input_block);
        if (ret != K_SUCCESS)
            return ret;
        self->input_block = VB_INVALID_HANDLE;
    }
    if (self->input_pool_id != VB_INVALID_POOLID) {
        ret = kd_mpi_vb_destory_pool(self->input_pool_id);
        if (ret != K_SUCCESS)
            return ret;
        self->input_pool_id = VB_INVALID_POOLID;
    }
    self->input_phys_addr = 0;
    self->input_block_size = 0;
    self->input_data_size = 0;

    return K_SUCCESS;
}

static int mjpeg_encoder_init_locked(py_media_mjpeg_encoder_obj_t* self, int width, int height,
                                     k_pixel_format pixel_format, size_t output_block_size, const char** failed_op)
{
    k_s32 ret;
    k_s32 cleanup_ret;
    k_u32 chn_id = UINT32_MAX;
    k_venc_chn_attr attr;

    ret = mjpeg_encoder_cleanup_locked(self);
    if (ret != K_SUCCESS) {
        *failed_op = "clean up previous VENC channel";
        return ret;
    }

    ret = kd_mpi_venc_acquire_fd();
    if (ret != K_SUCCESS) {
        *failed_op = "acquire VENC fd";
        return ret;
    }
    self->fd_acquired = 1;

    ret = kd_mpi_venc_request_chn(&chn_id);
    if (ret != K_SUCCESS) {
        *failed_op = "request VENC channel";
        (void)mjpeg_encoder_cleanup_locked(self);
        return ret;
    }
    self->chn_id = (int)chn_id;
    self->chn_requested = 1;

    self->output_block_size = output_block_size;
    self->output_pool_id = kd_mpi_vb_create_pool_ex(self->output_block_size, 1, VB_REMAP_MODE_NOCACHE);
    if (self->output_pool_id == VB_INVALID_POOLID) {
        *failed_op = "create VENC output pool";
        cleanup_ret = mjpeg_encoder_cleanup_locked(self);
        if (cleanup_ret != K_SUCCESS) {
            *failed_op = "clean up after output pool failure";
            return cleanup_ret;
        }
        return -1;
    }

    ret = kd_mpi_venc_attach_vb_pool_ex(self->chn_id, self->output_pool_id, 1);
    if (ret != K_SUCCESS) {
        *failed_op = "attach VENC output pool";
        cleanup_ret = mjpeg_encoder_cleanup_locked(self);
        if (cleanup_ret != K_SUCCESS) {
            *failed_op = "clean up after VENC pool attach failure";
            return cleanup_ret;
        }
        return ret;
    }
    self->pool_attached = 1;

    hal_rvv_memset(&attr, 0, sizeof(attr));
    attr.venc_attr.type = K_PT_JPEG;
    attr.venc_attr.pic_width = width;
    attr.venc_attr.pic_height = height;
    attr.rc_attr.rc_mode = K_VENC_RC_MODE_MJPEG_FIXQP;
    attr.rc_attr.mjpeg_fixqp.src_frame_rate = 30;
    attr.rc_attr.mjpeg_fixqp.dst_frame_rate = 30;
    attr.rc_attr.mjpeg_fixqp.q_factor = self->quality;

    ret = kd_mpi_venc_create_chn(self->chn_id, &attr);
    if (ret != K_SUCCESS) {
        *failed_op = "create VENC channel";
        cleanup_ret = mjpeg_encoder_cleanup_locked(self);
        if (cleanup_ret != K_SUCCESS) {
            *failed_op = "clean up after VENC create failure";
            return cleanup_ret;
        }
        return ret;
    }
    self->chn_created = 1;

    ret = kd_mpi_venc_start_chn(self->chn_id);
    if (ret != K_SUCCESS) {
        *failed_op = "start VENC channel";
        cleanup_ret = mjpeg_encoder_cleanup_locked(self);
        if (cleanup_ret != K_SUCCESS) {
            *failed_op = "clean up after VENC start failure";
            return cleanup_ret;
        }
        return ret;
    }
    self->chn_started = 1;

    self->width = width;
    self->height = height;
    self->pixel_format = pixel_format;
    return K_SUCCESS;
}

static int mjpeg_encoder_ensure_input_buffer_locked(py_media_mjpeg_encoder_obj_t* self, size_t data_size,
                                                     const char** failed_op)
{
    size_t block_size;

    if (self->input_block != VB_INVALID_HANDLE && self->input_block_size >= data_size) {
        self->input_data_size = data_size;
        return K_SUCCESS;
    }

    if (self->input_virt_addr != NULL) {
        kd_mpi_sys_munmap(self->input_virt_addr, self->input_block_size);
        self->input_virt_addr = NULL;
    }
    if (self->input_block != VB_INVALID_HANDLE) {
        kd_mpi_vb_release_block(self->input_block);
        self->input_block = VB_INVALID_HANDLE;
    }
    if (self->input_pool_id != VB_INVALID_POOLID) {
        kd_mpi_vb_destory_pool(self->input_pool_id);
        self->input_pool_id = VB_INVALID_POOLID;
    }

    if (data_size > SIZE_MAX - (MJPEG_VPU_PAGE_SIZE - 1)) {
        *failed_op = "calculate input buffer size";
        return -1;
    }
    block_size = VB_ALIGN_UP(data_size, MJPEG_VPU_PAGE_SIZE);

    self->input_pool_id = kd_mpi_vb_create_pool_ex(block_size, 1, VB_REMAP_MODE_CACHED);
    if (self->input_pool_id == VB_INVALID_POOLID) {
        *failed_op = "create VENC input pool";
        return -1;
    }

    self->input_block = kd_mpi_vb_get_block(self->input_pool_id, block_size, NULL);
    if (self->input_block == VB_INVALID_HANDLE) {
        *failed_op = "allocate VENC input block";
        kd_mpi_vb_destory_pool(self->input_pool_id);
        self->input_pool_id = VB_INVALID_POOLID;
        return -1;
    }

    self->input_phys_addr = kd_mpi_vb_handle_to_phyaddr(self->input_block);
    if (self->input_phys_addr == 0) {
        *failed_op = "get VENC input physical address";
        kd_mpi_vb_release_block(self->input_block);
        kd_mpi_vb_destory_pool(self->input_pool_id);
        self->input_block = VB_INVALID_HANDLE;
        self->input_pool_id = VB_INVALID_POOLID;
        return -1;
    }

    self->input_virt_addr = kd_mpi_sys_mmap_cached(self->input_phys_addr, block_size);
    if (self->input_virt_addr == NULL) {
        *failed_op = "map VENC input block";
        kd_mpi_vb_release_block(self->input_block);
        kd_mpi_vb_destory_pool(self->input_pool_id);
        self->input_block = VB_INVALID_HANDLE;
        self->input_pool_id = VB_INVALID_POOLID;
        self->input_phys_addr = 0;
        return -1;
    }

    self->input_block_size = block_size;
    self->input_data_size = data_size;
    return K_SUCCESS;
}

static int mjpeg_venc_pixel_format_supported(k_pixel_format pixel_format)
{
    switch (pixel_format) {
    case PIXEL_FORMAT_ARGB_8888:
    case PIXEL_FORMAT_ABGR_8888:
    case PIXEL_FORMAT_BGRA_8888:
    case PIXEL_FORMAT_BGR_888_PLANAR:
    case PIXEL_FORMAT_RGB_888_PLANAR:
    case PIXEL_FORMAT_YUV_SEMIPLANAR_420:
    case PIXEL_FORMAT_YVU_PLANAR_420:
    case PIXEL_FORMAT_YVU_SEMIPLANAR_420:
    case PIXEL_FORMAT_UYVY_PACKAGE_422:
    case PIXEL_FORMAT_YUYV_PACKAGE_422:
        return 1;
    default:
        return 0;
    }
}

static void mjpeg_validate_dimensions(int width, int height)
{
    if (width <= 0 || height <= 0 || (size_t)width > SIZE_MAX / (size_t)height) {
        mp_raise_ValueError(MP_ERROR_TEXT("invalid image dimensions"));
    }
}

static void mjpeg_prepare_video_frame(mp_obj_t input_obj, mjpeg_input_t* input)
{
    k_vb_blk_handle block;
    int plane_count = 1;

    hal_rvv_memset(input, 0, sizeof(*input));
    if (mp_obj_is_type(input_obj, &py_media_video_frame_info_type)) {
        hal_rvv_memcpy(&input->frame_info, py_video_frame_info_cobj(input_obj), sizeof(input->frame_info));
    } else {
        hal_rvv_memcpy(&input->frame_info.v_frame, py_video_frame_cobj(input_obj),
                       sizeof(input->frame_info.v_frame));
        input->frame_info.pool_id = VB_INVALID_POOLID;
    }

    mjpeg_validate_dimensions(input->frame_info.v_frame.width, input->frame_info.v_frame.height);
    input->pixel_format = input->frame_info.v_frame.pixel_format;
    if (!mjpeg_venc_pixel_format_supported(input->pixel_format)) {
        mp_raise_msg_varg(&mp_type_ValueError, MP_ERROR_TEXT("unsupported video frame pixel format %d"),
                          input->pixel_format);
    }
    if (input->frame_info.v_frame.phys_addr[0] == 0) {
        mp_raise_ValueError(MP_ERROR_TEXT("video frame has no physical address"));
    }
    switch (input->pixel_format) {
    case PIXEL_FORMAT_BGR_888_PLANAR:
    case PIXEL_FORMAT_RGB_888_PLANAR:
    case PIXEL_FORMAT_YVU_PLANAR_420:
        plane_count = 3;
        if (input->frame_info.v_frame.phys_addr[1] == 0 || input->frame_info.v_frame.phys_addr[2] == 0) {
            mp_raise_ValueError(MP_ERROR_TEXT("video frame has missing plane addresses"));
        }
        break;
    case PIXEL_FORMAT_YUV_SEMIPLANAR_420:
    case PIXEL_FORMAT_YVU_SEMIPLANAR_420:
        plane_count = 2;
        if (input->frame_info.v_frame.phys_addr[1] == 0) {
            mp_raise_ValueError(MP_ERROR_TEXT("video frame has a missing chroma plane address"));
        }
        break;
    default:
        break;
    }

    for (int i = 0; i < plane_count; ++i) {
        if (input->frame_info.v_frame.phys_addr[i] & (MJPEG_VPU_PAGE_SIZE - 1)) {
            mp_raise_ValueError(
                MP_ERROR_TEXT("video frame planes must be 4096-byte aligned (use sensor alignment=12)"));
        }
    }

    block = kd_mpi_vb_phyaddr_to_handle(input->frame_info.v_frame.phys_addr[0]);
    if (block == VB_INVALID_HANDLE
        || (input->frame_info.pool_id = kd_mpi_vb_handle_to_pool_id(block)) == VB_INVALID_POOLID) {
        mp_raise_ValueError(MP_ERROR_TEXT("video frame is not backed by a VB pool"));
    }
}

static void mjpeg_prepare_image(image_t* image, mjpeg_input_t* input)
{
    size_t pixel_count;
    size_t source_size;
    size_t required_source_size;

    hal_rvv_memset(input, 0, sizeof(*input));
    mjpeg_validate_dimensions(image->w, image->h);
    if (image->data == NULL) {
        mp_raise_ValueError(MP_ERROR_TEXT("image has no pixel data"));
    }

    pixel_count = (size_t)image->w * image->h;
    source_size = image_size(image);
    input->image = image;
    input->staged = 1;

    switch (image->pixfmt) {
    case PIXFORMAT_BINARY:
        required_source_size = source_size;
        if (pixel_count > SIZE_MAX / 3) {
            mp_raise_ValueError(MP_ERROR_TEXT("image is too large"));
        }
        input->pixel_format = PIXEL_FORMAT_RGB_888_PLANAR;
        input->data_size = pixel_count * 3;
        break;
    case PIXFORMAT_GRAYSCALE:
        required_source_size = pixel_count;
        if (pixel_count > SIZE_MAX / 3) {
            mp_raise_ValueError(MP_ERROR_TEXT("image is too large"));
        }
        input->pixel_format = PIXEL_FORMAT_RGB_888_PLANAR;
        input->data_size = pixel_count * 3;
        break;
    case PIXFORMAT_RGB565:
        required_source_size = pixel_count * 2;
        if (pixel_count > SIZE_MAX / 3) {
            mp_raise_ValueError(MP_ERROR_TEXT("image is too large"));
        }
        input->pixel_format = PIXEL_FORMAT_RGB_888_PLANAR;
        input->data_size = pixel_count * 3;
        break;
    case PIXFORMAT_RGB888:
    case PIXFORMAT_BGR888:
    case PIXFORMAT_RGBP888:
    case PIXFORMAT_BGRP888:
        if (pixel_count > SIZE_MAX / 3) {
            mp_raise_ValueError(MP_ERROR_TEXT("image is too large"));
        }
        required_source_size = pixel_count * 3;
        input->pixel_format = PIXEL_FORMAT_RGB_888_PLANAR;
        input->data_size = pixel_count * 3;
        break;
    case PIXFORMAT_ARGB8888:
        if (pixel_count > SIZE_MAX / 4) {
            mp_raise_ValueError(MP_ERROR_TEXT("image is too large"));
        }
        required_source_size = pixel_count * 4;
        input->pixel_format = PIXEL_FORMAT_BGRA_8888;
        input->data_size = pixel_count * 4;
        break;
    case PIXFORMAT_ABGR8888:
        if (pixel_count > SIZE_MAX / 4) {
            mp_raise_ValueError(MP_ERROR_TEXT("image is too large"));
        }
        required_source_size = pixel_count * 4;
        input->pixel_format = PIXEL_FORMAT_BGRA_8888;
        input->data_size = pixel_count * 4;
        break;
    case PIXFORMAT_RGBA8888:
        if (pixel_count > SIZE_MAX / 4) {
            mp_raise_ValueError(MP_ERROR_TEXT("image is too large"));
        }
        required_source_size = pixel_count * 4;
        input->pixel_format = PIXEL_FORMAT_ABGR_8888;
        input->data_size = pixel_count * 4;
        break;
    case PIXFORMAT_BGRA8888:
        if (pixel_count > SIZE_MAX / 4) {
            mp_raise_ValueError(MP_ERROR_TEXT("image is too large"));
        }
        required_source_size = pixel_count * 4;
        input->pixel_format = PIXEL_FORMAT_ARGB_8888;
        input->data_size = pixel_count * 4;
        break;
    case PIXFORMAT_YUV422:
    case PIXFORMAT_YVU422:
        if (image->w & 1) {
            mp_raise_ValueError(MP_ERROR_TEXT("YUV422 image width must be even"));
        }
        if (pixel_count > SIZE_MAX / 2) {
            mp_raise_ValueError(MP_ERROR_TEXT("image is too large"));
        }
        required_source_size = pixel_count * 2;
        input->pixel_format = PIXEL_FORMAT_YUYV_PACKAGE_422;
        input->data_size = pixel_count * 2;
        break;
    case PIXFORMAT_YUV420:
        if ((image->w & 1) || (image->h & 1)) {
            mp_raise_ValueError(MP_ERROR_TEXT("YUV420 image dimensions must be even"));
        }
        if (pixel_count > SIZE_MAX / 3 * 2) {
            mp_raise_ValueError(MP_ERROR_TEXT("image is too large"));
        }
        required_source_size = pixel_count / 2 * 3;
        input->pixel_format = PIXEL_FORMAT_YUV_SEMIPLANAR_420;
        input->data_size = pixel_count / 2 * 3;
        break;
    case PIXFORMAT_YVU420:
        if ((image->w & 1) || (image->h & 1)) {
            mp_raise_ValueError(MP_ERROR_TEXT("YVU420 image dimensions must be even"));
        }
        if (pixel_count > SIZE_MAX / 3 * 2) {
            mp_raise_ValueError(MP_ERROR_TEXT("image is too large"));
        }
        required_source_size = pixel_count / 2 * 3;
        input->pixel_format = PIXEL_FORMAT_YVU_SEMIPLANAR_420;
        input->data_size = pixel_count / 2 * 3;
        break;
    default:
        mp_raise_msg_varg(&mp_type_ValueError, MP_ERROR_TEXT("unsupported image pixel format %d"), image->pixfmt);
    }

    if (source_size == 0 || source_size < required_source_size) {
        mp_raise_ValueError(MP_ERROR_TEXT("image pixel buffer is too small"));
    }

    // VPU input planes must start on page-aligned physical addresses.
    switch (input->pixel_format) {
    case PIXEL_FORMAT_RGB_888_PLANAR: {
        size_t aligned_plane_size;
        if (pixel_count > SIZE_MAX - (MJPEG_VPU_PAGE_SIZE - 1)) {
            mp_raise_ValueError(MP_ERROR_TEXT("image is too large"));
        }
        aligned_plane_size = VB_ALIGN_UP(pixel_count, MJPEG_VPU_PAGE_SIZE);
        if (aligned_plane_size > (SIZE_MAX - pixel_count) / 2) {
            mp_raise_ValueError(MP_ERROR_TEXT("image is too large"));
        }
        input->plane_offset[1] = aligned_plane_size;
        input->plane_offset[2] = aligned_plane_size * 2;
        input->data_size = input->plane_offset[2] + pixel_count;
        break;
    }
    case PIXEL_FORMAT_YUV_SEMIPLANAR_420:
    case PIXEL_FORMAT_YVU_SEMIPLANAR_420:
        if (pixel_count > SIZE_MAX - (MJPEG_VPU_PAGE_SIZE - 1)) {
            mp_raise_ValueError(MP_ERROR_TEXT("image is too large"));
        }
        input->plane_offset[1] = VB_ALIGN_UP(pixel_count, MJPEG_VPU_PAGE_SIZE);
        if (input->plane_offset[1] > SIZE_MAX - pixel_count / 2) {
            mp_raise_ValueError(MP_ERROR_TEXT("image is too large"));
        }
        input->data_size = input->plane_offset[1] + pixel_count / 2;
        break;
    default:
        break;
    }
}

static void mjpeg_copy_image_to_input(py_media_mjpeg_encoder_obj_t* self, const mjpeg_input_t* input,
                                      k_video_frame_info* frame_info)
{
    image_t* image = input->image;
    size_t pixel_count = (size_t)image->w * image->h;
    uint8_t* dst = self->input_virt_addr;
    const uint8_t* src = image->data;

    switch (image->pixfmt) {
    case PIXFORMAT_BINARY: {
        uint8_t* r = dst;
        uint8_t* g = dst + input->plane_offset[1];
        uint8_t* b = dst + input->plane_offset[2];
        for (int y = 0; y < image->h; ++y) {
            for (int x = 0; x < image->w; ++x) {
                uint8_t value = IMAGE_GET_BINARY_PIXEL(image, x, y) ? 255 : 0;
                size_t offset = (size_t)y * image->w + x;
                r[offset] = value;
                g[offset] = value;
                b[offset] = value;
            }
        }
        break;
    }
    case PIXFORMAT_GRAYSCALE:
        hal_rvv_memcpy(dst, src, pixel_count);
        hal_rvv_memcpy(dst + input->plane_offset[1], src, pixel_count);
        hal_rvv_memcpy(dst + input->plane_offset[2], src, pixel_count);
        break;
    case PIXFORMAT_RGB565: {
        const uint16_t* src16 = (const uint16_t*)src;
        uint8_t* r = dst;
        uint8_t* g = dst + input->plane_offset[1];
        uint8_t* b = dst + input->plane_offset[2];
        for (size_t i = 0; i < pixel_count; ++i) {
            uint16_t pixel = src16[i];
            r[i] = COLOR_RGB565_TO_R8(pixel);
            g[i] = COLOR_RGB565_TO_G8(pixel);
            b[i] = COLOR_RGB565_TO_B8(pixel);
        }
        break;
    }
    case PIXFORMAT_RGB888: {
        uint8_t* r = dst;
        uint8_t* g = dst + input->plane_offset[1];
        uint8_t* b = dst + input->plane_offset[2];
        for (size_t i = 0; i < pixel_count; ++i) {
            r[i] = src[i * 3];
            g[i] = src[i * 3 + 1];
            b[i] = src[i * 3 + 2];
        }
        break;
    }
    case PIXFORMAT_BGR888: {
        uint8_t* r = dst;
        uint8_t* g = dst + input->plane_offset[1];
        uint8_t* b = dst + input->plane_offset[2];
        for (size_t i = 0; i < pixel_count; ++i) {
            r[i] = src[i * 3 + 2];
            g[i] = src[i * 3 + 1];
            b[i] = src[i * 3];
        }
        break;
    }
    case PIXFORMAT_RGBP888:
        hal_rvv_memcpy(dst, src, pixel_count);
        hal_rvv_memcpy(dst + input->plane_offset[1], src + pixel_count, pixel_count);
        hal_rvv_memcpy(dst + input->plane_offset[2], src + pixel_count * 2, pixel_count);
        break;
    case PIXFORMAT_BGRP888:
        hal_rvv_memcpy(dst, src + pixel_count * 2, pixel_count);
        hal_rvv_memcpy(dst + input->plane_offset[1], src + pixel_count, pixel_count);
        hal_rvv_memcpy(dst + input->plane_offset[2], src, pixel_count);
        break;
    case PIXFORMAT_ABGR8888: {
        const uint32_t* src32 = (const uint32_t*)src;
        uint32_t* dst32 = (uint32_t*)dst;
        for (size_t i = 0; i < pixel_count; ++i) {
            uint32_t pixel = src32[i];
            dst32[i] = (pixel & 0xff000000U) | ((pixel & 0x000000ffU) << 16) | (pixel & 0x0000ff00U)
                       | ((pixel & 0x00ff0000U) >> 16);
        }
        break;
    }
    case PIXFORMAT_YUV422:
        for (size_t i = 0; i < pixel_count * 2; i += 4) {
            dst[i] = src[i];
            dst[i + 1] = src[i + 3];
            dst[i + 2] = src[i + 2];
            dst[i + 3] = src[i + 1];
        }
        break;
    case PIXFORMAT_YUV420:
    case PIXFORMAT_YVU420:
        hal_rvv_memcpy(dst, src, pixel_count);
        hal_rvv_memcpy(dst + input->plane_offset[1], src + pixel_count, pixel_count / 2);
        break;
    default:
        hal_rvv_memcpy(dst, src, input->data_size);
        break;
    }

    hal_rvv_memset(frame_info, 0, sizeof(*frame_info));
    frame_info->mod_id = K_ID_VENC;
    frame_info->pool_id = self->input_pool_id;
    frame_info->v_frame.width = image->w;
    frame_info->v_frame.height = image->h;
    frame_info->v_frame.pixel_format = input->pixel_format;
    frame_info->v_frame.phys_addr[0] = self->input_phys_addr;
    frame_info->v_frame.virt_addr[0] = (k_u64)(uintptr_t)self->input_virt_addr;

    switch (input->pixel_format) {
    case PIXEL_FORMAT_RGB_888_PLANAR:
        frame_info->v_frame.stride[0] = image->w;
        frame_info->v_frame.stride[1] = image->w;
        frame_info->v_frame.stride[2] = image->w;
        frame_info->v_frame.phys_addr[1] = self->input_phys_addr + input->plane_offset[1];
        frame_info->v_frame.phys_addr[2] = self->input_phys_addr + input->plane_offset[2];
        frame_info->v_frame.virt_addr[1] = (k_u64)(uintptr_t)(dst + input->plane_offset[1]);
        frame_info->v_frame.virt_addr[2] = (k_u64)(uintptr_t)(dst + input->plane_offset[2]);
        break;
    case PIXEL_FORMAT_YUV_SEMIPLANAR_420:
    case PIXEL_FORMAT_YVU_SEMIPLANAR_420:
        frame_info->v_frame.stride[0] = image->w;
        frame_info->v_frame.stride[1] = image->w;
        frame_info->v_frame.phys_addr[1] = self->input_phys_addr + input->plane_offset[1];
        frame_info->v_frame.virt_addr[1] = (k_u64)(uintptr_t)(dst + input->plane_offset[1]);
        break;
    case PIXEL_FORMAT_YUYV_PACKAGE_422:
        frame_info->v_frame.stride[0] = image->w * 2;
        break;
    default:
        frame_info->v_frame.stride[0] = image->w * 4;
        break;
    }
}

static int mjpeg_encode_frame_locked(py_media_mjpeg_encoder_obj_t* self, k_video_frame_info* frame_info,
                                     int timeout_ms, int staged, vstr_t* output, const char** failed_op)
{
    k_s32 ret;
    k_venc_chn_status status;
    k_venc_stream stream;
    size_t total_size = 0;
    size_t offset = 0;
    int copy_failed = 0;

    if (staged) {
        ret = kd_mpi_sys_mmz_flush_cache(self->input_phys_addr, self->input_virt_addr, self->input_data_size);
        if (ret != K_SUCCESS) {
            *failed_op = "flush VENC input cache";
            return ret;
        }
    }

    ret = kd_mpi_venc_send_frame(self->chn_id, frame_info, timeout_ms);
    if (ret != K_SUCCESS) {
        *failed_op = "send frame to VENC";
        return ret;
    }

    hal_rvv_memset(&status, 0, sizeof(status));
    ret = kd_mpi_venc_query_status(self->chn_id, &status);
    if (ret != K_SUCCESS) {
        *failed_op = "query VENC status";
        return ret;
    }

    hal_rvv_memset(&stream, 0, sizeof(stream));
    stream.pack_cnt = status.cur_packs > 0 ? status.cur_packs : 1;
    if (stream.pack_cnt > MJPEG_MAX_PACKS) {
        *failed_op = "receive VENC packet list";
        return -1;
    }
    hal_rvv_memset(self->packs, 0, sizeof(k_venc_pack) * stream.pack_cnt);
    stream.pack = self->packs;

    ret = kd_mpi_venc_get_stream(self->chn_id, &stream, timeout_ms);
    if (ret != K_SUCCESS) {
        *failed_op = "get VENC stream";
        return ret;
    }

    for (k_u32 i = 0; i < stream.pack_cnt; ++i) {
        if (self->packs[i].len > SIZE_MAX - total_size) {
            copy_failed = 1;
            break;
        }
        total_size += self->packs[i].len;
    }
    if (total_size == 0 || total_size > self->output_block_size) {
        copy_failed = 1;
    }

    if (!copy_failed) {
        for (k_u32 i = 0; i < stream.pack_cnt; ++i) {
            void* pack_data;
            if (self->packs[i].len == 0) {
                continue;
            }
            if (self->packs[i].phys_addr == 0) {
                copy_failed = 1;
                break;
            }
            pack_data = kd_mpi_sys_mmap(self->packs[i].phys_addr, self->packs[i].len);
            if (pack_data == NULL) {
                copy_failed = 1;
                break;
            }
            hal_rvv_memcpy(output->buf + offset, pack_data, self->packs[i].len);
            offset += self->packs[i].len;
            kd_mpi_sys_munmap(pack_data, self->packs[i].len);
        }
    }

    ret = kd_mpi_venc_release_stream(self->chn_id, &stream);
    if (ret != K_SUCCESS) {
        *failed_op = "release VENC stream";
        return ret;
    }
    if (copy_failed) {
        *failed_op = "copy VENC stream";
        return -1;
    }

    output->len = total_size;
    return K_SUCCESS;
}

static mp_obj_t mjpeg_encoder_make_new(const mp_obj_type_t* type, size_t n_args, size_t n_kw, const mp_obj_t* args)
{
    enum { ARG_quality };
    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_quality, MP_ARG_INT, { .u_int = 90 } },
    };
    mp_map_t kw_args;
    mp_arg_val_t parsed_args[MP_ARRAY_SIZE(allowed_args)];
    py_media_mjpeg_encoder_obj_t* self;

    mp_arg_check_num(n_args, n_kw, 0, 1, true);
    mp_map_init_fixed_table(&kw_args, n_kw, args + n_args);
    mp_arg_parse_all(n_args, args, &kw_args, MP_ARRAY_SIZE(allowed_args), allowed_args, parsed_args);

    if (parsed_args[ARG_quality].u_int < 1 || parsed_args[ARG_quality].u_int > 99) {
        mp_raise_ValueError(MP_ERROR_TEXT("quality must be between 1 and 99"));
    }

    self = m_new_obj_with_finaliser(py_media_mjpeg_encoder_obj_t);
    hal_rvv_memset(self, 0, sizeof(*self));
    self->base.type = type;
    self->quality = parsed_args[ARG_quality].u_int;
    self->chn_id = -1;
    self->pixel_format = PIXEL_FORMAT_BUTT;
    self->output_pool_id = VB_INVALID_POOLID;
    self->input_pool_id = VB_INVALID_POOLID;
    self->input_block = VB_INVALID_HANDLE;
    pthread_mutex_init(&self->mutex, NULL);

    return MP_OBJ_FROM_PTR(self);
}

static void mjpeg_encoder_print(const mp_print_t* print, mp_obj_t self_in, mp_print_kind_t kind)
{
    py_media_mjpeg_encoder_obj_t* self = MP_OBJ_TO_PTR(self_in);
    mp_printf(print, "MJPEGEncoder(quality=%d, width=%d, height=%d, closed=%d)", self->quality, self->width,
              self->height, self->closed);
}

static void mjpeg_encoder_attr(mp_obj_t self_in, qstr attr, mp_obj_t* dest)
{
    py_media_mjpeg_encoder_obj_t* self = MP_OBJ_TO_PTR(self_in);

    if (dest[0] == MP_OBJ_NULL) {
        switch (attr) {
        case MP_QSTR_quality:
            dest[0] = mp_obj_new_int(self->quality);
            break;
        case MP_QSTR_width:
            dest[0] = mp_obj_new_int(self->width);
            break;
        case MP_QSTR_height:
            dest[0] = mp_obj_new_int(self->height);
            break;
        case MP_QSTR_chn:
            dest[0] = mp_obj_new_int(self->chn_id);
            break;
        default:
            dest[1] = MP_OBJ_SENTINEL;
            break;
        }
    }
}

static mp_obj_t mjpeg_encoder_encode(mp_uint_t n_args, const mp_obj_t* pos_args, mp_map_t* kw_args)
{
    enum { ARG_input, ARG_timeout_ms };
    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_input, MP_ARG_OBJ | MP_ARG_REQUIRED, { .u_obj = MP_OBJ_NULL } },
        { MP_QSTR_timeout_ms, MP_ARG_INT, { .u_int = 1000 } },
    };
    mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
    py_media_mjpeg_encoder_obj_t* self = MP_OBJ_TO_PTR(pos_args[0]);
    mjpeg_input_t input;
    k_video_frame_info staged_frame;
    k_video_frame_info* frame_info;
    const char* failed_op = NULL;
    int input_width;
    int input_height;
    int ret;
    int cleanup_ret;
    size_t output_block_size;
    vstr_t output;

    mp_arg_parse_all(n_args - 1, pos_args + 1, kw_args, MP_ARRAY_SIZE(allowed_args), allowed_args, args);
    if (args[ARG_timeout_ms].u_int < -1) {
        mp_raise_ValueError(MP_ERROR_TEXT("timeout_ms must be -1 or greater"));
    }

    if (mp_obj_is_type(args[ARG_input].u_obj, &py_media_video_frame_info_type)
        || mp_obj_is_type(args[ARG_input].u_obj, &py_media_video_frame_type)) {
        mjpeg_prepare_video_frame(args[ARG_input].u_obj, &input);
    } else {
        mjpeg_prepare_image((image_t*)py_image_cobj(args[ARG_input].u_obj), &input);
    }

    input_width = input.image ? input.image->w : (int)input.frame_info.v_frame.width;
    input_height = input.image ? input.image->h : (int)input.frame_info.v_frame.height;
    if (mjpeg_output_block_size(input_width, input_height, &output_block_size) != 0) {
        mp_raise_ValueError(MP_ERROR_TEXT("image is too large"));
    }

    // Allocate before taking the object lock because vstr_init may raise MemoryError.
    vstr_init(&output, output_block_size + 1);

    mjpeg_encoder_lock(self);
    if (self->closed) {
        mjpeg_encoder_unlock(self);
        vstr_clear(&output);
        mp_raise_ValueError(MP_ERROR_TEXT("MJPEGEncoder is closed"));
    }

    if (self->chn_id < 0 || self->width != input_width || self->height != input_height
        || self->pixel_format != input.pixel_format) {
        ret = mjpeg_encoder_init_locked(self, input_width, input_height, input.pixel_format, output_block_size,
                                        &failed_op);
        if (ret != K_SUCCESS) {
            mjpeg_encoder_unlock(self);
            vstr_clear(&output);
            mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("MJPEGEncoder failed to %s (%d)"), failed_op,
                              ret < 0 ? ret : (ret & 0x1ff));
        }
    }

    if (input.staged) {
        ret = mjpeg_encoder_ensure_input_buffer_locked(self, input.data_size, &failed_op);
        if (ret != K_SUCCESS) {
            cleanup_ret = mjpeg_encoder_cleanup_locked(self);
            if (cleanup_ret != K_SUCCESS) {
                failed_op = "clean up after input buffer failure";
                ret = cleanup_ret;
            }
            mjpeg_encoder_unlock(self);
            vstr_clear(&output);
            mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("MJPEGEncoder failed to %s (%d)"), failed_op,
                              ret < 0 ? ret : (ret & 0x1ff));
        }
        mjpeg_copy_image_to_input(self, &input, &staged_frame);
        frame_info = &staged_frame;
    } else {
        frame_info = &input.frame_info;
    }

    MP_THREAD_GIL_EXIT();
    ret = mjpeg_encode_frame_locked(self, frame_info, args[ARG_timeout_ms].u_int, input.staged, &output, &failed_op);
    if (ret != K_SUCCESS) {
        cleanup_ret = mjpeg_encoder_cleanup_locked(self);
        if (cleanup_ret != K_SUCCESS) {
            failed_op = "clean up after encode failure";
            ret = cleanup_ret;
        }
    }
    mjpeg_encoder_unlock(self);
    MP_THREAD_GIL_ENTER();

    if (ret != K_SUCCESS) {
        vstr_clear(&output);
        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("MJPEGEncoder failed to %s (%d)"), failed_op,
                          ret < 0 ? ret : (ret & 0x1ff));
    }

    return mp_obj_new_bytes_from_vstr(&output);
}
static MP_DEFINE_CONST_FUN_OBJ_KW(mjpeg_encoder_encode_obj, 2, mjpeg_encoder_encode);

static mp_obj_t mjpeg_encoder_close(mp_obj_t self_in)
{
    py_media_mjpeg_encoder_obj_t* self = MP_OBJ_TO_PTR(self_in);
    k_s32 ret = K_SUCCESS;

    mjpeg_encoder_lock(self);
    if (!self->closed) {
        ret = mjpeg_encoder_cleanup_locked(self);
        if (ret == K_SUCCESS)
            self->closed = 1;
    }
    mjpeg_encoder_unlock(self);

    if (ret != K_SUCCESS) {
        mp_raise_msg_varg(&mp_type_RuntimeError,
                          MP_ERROR_TEXT("MJPEGEncoder cleanup failed (%d)"),
                          ret < 0 ? ret : (ret & 0x1ff));
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(mjpeg_encoder_close_obj, mjpeg_encoder_close);

static mp_obj_t mjpeg_encoder_finalize(mp_obj_t self_in)
{
    py_media_mjpeg_encoder_obj_t* self = MP_OBJ_TO_PTR(self_in);

    mjpeg_encoder_lock(self);
    if (!self->closed) {
        if (mjpeg_encoder_cleanup_locked(self) != K_SUCCESS)
            printf("MJPEGEncoder finalizer could not release all resources\n");
        self->closed = 1;
    }
    mjpeg_encoder_unlock(self);

    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(mjpeg_encoder_finalize_obj, mjpeg_encoder_finalize);

static mp_obj_t mjpeg_encoder_is_closed(mp_obj_t self_in)
{
    py_media_mjpeg_encoder_obj_t* self = MP_OBJ_TO_PTR(self_in);
    return mp_obj_new_bool(self->closed);
}
static MP_DEFINE_CONST_FUN_OBJ_1(mjpeg_encoder_is_closed_obj, mjpeg_encoder_is_closed);

//| # Auto-generated CanMV stub docs. Edit the signatures/docstrings here.
//| module: _media
//| class MJPEGEncoder:
//|     """Hardware MJPEG encoder for image.Image and media video frames."""
//|     def __init__(self, quality: int = 90) -> None:
//|         """Create an encoder. Hardware resources are allocated by the first encode call."""
//|     def close(self) -> None:
//|         """Release the VENC channel and VB pools."""
//|     def encode(self, input: Any, timeout_ms: int = 1000) -> bytes:
//|         """Encode an image.Image, py_video_frame, or py_video_frame_info as one JPEG image."""
//|     def is_closed(self) -> bool:
//|         """Return True after the encoder has been closed."""

static const mp_rom_map_elem_t mjpeg_encoder_locals_dict_table[] = {
    { MP_ROM_QSTR(MP_QSTR___del__), MP_ROM_PTR(&mjpeg_encoder_finalize_obj) },
    { MP_ROM_QSTR(MP_QSTR_close), MP_ROM_PTR(&mjpeg_encoder_close_obj) },
    { MP_ROM_QSTR(MP_QSTR_encode), MP_ROM_PTR(&mjpeg_encoder_encode_obj) },
    { MP_ROM_QSTR(MP_QSTR_is_closed), MP_ROM_PTR(&mjpeg_encoder_is_closed_obj) },
};
static MP_DEFINE_CONST_DICT(mjpeg_encoder_locals_dict, mjpeg_encoder_locals_dict_table);

/* clang-format off */
MP_DEFINE_CONST_OBJ_TYPE(
    py_media_mjpeg_encoder_type,
    MP_QSTR_MJPEGEncoder,
    MP_TYPE_FLAG_NONE,
    make_new, mjpeg_encoder_make_new,
    print, mjpeg_encoder_print,
    attr, mjpeg_encoder_attr,
    locals_dict, &mjpeg_encoder_locals_dict
);
/* clang-format on */
