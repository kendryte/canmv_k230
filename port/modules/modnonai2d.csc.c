/* Copyright (c) 2025, Canaan Bright Sight Co., Ltd
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

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "mpprint.h"
#include "py/obj.h"
#include "py/runtime.h"

#include "imlib.h"
#include "py_assert.h" // use openmv marco, PY_ASSERT_TYPE
#include "py_image.h"

#include "py_modules.h"

#include "mpi_nonai_2d_api.h"
#include "mpi_sys_api.h"
#include "mpi_vb_api.h"

const mp_obj_type_t py_nonai_2d_csc_type;

extern k_u32 calc_video_size(k_pixel_format video_fmt, k_u16 width, k_u16 height);

/**
    from nonai2d import CSC

    # 在MediaManager.init()之前构造
    csc = CSC(chn, fmt, max_width = 1920, max_height = 1080, buf_num = 2)

    img = csc.convert(dump_frame = False)
    frame = csc.convert(dump_frame = True)

    csc.destory()

    PIXEL_FORMAT_RGB_565
    PIXEL_FORMAT_RGB_565_LE
    PIXEL_FORMAT_BGR_565
    PIXEL_FORMAT_BGR_565_LE
    PIXEL_FORMAT_RGB_888
    PIXEL_FORMAT_BGR_888
    PIXEL_FORMAT_ARGB_8888
    PIXEL_FORMAT_ARGB_1555
    PIXEL_FORMAT_ARGB_4444

    PIXEL_FORMAT_BGR_888_PLANAR
    PIXEL_FORMAT_RGB_888_PLANAR

    PIXEL_FORMAT_YVU_PLANAR_420
    PIXEL_FORMAT_YUV_SEMIPLANAR_420
    PIXEL_FORMAT_YVU_SEMIPLANAR_420
    PIXEL_FORMAT_YVU_PLANAR_444
    PIXEL_FORMAT_YUV_PACKAGE_444
    PIXEL_FORMAT_YUV_SEMIPLANAR_444
    PIXEL_FORMAT_YVU_SEMIPLANAR_444
*/

typedef struct _py_nonai_2d_csc {
    /* user configure */
    int            chn;
    k_pixel_format dst_fmt;
    k_u32          dst_max_width;
    k_u32          dst_max_height;
    k_u32          buffer_num;

    /* internal use */
    int stat; /* 0: not enable, 1: enable but not dumped, 2: enable and dumped */
    int cvt_yuv_to_gray;

    k_s32 poolid;

    k_video_frame_info dumped_frame;
    void*              frame_virt_addr;
    k_u64              frame_mmap_size;
} py_nonai_2d_csc_t;

typedef struct _py_nonai_2d_csc_obj {
    mp_obj_base_t     base;
    py_nonai_2d_csc_t _cobj;
} py_nonai_2d_csc_obj_t;

static const k_pixel_format supported_format[] = {
    PIXEL_FORMAT_RGB_565,
    PIXEL_FORMAT_RGB_565_LE,
    PIXEL_FORMAT_BGR_565,
    PIXEL_FORMAT_BGR_565_LE,
    PIXEL_FORMAT_RGB_888,
    PIXEL_FORMAT_BGR_888,
    PIXEL_FORMAT_ARGB_8888,
    PIXEL_FORMAT_ARGB_1555,
    PIXEL_FORMAT_ARGB_4444,
    PIXEL_FORMAT_BGR_888_PLANAR,
    PIXEL_FORMAT_RGB_888_PLANAR,
    PIXEL_FORMAT_YVU_PLANAR_420,
    PIXEL_FORMAT_YUV_SEMIPLANAR_420,
    PIXEL_FORMAT_YVU_SEMIPLANAR_420,
    PIXEL_FORMAT_YVU_PLANAR_444,
    PIXEL_FORMAT_YUV_PACKAGE_444,
    PIXEL_FORMAT_YUV_SEMIPLANAR_444,
    PIXEL_FORMAT_YVU_SEMIPLANAR_444,
};

static int is_valid_format(k_pixel_format format)
{
    for (size_t i = 0; i < sizeof(supported_format) / sizeof(supported_format[0]); i++) {
        if (format == supported_format[i]) {
            return 1;
        }
    }
    return 0;
}

