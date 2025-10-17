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

#include "generated/autoconf.h"

#if defined(CONFIG_ENABLE_UVC_CAMERA)

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <sys/ioctl.h>
#include <unistd.h>

#include "py/obj.h"
#include "py/runtime.h"

#include "py_assert.h" // use openmv marco, PY_ASSERT_TYPE
#include "py_image.h"

#include "mpprint.h"

#include "py_modules.h"

#include "mpi_uvc_api.h"

/* hard jpeg decode **********************************************************/
#include <mpi_uvc_api.h>
#include <mpi_vb_api.h>
#include <mpi_vdec_api.h>

#define ALIGN_UP(x, align)            (((x) + ((align) - 1)) & ~((align) - 1))
#define HARD_JPEG_VDEC_OUTPUT_BUF_CNT (4)

static int                hard_jpeg_decoder_enabled      = 0;
static k_s32              hard_jpeg_decoder_vb_pool_id   = VB_INVALID_POOLID;
static k_u32              hard_jpeg_decoder_vdev_chn     = UINT32_MAX;
static k_vdec_chn_attr    hard_jpeg_decoder_attr         = { 0 };
static k_u32              hard_jpeg_decoder_frame_dumped = 0;
static k_video_frame_info hard_jpeg_decoder_dumped_frame;

static k_s32 vb_create_vdec_pool(int width, int height)
{
    k_vb_pool_config pool_config;

    memset(&pool_config, 0, sizeof(pool_config));
    pool_config.blk_cnt  = HARD_JPEG_VDEC_OUTPUT_BUF_CNT;
    pool_config.blk_size = ALIGN_UP(width * height, 0x1000) * 2;
    pool_config.mode     = VB_REMAP_MODE_NOCACHE;

    return kd_mpi_vb_create_pool(&pool_config);
}

static k_s32 vb_destroy_vdec_pool(k_s32 vdec_poolid) { return kd_mpi_vb_destory_pool(vdec_poolid); }

static int hard_jpeg_decompress_start(struct uvc_format* fmt)
{
    int   ret  = 0;
    k_u32 _chn = UINT32_MAX;

    hard_jpeg_decoder_enabled = 0;

    if (0x00 != kd_mpi_vdec_request_chn(&_chn)) {
        printf("failed to request vdec channel\n");

        ret = 1;
        goto _error1;
    }
    hard_jpeg_decoder_vdev_chn = _chn;

    hard_jpeg_decoder_vb_pool_id = vb_create_vdec_pool(fmt->width, fmt->height);
    if (VB_INVALID_POOLID == hard_jpeg_decoder_vb_pool_id) {
        printf("fail to create vdec pool\n");

        ret = 2;
        goto _error2;
    }

    if (K_SUCCESS != kd_mpi_vdec_attach_vb_pool(hard_jpeg_decoder_vdev_chn, hard_jpeg_decoder_vb_pool_id)) {
        printf("failed to attach vdec pool\n");

        ret = 3;
        goto _error3;
    }

    memset(&hard_jpeg_decoder_attr, 0x00, sizeof(hard_jpeg_decoder_attr));

    hard_jpeg_decoder_attr.type            = K_PT_JPEG;
    hard_jpeg_decoder_attr.mode            = K_VDEC_SEND_MODE_FRAME;
    hard_jpeg_decoder_attr.pic_width       = fmt->width;
    hard_jpeg_decoder_attr.pic_height      = fmt->height;
    hard_jpeg_decoder_attr.stream_buf_size = ALIGN_UP(fmt->width * fmt->height, 0x1000);

    ret = kd_mpi_vdec_create_chn(hard_jpeg_decoder_vdev_chn, &hard_jpeg_decoder_attr);
    if (ret) {
        printf("kd_mpi_vdec_create_chn fail, ret = %d\n", ret);

        ret = 4;
        goto _error4;
    }

    ret = kd_mpi_vdec_start_chn(hard_jpeg_decoder_vdev_chn);
    if (ret) {
        printf("kd_mpi_vdec_start_chn fail, ret = %d\n", ret);

        ret = 5;
        goto _error5;
    }

    hard_jpeg_decoder_enabled = 1;

    return 0;

_error5:
    kd_mpi_vdec_destroy_chn(hard_jpeg_decoder_vdev_chn);
_error4:
    kd_mpi_vdec_detach_vb_pool(hard_jpeg_decoder_vdev_chn);
_error3:
    vb_destroy_vdec_pool(hard_jpeg_decoder_vb_pool_id);
_error2:
    kd_mpi_vdec_release_chn(_chn);
    hard_jpeg_decoder_vdev_chn = UINT32_MAX;
_error1:

    return ret;
}

