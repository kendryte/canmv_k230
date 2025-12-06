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

#include "k_type.h"
#include "mphal.h"
#include "py/obj.h"
#include "py/runtime.h"

#include "py_assert.h" // use openmv marco, PY_ASSERT_TYPE
#include "py_image.h"

#include "mpprint.h"

#include "py_modules.h"

#include "mpi_sys_api.h"
#include "mpi_vb_api.h"

/** class Buffer *************************************************************/
const mp_obj_type_t py_media_vbmgmt_buffer_type;

typedef struct _py_media_vbmgmt_buffer {
    void* virt_addr;
    k_u64 phys_addr;
    k_u64 blk_size;

    k_s32           poolid;
    k_vb_blk_handle handle;
} py_media_vbmgmt_buffer_t;

typedef struct _py_media_vbmgmt_buffer_obj {
    mp_obj_base_t            base;
    int                      is_destroyed;
    py_media_vbmgmt_buffer_t _cobj;
} py_media_vbmgmt_buffer_obj_t;

mp_obj_t py_media_vbmgmt_buffer_from_struct(py_media_vbmgmt_buffer_t* buffer)
{
    py_media_vbmgmt_buffer_obj_t* o = m_new_obj(py_media_vbmgmt_buffer_obj_t);
    o->base.type                    = &py_media_vbmgmt_buffer_type;

    if (buffer) {
        memcpy(&o->_cobj, buffer, sizeof(*buffer));

        mp_obj_list_append(MP_STATE_PORT(py_media_vbmgmt_buffer_list), o);
    } else {
        memset(&o->_cobj, 0x00, sizeof(py_media_vbmgmt_buffer_t));
        o->_cobj.handle = VB_INVALID_HANDLE;
    }

    o->is_destroyed = 0;

    return MP_OBJ_FROM_PTR(o);
}

void* py_media_vbmgmt_buffer_cobj(mp_obj_t buffer_obj)
{
    PY_ASSERT_TYPE(buffer_obj, &py_media_vbmgmt_buffer_type);

    return &((py_media_vbmgmt_buffer_obj_t*)buffer_obj)->_cobj;
}

STATIC void py_media_vbmgmt_buffer_print(const mp_print_t* print, mp_obj_t self_in, mp_print_kind_t kind)
{
    py_media_vbmgmt_buffer_obj_t* self   = MP_OBJ_TO_PTR(self_in);
    py_media_vbmgmt_buffer_t*     buffer = py_media_vbmgmt_buffer_cobj(self);

    mp_printf(print,
              "{ \"VBBuffer\": { "
              "\"virt_addr\": \"0x%p\", "
              "\"phys_addr\": \"0x%lx\", "
              "\"size\": %ld, "
              "\"poolid\": %d, "
              "\"handle\": \"0x%08x\" "
              "} }",
              buffer->virt_addr, buffer->phys_addr, buffer->blk_size, buffer->poolid, buffer->handle);
}

STATIC void py_media_vbmgmt_buffer_attr(mp_obj_t self_in, qstr attr, mp_obj_t* dest)
{
    py_media_vbmgmt_buffer_obj_t* self   = MP_OBJ_TO_PTR(self_in);
    py_media_vbmgmt_buffer_t*     buffer = py_media_vbmgmt_buffer_cobj(self);

    if (MP_OBJ_NULL == dest[0]) {
        // load attribute
        switch (attr) {
        case MP_QSTR_handle:
            dest[0] = mp_obj_new_int(buffer->handle);
            break;
        case MP_QSTR_pool_id:
            dest[0] = mp_obj_new_int(buffer->poolid);
            break;
        case MP_QSTR_phys_addr:
            dest[0] = mp_obj_new_int_from_ull(buffer->phys_addr);
            break;
        case MP_QSTR_virt_addr:
            dest[0] = mp_obj_new_int_from_ull((uintptr_t)buffer->virt_addr);
            break;
        case MP_QSTR_size:
            dest[0] = mp_obj_new_int_from_ull(buffer->blk_size);
            break;
        default:
            dest[1] = MP_OBJ_SENTINEL; // continue lookup in locals_dict
            break;
        }
    }
}

