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

#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <sys/ioctl.h>
#include <unistd.h>

#include "py/binary.h"
#include "py/obj.h"
#include "py/runtime.h"

#include "py_assert.h" // use openmv marco, PY_ASSERT_TYPE
#include "py_image.h"

#include "mpi_sys_api.h"
#include "mpi_vb_api.h"
#include "mpprint.h"
#include "py_modules.h"

k_u32 calc_video_size(k_pixel_format video_fmt, k_u16 width, k_u16 height)
{
    k_u32 size = 0;
    switch (video_fmt) {
    case PIXEL_FORMAT_YUV_SEMIPLANAR_420:
    case PIXEL_FORMAT_YVU_SEMIPLANAR_420:
    case PIXEL_FORMAT_YVU_PLANAR_420:
        size = width * height * 3 / 2;
        break;

    case PIXEL_FORMAT_RGB_888:
    case PIXEL_FORMAT_BGR_888:
    case PIXEL_FORMAT_YUV_PACKAGE_444:
    case PIXEL_FORMAT_BGR_888_PLANAR:
    case PIXEL_FORMAT_RGB_888_PLANAR:
    case PIXEL_FORMAT_YVU_PLANAR_444:
        size = width * height * 3;
        break;

    case PIXEL_FORMAT_RGB_565:
    case PIXEL_FORMAT_BGR_565:
    case PIXEL_FORMAT_RGB_565_LE:
    case PIXEL_FORMAT_BGR_565_LE:
    case PIXEL_FORMAT_ARGB_1555:
    case PIXEL_FORMAT_ARGB_4444:
    case PIXEL_FORMAT_ABGR_1555:
    case PIXEL_FORMAT_ABGR_4444:
        size = width * height * 2;
        break;

    case PIXEL_FORMAT_ABGR_8888:
    case PIXEL_FORMAT_BGRA_8888:
        size = width * height * 4;
        break;

    default:
        printf("%s>unknown data type %d\n", __func__, video_fmt);
        return 0;
    }

    return size;
}

/* k_video_frame *************************************************************/
typedef struct py_video_frame_obj {
    mp_obj_base_t base;
    k_video_frame _cobj;

    // used with to_image
    void* frame_vaddr;
    k_u64 frame_size;
} py_video_frame_obj_t;

mp_obj_t py_video_frame_from_struct(k_video_frame* frame)
{
    py_video_frame_obj_t* o = m_new_obj(py_video_frame_obj_t);

    o->base.type = &py_media_video_frame_type;

    if (frame) {
        memcpy(&o->_cobj, frame, sizeof(*frame));
    } else {
        memset(&o->_cobj, 0x00, sizeof(*frame));
    }

    o->frame_size  = 0;
    o->frame_vaddr = NULL;

    return MP_OBJ_FROM_PTR(o);
}

void* py_video_frame_cobj(mp_obj_t frame_obj)
{
    PY_ASSERT_TYPE(frame_obj, &py_media_video_frame_type);

    return &((py_video_frame_obj_t*)frame_obj)->_cobj;
}

void py_video_frame_destory(mp_obj_t frame_obj)
{
    PY_ASSERT_TYPE(frame_obj, &py_media_video_frame_type);
    py_video_frame_obj_t* self = MP_OBJ_TO_PTR(frame_obj);

    if (self->frame_vaddr && self->frame_size) {
        kd_mpi_sys_munmap(self->frame_vaddr, self->frame_size);

        self->frame_vaddr = 0;
        self->frame_size  = 0;
    }
}

STATIC mp_obj_t py_video_frame_make_new(const mp_obj_type_t* type, size_t n_args, size_t n_kw, const mp_obj_t* args)
{
    mp_buffer_info_t bufinfo;

    mp_arg_check_num(n_args, n_kw, 1, 1, false);

    mp_get_buffer_raise(args[0], &bufinfo, MP_BUFFER_READ);

    if (sizeof(k_video_frame) != bufinfo.len) {
        mp_raise_msg_varg(&mp_type_TypeError, MP_ERROR_TEXT("expect size: %u, actual size: %u"), sizeof(k_video_frame),
                          bufinfo.len);
    }

    return py_video_frame_from_struct(bufinfo.buf);
}