void hard_jpeg_decmpress_exit()
{
    if (hard_jpeg_decoder_enabled) {
        hard_jpeg_decoder_enabled = 0;

        if (hard_jpeg_decoder_frame_dumped) {
            hard_jpeg_decoder_frame_dumped = 0;

            kd_mpi_vdec_release_frame(hard_jpeg_decoder_vdev_chn, &hard_jpeg_decoder_dumped_frame);
            memset(&hard_jpeg_decoder_dumped_frame, 0x00, sizeof(hard_jpeg_decoder_dumped_frame));
        }

        kd_mpi_vdec_stop_chn(hard_jpeg_decoder_vdev_chn);
        kd_mpi_vdec_destroy_chn(hard_jpeg_decoder_vdev_chn);

        kd_mpi_vdec_detach_vb_pool(hard_jpeg_decoder_vdev_chn);
        if (VB_INVALID_POOLID != hard_jpeg_decoder_vb_pool_id) {
            vb_destroy_vdec_pool(hard_jpeg_decoder_vb_pool_id);
        }

        kd_mpi_vdec_release_chn(hard_jpeg_decoder_vdev_chn);
        hard_jpeg_decoder_vdev_chn = UINT32_MAX;

        hard_jpeg_decoder_vb_pool_id = VB_INVALID_POOLID;
    }
}

static k_video_frame_info* hard_jpeg_decompress(k_vdec_stream* stream, int timeout_ms)
{
    k_s32                  ret   = 0;
    k_video_frame_info*    frame = NULL;
    k_vdec_supplement_info supplement;

    if (hard_jpeg_decoder_frame_dumped) {
        hard_jpeg_decoder_frame_dumped = 0;
        kd_mpi_vdec_release_frame(hard_jpeg_decoder_vdev_chn, &hard_jpeg_decoder_dumped_frame);
        memset(&hard_jpeg_decoder_dumped_frame, 0x00, sizeof(hard_jpeg_decoder_dumped_frame));
    }

    ret = kd_mpi_vdec_send_stream(hard_jpeg_decoder_vdev_chn, stream, timeout_ms);
    if (ret) {
        printf("kd_mpi_vdec_send_stream fail, 0x%08X\n", ret);
        goto _error;
    }

    ret = kd_mpi_vdec_get_frame(hard_jpeg_decoder_vdev_chn, &hard_jpeg_decoder_dumped_frame, &supplement, timeout_ms);
    if (ret) {
        printf("kd_mpi_vdec_get_frame fail, 0x%08X\n", ret);
        goto _error;
    }
    frame = &hard_jpeg_decoder_dumped_frame;

    hard_jpeg_decoder_frame_dumped = 1;

_error:
    return frame;
}

/* uvc_video_mode ************************************************************/
STATIC const mp_obj_type_t py_uvc_video_mode_type;

typedef struct _py_uvc_vicdeo_mode_obj_t {
    mp_obj_base_t     base;
    struct uvc_format _cobj;
} py_uvc_vicdeo_mode_obj_t;

STATIC mp_obj_t py_uvc_video_mode_from_struct(struct uvc_format* mode)
{
    py_uvc_vicdeo_mode_obj_t* o = m_new_obj(py_uvc_vicdeo_mode_obj_t);

    o->base.type = &py_uvc_video_mode_type;
    if (mode) {
        memcpy(&o->_cobj, mode, sizeof(*mode));
    } else {
        memset(&o->_cobj, 0x00, sizeof(*mode));
    }

    return MP_OBJ_FROM_PTR(o);
}

STATIC void* py_uvc_video_mode_cobj(mp_obj_t uvc_video_mode)
{
    PY_ASSERT_TYPE(uvc_video_mode, &py_uvc_video_mode_type);
    return &((py_uvc_vicdeo_mode_obj_t*)uvc_video_mode)->_cobj;
}

STATIC void py_uvc_video_mode_print(const mp_print_t* print, mp_obj_t self_in, mp_print_kind_t kind)
{
    py_uvc_vicdeo_mode_obj_t* self = MP_OBJ_TO_PTR(self_in);
    struct uvc_format*        mode = py_uvc_video_mode_cobj(self);

    mp_printf(print, "{\"width\":%u, \"height\":%u, \"format\":%s, \"fps\":%.2f}", mode->width, mode->height,
              (USBH_VIDEO_FORMAT_UNCOMPRESSED == mode->format_type) ? "uncompress"
                  : (USBH_VIDEO_FORMAT_MJPEG == mode->format_type)  ? "mjpeg"
                                                                    : "unknown",
              10000000.0f / mode->frameinterval);
}

