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

#pragma once

#include "py/obj.h"

#include "k_vb_comm.h"
#include "k_video_comm.h"

extern const mp_obj_type_t py_media_uvc_type;

extern const mp_obj_type_t py_media_video_frame_type;
extern const mp_obj_type_t py_media_video_frame_info_type;

extern const mp_obj_type_t py_nonai_2d_csc_type;

extern const mp_obj_type_t py_media_vbmgmt_type;

extern const mp_obj_type_t py_usb_serial_type;

mp_obj_t py_video_frame_from_struct(k_video_frame* frame);
void*    py_video_frame_cobj(mp_obj_t frame_obj);
void     py_video_frame_destory(mp_obj_t video_frame);

mp_obj_t py_video_frame_info_from_struct(k_video_frame_info* info);
void*    py_video_frame_info_cobj(mp_obj_t info_obj);
void     py_video_frame_info_destory(mp_obj_t info_obj);

void py_media_vbmgmt_init(void);
void py_media_vbmgmt_deinit(void);

int py_media_vbmgmt_config_vb_comm_pool(k_vb_config* cfg);