STATIC void py_video_frame_print(const mp_print_t* print, mp_obj_t self_in, mp_print_kind_t kind)
{
    py_video_frame_obj_t* self  = MP_OBJ_TO_PTR(self_in);
    k_video_frame*        frame = py_video_frame_cobj(self);

    mp_printf(print,
              "\"video_frame\":{\"width\"=%u, \"height\"=%u, \"pixel_format\"=%u, \"phys_addr\"=(0x%08X, 0x%08X, "
              "0x%08X), \"virt_addr\"=(0x%08X, 0x%08X, 0x%08X), \"pts\"=%u}",
              frame->width, frame->height, frame->pixel_format, frame->phys_addr[0], frame->phys_addr[1], frame->phys_addr[2],
              frame->virt_addr[0], frame->virt_addr[1], frame->virt_addr[2], frame->pts);
}

STATIC void py_video_frame_attr(mp_obj_t self_in, qstr attr, mp_obj_t* dest)
{
    py_video_frame_obj_t* self  = MP_OBJ_TO_PTR(self_in);
    k_video_frame*        frame = py_video_frame_cobj(self);

    if (MP_OBJ_NULL == dest[0]) {
        // load attribute
        switch (attr) {
        case MP_QSTR_width:
            dest[0] = mp_obj_new_int(frame->width);
            break;
        case MP_QSTR_height:
            dest[0] = mp_obj_new_int(frame->height);
            break;
        case MP_QSTR_pixel_format:
            dest[0] = mp_obj_new_int(frame->pixel_format);
            break;
        case MP_QSTR_phys_addr:
            dest[0] = mp_obj_new_list(3,
                                      (mp_obj_t[]) { mp_obj_new_int_from_uint(frame->phys_addr[0]),
                                                     mp_obj_new_int_from_uint(frame->phys_addr[1]),
                                                     mp_obj_new_int_from_uint(frame->phys_addr[2]) });
            break;
        case MP_QSTR_virt_addr:
            dest[0] = mp_obj_new_list(3,
                                      (mp_obj_t[]) { mp_obj_new_int_from_uint(frame->virt_addr[0]),
                                                     mp_obj_new_int_from_uint(frame->virt_addr[1]),
                                                     mp_obj_new_int_from_uint(frame->virt_addr[2]) });
            break;
        case MP_QSTR_pts:
            dest[0] = mp_obj_new_int(frame->pts);
            break;
        default:
            dest[1] = MP_OBJ_SENTINEL; // continue lookup in locals_dict
            break;
        }
    }
}

STATIC mp_int_t py_video_frame_buffer(mp_obj_t self_in, mp_buffer_info_t* bufinfo, mp_uint_t flags)
{
    py_video_frame_obj_t* self  = MP_OBJ_TO_PTR(self_in);
    k_video_frame*        frame = py_video_frame_cobj(self);

    bufinfo->buf      = frame;
    bufinfo->len      = sizeof(*frame);
    bufinfo->typecode = BYTEARRAY_TYPECODE;

    return 0;
}

// int video_frame_to_image(k_video_frame *video_frame, image_t *image, void *frame_vaddr, k_u64 *frame_size) {

//}

