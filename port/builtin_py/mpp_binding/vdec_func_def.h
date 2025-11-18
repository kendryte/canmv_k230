/* Copyright (c) 2023, Canaan Bright Sight Co., Ltd
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

DEF_INT_FUNC_INT_STRUCTPTR(kd_mpi_vdec_create_chn, k_vdec_chn_attr)
DEF_INT_FUNC_INT(kd_mpi_vdec_start_chn)
DEF_INT_FUNC_INT(kd_mpi_vdec_stop_chn)
DEF_INT_FUNC_INT(kd_mpi_vdec_destroy_chn)
DEF_INT_FUNC_INT_STRUCTPTR_INT(kd_mpi_vdec_send_stream, k_vdec_stream)
DEF_INT_FUNC_INT_STRUCTPTR_STRUCTPTR_INT(kd_mpi_vdec_get_frame, k_video_frame_info, k_vdec_supplement_info)
DEF_INT_FUNC_INT_STRUCTPTR(kd_mpi_vdec_release_frame, k_video_frame_info)
DEF_INT_FUNC_INT_STRUCTPTR(kd_mpi_vdec_query_status, k_vdec_chn_status)
DEF_INT_FUNC_VOID(kd_mpi_vdec_close_fd)
DEF_INT_FUNC_INT_INT(kd_mpi_vdec_set_rotation)
DEF_INT_FUNC_INT_STRUCTPTR(kd_mpi_vdec_set_downscale, k_vdec_downscale)
DEF_INT_FUNC_INT_INT(kd_mpi_vdec_attach_vb_pool)
DEF_INT_FUNC_INT(kd_mpi_vdec_detach_vb_pool)