STATIC void py_uvc_video_mode_attr(mp_obj_t self_in, qstr attr, mp_obj_t* dest)
{
    py_uvc_vicdeo_mode_obj_t* self = MP_OBJ_TO_PTR(self_in);
    struct uvc_format*        mode = py_uvc_video_mode_cobj(self);

    if (MP_OBJ_NULL == dest[0]) {
        // load attribute
        switch (attr) {
        case MP_QSTR_width:
            dest[0] = mp_obj_new_int(mode->width);
            break;
        case MP_QSTR_height:
            dest[0] = mp_obj_new_int(mode->height);
            break;
        case MP_QSTR_format:
            dest[0] = mp_obj_new_int(mode->format_type);
            break;
        case MP_QSTR_fps:
            dest[0] = mp_obj_new_float(10000000.0f / mode->frameinterval);
            break;
        default:
            dest[1] = MP_OBJ_SENTINEL; // continue lookup in locals_dict
            break;
        }
    }
}

/* clang-format off */
STATIC MP_DEFINE_CONST_OBJ_TYPE(
    py_uvc_video_mode_type,
    MP_QSTR_uvc_video_mode,
    MP_TYPE_FLAG_NONE,
    print, py_uvc_video_mode_print,
    attr, py_uvc_video_mode_attr
);
/* clang-format on */
/* uvc wrap ******************************************************************/
static struct uvc_format curr_format = { 0 };
static struct uvc_frame  curr_frame  = { .index = INVALID_FRAME_INDEX, 0 };

static int snap_cfg_convert = 1;

STATIC mp_obj_t uvc_video_mode(size_t n, const mp_obj_t* objs)
{
    if (0x00 == n) {
        // get current mode
        return py_uvc_video_mode_from_struct(&curr_format);
    } else {
        struct uvc_format format = { .width = 0, .height = 0, .format_type = USBH_VIDEO_FORMAT_MJPEG, .frameinterval = 0 };

        if (0x02 > n) {
            mp_raise_msg(&mp_type_ValueError, MP_ERROR_TEXT("must set width and height"));
        }
        format.width  = mp_obj_get_int(objs[0]);
        format.height = mp_obj_get_int(objs[1]);

        if (0x03 <= n) {
            format.format_type = mp_obj_get_int(objs[2]);
        }

        if (0x04 <= n) {
            format.frameinterval = 10000000 / mp_obj_get_int(objs[3]);
        }

        return py_uvc_video_mode_from_struct(&format);
    }
}
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(uvc_video_mode_obj, 0, 4, uvc_video_mode);
STATIC MP_DEFINE_CONST_STATICMETHOD_OBJ(uvc_video_mode_method, MP_ROM_PTR(&uvc_video_mode_obj));

STATIC mp_obj_t uvc_probe(void)
{
    int  find = 0;
    char info[256];

    mp_obj_t info_obj = mp_const_none;

    memset(info, 0, sizeof(info));
    if (0x00 == uvc_get_devinfo(&info[0], sizeof(info))) {
        find = 1;

        info_obj = mp_obj_new_str(info, strlen(info));
    }

    return mp_obj_new_tuple(2, ((mp_obj_t[]) { mp_obj_new_bool(find), info_obj }));
}
STATIC MP_DEFINE_CONST_FUN_OBJ_0(uvc_probe_obj, uvc_probe);
STATIC MP_DEFINE_CONST_STATICMETHOD_OBJ(uvc_probe_method, MP_ROM_PTR(&uvc_probe_obj));

