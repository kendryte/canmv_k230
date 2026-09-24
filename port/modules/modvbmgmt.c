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
#include "k_vb_comm.h"
#include "mphal.h"
#include "py/obj.h"
#include "py/runtime.h"

#include "py_assert.h" // use openmv marco, PY_ASSERT_TYPE
#include "py_image.h"

#include "mperrno.h"
#include "mpprint.h"

#include "py_modules.h"

#include "mpi_sys_api.h"
#include "mpi_vb_api.h"

#include "list.h"

/** class Buffer *************************************************************/
const mp_obj_type_t py_media_vbmgmt_buffer_type;

typedef struct _py_media_vbmgmt_buffer {
    void* virt_addr;
    k_u64 phys_addr;
    k_u64 blk_size;

    k_s32           poolid;
    k_vb_blk_handle handle;
} py_media_vbmgmt_buffer_t;

typedef struct _py_media_vbmgmt_pending_buffer {
    struct list_head         list;
    py_media_vbmgmt_buffer_t buffer;
} py_media_vbmgmt_pending_buffer_t;

typedef struct _py_media_vbmgmt_buffer_obj {
    mp_obj_base_t            base;
    int                      is_destroyed;
    int                      is_tracked;
    py_media_vbmgmt_pending_buffer_t* cleanup_record;
    struct list_head         list;
    py_media_vbmgmt_buffer_t _cobj;
} py_media_vbmgmt_buffer_obj_t;

STATIC LIST_HEAD(py_media_vbmgmt_buffer_list_head);
STATIC LIST_HEAD(py_media_vbmgmt_pending_buffer_list_head);
STATIC unsigned int py_media_vbmgmt_buffer_cleanup_failures;

STATIC void py_media_vbmgmt_buffer_reset_resource(py_media_vbmgmt_buffer_t* buffer)
{
    memset(buffer, 0x00, sizeof(*buffer));
    buffer->poolid = VB_INVALID_POOLID;
    buffer->handle = VB_INVALID_HANDLE;
}

STATIC bool py_media_vbmgmt_buffer_ensure_cleanup_record(py_media_vbmgmt_buffer_obj_t* self)
{
    if (self->cleanup_record != NULL) {
        return true;
    }

    self->cleanup_record = malloc(sizeof(*self->cleanup_record));
    if (self->cleanup_record == NULL) {
        return false;
    }

    INIT_LIST_HEAD(&self->cleanup_record->list);
    py_media_vbmgmt_buffer_reset_resource(&self->cleanup_record->buffer);
    return true;
}

STATIC void py_media_vbmgmt_buffer_set_struct(mp_obj_t buffer_obj, const py_media_vbmgmt_buffer_t* buffer)
{
    py_media_vbmgmt_buffer_obj_t* self = MP_OBJ_TO_PTR(buffer_obj);
    if (!py_media_vbmgmt_buffer_ensure_cleanup_record(self)) {
        mp_raise_msg(&mp_type_MemoryError, MP_ERROR_TEXT("VB buffer cleanup tracking allocation failed"));
    }
    memcpy(&self->_cobj, buffer, sizeof(*buffer));
    list_add_tail(&self->list, &py_media_vbmgmt_buffer_list_head);
    self->is_destroyed = 0;
    self->is_tracked   = 1;
}