STATIC mp_obj_t py_nonai_2d_csc_from_struct(py_nonai_2d_csc_t* csc)
{
    py_nonai_2d_csc_obj_t* o = m_new_obj_with_finaliser(py_nonai_2d_csc_obj_t);

    o->base.type = &py_nonai_2d_csc_type;

    if (csc) {
        memcpy(&o->_cobj, csc, sizeof(*csc));
    } else {
        memset(&o->_cobj, 0x00, sizeof(*csc));
    }

    return MP_OBJ_FROM_PTR(o);
}

STATIC void* py_nonai_2d_csc_cobj(mp_obj_t self)
{
    PY_ASSERT_TYPE(self, &py_nonai_2d_csc_type);
    return &((py_nonai_2d_csc_obj_t*)self)->_cobj;
}

STATIC mp_obj_t py_nonai_2d_csc_make_new(const mp_obj_type_t* type, size_t n_args, size_t n_kw, const mp_obj_t* args)
{
    /* clang-format off */
    enum {ARG_fmt, ARG_max_width, ARG_max_height, ARG_buf_num, };
    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_fmt,          MP_ARG_INT,                     { .u_int = 0 }      },
        { MP_QSTR_max_width,    MP_ARG_KW_ONLY | MP_ARG_INT,    { .u_int = 1920 }   },
        { MP_QSTR_max_height,   MP_ARG_KW_ONLY | MP_ARG_INT,    { .u_int = 1080 }   },
        { MP_QSTR_buf_num,      MP_ARG_KW_ONLY | MP_ARG_INT,    { .u_int = 2 }      },
    };
    /* clang-format on */
    mp_map_t     kw_args;
    mp_arg_val_t parsed_args[MP_ARRAY_SIZE(allowed_args)];

    mp_arg_check_num(n_args, n_kw, 1, 4, true);
    mp_map_init_fixed_table(&kw_args, n_kw, args + n_args);

    mp_arg_parse_all(n_args, args, &kw_args, MP_ARRAY_SIZE(allowed_args), allowed_args, parsed_args);

    py_nonai_2d_csc_t csc;

    csc.dst_fmt        = parsed_args[ARG_fmt].u_int;
    csc.dst_max_width  = parsed_args[ARG_max_width].u_int;
    csc.dst_max_height = parsed_args[ARG_max_height].u_int;
    csc.buffer_num     = parsed_args[ARG_buf_num].u_int;

    csc.cvt_yuv_to_gray = 0;
    csc.frame_virt_addr = 0;
    csc.frame_mmap_size = 0;

    if ((0x00 == is_valid_format(csc.dst_fmt)) && (PIXFORMAT_GRAYSCALE != (int)csc.dst_fmt)) {
        mp_raise_msg_varg(&mp_type_ValueError, MP_ERROR_TEXT("invalid fmt %d"), csc.dst_fmt);
    }
    if ((PIXFORMAT_GRAYSCALE == (int)csc.dst_fmt)) {
        csc.dst_fmt         = PIXEL_FORMAT_YUV_SEMIPLANAR_420;
        csc.cvt_yuv_to_gray = 1;
    }

    k_u32 csc_chn = UINT32_MAX;
    k_s32 ret = K_SUCCESS, image_size = 0, poolid = VB_INVALID_POOLID;

    if (0x00 != kd_mpi_nonai_2d_request_chn(&csc_chn)) {
        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("request nonai2d channle failed"));
    }
    csc.chn = (int)csc_chn;
    if ((0 > csc.chn) || (K_NONAI_2D_MAX_CHN_NUMS <= csc.chn)) {
        kd_mpi_nonai_2d_release_chn(csc_chn); // maybe not reached.

        mp_raise_msg_varg(&mp_type_ValueError, MP_ERROR_TEXT("invalid chn %d"), csc.chn);
    }

    image_size = VB_ALIGN_UP(calc_video_size(csc.dst_fmt, csc.dst_max_width, csc.dst_max_height), 4096);

    poolid = kd_mpi_vb_create_pool_ex(image_size, csc.buffer_num, VB_REMAP_MODE_NOCACHE);
    if (VB_INVALID_POOLID == poolid) {
        kd_mpi_nonai_2d_release_chn(csc_chn);

        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("create vb pool failed"));
    }

    if (K_SUCCESS != (ret = kd_mpi_nonai_2d_attach_vb_pool(csc.chn, poolid))) {
        kd_mpi_vb_destory_pool(poolid);

        kd_mpi_nonai_2d_release_chn(csc_chn);

        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("attach vb pool failed %d"), ret & 0x1FF);
    }
    csc.poolid = poolid;

    k_nonai_2d_chn_attr nonai2d_attr = { csc.dst_fmt, K_NONAI_2D_CALC_MODE_CSC };

    if (K_SUCCESS != (ret = kd_mpi_nonai_2d_create_chn(csc.chn, &nonai2d_attr))) {
        kd_mpi_vb_destory_pool(poolid);

        kd_mpi_nonai_2d_release_chn(csc_chn);

        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("create chn failed %d"), ret & 0x1FF);
    }

    if (K_SUCCESS != (ret = kd_mpi_nonai_2d_start_chn(csc.chn))) {
        kd_mpi_nonai_2d_destroy_chn(csc_chn);
        kd_mpi_vb_destory_pool(poolid);

        kd_mpi_nonai_2d_release_chn(csc_chn);

        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("start chn failed %d"), ret & 0x1FF);
    }

    csc.stat = 1;

    return py_nonai_2d_csc_from_struct(&csc);
}

