#pragma once

#include "mpi_vb_api.h"
#include "mpi_sys_api.h"
#include "mpi_vicap_api.h"

typedef struct 
{
    void *virt_addr; // self.virt_addr = virt_addr
    k_u64 phys_addr; // self.phys_addr = phys_addr

    k_vb_blk_handle handle; // self.handle = handle

    k_s32 pool_id;          // self.pool_id = pool_id
    k_u32 size; // self.size = size, user set
}vb_block_info;

typedef struct {
    k_vicap_dev dev_num;
    k_vicap_chn chn_num;
    k_vicap_dump_format foramt;
    k_u32 milli_sec;
} vb_mgmt_dump_vicap_config;

typedef struct {
    k_u64 magic;

    k_u64 image_size;
    vb_mgmt_dump_vicap_config cfg;
    k_video_frame_info vf_info;
} vb_mgmt_vicap_image;

// in ide_dbg.c
extern k_s32 vb_mgmt_init(void);

extern k_s32 vb_mgmt_deinit(void);

extern k_s32 vb_mgmt_get_block(vb_block_info *info);

extern k_s32 vb_mgmt_put_block(vb_block_info *info);

extern k_s32 vb_mgmt_vicap_dev_inited(k_u32 id);

extern k_s32 vb_mgmt_vicap_dev_deinited(k_u32 id);

extern k_s32 vb_mgmt_push_link_info(k_mpp_chn *src, k_mpp_chn *dst);

extern k_s32 vb_mgmt_pop_link_info(k_mpp_chn *src, k_mpp_chn *dst);

extern k_s32 vb_mgmt_enable_video_layer(k_u32 layer);
extern k_s32 vb_mgmt_disable_video_layer(k_u32 layer);

extern k_s32 vb_mgmt_enable_osd_layer(k_u32 layer);
extern k_s32 vb_mgmt_disable_osd_layer(k_u32 layer);

struct vb_mgmt_dump_vicap_config;
struct vb_mgmt_vicap_image;
k_s32 vb_mgmt_dump_vicap_frame(vb_mgmt_dump_vicap_config *cfg, vb_mgmt_vicap_image *image);
k_s32 vb_mgmt_release_vicap_frame(vb_mgmt_vicap_image *image);

extern void vb_mgmt_py_at_exit(void);