STATIC mp_obj_t py_media_vbmgmt_buffer_destroy_r(mp_obj_t self_in)
{
    k_s32                         result = 0;
    py_media_vbmgmt_buffer_obj_t* self   = MP_OBJ_TO_PTR(self_in);
    py_media_vbmgmt_buffer_t*     buffer = py_media_vbmgmt_buffer_cobj(self);

    if (self->is_destroyed) {
        return mp_const_true;
    }
    self->is_destroyed = 1;

    if (VB_INVALID_HANDLE != buffer->handle) {
        if (K_SUCCESS != (result = kd_mpi_vb_release_block(buffer->handle))) {
            printf("vb_buffer release block failed %d\n", buffer->handle);
        }
        buffer->handle = VB_INVALID_HANDLE;
    }

    if (buffer->virt_addr && buffer->blk_size) {
        if (K_SUCCESS != (result = kd_mpi_sys_munmap(buffer->virt_addr, buffer->blk_size))) {
            printf("vb_buffer umap block failed %p, %ld\n", buffer->virt_addr, buffer->blk_size);
        }

        buffer->virt_addr = 0;
        buffer->blk_size  = 0;
    }

    return mp_obj_new_bool(K_SUCCESS == result);
}

STATIC mp_obj_t py_media_vbmgmt_buffer_destroy(mp_obj_t self_in)
{
    mp_obj_list_remove(MP_STATE_PORT(py_media_vbmgmt_buffer_list), self_in);

    return py_media_vbmgmt_buffer_destroy_r(self_in);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_1(py_media_vbmgmt_buffer_destroy_obj, py_media_vbmgmt_buffer_destroy);

STATIC mp_obj_t py_media_vbmgmt_buffer_get(size_t n_args, const mp_obj_t* args)
{
    py_media_vbmgmt_buffer_t buffer;

    memset(&buffer, 0x00, sizeof(buffer));

    buffer.poolid   = VB_INVALID_POOLID;
    buffer.blk_size = mp_obj_get_int(args[0]);
    if (0x02 == n_args) {
        buffer.poolid = mp_obj_get_int(args[1]);
    }

    buffer.handle = kd_mpi_vb_get_block(buffer.poolid, buffer.blk_size, (void*)0);
    if (VB_INVALID_HANDLE == buffer.handle) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("MediaManager get buffer failed 1."));
    }

    buffer.poolid = kd_mpi_vb_handle_to_pool_id(buffer.handle);
    if (VB_INVALID_POOLID == buffer.poolid) {
        kd_mpi_vb_release_block(buffer.handle);
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("MediaManager get buffer failed 2."));
    }

    buffer.phys_addr = kd_mpi_vb_handle_to_phyaddr(buffer.handle);
    if (0x00 == buffer.phys_addr) {
        kd_mpi_vb_release_block(buffer.handle);
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("MediaManager get buffer failed 3."));
    }

    buffer.virt_addr = kd_mpi_sys_mmap(buffer.phys_addr, buffer.blk_size);
    if (0x00 == buffer.virt_addr) {
        kd_mpi_vb_release_block(buffer.handle);
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("MediaManager get buffer failed 4."));
    }

    return py_media_vbmgmt_buffer_from_struct(&buffer);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(py_media_vbmgmt_buffer_get_obj, 1, 2, py_media_vbmgmt_buffer_get);
STATIC MP_DEFINE_CONST_STATICMETHOD_OBJ(py_media_vbmgmt_buffer_get_method, MP_ROM_PTR(&py_media_vbmgmt_buffer_get_obj));

STATIC const mp_rom_map_elem_t py_media_vbmgmt_buffer_locals_dict_table[] = {
    { MP_ROM_QSTR(MP_QSTR___del__), MP_ROM_PTR(&py_media_vbmgmt_buffer_destroy_obj) },

    { MP_ROM_QSTR(MP_QSTR_get), MP_ROM_PTR(&py_media_vbmgmt_buffer_get_method) },
    { MP_ROM_QSTR(MP_QSTR_destroy), MP_ROM_PTR(&py_media_vbmgmt_buffer_destroy_obj) },
};
STATIC MP_DEFINE_CONST_DICT(py_media_vbmgmt_buffer_locals_dict, py_media_vbmgmt_buffer_locals_dict_table);

/* clang-format off */
MP_DEFINE_CONST_OBJ_TYPE(
    py_media_vbmgmt_buffer_type,
    MP_QSTR_py_media_vbmgmt_buffer,
    MP_TYPE_FLAG_NONE,
    print, py_media_vbmgmt_buffer_print,
    attr, py_media_vbmgmt_buffer_attr,
    locals_dict, &py_media_vbmgmt_buffer_locals_dict
);
/* clang-format on */