STATIC void py_nonai_2d_csc_print(const mp_print_t* print, mp_obj_t self_in, mp_print_kind_t kind)
{
    py_nonai_2d_csc_t* csc = py_nonai_2d_csc_cobj(MP_OBJ_TO_PTR(self_in));

    mp_printf(print, "{\"chn\":%u, \"format\":%u, \"width\"=%u, \"height\"=%u, \"buf_bum\"=%u}", csc->chn, csc->dst_fmt,
              csc->dst_max_width, csc->dst_max_height, csc->buffer_num);
}

STATIC void py_nonai_2d_csc_attr(mp_obj_t self_in, qstr attr, mp_obj_t* dest)
{
    py_nonai_2d_csc_t* csc = py_nonai_2d_csc_cobj(MP_OBJ_TO_PTR(self_in));

    if (MP_OBJ_NULL == dest[0]) {
        // load attribute
        switch (attr) {
        case MP_QSTR_chn:
            dest[0] = mp_obj_new_int(csc->chn);
            break;
        case MP_QSTR_dst_fmt:
            dest[0] = mp_obj_new_int(csc->dst_fmt);
            break;
        case MP_QSTR_stat:
            dest[0] = mp_obj_new_int(csc->stat);
            break;
        default:
            dest[1] = MP_OBJ_SENTINEL; // continue lookup in locals_dict
            break;
        }
    }
}

