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

DEF_INT_FUNC_INT_STRUCTPTR(kd_mpi_venc_create_chn, k_venc_chn_attr)
DEF_INT_FUNC_INT(kd_mpi_venc_start_chn)
DEF_INT_FUNC_INT(kd_mpi_venc_stop_chn)
DEF_INT_FUNC_INT(kd_mpi_venc_destroy_chn)
DEF_INT_FUNC_INT_STRUCTPTR_INT_GIL(kd_mpi_venc_send_frame, k_video_frame_info)
DEF_INT_FUNC_INT_STRUCTPTR_INT_GIL(kd_mpi_venc_get_stream, k_venc_stream)
DEF_INT_FUNC_INT_STRUCTPTR(kd_mpi_venc_release_stream, k_venc_stream)
DEF_INT_FUNC_INT_STRUCTPTR(kd_mpi_venc_query_status, k_venc_chn_status)
DEF_INT_FUNC_VOID(kd_mpi_venc_close_fd)
DEF_INT_FUNC_INT_INT(kd_mpi_venc_set_rotation)
DEF_INT_FUNC_INT_STRUCTPTR(kd_mpi_venc_get_rotation, k_u32)
DEF_INT_FUNC_INT_INT(kd_mpi_venc_set_mirror)
DEF_INT_FUNC_INT_STRUCTPTR(kd_mpi_venc_get_mirror, k_u32)
DEF_INT_FUNC_INT_INT(kd_mpi_venc_enable_idr)
DEF_INT_FUNC_INT(kd_mpi_venc_request_idr)
DEF_INT_FUNC_INT_STRUCTPTR(kd_mpi_venc_set_h265_sao, k_venc_h265_sao)
DEF_INT_FUNC_INT_STRUCTPTR(kd_mpi_venc_get_h265_sao, k_venc_h265_sao)
DEF_INT_FUNC_INT_INT(kd_mpi_venc_set_dblk)
DEF_INT_FUNC_INT_STRUCTPTR(kd_mpi_venc_get_dblk, k_u32)
DEF_INT_FUNC_INT_STRUCTPTR(kd_mpi_venc_set_h264_entropy, k_venc_h264_entropy)
DEF_INT_FUNC_INT_STRUCTPTR(kd_mpi_venc_get_h264_entropy, k_venc_h264_entropy)
DEF_INT_FUNC_INT_STRUCTPTR(kd_mpi_venc_set_h265_entropy, k_venc_h265_entropy)
DEF_INT_FUNC_INT_STRUCTPTR(kd_mpi_venc_get_h265_entropy, k_venc_h265_entropy)
DEF_INT_FUNC_INT(kd_mpi_venc_start_2d_chn)
DEF_INT_FUNC_INT(kd_mpi_venc_stop_2d_chn)
DEF_INT_FUNC_INT_STRUCTPTR(kd_mpi_venc_send_2d_frame, k_video_frame_info)
DEF_INT_FUNC_INT_STRUCTPTR(kd_mpi_venc_get_2d_frame, k_video_frame_info)
DEF_INT_FUNC_INT_INT(kd_mpi_venc_set_2d_mode)
DEF_INT_FUNC_INT_STRUCTPTR(kd_mpi_venc_get_2d_mode, k_u32)
DEF_INT_FUNC_INT_STRUCTPTR(kd_mpi_venc_set_2d_csc_param, k_venc_2d_csc_attr)
DEF_INT_FUNC_INT_STRUCTPTR(kd_mpi_venc_get_2d_csc_param, k_venc_2d_csc_attr)
DEF_INT_FUNC_INT_INT_STRUCTPTR(kd_mpi_venc_set_2d_osd_param, k_venc_2d_osd_attr)
DEF_INT_FUNC_INT_INT_STRUCTPTR(kd_mpi_venc_get_2d_osd_param, k_venc_2d_osd_attr)
DEF_INT_FUNC_INT_INT_STRUCTPTR(kd_mpi_venc_set_2d_border_param, k_venc_2d_border_attr)
DEF_INT_FUNC_INT_INT_STRUCTPTR(kd_mpi_venc_get_2d_border_param, k_venc_2d_border_attr)
DEF_INT_FUNC_INT_ARRAY(kd_mpi_venc_set_2d_custom_coef, k_s16)
DEF_INT_FUNC_INT_ARRAY(kd_mpi_venc_get_2d_custom_coef, k_s16)
DEF_INT_FUNC_INT_INT(kd_mpi_venc_set_2d_color_gamut)
DEF_INT_FUNC_INT_STRUCTPTR(kd_mpi_venc_get_2d_color_gamut, k_u32)
DEF_INT_FUNC_INT(kd_mpi_venc_attach_2d)
DEF_INT_FUNC_INT(kd_mpi_venc_detach_2d)
DEF_INT_FUNC_INT_INT(kd_mpi_venc_attach_vb_pool)
DEF_INT_FUNC_INT(kd_mpi_venc_detach_vb_pool)
