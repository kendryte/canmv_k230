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

#include "py/obj.h"
#include "py/runtime.h"

#include "py_modules.h"

STATIC const mp_rom_map_elem_t media_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR__media) },

    { MP_ROM_QSTR(MP_QSTR_py_video_frame), MP_ROM_PTR(&py_media_video_frame_type) },
    { MP_ROM_QSTR(MP_QSTR_py_video_frame_info), MP_ROM_PTR(&py_media_video_frame_info_type) },
    
    { MP_ROM_QSTR(MP_QSTR__MediaManager), MP_ROM_PTR(&py_media_vbmgmt_type) },

#if defined(CONFIG_ENABLE_UVC_CAMERA)
    { MP_ROM_QSTR(MP_QSTR_UVC), MP_ROM_PTR(&py_media_uvc_type) },
#endif // CONFIG_ENABLE_UVC_CAMERA

    { MP_ROM_QSTR(MP_QSTR_GSDMA), MP_ROM_PTR(&py_media_gsdma_type) },
};
STATIC MP_DEFINE_CONST_DICT(media_module_globals, media_module_globals_table);

const mp_obj_module_t media_module = {
    .base    = { &mp_type_module },
    .globals = (mp_obj_dict_t*)&media_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR__media, media_module);