/** class linker *************************************************************/
const mp_obj_type_t py_media_vbmgmt_linker_type;

typedef struct _py_media_vbmgmt_linker {
    k_mpp_chn src, dst;
} py_media_vbmgmt_linker_t;

typedef struct _py_media_vbmgmt_linker_obj {
    mp_obj_base_t            base;
    int                      is_destroyed;
    py_media_vbmgmt_linker_t _cobj;
} py_media_vbmgmt_linker_obj_t;

mp_obj_t py_media_vbmgmt_linker_from_struct(k_mpp_chn* src, k_mpp_chn* dst)
{
    py_media_vbmgmt_linker_obj_t* o = m_new_obj(py_media_vbmgmt_linker_obj_t);
    o->base.type                    = &py_media_vbmgmt_linker_type;

    if (src && dst) {
        memcpy(&o->_cobj.src, src, sizeof(*src));
        memcpy(&o->_cobj.dst, dst, sizeof(*dst));

        mp_obj_list_append(MP_STATE_PORT(py_media_vbmgmt_link_list), o);
    } else {
        memset(&o->_cobj, 0x00, sizeof(py_media_vbmgmt_linker_t));
    }

    o->is_destroyed = 0;

    return MP_OBJ_FROM_PTR(o);
}

void* py_media_vbmgmt_linker_cobj(mp_obj_t linker_obj)
{
    PY_ASSERT_TYPE(linker_obj, &py_media_vbmgmt_linker_type);

    return &((py_media_vbmgmt_linker_obj_t*)linker_obj)->_cobj;
}

STATIC void py_media_vbmgmt_linker_print(const mp_print_t* print, mp_obj_t self_in, mp_print_kind_t kind)
{
    py_media_vbmgmt_linker_obj_t* self   = MP_OBJ_TO_PTR(self_in);
    py_media_vbmgmt_linker_t*     linker = py_media_vbmgmt_linker_cobj(self);

    mp_printf(print,
              "{ \"MPPLink\": { "
              "\"src\": { \"mod_id\": %d, \"dev_id\": %d, \"chn_id\": %d }, "
              "\"dst\": { \"mod_id\": %d, \"dev_id\": %d, \"chn_id\": %d }"
              " } }",
              linker->src.mod_id, linker->src.dev_id, linker->src.chn_id, linker->dst.mod_id, linker->dst.dev_id,
              linker->dst.chn_id);
}

STATIC void py_media_vbmgmt_linker_attr(mp_obj_t self_in, qstr attr, mp_obj_t* dest)
{
    py_media_vbmgmt_linker_obj_t* self   = MP_OBJ_TO_PTR(self_in);
    py_media_vbmgmt_linker_t*     linker = py_media_vbmgmt_linker_cobj(self);

    if (dest[0] == MP_OBJ_NULL) {
        // load attribute
        switch (attr) {
        case MP_QSTR_src: {
            k_mpp_chn* chn = &linker->src;
            dest[0]        = mp_obj_new_tuple(
                3,
                (mp_obj_t[]) { mp_obj_new_int(chn->mod_id), mp_obj_new_int(chn->dev_id), mp_obj_new_int(chn->chn_id) });
        } break;
        case MP_QSTR_dst: {
            k_mpp_chn* chn = &linker->dst;
            dest[0]        = mp_obj_new_tuple(
                3,
                (mp_obj_t[]) { mp_obj_new_int(chn->mod_id), mp_obj_new_int(chn->dev_id), mp_obj_new_int(chn->chn_id) });
        } break;
        default:
            dest[1] = MP_OBJ_SENTINEL; // continue lookup in locals_dict
            break;
        }
    }
}

STATIC mp_obj_t py_media_vbmgmt_linker_destroy_r(mp_obj_t self_in)
{
    k_s32 result = 0;

    py_media_vbmgmt_linker_obj_t* self   = MP_OBJ_TO_PTR(self_in);
    py_media_vbmgmt_linker_t*     linker = py_media_vbmgmt_linker_cobj(self);

    if (self->is_destroyed) {
        return mp_const_true;
    }
    self->is_destroyed = 1;

    if (K_SUCCESS != (result = kd_mpi_sys_unbind(&linker->src, &linker->dst))) {
        mp_printf(&mp_plat_print, "vb unbind failed %u\n", result & 0x1FF);
    }

    return mp_obj_new_bool(K_SUCCESS == result);
}