/* CSC.convert(image_or_frame, timeout_ms = 1000, convert_to_image = 1)*/
STATIC mp_obj_t py_nonai_2d_csc_convert(mp_uint_t n_args, const mp_obj_t* pos_args, mp_map_t* kw_args)
{
    k_s32              ret;
    image_t            image;
    k_video_frame_info info;

    int     timeout_ms       = 1000;
    uint8_t convert_to_image = 1;

    enum { ARG_image, ARG_timeout_ms, ARG_cvt };
    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_image, MP_ARG_OBJ | MP_ARG_REQUIRED, { .u_obj = MP_OBJ_NULL } },
        { MP_QSTR_timeout_ms, MP_ARG_INT, { .u_int = 1000 } },
        { MP_QSTR_cvt, MP_ARG_BOOL, { .u_bool = true } },
    };
    mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all(n_args - 1, pos_args + 1, kw_args, MP_ARRAY_SIZE(allowed_args), allowed_args, args);

    mp_buffer_info_t bufinfo;
    mp_get_buffer_raise(args[ARG_image].u_obj, &bufinfo, MP_BUFFER_READ);
    if (sizeof(k_video_frame_info) != bufinfo.len) {
        mp_raise_msg_varg(&mp_type_TypeError,
                          MP_ERROR_TEXT("CSC.convert only accept py_video_frame_info or k_video_frame_info"));
    }
    memcpy(&info, bufinfo.buf, sizeof(k_video_frame_info));

    timeout_ms       = args[ARG_timeout_ms].u_int;
    convert_to_image = args[ARG_cvt].u_bool;

    py_nonai_2d_csc_t* csc = py_nonai_2d_csc_cobj(MP_OBJ_TO_PTR(pos_args[0]));

    if (0x02 == csc->stat) {
        if (csc->frame_virt_addr && csc->frame_mmap_size) {
            kd_mpi_sys_munmap(csc->frame_virt_addr, csc->frame_mmap_size);

            csc->frame_virt_addr = 0;
            csc->frame_mmap_size = 0;
        }
        kd_mpi_nonai_2d_release_frame(csc->chn, &csc->dumped_frame);
        csc->stat = 0x01;
    }

    if (K_SUCCESS != (ret = kd_mpi_nonai_2d_send_frame(csc->chn, &info, timeout_ms))) {
        if (K_ERR_BUSY == (ret & 0x1FF)) {
            mp_printf(&mp_plat_print, "CSC.convert send_frame timeout\n");
            return mp_const_none;
        }
        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("CSC.convert send_frame failed %d"), ret & 0x1FF);
    }

    if (K_SUCCESS != (ret = kd_mpi_nonai_2d_get_frame(csc->chn, &csc->dumped_frame, timeout_ms))) {
        if (K_ERR_BUF_EMPTY == (ret & 0x1FF)) {
            mp_printf(&mp_plat_print, "CSC.convert get_frame timeout\n");
            return mp_const_none;
        }
        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("CSC.convert get_frame failed %d"), ret & 0x1FF);
    }
    csc->stat            = 0x02;
    csc->frame_virt_addr = 0;
    csc->frame_mmap_size = 0;
    memcpy(&info, &csc->dumped_frame, sizeof(k_video_frame_info));

    if (convert_to_image) {
        image.w = info.v_frame.width;
        image.h = info.v_frame.height;

        if ((PIXEL_FORMAT_YUV_SEMIPLANAR_420 == info.v_frame.pixel_format) && (csc->cvt_yuv_to_gray)) {
            image.pixfmt         = PIXFORMAT_GRAYSCALE;
            csc->frame_mmap_size = image.w * image.h;
        } else {
            switch (info.v_frame.pixel_format) {
            case PIXEL_FORMAT_RGB_565:
            case PIXEL_FORMAT_RGB_565_LE:
            case PIXEL_FORMAT_BGR_565:
            case PIXEL_FORMAT_BGR_565_LE:
                image.pixfmt = PIXFORMAT_RGB565;
                break;
            case PIXEL_FORMAT_RGB_888:
            case PIXEL_FORMAT_BGR_888:
                image.pixfmt = PIXFORMAT_RGB888;
                break;
            case PIXEL_FORMAT_ARGB_8888:
                image.pixfmt = PIXFORMAT_ARGB8888;
                break;
            case PIXEL_FORMAT_RGB_888_PLANAR:
                image.pixfmt = PIXFORMAT_RGBP888;
                break;
            case PIXEL_FORMAT_BGR_888_PLANAR:
                image.pixfmt = PIXFORMAT_BGRP888;
                break;
            case PIXEL_FORMAT_YUV_SEMIPLANAR_420:
                image.pixfmt = PIXFORMAT_YUV420;
                break;
            case PIXEL_FORMAT_YVU_SEMIPLANAR_420:
                image.pixfmt = PIXFORMAT_YVU420;
                break;
            default:
                image.pixfmt = PIXFORMAT_INVALID;
                break;
            }

            csc->frame_mmap_size = (calc_video_size(info.v_frame.pixel_format, image.w, image.h) + 0x2FFF) & ~0x2FFF;
        }

        csc->frame_virt_addr = (k_u64)kd_mpi_sys_mmap_cached(info.v_frame.phys_addr[0], csc->frame_mmap_size);
        if (0x00 == csc->frame_virt_addr) {
            mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("CSC.convert mmap failed"));
        }

        if ((PIXEL_FORMAT_BGR_888_PLANAR == info.v_frame.pixel_format)
            || (PIXEL_FORMAT_RGB_888_PLANAR == info.v_frame.pixel_format)) {
            k_u32 size = image.w * image.h;

            if ((info.v_frame.phys_addr[0] + size) != info.v_frame.phys_addr[1]) {
                memmove(csc->frame_virt_addr + size,
                        csc->frame_virt_addr + (info.v_frame.phys_addr[1] - info.v_frame.phys_addr[0]), size);
            }

            if ((info.v_frame.phys_addr[0] + size * 2) != info.v_frame.phys_addr[2]) {
                memmove(csc->frame_virt_addr + size * 2,
                        csc->frame_virt_addr + (info.v_frame.phys_addr[2] - info.v_frame.phys_addr[0]), size);
            }
        }

        image.alloc_type = ALLOC_VB;
        image.size       = csc->frame_mmap_size;
        image.data       = csc->frame_virt_addr;

        return py_image_from_struct(&image);
    } else {
        return py_video_frame_info_from_struct(&csc->dumped_frame);
    }
}
STATIC MP_DEFINE_CONST_FUN_OBJ_KW(py_nonai_2d_csc_convert_obj, 2, py_nonai_2d_csc_convert);