mp_obj_t py_media_vbmgmt_buffer_from_struct(py_media_vbmgmt_buffer_t* buffer)
{
    py_media_vbmgmt_buffer_obj_t* o = m_new_obj_with_finaliser(py_media_vbmgmt_buffer_obj_t);
    o->base.type                    = &py_media_vbmgmt_buffer_type;
    o->is_destroyed                 = 0;
    o->is_tracked                   = 0;
    o->cleanup_record               = NULL;
    INIT_LIST_HEAD(&o->list);
    py_media_vbmgmt_buffer_reset_resource(&o->_cobj);

    // Allocate the fallback record before acquiring a native buffer. It can
    // outlive the MicroPython object if a GC-finaliser cleanup must be retried.
    if (!py_media_vbmgmt_buffer_ensure_cleanup_record(o)) {
        mp_raise_msg(&mp_type_MemoryError, MP_ERROR_TEXT("VB buffer cleanup tracking allocation failed"));
    }

    if (buffer) {
        py_media_vbmgmt_buffer_set_struct(MP_OBJ_FROM_PTR(o), buffer);
    }

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

STATIC bool py_media_vbmgmt_buffer_release_resource(py_media_vbmgmt_buffer_t* buffer)
{
    k_s32 result;

    if (VB_INVALID_HANDLE != buffer->handle) {
        if (buffer->virt_addr && buffer->blk_size) {
            result = kd_mpi_sys_munmap(buffer->virt_addr, buffer->blk_size);
            if (K_SUCCESS != result) {
                printf("vb_buffer unmap block failed %p, %ld\n", buffer->virt_addr, buffer->blk_size);
                return false;
            }
            buffer->virt_addr = NULL;
        }

        result = kd_mpi_vb_release_block(buffer->handle);
        if (K_SUCCESS != result) {
            printf("vb_buffer release block failed %d\n", buffer->handle);
            return false;
        }
        buffer->handle = VB_INVALID_HANDLE;
    } else if (buffer->virt_addr && buffer->phys_addr) {
        result = kd_mpi_sys_mmz_free(buffer->phys_addr, buffer->virt_addr);
        if (K_SUCCESS != result) {
            printf("mmz_buffer free failed 0x%lx, %p\n", buffer->phys_addr, buffer->virt_addr);
            return false;
        }
        buffer->virt_addr = NULL;
    } else if (buffer->virt_addr && buffer->blk_size) {
        result = kd_mpi_sys_munmap(buffer->virt_addr, buffer->blk_size);
        if (K_SUCCESS != result) {
            printf("vb_buffer unmap block failed %p, %ld\n", buffer->virt_addr, buffer->blk_size);
            return false;
        }
        buffer->virt_addr = NULL;
    }

    py_media_vbmgmt_buffer_reset_resource(buffer);
    return true;
}

STATIC void py_media_vbmgmt_buffer_untrack(py_media_vbmgmt_buffer_obj_t* self)
{
    if (self->is_tracked) {
        list_del(&self->list);
        INIT_LIST_HEAD(&self->list);
        self->is_tracked = 0;
    }
}

STATIC bool py_media_vbmgmt_buffer_queue_cleanup(py_media_vbmgmt_buffer_obj_t* self)
{
    // set_struct() normally arms this record before attaching a resource. The
    // lazy allocation also keeps reused or legacy-created objects recoverable,
    // and uses only the system heap so it is safe in a GC finaliser.
    if (!py_media_vbmgmt_buffer_ensure_cleanup_record(self)) {
        printf("VB buffer cleanup record allocation failed\n");
        return false;
    }
    py_media_vbmgmt_pending_buffer_t* pending = self->cleanup_record;

    memcpy(&pending->buffer, &self->_cobj, sizeof(pending->buffer));
    list_add_tail(&pending->list, &py_media_vbmgmt_pending_buffer_list_head);
    py_media_vbmgmt_buffer_cleanup_failures++;
    self->cleanup_record = NULL;

    py_media_vbmgmt_buffer_reset_resource(&self->_cobj);
    self->is_destroyed = 1;
    py_media_vbmgmt_buffer_untrack(self);
    return true;
}

STATIC void py_media_vbmgmt_buffer_retry_pending_cleanup(void)
{
    py_media_vbmgmt_pending_buffer_t *pending, *pending_tmp;
    list_for_each_entry_safe(pending, pending_tmp, &py_media_vbmgmt_pending_buffer_list_head, list)
    {
        if (py_media_vbmgmt_buffer_release_resource(&pending->buffer)) {
            list_del(&pending->list);
            free(pending);
            py_media_vbmgmt_buffer_cleanup_failures--;
        }
    }
}

STATIC mp_obj_t py_media_vbmgmt_buffer_destroy_r(mp_obj_t self_in)
{
    py_media_vbmgmt_buffer_obj_t* self   = MP_OBJ_TO_PTR(self_in);
    py_media_vbmgmt_buffer_t*     buffer = py_media_vbmgmt_buffer_cobj(self);

    if (self->is_destroyed) {
        return mp_const_true;
    }

    if (!py_media_vbmgmt_buffer_release_resource(buffer)) {
        return mp_const_false;
    }
    self->is_destroyed = 1;

    return mp_const_true;
}

STATIC mp_obj_t py_media_vbmgmt_buffer_destroy(mp_obj_t self_in)
{
    py_media_vbmgmt_buffer_obj_t* self = MP_OBJ_TO_PTR(self_in);

    // A normal buffer release provides an inexpensive opportunity to recover
    // transient failures without waiting for VM or media-manager teardown.
    py_media_vbmgmt_buffer_retry_pending_cleanup();

    mp_obj_t result = py_media_vbmgmt_buffer_destroy_r(self_in);

    if (result == mp_const_false) {
        // Transfer ownership to native storage before this object can be
        // reclaimed by GC. The pending record is retried across soft resets.
        if (!py_media_vbmgmt_buffer_queue_cleanup(self)) {
            return mp_const_false;
        }
    } else {
        py_media_vbmgmt_buffer_untrack(self);
        free(self->cleanup_record);
        self->cleanup_record = NULL;
    }

    return result;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_1(py_media_vbmgmt_buffer_destroy_obj, py_media_vbmgmt_buffer_destroy);

STATIC mp_obj_t py_media_vbmgmt_buffer_get(size_t n_args, const mp_obj_t* args)
{
    py_media_vbmgmt_buffer_t buffer;
    mp_obj_t                  buffer_obj;
    mp_int_t                  block_size;

    memset(&buffer, 0x00, sizeof(buffer));

    buffer.poolid = VB_INVALID_POOLID;
    block_size    = mp_obj_get_int(args[0]);
    if (0x00 >= block_size) {
        mp_raise_ValueError(MP_ERROR_TEXT("invalid buffer size"));
    }
    buffer.blk_size = (k_u64)block_size;
    if (0x02 == n_args) {
        buffer.poolid = mp_obj_get_int(args[1]);
    }
    buffer_obj = py_media_vbmgmt_buffer_from_struct(NULL);

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

    buffer.virt_addr = kd_mpi_sys_mmap_cached(buffer.phys_addr, buffer.blk_size);
    if (0x00 == buffer.virt_addr) {
        kd_mpi_vb_release_block(buffer.handle);
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("MediaManager get buffer failed 4."));
    }

    py_media_vbmgmt_buffer_set_struct(buffer_obj, &buffer);
    return buffer_obj;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(py_media_vbmgmt_buffer_get_obj, 1, 2, py_media_vbmgmt_buffer_get);
STATIC MP_DEFINE_CONST_STATICMETHOD_OBJ(py_media_vbmgmt_buffer_get_method, MP_ROM_PTR(&py_media_vbmgmt_buffer_get_obj));

STATIC mp_obj_t py_media_vbmgmt_buffer_alloc(mp_obj_t size_obj)
{
    py_media_vbmgmt_buffer_t buffer;
    mp_obj_t                  buffer_obj;
    mp_int_t                  block_size;

    memset(&buffer, 0x00, sizeof(buffer));

    buffer.poolid = VB_INVALID_POOLID;
    buffer.handle = VB_INVALID_HANDLE;
    block_size    = mp_obj_get_int(size_obj);

    if (0x00 >= block_size) {
        mp_raise_ValueError(MP_ERROR_TEXT("invalid alloc size"));
    }
    buffer.blk_size = (k_u64)block_size;
    buffer_obj = py_media_vbmgmt_buffer_from_struct(NULL);

    if (K_SUCCESS != kd_mpi_sys_mmz_alloc_cached(&buffer.phys_addr, &buffer.virt_addr, "mgnt", "anonymous", buffer.blk_size)) {
        mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("alloc failed"));
    }

    py_media_vbmgmt_buffer_set_struct(buffer_obj, &buffer);
    return buffer_obj;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_1(py_media_vbmgmt_buffer_alloc_obj, py_media_vbmgmt_buffer_alloc);
STATIC MP_DEFINE_CONST_STATICMETHOD_OBJ(py_media_vbmgmt_buffer_alloc_method, MP_ROM_PTR(&py_media_vbmgmt_buffer_alloc_obj));

STATIC mp_obj_t py_media_vbmgmt_buffer_flush_cache(mp_obj_t self_in)
{
    py_media_vbmgmt_buffer_obj_t* self   = MP_OBJ_TO_PTR(self_in);
    py_media_vbmgmt_buffer_t*     buffer = py_media_vbmgmt_buffer_cobj(self);

    if (self->is_destroyed) {
        return mp_const_false;
    }

    if (buffer->virt_addr && buffer->blk_size) {
        if (K_SUCCESS == kd_mpi_sys_mmz_flush_cache(buffer->phys_addr, buffer->virt_addr, buffer->blk_size)) {
            return mp_const_true;
        }
    }

    return mp_const_false;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_1(py_media_vbmgmt_buffer_flush_cache_obj, py_media_vbmgmt_buffer_flush_cache);

//| # Auto-generated CanMV stub docs. Edit the signatures/docstrings here.
//| module: _media
//| class Buffer:
//|     """Native video-buffer allocation."""
//|     def destroy(self, /) -> bool:
//|         """Release this buffer. False means immediate release failed; native cleanup is queued for retry when tracking storage is available."""
//|     def free(self, /) -> bool:
//|         """Alias of destroy()."""

STATIC const mp_rom_map_elem_t py_media_vbmgmt_buffer_locals_dict_table[] = {
    { MP_ROM_QSTR(MP_QSTR___del__), MP_ROM_PTR(&py_media_vbmgmt_buffer_destroy_obj) },

    { MP_ROM_QSTR(MP_QSTR_get), MP_ROM_PTR(&py_media_vbmgmt_buffer_get_method) },
    { MP_ROM_QSTR(MP_QSTR_destroy), MP_ROM_PTR(&py_media_vbmgmt_buffer_destroy_obj) },

    { MP_ROM_QSTR(MP_QSTR_alloc), MP_ROM_PTR(&py_media_vbmgmt_buffer_alloc_method) },
    { MP_ROM_QSTR(MP_QSTR_free), MP_ROM_PTR(&py_media_vbmgmt_buffer_destroy_obj) },
    { MP_ROM_QSTR(MP_QSTR_flush_cache), MP_ROM_PTR(&py_media_vbmgmt_buffer_flush_cache_obj) },
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
                3, (mp_obj_t[]) { mp_obj_new_int(chn->mod_id), mp_obj_new_int(chn->dev_id), mp_obj_new_int(chn->chn_id) });
        } break;
        case MP_QSTR_dst: {
            k_mpp_chn* chn = &linker->dst;
            dest[0]        = mp_obj_new_tuple(
                3, (mp_obj_t[]) { mp_obj_new_int(chn->mod_id), mp_obj_new_int(chn->dev_id), mp_obj_new_int(chn->chn_id) });
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

/** class VBPool *************************************************************/
const mp_obj_type_t py_media_vbmgmt_pool_type;

STATIC LIST_HEAD(py_media_vbmgmt_pool_list_head);

typedef struct _py_media_vbmgmt_pool {
    k_s32            pool_id;
    k_u64            blk_size;
    k_u32            blk_cnt;
    k_vb_remap_mode  mode;
    struct list_head list;
} py_media_vbmgmt_pool_t;

typedef struct _py_media_vbmgmt_pool_obj {
    mp_obj_base_t           base;
    int                     is_destroyed;
    py_media_vbmgmt_pool_t* _cobj;
} py_media_vbmgmt_pool_obj_t;

mp_obj_t py_media_vbmgmt_pool_from_struct(py_media_vbmgmt_pool_t* pool)
{
    py_media_vbmgmt_pool_obj_t* o = m_new_obj(py_media_vbmgmt_pool_obj_t);

    if (NULL == (o->_cobj = malloc(sizeof(py_media_vbmgmt_pool_t)))) {
        mp_raise_OSError(MP_ENOMEM);
    }
    o->base.type = &py_media_vbmgmt_pool_type;

    if (pool) {
        memcpy(o->_cobj, pool, sizeof(*pool));
    } else {
        memset(o->_cobj, 0x00, sizeof(py_media_vbmgmt_pool_t));
        o->_cobj->pool_id = VB_INVALID_POOLID;
    }

    o->is_destroyed = 0;

    list_add_tail(&o->_cobj->list, &py_media_vbmgmt_pool_list_head);

    return MP_OBJ_FROM_PTR(o);
}

void* py_media_vbmgmt_pool_cobj(mp_obj_t pool_obj)
{
    PY_ASSERT_TYPE(pool_obj, &py_media_vbmgmt_pool_type);

    return ((py_media_vbmgmt_pool_obj_t*)pool_obj)->_cobj;
}

STATIC void py_media_vbmgmt_pool_print(const mp_print_t* print, mp_obj_t self_in, mp_print_kind_t kind)
{
    py_media_vbmgmt_pool_obj_t* self = MP_OBJ_TO_PTR(self_in);
    py_media_vbmgmt_pool_t*     pool = py_media_vbmgmt_pool_cobj(self);

    mp_printf(print,
              "{ \"VBPool\": { "
              "\"pool_id\": %d, "
              "\"blk_size\": %ld, "
              "\"blk_cnt\": %d, "
              "\"mode\": %d "
              "} }",
              pool->pool_id, pool->blk_size, pool->blk_cnt, pool->mode);
}

STATIC void py_media_vbmgmt_pool_attr(mp_obj_t self_in, qstr attr, mp_obj_t* dest)
{
    py_media_vbmgmt_pool_obj_t* self = MP_OBJ_TO_PTR(self_in);
    py_media_vbmgmt_pool_t*     pool = py_media_vbmgmt_pool_cobj(self);

    if (MP_OBJ_NULL == dest[0]) {
        // load attribute
        switch (attr) {
        case MP_QSTR_pool_id:
            dest[0] = mp_obj_new_int(pool->pool_id);
            break;
        case MP_QSTR_blk_size:
            dest[0] = mp_obj_new_int_from_ull(pool->blk_size);
            break;
        case MP_QSTR_blk_cnt:
            dest[0] = mp_obj_new_int(pool->blk_cnt);
            break;
        case MP_QSTR_mode:
            dest[0] = mp_obj_new_int(pool->mode);
            break;
        default:
            dest[1] = MP_OBJ_SENTINEL; // continue lookup in locals_dict
            break;
        }
    }
}

static k_s32 vbmgmt_pool_destroy_c(py_media_vbmgmt_pool_t* pool)
{
    k_s32 result = K_SUCCESS;

    if (VB_INVALID_POOLID != pool->pool_id) {
        if (K_SUCCESS != (result = kd_mpi_vb_destory_pool(pool->pool_id))) {
            printf("vb_pool destroy pool failed %d\n", pool->pool_id);
        }
        pool->pool_id = VB_INVALID_POOLID;
    }
    list_del(&pool->list);

    return result;
}

static void vbmgmt_pool_desroy_all(void)
{
    py_media_vbmgmt_pool_t *pos, *n;

    list_for_each_entry_safe(pos, n, &py_media_vbmgmt_pool_list_head, list)
    {
        vbmgmt_pool_destroy_c(pos);
        free(pos);
    }
}

STATIC mp_obj_t py_media_vbmgmt_pool_destroy(mp_obj_t self_in)
{
    k_s32 result = 0;

    py_media_vbmgmt_pool_obj_t* self = MP_OBJ_TO_PTR(self_in);
    py_media_vbmgmt_pool_t*     pool = py_media_vbmgmt_pool_cobj(self);

    if (self->is_destroyed) {
        return mp_const_true;
    }
    self->is_destroyed = 1;

    if (pool) {
        result = vbmgmt_pool_destroy_c(pool);
        free(self->_cobj);
        self->_cobj = NULL;
    }

    return mp_obj_new_bool(K_SUCCESS == result);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_1(py_media_vbmgmt_pool_destroy_obj, py_media_vbmgmt_pool_destroy);

STATIC mp_obj_t py_media_vbmgmt_pool_create(size_t n_args, const mp_obj_t* args)
{
    py_media_vbmgmt_pool_t pool;
    k_vb_pool_config       cfg;
    k_s32                  pool_id;

    memset(&pool, 0x00, sizeof(pool));
    memset(&cfg, 0x00, sizeof(cfg));

    // Arguments: blk_size (required), blk_cnt (required), mode (optional, default to VB_REMAP_MODE_NOCACHE)
    if (n_args < 2 || n_args > 3) {
        // This should be caught by the function definition, but for safety.
        mp_raise_TypeError(MP_ERROR_TEXT("VBPool.create() takes 2 or 3 arguments (blk_size, blk_cnt, [mode])"));
    }

    pool.blk_size = mp_obj_get_int(args[0]);
    pool.blk_cnt  = mp_obj_get_int(args[1]);
    pool.mode     = (n_args == 3) ? mp_obj_get_int(args[2]) : VB_REMAP_MODE_NOCACHE;

    cfg.blk_size = pool.blk_size;
    cfg.blk_cnt  = pool.blk_cnt;
    cfg.mode     = pool.mode;

    pool_id = kd_mpi_vb_create_pool(&cfg);
    if (VB_INVALID_POOLID == pool_id) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("VBPool create failed."));
    }

    pool.pool_id = pool_id;

    return py_media_vbmgmt_pool_from_struct(&pool);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(py_media_vbmgmt_pool_create_obj, 2, 3, py_media_vbmgmt_pool_create);
STATIC MP_DEFINE_CONST_STATICMETHOD_OBJ(py_media_vbmgmt_pool_create_method, MP_ROM_PTR(&py_media_vbmgmt_pool_create_obj));

STATIC const mp_rom_map_elem_t py_media_vbmgmt_pool_locals_dict_table[] = {
    { MP_ROM_QSTR(MP_QSTR_create), MP_ROM_PTR(&py_media_vbmgmt_pool_create_method) },
    { MP_ROM_QSTR(MP_QSTR_destroy), MP_ROM_PTR(&py_media_vbmgmt_pool_destroy_obj) },
};
STATIC MP_DEFINE_CONST_DICT(py_media_vbmgmt_pool_locals_dict, py_media_vbmgmt_pool_locals_dict_table);

/* clang-format off */
MP_DEFINE_CONST_OBJ_TYPE(
    py_media_vbmgmt_pool_type,
    MP_QSTR_VBPool,
    MP_TYPE_FLAG_NONE,
    print, py_media_vbmgmt_pool_print,
    attr, py_media_vbmgmt_pool_attr,
    locals_dict, &py_media_vbmgmt_pool_locals_dict
);
/* clang-format on */

/** class MediaManager *******************************************************/
static int py_media_vbmgmt_inited = 0;

void py_media_vbmgmt_init(void)
{
    k_s32 ret;
    extern k_s32 vb_mgmt_init(void);

    MP_STATE_PORT(py_media_vbmgmt_link_list) = mp_obj_new_list(0, NULL);

    // This resets only the per-VM producer bookkeeping; it does not initialize
    // the shared VB backend. Backend configuration remains gated below.
    vb_mgmt_init();
    py_media_vbmgmt_buffer_retry_pending_cleanup();

    if (py_media_vbmgmt_inited) {
        return;
    }

    k_vb_config vb_cfg = { .max_pool_cnt = VB_MAX_COMM_POOLS };
    if (K_SUCCESS != (ret = kd_mpi_vb_set_config(&vb_cfg))) {
        printf("kd_mpi_vb_set_config failed %d\n", ret);
        return;
    }

    k_vb_supplement_config supplement_config = { VB_SUPPLEMENT_JPEG_MASK };
    if (K_SUCCESS != (ret = kd_mpi_vb_set_supplement_config(&supplement_config))) {
        printf("MediaManager, vb supplement config failed(%d).\n", ret);
        return;
    }

    if (K_SUCCESS != (ret = kd_mpi_vb_init())) {
        printf("MediaManager, vb init failed(%d), at now please reboot the board to fix it.", ret);
        return;
    }

    py_media_vbmgmt_inited = 1;
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

    // A CSC channel may be an endpoint in the link list above. Unbind it
    // before stopping and destroying the channel.
    py_nonai_2d_csc_destroy_all();

    py_media_vbmgmt_buffer_obj_t *buffer, *buffer_tmp;
    list_for_each_entry_safe(buffer, buffer_tmp, &py_media_vbmgmt_buffer_list_head, list)
    {
        py_media_vbmgmt_buffer_destroy(MP_OBJ_FROM_PTR(buffer));
    }
}

void py_media_vbmgmt_deinit(void)
{
    extern k_s32 vb_mgmt_deinit(void);

    if (0x00 == py_media_vbmgmt_inited) {
        return;
    }

    // Producers must be stopped on every soft reset. Only the shared VB
    // backend needs to remain alive while a failed buffer cleanup is pending.
    vb_mgmt_deinit();

#if defined(CONFIG_ENABLE_UVC_CAMERA)
    extern void mod_uvc_exit();
    mod_uvc_exit();
#endif

    py_media_vbmgmt_buffer_retry_pending_cleanup();
    if (py_media_vbmgmt_buffer_cleanup_failures) {
        printf("MediaManager, keep VB backend initialized: %u buffer cleanup failure(s).\n",
               py_media_vbmgmt_buffer_cleanup_failures);
        return;
    }

    vbmgmt_pool_desroy_all();

    // vb_do_exit() refuses while any block is still checked out, which leaves
    // the backend configured. Clearing the flag regardless would desynchronize
    // it from the backend: py_media_vbmgmt_init() would then retry
    // kd_mpi_vb_set_config() forever and, worse, every later deinit would
    // return at the flag check above without running vb_mgmt_deinit(), so
    // vicap producers would never be stopped again. Keep the flag set instead
    // and let the next soft reset retry the teardown.
    k_s32 ret = kd_mpi_vb_exit();
    if (K_SUCCESS != ret) {
        printf("MediaManager, keep VB backend initialized: vb exit failed(%d).\n", ret);
        return;
    }

    py_media_vbmgmt_inited = 0;
}

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
//| # Auto-generated CanMV stub docs. Edit the signatures/docstrings here.
//| module: _media
//| class _MediaManager:
//|     """_media._MediaManager object."""
//|     def _link(src: Any, dst: Any, /) -> Any:
//|         """Perform link for _media._MediaManager."""


STATIC const mp_rom_map_elem_t py_media_vbmgmt_dict_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR__MediaManager) },

    { MP_ROM_QSTR(MP_QSTR__link), MP_ROM_PTR(&py_media_vbmgmt_link_method) },

    { MP_ROM_QSTR(MP_QSTR_Buffer), MP_ROM_PTR(&py_media_vbmgmt_buffer_type) },
    { MP_ROM_QSTR(MP_QSTR_VBPool), MP_ROM_PTR(&py_media_vbmgmt_pool_type) },
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