STATIC mp_obj_t py_video_frame_to_image(mp_uint_t n_args, const mp_obj_t* pos_args, mp_map_t* kw_args)
{
    image_t               image;
    py_video_frame_obj_t* self        = MP_OBJ_TO_PTR(pos_args[0]);
    k_video_frame*        frame       = py_video_frame_cobj(self);
    bool                  yuv_to_gray = false;

    enum { ARG_yuv_to_gray };
    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_yuv_to_gray, MP_ARG_BOOL, { .u_bool = false } },
    };
    mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all(n_args - 1, pos_args + 1, kw_args, MP_ARRAY_SIZE(allowed_args), allowed_args, args);
    yuv_to_gray = args[ARG_yuv_to_gray].u_bool;

    image.w = frame->width;
    image.h = frame->height;

    k_u32 size = image.w * image.h;
    if ((PIXEL_FORMAT_YUV_SEMIPLANAR_420 == frame->pixel_format) && (yuv_to_gray)) {
        image.pixfmt     = PIXFORMAT_GRAYSCALE;
        self->frame_size = size;
    } else {
        switch (frame->pixel_format) {
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

        self->frame_size = (calc_video_size(frame->pixel_format, image.w, image.h) + 0x2FFF) & ~0x2FFF;
    }

    if (0x00 == (self->frame_vaddr = (k_u64)kd_mpi_sys_mmap_cached(frame->phys_addr[0], self->frame_size))) {
        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("py_video_frame_to_image mmap failed"));
    }

    if ((PIXEL_FORMAT_BGR_888_PLANAR == frame->pixel_format) || (PIXEL_FORMAT_RGB_888_PLANAR == frame->pixel_format)) {
        if ((frame->phys_addr[0] + self->frame_size) != frame->phys_addr[1]) {
            memmove(self->frame_vaddr + size, self->frame_vaddr + (frame->phys_addr[1] - frame->phys_addr[0]), size);
        }
        if ((frame->phys_addr[0] + size * 2) != frame->phys_addr[2]) {
            memmove(self->frame_vaddr + size * 2, self->frame_vaddr + (frame->phys_addr[2] - frame->phys_addr[0]), size);
        }
    }

    image.alloc_type = ALLOC_VB;
    image.size       = self->frame_size;
    image.data       = self->frame_vaddr;

    return py_image_from_struct(&image);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_KW(py_video_frame_to_image_obj, 0, py_video_frame_to_image);