/* CSC.convert(image_or_frame, timeout_ms = 1000, convert_to_image = 1)*/
STATIC mp_obj_t py_nonai_2d_csc_getframe(mp_uint_t n_args, const mp_obj_t* pos_args, mp_map_t* kw_args)
{
    k_s32              ret;
    image_t            image;
    k_video_frame_info info;

    int timeout_ms = 1000;

    enum { ARG_timeout_ms };
    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_timeout_ms, MP_ARG_INT, { .u_int = 1000 } },
    };
    mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all(n_args - 1, pos_args + 1, kw_args, MP_ARRAY_SIZE(allowed_args), allowed_args, args);

    py_nonai_2d_csc_t* csc = py_nonai_2d_csc_cobj(MP_OBJ_TO_PTR(pos_args[0]));

    timeout_ms = args[ARG_timeout_ms].u_int;

    if (0x02 == csc->stat) {
        if (csc->frame_virt_addr && csc->frame_mmap_size) {
            kd_mpi_sys_munmap(csc->frame_virt_addr, csc->frame_mmap_size);

            csc->frame_virt_addr = 0;
            csc->frame_mmap_size = 0;
        }
        kd_mpi_nonai_2d_release_frame(csc->chn, &csc->dumped_frame);
        csc->stat = 0x01;
    }

    if (K_SUCCESS != (ret = kd_mpi_nonai_2d_get_frame(csc->chn, &csc->dumped_frame, timeout_ms))) {
        mp_printf(&mp_plat_print, "CSC.getframe get_frame ret %d\n", ret & 0x1FF);
        if (K_ERR_BUF_EMPTY == (ret & 0x1FF)) {
            mp_printf(&mp_plat_print, "CSC.getframe get_frame timeout\n");
            return mp_const_none;
        }
        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("CSC.getframe get_frame failed %d"), ret & 0x1FF);
    }
    csc->stat            = 0x02;
    csc->frame_virt_addr = 0;
    csc->frame_mmap_size = 0;
    memcpy(&info, &csc->dumped_frame, sizeof(k_video_frame_info));

    image.w = info.v_frame.width;
    image.h = info.v_frame.height;

    if ((PIXEL_FORMAT_YUV_SEMIPLANAR_420 == info.v_frame.pixel_format) && (csc->cvt_yuv_to_gray)) {
        image.pixfmt         = PIXFORMAT_GRAYSCALE;
        csc->frame_mmap_size = image.w * image.h;
    } else {
        switch (info.v_frame.pixel_format) {
        case PIXEL_FORMAT_RGB_565:
        case PIXEL_FORMAT_RGB_565_LE:
        case PIXEL_FORMAT_BGR_565:
        case PIXEL_FORMAT_BGR_565_LE:
            image.pixfmt = PIXFORMAT_RGB565;
            break;
        case PIXEL_FORMAT_RGB_888:
        case PIXEL_FORMAT_BGR_888:
            image.pixfmt = PIXFORMAT_RGB888;
            break;
        case PIXEL_FORMAT_ARGB_8888:
            image.pixfmt = PIXFORMAT_ARGB8888;
            break;
        case PIXEL_FORMAT_RGB_888_PLANAR:
            image.pixfmt = PIXFORMAT_RGBP888;
            break;
        case PIXEL_FORMAT_BGR_888_PLANAR:
            image.pixfmt = PIXFORMAT_BGRP888;
            break;
        case PIXEL_FORMAT_YUV_SEMIPLANAR_420:
            image.pixfmt = PIXFORMAT_YUV420;
            break;
        case PIXEL_FORMAT_YVU_SEMIPLANAR_420:
            image.pixfmt = PIXFORMAT_YVU420;
            break;
        default:
            image.pixfmt = PIXFORMAT_INVALID;
            break;
        }

        csc->frame_mmap_size = (calc_video_size(info.v_frame.pixel_format, image.w, image.h) + 0x2FFF) & ~0x2FFF;
    }

    csc->frame_virt_addr = (k_u64)kd_mpi_sys_mmap_cached(info.v_frame.phys_addr[0], csc->frame_mmap_size);
    if (0x00 == csc->frame_virt_addr) {
        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("CSC.convert mmap failed"));
    }

    if ((PIXEL_FORMAT_BGR_888_PLANAR == info.v_frame.pixel_format)
        || (PIXEL_FORMAT_RGB_888_PLANAR == info.v_frame.pixel_format)) {

        k_u32 size = image.w * image.h;

        if ((info.v_frame.phys_addr[0] + size) != info.v_frame.phys_addr[1]) {
            memmove(csc->frame_virt_addr + size, csc->frame_virt_addr + (info.v_frame.phys_addr[1] - info.v_frame.phys_addr[0]),
                    size);
        }

        if ((info.v_frame.phys_addr[0] + size * 2) != info.v_frame.phys_addr[2]) {
            memmove(csc->frame_virt_addr + size * 2,
                    csc->frame_virt_addr + (info.v_frame.phys_addr[2] - info.v_frame.phys_addr[0]), size);
        }
    }

    image.alloc_type = ALLOC_VB;
    image.size       = csc->frame_mmap_size;
    image.data       = csc->frame_virt_addr;

    return py_image_from_struct(&image);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_KW(py_nonai_2d_csc_getframe_obj, 0, py_nonai_2d_csc_getframe);

