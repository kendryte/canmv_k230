#include "multimedia_wrap.h"
#include "multimedia_type.h"
#include "RtspPusher.h"
#include "py/obj.h"
#include "py/runtime.h"
#include "py/binary.h"
#include "string.h"
#include <stdlib.h>
#include <stdio.h>


STATIC KdRtspPusher *mp_rtsppusher_get(mp_obj_t self_in) {
    rtsppusher_obj_t *self = MP_OBJ_TO_PTR(self_in);
    if (self->interp == NULL) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("RTSP pusher is deinitialized"));
    }
    return self->interp;
}


// init
STATIC mp_obj_t mp_rtsppusher_create() {
    rtsppusher_obj_t *self = m_new_obj_with_finaliser(rtsppusher_obj_t);
    self->interp = RtspPusher_create();
    self->base.type = &rtsp_pusher_type;
    return MP_OBJ_FROM_PTR(self);
}
STATIC MP_DEFINE_CONST_FUN_OBJ_0(rtsppusher_create_obj, mp_rtsppusher_create);

STATIC mp_obj_t mp_rtsppusher_destroy(mp_obj_t self_in) {
    rtsppusher_obj_t *self = MP_OBJ_TO_PTR(self_in);
    if (self->interp != NULL) {
        RtspPusher_destroy(self->interp);
        self->interp = NULL;
    }
    return mp_const_none;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_1(rtsppusher_destroy_obj, mp_rtsppusher_destroy);


//| # Auto-generated CanMV stub docs. Edit the signatures/docstrings here.
//| module: multimedia
//| class rtsp_pusher:
//|     """multimedia.rtsp_pusher object."""
//|     def __init__(self) -> None:
//|         """Create a multimedia.rtsp_pusher object."""
//|     def rtsppusher_create(self, /) -> Any:
//|         """Perform rtsppusher create for multimedia.rtsp_pusher."""
//|     def rtsppusher_init(self, video_width: Any, video_height: Any, url: Any, fps: Any = 25, transport: Any = "tcp", /) -> Any:
//|         """Perform rtsppusher init for multimedia.rtsp_pusher."""
//|     def rtsppusher_deinit(self, /) -> Any:
//|         """Perform rtsppusher deinit for multimedia.rtsp_pusher."""
//|     def rtsppusher_destroy(self, /) -> Any:
//|         """Release resources held by multimedia.rtsp_pusher."""
//|     def rtsppusher_open(self, /) -> Any:
//|         """Perform rtsppusher open for multimedia.rtsp_pusher."""
//|     def rtsppusher_close(self, /) -> Any:
//|         """Perform rtsppusher close for multimedia.rtsp_pusher."""
//|     def rtsppusher_pushvideodata(self, data: Any, size: Any, key_frame: Any, timestamp: Any, /) -> Any:
//|         """Perform rtsppusher pushvideodata for multimedia.rtsp_pusher."""
//|     def rtsppusher_pushvideoheader(self, data: Any, size: Any, /) -> Any:
//|         """Push SPS/PPS header (Annex-B) to multimedia.rtsp_pusher. Must be called before rtsppusher_open()."""

STATIC mp_obj_t mp_rtsppusher_init(size_t n_args, const mp_obj_t *args) {
    // args[0]: self
    // args[1]: video_width
    // args[2]: video_height
    // args[3]: url
    // args[4]: fps (optional, default 25)
    // args[5]: transport (optional, default "tcp")
    int video_width = mp_obj_get_int(args[1]);
    int video_height = mp_obj_get_int(args[2]);
    const char *url = mp_obj_str_get_str(args[3]);
    int fps = 25;
    const char *transport = "tcp";
    if (n_args > 4) {
        fps = mp_obj_get_int(args[4]);
    }
    if (n_args > 5) {
        transport = mp_obj_str_get_str(args[5]);
    }
    return mp_obj_new_int(RtspPusher_Init(mp_rtsppusher_get(args[0]), video_width, video_height, url, fps, transport));
}
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(rtsppusher_init_obj, 4, 6, mp_rtsppusher_init);

STATIC mp_obj_t mp_rtsppusher_deinit(mp_obj_t self_in) {
    RtspPusher_DeInit(mp_rtsppusher_get(self_in));
    return mp_const_none;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_1(rtsppusher_deinit_obj, mp_rtsppusher_deinit);

STATIC mp_obj_t mp_rtsppusher_open(mp_obj_t self_in) {
    return mp_obj_new_int(RtspPusher_Open(mp_rtsppusher_get(self_in)));
}
STATIC MP_DEFINE_CONST_FUN_OBJ_1(rtsppusher_open_obj, mp_rtsppusher_open);

STATIC mp_obj_t mp_rtsppusher_close(mp_obj_t self_in) {
    RtspPusher_Close(mp_rtsppusher_get(self_in));
    return mp_const_none;
}
STATIC MP_DEFINE_CONST_FUN_OBJ_1(rtsppusher_close_obj, mp_rtsppusher_close);

STATIC mp_obj_t mp_rtsppusher_pushvideodata(size_t n_args, const mp_obj_t *args) {
    // args[0]: self
    // args[1]: data
    // args[2]: size
    // args[3]: key_frame
    // args[4]: timestamp (microseconds)
    const uint8_t *data = (const uint8_t *)mp_obj_str_get_str(args[1]);
    size_t size = mp_obj_get_int(args[2]);
    bool key_frame = mp_obj_get_int(args[3]) ? true : false;
    uint64_t timestamp = mp_obj_get_int(args[4]);
    return mp_obj_new_int(RtspPusher_PushVideoData(mp_rtsppusher_get(args[0]), data, size, key_frame, timestamp));
}
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(rtsppusher_pushvideodata_obj, 5, 5, mp_rtsppusher_pushvideodata);

STATIC mp_obj_t mp_rtsppusher_pushvideoheader(size_t n_args, const mp_obj_t *args) {
    // args[0]: self
    // args[1]: data (SPS/PPS, Annex-B)
    // args[2]: size
    const uint8_t *data = (const uint8_t *)mp_obj_str_get_str(args[1]);
    size_t size = mp_obj_get_int(args[2]);
    return mp_obj_new_int(RtspPusher_PushVideoHeader(mp_rtsppusher_get(args[0]), data, size));
}
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(rtsppusher_pushvideoheader_obj, 3, 3, mp_rtsppusher_pushvideoheader);


STATIC const mp_rom_map_elem_t RtspPusher_locals_dict_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_rtsppusher) },
    { MP_ROM_QSTR(MP_QSTR_rtsppusher_create), MP_ROM_PTR(&rtsppusher_create_obj) },
    { MP_ROM_QSTR(MP_QSTR_rtsppusher_destroy), MP_ROM_PTR(&rtsppusher_destroy_obj) },
    { MP_ROM_QSTR(MP_QSTR___del__), MP_ROM_PTR(&rtsppusher_destroy_obj) },
    { MP_ROM_QSTR(MP_QSTR_rtsppusher_init), MP_ROM_PTR(&rtsppusher_init_obj) },
    { MP_ROM_QSTR(MP_QSTR_rtsppusher_deinit), MP_ROM_PTR(&rtsppusher_deinit_obj) },
    { MP_ROM_QSTR(MP_QSTR_rtsppusher_open), MP_ROM_PTR(&rtsppusher_open_obj) },
    { MP_ROM_QSTR(MP_QSTR_rtsppusher_close), MP_ROM_PTR(&rtsppusher_close_obj) },
    { MP_ROM_QSTR(MP_QSTR_rtsppusher_pushvideodata), MP_ROM_PTR(&rtsppusher_pushvideodata_obj) },
    { MP_ROM_QSTR(MP_QSTR_rtsppusher_pushvideoheader), MP_ROM_PTR(&rtsppusher_pushvideoheader_obj) },
};

STATIC MP_DEFINE_CONST_DICT(RtspPusher_locals_dict, RtspPusher_locals_dict_table);

const mp_obj_module_t mp_module_rtsppusher = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&RtspPusher_locals_dict,
};

MP_REGISTER_EXTENSIBLE_MODULE (MP_QSTR_rtsppusher, mp_module_rtsppusher);

MP_DEFINE_CONST_OBJ_TYPE(
    rtsp_pusher_type,
    MP_QSTR_rtsppusher,
    MP_TYPE_FLAG_NONE,
    make_new,mp_rtsppusher_create,
    locals_dict, &RtspPusher_locals_dict
    );
