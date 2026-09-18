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

DEF_INT_FUNC_INT_STRUCTPTR(kd_mpi_vicap_get_sensor_info, k_vicap_sensor_info)
DEF_INT_FUNC_STRUCTPTR(kd_mpi_vicap_get_sensor_fd, k_vicap_sensor_attr)
DEF_INT_FUNC_INT_STRUCT(kd_mpi_vicap_set_dev_attr, k_vicap_dev_attr)
DEF_INT_FUNC_INT_STRUCTPTR(kd_mpi_vicap_get_dev_attr, k_vicap_dev_attr)
DEF_INT_FUNC_INT_INT_STRUCT(kd_mpi_vicap_set_chn_attr, k_vicap_chn_attr)
DEF_INT_FUNC_INT_INT_STRUCTPTR(kd_mpi_vicap_get_chn_attr, k_vicap_chn_attr)
DEF_INT_FUNC_INT(kd_mpi_vicap_init)
DEF_INT_FUNC_INT(kd_mpi_vicap_deinit)
DEF_INT_FUNC_INT(kd_mpi_vicap_start_stream)
DEF_INT_FUNC_INT(kd_mpi_vicap_stop_stream)
DEF_INT_FUNC_INT_INT_STRUCTPTR(kd_mpi_vicap_dump_release, k_video_frame_info)
DEF_INT_FUNC_INT_STRUCTPTR_INT(kd_mpi_vicap_set_vi_drop_frame, k_vicap_drop_frame)
DEF_INT_FUNC_INT_INT(kd_mpi_vicap_set_database_parse_mode)
DEF_INT_FUNC_INT(kd_mpi_vicap_tpg_enable)
DEF_INT_FUNC_INT_ARRAY_INT(kd_mpi_vicap_load_image, void)
DEF_INT_FUNC_STRUCTPTR_STRUCTPTR_INT(kd_mpi_sensor_adapt_get_ex, k_vicap_probe_config, k_vicap_sensor_info)

DEF_INT_FUNC_INT_STRUCT(kd_mpi_sensor_again_set, k_sensor_gain)
DEF_INT_FUNC_INT_STRUCTPTR(kd_mpi_sensor_again_get, k_sensor_gain)

DEF_INT_FUNC_STRUCTPTR_STRUCTPTR(vb_mgmt_dump_vicap_frame, vb_mgmt_dump_vicap_config, vb_mgmt_vicap_image)
DEF_INT_FUNC_STRUCTPTR(vb_mgmt_release_vicap_frame, vb_mgmt_vicap_image)