STATIC mp_obj_t py_media_vbmgmt_linker_destroy(mp_obj_t self_in)
{
    mp_obj_list_remove(MP_STATE_PORT(py_media_vbmgmt_link_list), self_in);

    return py_media_vbmgmt_linker_destroy_r(self_in);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_1(py_media_vbmgmt_linker_destroy_obj, py_media_vbmgmt_linker_destroy);

STATIC const mp_rom_map_elem_t py_media_vbmgmt_linker_locals_dict_table[] = {
    { MP_ROM_QSTR(MP_QSTR___del__), MP_ROM_PTR(&py_media_vbmgmt_linker_destroy_obj) },

    { MP_ROM_QSTR(MP_QSTR_destroy), MP_ROM_PTR(&py_media_vbmgmt_linker_destroy_obj) },
};
STATIC MP_DEFINE_CONST_DICT(py_media_vbmgmt_linker_locals_dict, py_media_vbmgmt_linker_locals_dict_table);

/* clang-format off */
MP_DEFINE_CONST_OBJ_TYPE(
    py_media_vbmgmt_linker_type,
    MP_QSTR_py_media_vbmgmt_linker,
    MP_TYPE_FLAG_NONE,
    print, py_media_vbmgmt_linker_print,
    attr, py_media_vbmgmt_linker_attr,
    locals_dict, &py_media_vbmgmt_linker_locals_dict
);
/* clang-format on */

/** class MediaManager *******************************************************/
static int py_media_vbmgmt_inited = 0;

static k_vb_config py_media_vbmgmt_vb_cfg        = { 0 };
static int         py_media_vbmgmt_vb_pool_index = 0;

void py_media_vbmgmt_init(void)
{
    extern k_s32 vb_mgmt_init(void);
    vb_mgmt_init();

    py_media_vbmgmt_inited        = 0;
    py_media_vbmgmt_vb_pool_index = 0;
    memset(&py_media_vbmgmt_vb_cfg, 0x00, sizeof(py_media_vbmgmt_vb_cfg));

    MP_STATE_PORT(py_media_vbmgmt_link_list)   = mp_obj_new_list(0, NULL);
    MP_STATE_PORT(py_media_vbmgmt_buffer_list) = mp_obj_new_list(0, NULL);
}

void py_media_vbmgmt_deinit(void)
{
    py_media_vbmgmt_inited        = 0;
    py_media_vbmgmt_vb_pool_index = 0;
    memset(&py_media_vbmgmt_vb_cfg, 0x00, sizeof(py_media_vbmgmt_vb_cfg));

    extern void  dma_dev_deinit(void);
    extern void  ide_dbg_vo_wbc_deinit(void);
    extern int   ide_dbg_set_vo_wbc(int quality, int width, int height);
    extern k_s32 vb_mgmt_deinit(void);

    vb_mgmt_deinit();

    ide_dbg_set_vo_wbc(0, 0, 0);
    ide_dbg_vo_wbc_deinit();
    dma_dev_deinit();

#if defined(CONFIG_ENABLE_UVC_CAMERA)
    extern void mod_uvc_exit();
    mod_uvc_exit();
#endif

    kd_mpi_vb_exit();
}

void py_media_vbmgmt_deinit_pre(void)
{
    if (MP_OBJ_NULL != MP_STATE_PORT(py_media_vbmgmt_link_list)) {
        for (mp_uint_t i = 0; i < MP_STATE_PORT(py_media_vbmgmt_link_list)->len; i++) {
            py_media_vbmgmt_linker_obj_t* linker = MP_STATE_PORT(py_media_vbmgmt_link_list)->items[i];

            py_media_vbmgmt_linker_destroy_r(linker);
            // m_del_obj(py_media_vbmgmt_linker_obj_t, linker);
        }
        MP_STATE_PORT(py_media_vbmgmt_link_list) = MP_OBJ_NULL;
    }

    if (MP_OBJ_NULL != MP_STATE_PORT(py_media_vbmgmt_buffer_list)) {
        for (mp_uint_t i = 0; i < MP_STATE_PORT(py_media_vbmgmt_buffer_list)->len; i++) {
            py_media_vbmgmt_buffer_obj_t* buffer = MP_STATE_PORT(py_media_vbmgmt_buffer_list)->items[i];

            py_media_vbmgmt_buffer_destroy_r(buffer);
            // m_del_obj(py_media_vbmgmt_buffer_obj_t, buffer);
        }
        MP_STATE_PORT(py_media_vbmgmt_buffer_list) = MP_OBJ_NULL;
    }
}

int py_media_vbmgmt_config_vb_comm_pool(k_vb_config* cfg)
{
    k_vb_pool_config *spool, *dpool;

    if (VB_MAX_COMM_POOLS <= py_media_vbmgmt_vb_pool_index) {
        printf("too many common pool config 1\n");
        return -1;
    }

    dpool = &py_media_vbmgmt_vb_cfg.comm_pool[py_media_vbmgmt_vb_pool_index];

    for (k_u32 i = 0; i < cfg->max_pool_cnt; i++) {
        spool = &cfg->comm_pool[i];
        if ((0x00 == spool->blk_size) || (0x00 == spool->blk_cnt)) {
            continue;
        }
        memcpy(dpool, spool, sizeof(*dpool));

        dpool++;
        py_media_vbmgmt_vb_pool_index++;

        if (VB_MAX_COMM_POOLS <= py_media_vbmgmt_vb_pool_index) {
            printf("too many common pool config 2\n");
            return -1;
        }
    }

    return 0;
}

STATIC mp_obj_t py_media_vbmgmt_config(mp_obj_t config)
{
    int result = 0;

    mp_buffer_info_t bufinfo;
    mp_get_buffer_raise(config, &bufinfo, MP_BUFFER_READ);

    if (sizeof(k_vb_config) != bufinfo.len) {
        mp_raise_msg_varg(&mp_type_TypeError, MP_ERROR_TEXT("expect size: %u, actual size: %u"), sizeof(k_vb_config),
                          bufinfo.len);
    }

    result = py_media_vbmgmt_config_vb_comm_pool(bufinfo.buf);

    return mp_obj_new_bool(0x00 == result);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_1(py_media_vbmgmt_config_obj, py_media_vbmgmt_config);
STATIC MP_DEFINE_CONST_STATICMETHOD_OBJ(py_media_vbmgmt_config_method, MP_ROM_PTR(&py_media_vbmgmt_config_obj));

STATIC mp_obj_t py_media_vbmgmt_link(mp_obj_t src_obj, mp_obj_t dst_obj)
{
    k_s32     ret;
    k_mpp_chn src, dst;

    mp_buffer_info_t bufinfo;

    mp_get_buffer_raise(src_obj, &bufinfo, MP_BUFFER_READ);
    if (sizeof(k_mpp_chn) != bufinfo.len) {
        mp_raise_msg_varg(&mp_type_TypeError, MP_ERROR_TEXT("expect size: %u, actual size: %u"), sizeof(k_mpp_chn),
                          bufinfo.len);
    }
    memcpy(&src, bufinfo.buf, sizeof(k_mpp_chn));

    mp_get_buffer_raise(dst_obj, &bufinfo, MP_BUFFER_READ);
    if (sizeof(k_mpp_chn) != bufinfo.len) {
        mp_raise_msg_varg(&mp_type_TypeError, MP_ERROR_TEXT("expect size: %u, actual size: %u"), sizeof(k_mpp_chn),
                          bufinfo.len);
    }
    memcpy(&dst, bufinfo.buf, sizeof(k_mpp_chn));

    if (K_SUCCESS != (ret = kd_mpi_sys_bind(&src, &dst))) {
        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("MediaManager link failed(%d)"), ret & 0x1FF);
    }

    return py_media_vbmgmt_linker_from_struct(&src, &dst);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_2(py_media_vbmgmt_link_obj, py_media_vbmgmt_link);
STATIC MP_DEFINE_CONST_STATICMETHOD_OBJ(py_media_vbmgmt_link_method, MP_ROM_PTR(&py_media_vbmgmt_link_obj));

STATIC mp_obj_t py_media_vbmgmt_init_mp(size_t n_args, const mp_obj_t* args)
{
    k_s32 ret;
    int   for_comress = 1;

    k_vb_config vb_cfg = { 0 };

    if (py_media_vbmgmt_inited) {
        mp_raise_msg(&mp_type_AssertionError,
                     MP_ERROR_TEXT("The VideoBuffer has been initialized!!!\nThis method can only be called once, "
                                   "please check your code!!!"));
    }

    if (0x01 == n_args) {
        for_comress = mp_obj_get_int(args[0]);
    }

    if (for_comress) {
        vb_cfg.max_pool_cnt          = 1;
        vb_cfg.comm_pool[0].blk_cnt  = 2;
        vb_cfg.comm_pool[0].blk_size = (1920 * 1080 + (4096 - 1)) & ~(4096 - 1);
        vb_cfg.comm_pool[0].mode     = VB_REMAP_MODE_NOCACHE;

        if (0x00 != py_media_vbmgmt_config_vb_comm_pool(&vb_cfg)) {
            mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("config vb common pool failed."));
        }
    }

    mp_printf(&mp_plat_print, "vb common pool count %u\n", py_media_vbmgmt_vb_pool_index);

    py_media_vbmgmt_vb_cfg.max_pool_cnt = VB_MAX_COMM_POOLS;
    if (K_SUCCESS != (ret = kd_mpi_vb_set_config(&py_media_vbmgmt_vb_cfg))) {
        mp_raise_msg_varg(
            &mp_type_RuntimeError,
            MP_ERROR_TEXT("MediaManager, vb config failed(%d), at now please reboot the board to fix it."),
            ret & 0x1FF);
    }

    k_vb_supplement_config supplement_config = { VB_SUPPLEMENT_JPEG_MASK };
    if (K_SUCCESS != (ret = kd_mpi_vb_set_supplement_config(&supplement_config))) {
        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("MediaManager, vb supplement config failed(%d)."),
                          ret & 0x1FF);
    }

    if (K_SUCCESS != (ret = kd_mpi_vb_init())) {
        mp_raise_msg_varg(&mp_type_RuntimeError,
                          MP_ERROR_TEXT("MediaManager, vb init failed(%d), at now please reboot the board to fix it."),
                          ret & 0x1FF);
    }

    extern int ide_dbg_vo_wbc_init(void);
    ide_dbg_vo_wbc_init();

    py_media_vbmgmt_inited = 1;

    return mp_const_none;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(py_media_vbmgmt_init_obj, 0, 1, py_media_vbmgmt_init_mp);
STATIC MP_DEFINE_CONST_STATICMETHOD_OBJ(py_media_vbmgmt_init_method, MP_ROM_PTR(&py_media_vbmgmt_init_obj));

STATIC mp_obj_t py_media_vbmgmt_deinit_mp(size_t n_args, const mp_obj_t* args)
{
    py_media_vbmgmt_deinit_pre();
    py_media_vbmgmt_deinit();

    return mp_const_none;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(py_media_vbmgmt_deinit_obj, 0, 1, py_media_vbmgmt_deinit_mp);
STATIC MP_DEFINE_CONST_STATICMETHOD_OBJ(py_media_vbmgmt_deinit_method, MP_ROM_PTR(&py_media_vbmgmt_deinit_obj));

STATIC const mp_rom_map_elem_t py_media_vbmgmt_dict_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR__MediaManager) },

    { MP_ROM_QSTR(MP_QSTR_init), MP_ROM_PTR(&py_media_vbmgmt_init_method) },
    { MP_ROM_QSTR(MP_QSTR_deinit), MP_ROM_PTR(&py_media_vbmgmt_deinit_method) },
    { MP_ROM_QSTR(MP_QSTR__config), MP_ROM_PTR(&py_media_vbmgmt_config_method) },
    { MP_ROM_QSTR(MP_QSTR__link), MP_ROM_PTR(&py_media_vbmgmt_link_method) },

    { MP_ROM_QSTR(MP_QSTR_Buffer), MP_ROM_PTR(&py_media_vbmgmt_buffer_type) },
};
STATIC MP_DEFINE_CONST_DICT(py_media_vbmgmt_dict, py_media_vbmgmt_dict_table);

/* clang-format off */
MP_DEFINE_CONST_OBJ_TYPE(
    py_media_vbmgmt_type,
    MP_QSTR__MediaManager,
    MP_TYPE_FLAG_NONE,
    locals_dict, &py_media_vbmgmt_dict
);
/* clang-format on */

MP_REGISTER_ROOT_POINTER(struct _mp_obj_list_t* py_media_vbmgmt_link_list);
MP_REGISTER_ROOT_POINTER(struct _mp_obj_list_t* py_media_vbmgmt_buffer_list);