STATIC mp_obj_t py_video_frame_destroy(mp_obj_t self_in)
{
    py_video_frame_destory(self_in);

    return mp_const_none;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_1(py_video_frame_destroy_obj, py_video_frame_destroy);

STATIC mp_obj_t py_video_frame_release(mp_obj_t self_in) { return py_video_frame_destroy(self_in); }
STATIC          MP_DEFINE_CONST_FUN_OBJ_1(py_video_frame_release_obj, py_video_frame_release);

STATIC const mp_rom_map_elem_t py_video_frame_locals_dict_table[] = {
    { MP_ROM_QSTR(MP_QSTR___del__), MP_ROM_PTR(&py_video_frame_destroy_obj) },

    { MP_ROM_QSTR(MP_QSTR_to_image), MP_ROM_PTR(&py_video_frame_to_image_obj) },
    { MP_ROM_QSTR(MP_QSTR_release), MP_ROM_PTR(&py_video_frame_release_obj) },
};
STATIC MP_DEFINE_CONST_DICT(py_video_frame_locals_dict, py_video_frame_locals_dict_table);

/* clang-format off */
MP_DEFINE_CONST_OBJ_TYPE(
    py_media_video_frame_type,
    MP_QSTR_py_video_frame,
    MP_TYPE_FLAG_NONE,
    make_new, py_video_frame_make_new,
    print, py_video_frame_print,
    attr, py_video_frame_attr,
    buffer, py_video_frame_buffer,
    locals_dict, &py_video_frame_locals_dict
);
/* clang-format on */

/* k_video_frame_info ********************************************************/
typedef struct py_video_frame_info_obj {
    mp_obj_base_t      base;
    k_video_frame_info _cobj;
    mp_obj_t           _frame_obj;
} py_video_frame_info_obj_t;

mp_obj_t py_video_frame_info_from_struct(k_video_frame_info* info)
{
    py_video_frame_info_obj_t* o = m_new_obj(py_video_frame_info_obj_t);

    o->base.type = &py_media_video_frame_info_type;

    if (info) {
        memcpy(&o->_cobj, info, sizeof(*info));
    } else {
        memset(&o->_cobj, 0x00, sizeof(*info));
    }

    o->_frame_obj = mp_const_none;

    return MP_OBJ_FROM_PTR(o);
}

void* py_video_frame_info_cobj(mp_obj_t info_obj)
{
    PY_ASSERT_TYPE(info_obj, &py_media_video_frame_info_type);

    return &((py_video_frame_info_obj_t*)info_obj)->_cobj;
}

void py_video_frame_info_destory(mp_obj_t info_obj)
{
    PY_ASSERT_TYPE(info_obj, &py_media_video_frame_info_type);

    py_video_frame_info_obj_t* self = MP_OBJ_TO_PTR(info_obj);

    if (mp_const_none != self->_frame_obj) {
        py_video_frame_destory(self->_frame_obj);

        self->_frame_obj = mp_const_none;
    }
}


STATIC mp_obj_t py_video_frame_info_make_new(const mp_obj_type_t* type, size_t n_args, size_t n_kw, const mp_obj_t* args)
{
    mp_buffer_info_t bufinfo;

    mp_arg_check_num(n_args, n_kw, 1, 1, false);

    mp_get_buffer_raise(args[0], &bufinfo, MP_BUFFER_READ);

    if (sizeof(k_video_frame_info) != bufinfo.len) {
        mp_raise_msg_varg(&mp_type_TypeError, MP_ERROR_TEXT("expect size: %u, actual size: %u"), sizeof(k_video_frame_info),
                          bufinfo.len);
    }

    return py_video_frame_info_from_struct(bufinfo.buf);
}

STATIC void py_video_frame_info_print(const mp_print_t* print, mp_obj_t self_in, mp_print_kind_t kind)
{
    py_video_frame_info_obj_t* self = MP_OBJ_TO_PTR(self_in);
    k_video_frame_info*        info = py_video_frame_info_cobj(self);

    mp_printf(print, "\"video_frame_info\":{\"mod_id\"=%u, \"pool_id\"=%u, \"frame\"=", info->mod_id, info->pool_id);

    if (mp_const_none != self->_frame_obj) {
        mp_obj_print_helper(print, self->_frame_obj, PRINT_REPR);
    } else {
        mp_printf(print, "{null}");
    }

    mp_printf(print, "}\n");
}

STATIC void py_video_frame_info_attr(mp_obj_t self_in, qstr attr, mp_obj_t* dest)
{
    py_video_frame_info_obj_t* self = MP_OBJ_TO_PTR(self_in);
    k_video_frame_info*        info = py_video_frame_info_cobj(self);

    if (MP_OBJ_NULL == dest[0]) {
        // load attribute
        switch (attr) {
        case MP_QSTR_mod_id:
            dest[0] = mp_obj_new_int(info->mod_id);
            break;
        case MP_QSTR_pool_id:
            dest[0] = mp_obj_new_int(info->pool_id);
            break;
        case MP_QSTR_v_frame:
            if (mp_const_none != self->_frame_obj) {
                dest[0] = self->_frame_obj;
            } else {
                dest[0] = py_video_frame_from_struct(&info->v_frame);

                self->_frame_obj = dest[0];
            }
            break;
        default:
            dest[1] = MP_OBJ_SENTINEL; // continue lookup in locals_dict
            break;
        }
    }
}

STATIC mp_int_t py_video_frame_info_buffer(mp_obj_t self_in, mp_buffer_info_t* bufinfo, mp_uint_t flags)
{
    py_video_frame_info_obj_t* self = MP_OBJ_TO_PTR(self_in);
    k_video_frame_info*        info = py_video_frame_info_cobj(self);

    bufinfo->buf      = info;
    bufinfo->len      = sizeof(*info);
    bufinfo->typecode = BYTEARRAY_TYPECODE;

    return 0;
}

/* clang-format off */
MP_DEFINE_CONST_OBJ_TYPE(
    py_media_video_frame_info_type,
    MP_QSTR_py_video_frame_info,
    MP_TYPE_FLAG_NONE,
    make_new, py_video_frame_info_make_new,
    print, py_video_frame_info_print,
    attr, py_video_frame_info_attr,
    buffer, py_video_frame_info_buffer
);
/* clang-format on */