STATIC mp_obj_t uvc_list_video_mode(void)
{
    int                fmts_count = 0;
    struct uvc_format* fmts       = NULL;
    mp_obj_t           mode_list  = mp_obj_new_list(0, NULL);

    fmts_count = uvc_get_formats(&fmts);
    if (fmts_count && fmts) {
        for (int i = 0; i < fmts_count; i++) {
            mp_obj_t mode = py_uvc_video_mode_from_struct(&fmts[i]);
            mp_obj_list_append(mode_list, mode);
        }
    }
    uvc_free_formats(&fmts);

    return MP_OBJ_FROM_PTR(mode_list);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_0(uvc_list_video_mode_obj, uvc_list_video_mode);
STATIC MP_DEFINE_CONST_STATICMETHOD_OBJ(uvc_list_video_mode_method, MP_ROM_PTR(&uvc_list_video_mode_obj));

STATIC mp_obj_t uvc_select_video_mode(mp_obj_t mode_in)
{
    py_uvc_vicdeo_mode_obj_t* self = MP_OBJ_TO_PTR(mode_in);
    struct uvc_format*        mode = py_uvc_video_mode_cobj(self);

    int succ = uvc_init(mode);

    if (0x00 == succ) {
        memcpy(&curr_format, mode, sizeof(*mode));
    }

    return mp_obj_new_tuple(2, ((mp_obj_t[]) { mp_obj_new_bool(0x00 == succ), mode_in }));
}
STATIC MP_DEFINE_CONST_FUN_OBJ_1(uvc_select_video_mode_obj, uvc_select_video_mode);
STATIC MP_DEFINE_CONST_STATICMETHOD_OBJ(uvc_select_video_mode_method, MP_ROM_PTR(&uvc_select_video_mode_obj));

STATIC mp_obj_t py_uvc_start(mp_uint_t n_args, const mp_obj_t* pos_args, mp_map_t* kw_args)
{
    int start_delay_ms = 0, succ = 0;

    enum { ARG_delay_ms, ARG_cvt };
    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_delay_ms, MP_ARG_INT, { .u_int = 0 } },
        { MP_QSTR_cvt, MP_ARG_BOOL, { .u_bool = true } },
    };
    mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all(n_args, pos_args, kw_args, MP_ARRAY_SIZE(allowed_args), allowed_args, args);

    start_delay_ms   = args[ARG_delay_ms].u_int;
    snap_cfg_convert = args[ARG_cvt].u_bool;

    if (0x00 == (succ = uvc_start_stream())) {
        if ((USBH_VIDEO_FORMAT_MJPEG == curr_format.format_type) && (snap_cfg_convert)) {
            if (0x00 != hard_jpeg_decompress_start(&curr_format)) {
                mp_printf(&mp_plat_print, "start hard jpeg decoder faild\n");
            }
        }

        if (start_delay_ms) {
            mp_hal_delay_ms(start_delay_ms);
        }
    }

    return mp_obj_new_bool(0x00 == succ);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_KW(uvc_start_obj, 0, py_uvc_start);
STATIC MP_DEFINE_CONST_STATICMETHOD_OBJ(uvc_start_method, MP_ROM_PTR(&uvc_start_obj));

void mod_uvc_exit()
{
    snap_cfg_convert = 1;

    if (INVALID_FRAME_INDEX != curr_frame.index) {

        uvc_put_frame(&curr_frame);
        memset(&curr_frame, 0, sizeof(curr_frame));
        curr_frame.index = INVALID_FRAME_INDEX;
    }
    memset(&curr_format, 0, sizeof(curr_format));

    hard_jpeg_decmpress_exit();

    uvc_exit();
}

STATIC mp_obj_t uvc_stop(void)
{
    mod_uvc_exit();

    return mp_const_none;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_0(uvc_stop_obj, uvc_stop);
STATIC MP_DEFINE_CONST_STATICMETHOD_OBJ(uvc_stop_method, MP_ROM_PTR(&uvc_stop_obj));

static inline __attribute__((__always_inline__)) uint16_t rgb565(uint8_t r, uint8_t g, uint8_t b)
{
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3);
}

static void yuv_to_rgb(uint8_t y, uint8_t u, uint8_t v, uint8_t* r, uint8_t* g, uint8_t* b)
{
    int c = y - 16;
    int d = u - 128;
    int e = v - 128;

    int rt = (298 * c + 409 * e + 128) >> 8;
    int gt = (298 * c - 100 * d - 208 * e + 128) >> 8;
    int bt = (298 * c + 516 * d + 128) >> 8;

    *r = rt < 0 ? 0 : (rt > 255 ? 255 : rt);
    *g = gt < 0 ? 0 : (gt > 255 ? 255 : gt);
    *b = bt < 0 ? 0 : (bt > 255 ? 255 : bt);
}

static void yuyv_to_rgb565_inplace(char* buffer, int width, int height)
{
    int num_pixels = width * height;

    // Process 4 bytes at a time (2 YUYV pixels -> 2 RGB565 pixels)
    for (int i = num_pixels - 2; i >= 0; i -= 2) {
        int index = i * 2;

        uint8_t y0 = buffer[index + 0];
        uint8_t u  = buffer[index + 1];
        uint8_t y1 = buffer[index + 2];
        uint8_t v  = buffer[index + 3];

        uint8_t r, g, b;

        yuv_to_rgb(y0, u, v, &r, &g, &b);
        uint16_t rgb0 = rgb565(r, g, b);

        yuv_to_rgb(y1, u, v, &r, &g, &b);
        uint16_t rgb1 = rgb565(r, g, b);

        // Write RGB565 over the original YUYV data
        ((uint16_t*)buffer)[i]     = rgb0;
        ((uint16_t*)buffer)[i + 1] = rgb1;
    }
}