STATIC mp_obj_t py_nonai_2d_csc_destroy(mp_obj_t self_in)
{
    py_nonai_2d_csc_t* csc = py_nonai_2d_csc_cobj(MP_OBJ_TO_PTR(self_in));

    if (csc->stat) {
        if (0x02 == csc->stat) {
            if (csc->frame_virt_addr && csc->frame_mmap_size) {
                kd_mpi_sys_munmap(csc->frame_virt_addr, csc->frame_mmap_size);
                csc->frame_virt_addr = NULL;
                csc->frame_mmap_size = 0;
            }

            kd_mpi_nonai_2d_release_frame(csc->chn, &csc->dumped_frame);
        }

        kd_mpi_nonai_2d_stop_chn(csc->chn);
        kd_mpi_nonai_2d_destroy_chn(csc->chn);

        kd_mpi_nonai_2d_detach_vb_pool(csc->chn);

        if (VB_INVALID_POOLID != csc->poolid) {
            kd_mpi_vb_destory_pool(csc->poolid);
        }
        csc->poolid = VB_INVALID_POOLID;

        csc->stat = 0;

        kd_mpi_nonai_2d_release_chn((k_u32)csc->chn);
        csc->chn = -1;

        // kd_mpi_nonai_2d_close();
    }

    return mp_const_none;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_1(py_nonai_2d_csc_destroy_obj, py_nonai_2d_csc_destroy);

STATIC const mp_rom_map_elem_t py_nonai_2d_csc_locals_dict_table[] = {
    { MP_ROM_QSTR(MP_QSTR___del__), MP_ROM_PTR(&py_nonai_2d_csc_destroy_obj) },

    { MP_ROM_QSTR(MP_QSTR_convert), MP_ROM_PTR(&py_nonai_2d_csc_convert_obj) },
    { MP_ROM_QSTR(MP_QSTR_getframe), MP_ROM_PTR(&py_nonai_2d_csc_getframe_obj) },
    { MP_ROM_QSTR(MP_QSTR_destroy), MP_ROM_PTR(&py_nonai_2d_csc_destroy_obj) },

    // const
    { MP_ROM_QSTR(MP_QSTR_PIXEL_FORMAT_GRAYSCALE), MP_ROM_INT(PIXFORMAT_GRAYSCALE) },

    { MP_ROM_QSTR(MP_QSTR_PIXEL_FORMAT_RGB_565), MP_ROM_INT(PIXEL_FORMAT_RGB_565) },
    { MP_ROM_QSTR(MP_QSTR_PIXEL_FORMAT_RGB_565_LE), MP_ROM_INT(PIXEL_FORMAT_RGB_565_LE) },

    { MP_ROM_QSTR(MP_QSTR_PIXEL_FORMAT_BGR_565), MP_ROM_INT(PIXEL_FORMAT_BGR_565) },
    { MP_ROM_QSTR(MP_QSTR_PIXEL_FORMAT_BGR_565_LE), MP_ROM_INT(PIXEL_FORMAT_BGR_565_LE) },

    { MP_ROM_QSTR(MP_QSTR_PIXEL_FORMAT_RGB_888), MP_ROM_INT(PIXEL_FORMAT_RGB_888) },
    { MP_ROM_QSTR(MP_QSTR_PIXEL_FORMAT_BGR_888), MP_ROM_INT(PIXEL_FORMAT_BGR_888) },

    { MP_ROM_QSTR(MP_QSTR_PIXEL_FORMAT_ARGB_8888), MP_ROM_INT(PIXEL_FORMAT_ARGB_8888) },
    { MP_ROM_QSTR(MP_QSTR_PIXEL_FORMAT_ARGB_1555), MP_ROM_INT(PIXEL_FORMAT_ARGB_1555) },
    { MP_ROM_QSTR(MP_QSTR_PIXEL_FORMAT_ARGB_4444), MP_ROM_INT(PIXEL_FORMAT_ARGB_4444) },

    { MP_ROM_QSTR(MP_QSTR_PIXEL_FORMAT_BGR_888_PLANAR), MP_ROM_INT(PIXEL_FORMAT_BGR_888_PLANAR) },
    { MP_ROM_QSTR(MP_QSTR_PIXEL_FORMAT_RGB_888_PLANAR), MP_ROM_INT(PIXEL_FORMAT_RGB_888_PLANAR) },

    { MP_ROM_QSTR(MP_QSTR_PIXEL_FORMAT_YVU_PLANAR_420), MP_ROM_INT(PIXEL_FORMAT_YVU_PLANAR_420) },
    { MP_ROM_QSTR(MP_QSTR_PIXEL_FORMAT_YUV_SEMIPLANAR_420), MP_ROM_INT(PIXEL_FORMAT_YUV_SEMIPLANAR_420) },
    { MP_ROM_QSTR(MP_QSTR_PIXEL_FORMAT_YVU_SEMIPLANAR_420), MP_ROM_INT(PIXEL_FORMAT_YVU_SEMIPLANAR_420) },

    { MP_ROM_QSTR(MP_QSTR_PIXEL_FORMAT_YVU_PLANAR_444), MP_ROM_INT(PIXEL_FORMAT_YVU_PLANAR_444) },
    { MP_ROM_QSTR(MP_QSTR_PIXEL_FORMAT_YUV_PACKAGE_444), MP_ROM_INT(PIXEL_FORMAT_YUV_PACKAGE_444) },
    { MP_ROM_QSTR(MP_QSTR_PIXEL_FORMAT_YUV_SEMIPLANAR_444), MP_ROM_INT(PIXEL_FORMAT_YUV_SEMIPLANAR_444) },
    { MP_ROM_QSTR(MP_QSTR_PIXEL_FORMAT_YVU_SEMIPLANAR_444), MP_ROM_INT(PIXEL_FORMAT_YVU_SEMIPLANAR_444) },
};
STATIC MP_DEFINE_CONST_DICT(py_nonai_2d_csc_locals_dict, py_nonai_2d_csc_locals_dict_table);

/* clang-format off */
MP_DEFINE_CONST_OBJ_TYPE(
    py_nonai_2d_csc_type,
    MP_QSTR_py_nonai_2d_csc,
    MP_TYPE_FLAG_NONE,
    make_new, py_nonai_2d_csc_make_new,
    print, py_nonai_2d_csc_print,
    attr, py_nonai_2d_csc_attr,
    locals_dict, &py_nonai_2d_csc_locals_dict
);
/* clang-format on */