STATIC mp_obj_t uvc_snapshot(size_t n, const mp_obj_t* objs)
{
    int              timeout_ms = 1000;
    struct uvc_frame req_frame  = { 0 };
    image_t          image;

    if (0x00 == n) {
        timeout_ms = curr_format.frameinterval >> 11; // default timeout 4 frame
    }

    if (0x01 <= n) {
        timeout_ms = mp_obj_get_int(objs[0]);
    }

    if (INVALID_FRAME_INDEX != curr_frame.index) {
        uvc_put_frame(&curr_frame);
        memset(&curr_frame, 0, sizeof(curr_frame));
        curr_frame.index = INVALID_FRAME_INDEX;
    }

    if (0x00 == uvc_get_frame(&req_frame, timeout_ms)) {
        memcpy(&curr_frame, &req_frame, sizeof(req_frame));

        image.w          = curr_format.width;
        image.h          = curr_format.height;
        image.pixels     = (uint8_t*)req_frame.userptr;
        image.alloc_type = ALLOC_VB;

        if (USBH_VIDEO_FORMAT_UNCOMPRESSED == curr_format.format_type) {
            pixformat_t pixel_fmt = PIXFORMAT_YUV422;

            if (snap_cfg_convert) {
                pixel_fmt = PIXFORMAT_RGB565;
                yuyv_to_rgb565_inplace(req_frame.userptr, curr_format.width, curr_format.height);
            }

            image.pixfmt = pixel_fmt;
            image.size   = curr_format.width * curr_format.height * 2;

            return py_image_from_struct(&image);
        } else if (USBH_VIDEO_FORMAT_MJPEG == curr_format.format_type) {
            if (snap_cfg_convert) {
                k_video_frame_info* frame = NULL;

                if (NULL == (frame = hard_jpeg_decompress(&req_frame.v_stream, timeout_ms))) {
                    mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("jpeg decode failed"));
                }

                return py_video_frame_info_from_struct(frame);
            } else {
                image.pixfmt = PIXFORMAT_JPEG;
                image.size   = req_frame.v_stream.len;

                return py_image_from_struct(&image);
            }
        } else {
            mp_printf(&mp_plat_print, "unsupport format %d\n", curr_format.format_type);
            return mp_const_none;
        }
    }

    return mp_const_none;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(uvc_snapsho_obj, 0, 1, uvc_snapshot);
STATIC MP_DEFINE_CONST_STATICMETHOD_OBJ(uvc_snapsho_method, MP_ROM_PTR(&uvc_snapsho_obj));

STATIC const mp_rom_map_elem_t uvc_locals_dict_table[] = {
    { MP_ROM_QSTR(MP_QSTR_probe), MP_ROM_PTR(&uvc_probe_method) },
    { MP_ROM_QSTR(MP_QSTR_video_mode), MP_ROM_PTR(&uvc_video_mode_method) },
    { MP_ROM_QSTR(MP_QSTR_list_video_mode), MP_ROM_PTR(&uvc_list_video_mode_method) },
    { MP_ROM_QSTR(MP_QSTR_select_video_mode), MP_ROM_PTR(&uvc_select_video_mode_method) },
    { MP_ROM_QSTR(MP_QSTR_start), MP_ROM_PTR(&uvc_start_method) },
    { MP_ROM_QSTR(MP_QSTR_stop), MP_ROM_PTR(&uvc_stop_method) },
    { MP_ROM_QSTR(MP_QSTR_snapshot), MP_ROM_PTR(&uvc_snapsho_method) },

    // mode
    { MP_ROM_QSTR(MP_QSTR_FORMAT_MJPEG), MP_ROM_INT(USBH_VIDEO_FORMAT_MJPEG) },
    { MP_ROM_QSTR(MP_QSTR_FORMAT_UNCOMPRESS), MP_ROM_INT(USBH_VIDEO_FORMAT_UNCOMPRESSED) },
};
STATIC MP_DEFINE_CONST_DICT(uvc_locals_dict, uvc_locals_dict_table);

/* clang-format off */
MP_DEFINE_CONST_OBJ_TYPE(
    py_media_uvc_type,
    MP_QSTR_UVC,
    MP_TYPE_FLAG_NONE,
    locals_dict, &uvc_locals_dict
);
/* clang-format on */

#endif // CONFIG_ENABLE_UVC_CAMERA
