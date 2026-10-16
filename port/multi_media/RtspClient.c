#include <string.h>

#include "RtspClient.h"
#include "imlib.h"
#include "multimedia_type.h"
#include "multimedia_wrap.h"
#include "py/misc.h"
#include "py/obj.h"
#include "py/runtime.h"
#include "py_image.h"

static int rtsp_unreserved(unsigned char c) {
    return (c >= '0' && c <= '9') || (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z')
        || c == '-' || c == '.' || c == '_' || c == '~';
}

static void rtsp_append_userinfo(vstr_t *out, const byte *text, size_t len) {
    for (size_t i = 0; i < len; i++) {
        unsigned char c = text[i];
        if (rtsp_unreserved(c)) {
            vstr_add_byte(out, c);
        } else {
            static const char hex[] = "0123456789ABCDEF";
            vstr_add_byte(out, '%');
            vstr_add_byte(out, hex[c >> 4]);
            vstr_add_byte(out, hex[c & 0x0f]);
        }
    }
}

// Percent-encode username and password into rtsp://user:pass@authority/path.
// With both left unset, the original URL is returned unchanged.
static mp_obj_t rtsp_url_with_userinfo(mp_obj_t url_in, mp_obj_t username, mp_obj_t password) {
    size_t url_len = 0;
    const char *url = mp_obj_str_get_str(url_in);
    url_len = strlen(url);
    if (username == mp_const_none && password == mp_const_none) {
        return url_in;
    }
    if (username == mp_const_none) {
        mp_raise_ValueError(MP_ERROR_TEXT("username is required when password is set"));
    }
    size_t user_len = 0;
    const byte *user = (const byte *)mp_obj_str_get_data(username, &user_len);
    size_t pass_len = 0;
    const byte *pass = (const byte *)"";
    if (password != mp_const_none) {
        pass = (const byte *)mp_obj_str_get_data(password, &pass_len);
    }
    if (url_len < 7 || memcmp(url, "rtsp://", 7) != 0) {
        mp_raise_ValueError(MP_ERROR_TEXT("url must start with rtsp://"));
    }
    const char *rest = url + 7;
    size_t rest_len = url_len - 7;
    const char *slash = memchr(rest, '/', rest_len);
    size_t auth_len = slash == NULL ? rest_len : (size_t)(slash - rest);
    if (memchr(rest, '@', auth_len) != NULL) {
        mp_raise_ValueError(MP_ERROR_TEXT("url already contains user info"));
    }
    vstr_t built;
    vstr_init(&built, url_len + (user_len + pass_len) * 3 + 2);
    vstr_add_strn(&built, "rtsp://", 7);
    rtsp_append_userinfo(&built, user, user_len);
    vstr_add_byte(&built, ':');
    rtsp_append_userinfo(&built, pass, pass_len);
    vstr_add_byte(&built, '@');
    vstr_add_strn(&built, rest, rest_len);
    return mp_obj_new_str_from_vstr(&built);
}

static const mp_arg_t rtsp_client_allowed_args[] = {
    { MP_QSTR_url, MP_ARG_REQUIRED | MP_ARG_OBJ, { .u_obj = MP_OBJ_NULL } },
    { MP_QSTR_cache_count, MP_ARG_INT, { .u_int = 60 } },
    { MP_QSTR_buffer_count, MP_ARG_INT, { .u_int = 6 } },
    { MP_QSTR_width, MP_ARG_INT, { .u_int = 0 } },
    { MP_QSTR_height, MP_ARG_INT, { .u_int = 0 } },
    { MP_QSTR_username, MP_ARG_OBJ, { .u_obj = mp_const_none } },
    { MP_QSTR_password, MP_ARG_OBJ, { .u_obj = mp_const_none } },
};

enum {
    ARG_url,
    ARG_cache_count,
    ARG_buffer_count,
    ARG_width,
    ARG_height,
    ARG_username,
    ARG_password,
};

typedef struct _rtsp_open_args_t {
    const char *url;
    int cache_count;
    int buffer_count;
    int width;
    int height;
} rtsp_open_args_t;

// Parse and validate constructor arguments. The returned string object owns cfg->url.
static mp_obj_t rtsp_client_parse(size_t n_args, const mp_obj_t *pos_args, mp_map_t *kw_args, rtsp_open_args_t *cfg) {
    mp_arg_val_t args[MP_ARRAY_SIZE(rtsp_client_allowed_args)];
    mp_arg_parse_all(n_args, pos_args, kw_args, MP_ARRAY_SIZE(rtsp_client_allowed_args), rtsp_client_allowed_args, args);

    mp_obj_t url_obj = rtsp_url_with_userinfo(args[ARG_url].u_obj, args[ARG_username].u_obj, args[ARG_password].u_obj);
    cfg->url = mp_obj_str_get_str(url_obj);
    cfg->cache_count = args[ARG_cache_count].u_int;
    cfg->buffer_count = args[ARG_buffer_count].u_int;
    cfg->width = args[ARG_width].u_int;
    cfg->height = args[ARG_height].u_int;
    if (strncmp(cfg->url, "rtsp://", 7) != 0) {
        mp_raise_ValueError(MP_ERROR_TEXT("url must start with rtsp://"));
    }
    if (cfg->cache_count < 1 || cfg->cache_count > 120 || cfg->buffer_count < 3 || cfg->buffer_count > 8) {
        mp_raise_ValueError(MP_ERROR_TEXT("cache_count is 1..120, buffer_count is 3..8"));
    }
    if ((cfg->width == 0) != (cfg->height == 0) || cfg->width < 0 || cfg->height < 0 ||
        (cfg->width % 2) != 0 || (cfg->height % 2) != 0) {
        mp_raise_ValueError(MP_ERROR_TEXT("width and height must both be 0 or positive even numbers"));
    }
    return url_obj;
}

static KdRtspPlayer *player_of(mp_obj_t self_in) {
    rtspclient_obj_t *self = MP_OBJ_TO_PTR(self_in);
    if (self->interp == NULL) {
        mp_raise_msg(&mp_type_OSError, MP_ERROR_TEXT("rtsp client is closed"));
    }
    return self->interp;
}

static mp_obj_t mp_rtsp_client_make_new(const mp_obj_type_t *type, size_t n_args, size_t n_kw, const mp_obj_t *args) {
    mp_arg_check_num(n_args, n_kw, 0, MP_ARRAY_SIZE(rtsp_client_allowed_args), true);
    mp_map_t kw_args;
    mp_map_init_fixed_table(&kw_args, n_kw, args + n_args);
    rtsp_open_args_t cfg;
    mp_obj_t url_obj = rtsp_client_parse(n_args, args, &kw_args, &cfg);
    if (RtspPlayer_count() >= 4) {
        mp_raise_msg(&mp_type_OSError, MP_ERROR_TEXT("at most 4 rtsp clients"));
    }
    rtspclient_obj_t *self = m_new_obj_with_finaliser(rtspclient_obj_t);
    self->base.type = type;
    self->interp = RtspPlayer_create();
    if (self->interp == NULL) {
        if (RtspPlayer_count() >= 4) {
            mp_raise_msg(&mp_type_OSError, MP_ERROR_TEXT("at most 4 rtsp clients"));
        }
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("rtsp client alloc failed"));
    }
    int ret = RtspPlayer_init(self->interp, cfg.url, cfg.cache_count, cfg.buffer_count, cfg.width, cfg.height);
    (void)url_obj;
    if (ret != 0) {
        RtspPlayer_destroy(self->interp);
        self->interp = NULL;
        mp_raise_msg_varg(&mp_type_OSError, MP_ERROR_TEXT("rtsp init failed: %d"), ret);
    }
    return MP_OBJ_FROM_PTR(self);
}

static mp_obj_t mp_rtsp_client_destroy(mp_obj_t self_in) {
    rtspclient_obj_t *self = MP_OBJ_TO_PTR(self_in);
    if (self->interp != NULL) {
        RtspPlayer_destroy(self->interp);
        self->interp = NULL;
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(rtsp_client_destroy_obj, mp_rtsp_client_destroy);

static mp_obj_t mp_rtsp_client_init(size_t n_args, const mp_obj_t *pos_args, mp_map_t *kw_args) {
    KdRtspPlayer *player = player_of(pos_args[0]);
    rtsp_open_args_t cfg;
    mp_obj_t url_obj = rtsp_client_parse(n_args - 1, pos_args + 1, kw_args, &cfg);
    int ret = RtspPlayer_init(player, cfg.url, cfg.cache_count, cfg.buffer_count, cfg.width, cfg.height);
    (void)url_obj;
    if (ret != 0) {
        mp_raise_msg_varg(&mp_type_OSError, MP_ERROR_TEXT("rtsp init failed: %d"), ret);
    }
    return MP_OBJ_NEW_SMALL_INT(0);
}
static MP_DEFINE_CONST_FUN_OBJ_KW(rtsp_client_init_obj, 1, mp_rtsp_client_init);

static int optional_even(mp_obj_t obj, int *out) {
    if (obj == mp_const_none) {
        *out = 0;
        return 0;
    }
    int value = mp_obj_get_int(obj);
    if (value <= 0 || (value % 2) != 0) {
        return -1;
    }
    *out = value;
    return 0;
}

static mp_obj_t mp_rtsp_client_bind_info(size_t n_args, const mp_obj_t *pos_args, mp_map_t *kw_args) {
    enum { ARG_x, ARG_y, ARG_width, ARG_height };
    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_x, MP_ARG_INT, { .u_int = 0 } },
        { MP_QSTR_y, MP_ARG_INT, { .u_int = 0 } },
        { MP_QSTR_width, MP_ARG_OBJ, { .u_obj = mp_const_none } },
        { MP_QSTR_height, MP_ARG_OBJ, { .u_obj = mp_const_none } },
    };
    mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all(n_args - 1, pos_args + 1, kw_args, MP_ARRAY_SIZE(allowed_args), allowed_args, args);

    int x = args[ARG_x].u_int;
    int y = args[ARG_y].u_int;
    int width = 0;
    int height = 0;
    if (x < 0 || y < 0 || (x % 2) != 0 || (y % 2) != 0) {
        mp_raise_ValueError(MP_ERROR_TEXT("x and y must be non-negative even numbers"));
    }
    if (optional_even(args[ARG_width].u_obj, &width) != 0 ||
        optional_even(args[ARG_height].u_obj, &height) != 0) {
        mp_raise_ValueError(MP_ERROR_TEXT("width and height must be positive even numbers"));
    }

    int mod_id = 0;
    int dev_id = 0;
    int chn_id = 0;
    int pix_format = 0;
    int ret = RtspPlayer_bind_info(player_of(pos_args[0]), x, y, &width, &height,
                                   &mod_id, &dev_id, &chn_id, &pix_format);
    if (ret != 0) {
        mp_raise_msg(&mp_type_OSError, MP_ERROR_TEXT("rtsp bind_info failed"));
    }

    mp_obj_t src_items[3] = {
        mp_obj_new_int(mod_id),
        mp_obj_new_int(dev_id),
        mp_obj_new_int(chn_id),
    };
    mp_obj_t rect_items[4] = {
        mp_obj_new_int(x),
        mp_obj_new_int(y),
        mp_obj_new_int(width),
        mp_obj_new_int(height),
    };
    mp_obj_t dict = mp_obj_new_dict(3);
    mp_obj_dict_store(dict, MP_OBJ_NEW_QSTR(MP_QSTR_src), mp_obj_new_tuple(3, src_items));
    mp_obj_dict_store(dict, MP_OBJ_NEW_QSTR(MP_QSTR_rect), mp_obj_new_tuple(4, rect_items));
    mp_obj_dict_store(dict, MP_OBJ_NEW_QSTR(MP_QSTR_pix_format), mp_obj_new_int(pix_format));
    return dict;
}
static MP_DEFINE_CONST_FUN_OBJ_KW(rtsp_client_bind_info_obj, 1, mp_rtsp_client_bind_info);

static mp_obj_t mp_rtsp_client_start(mp_obj_t self_in) {
    int ret = RtspPlayer_start(player_of(self_in));
    if (ret != 0) {
        mp_raise_msg_varg(&mp_type_OSError, MP_ERROR_TEXT("rtsp start failed: %d"), ret);
    }
    return MP_OBJ_NEW_SMALL_INT(0);
}
static MP_DEFINE_CONST_FUN_OBJ_1(rtsp_client_start_obj, mp_rtsp_client_start);

static mp_obj_t mp_rtsp_client_stop(mp_obj_t self_in) {
    int ret = RtspPlayer_stop(player_of(self_in));
    if (ret != 0) {
        mp_raise_msg_varg(&mp_type_OSError, MP_ERROR_TEXT("rtsp stop failed: %d"), ret);
    }
    return MP_OBJ_NEW_SMALL_INT(0);
}
static MP_DEFINE_CONST_FUN_OBJ_1(rtsp_client_stop_obj, mp_rtsp_client_stop);

static mp_obj_t mp_rtsp_client_deinit(mp_obj_t self_in) {
    rtspclient_obj_t *self = MP_OBJ_TO_PTR(self_in);
    if (self->interp != NULL) {
        RtspPlayer_destroy(self->interp);
        self->interp = NULL;
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(rtsp_client_deinit_obj, mp_rtsp_client_deinit);

static mp_obj_t mp_rtsp_client_video_size(mp_obj_t self_in) {
    int width = 0;
    int height = 0;
    RtspPlayer_video_size(player_of(self_in), &width, &height);
    mp_obj_t items[2] = { mp_obj_new_int(width), mp_obj_new_int(height) };
    return mp_obj_new_tuple(2, items);
}
static MP_DEFINE_CONST_FUN_OBJ_1(rtsp_client_video_size_obj, mp_rtsp_client_video_size);

static mp_obj_t mp_rtsp_client_get_frame(size_t n_args, const mp_obj_t *pos_args, mp_map_t *kw_args) {
    enum { ARG_timeout_ms };
    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_timeout_ms, MP_ARG_INT, { .u_int = 100 } },
    };
    mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all(n_args - 1, pos_args + 1, kw_args, MP_ARRAY_SIZE(allowed_args), allowed_args, args);

    KdRtspPlayer *player = player_of(pos_args[0]);
    void *image = NULL;
    MP_THREAD_GIL_EXIT();
    int ret = RtspPlayer_get_frame(player, args[ARG_timeout_ms].u_int, &image);
    MP_THREAD_GIL_ENTER();
    if (ret == 1) {
        return mp_const_none;
    }
    if (ret == -3) {
        mp_raise_msg(&mp_type_OSError, MP_ERROR_TEXT("rtsp connection closed"));
    }
    if (ret != 0 || image == NULL) {
        mp_raise_msg(&mp_type_OSError, MP_ERROR_TEXT("rtsp client is not started"));
    }
    RtspPlayerFrame *view = (RtspPlayerFrame *)image;
    image_t img;
    memset(&img, 0, sizeof(img));
    image_init(&img, view->width, view->height, PIXFORMAT_RGBP888, view->size, view->data);
    img.phy_addr = view->phy_addr;
    img.alloc_type = ALLOC_REF;
    img.cache = 1;
    img.pool_id = view->pool_id;
    return py_image_from_struct(&img);
}
static MP_DEFINE_CONST_FUN_OBJ_KW(rtsp_client_get_frame_obj, 1, mp_rtsp_client_get_frame);

static mp_obj_t mp_rtsp_client_check(mp_obj_t self_in) {
    if (RtspPlayer_check(player_of(self_in)) != 0) {
        mp_raise_msg(&mp_type_OSError, MP_ERROR_TEXT("rtsp connection closed"));
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(rtsp_client_check_obj, mp_rtsp_client_check);

static const mp_rom_map_elem_t rtsp_client_locals_dict_table[] = {
    { MP_ROM_QSTR(MP_QSTR___del__), MP_ROM_PTR(&rtsp_client_destroy_obj) },
    { MP_ROM_QSTR(MP_QSTR_init), MP_ROM_PTR(&rtsp_client_init_obj) },
    { MP_ROM_QSTR(MP_QSTR_bind_info), MP_ROM_PTR(&rtsp_client_bind_info_obj) },
    { MP_ROM_QSTR(MP_QSTR_start), MP_ROM_PTR(&rtsp_client_start_obj) },
    { MP_ROM_QSTR(MP_QSTR_stop), MP_ROM_PTR(&rtsp_client_stop_obj) },
    { MP_ROM_QSTR(MP_QSTR_deinit), MP_ROM_PTR(&rtsp_client_deinit_obj) },
    { MP_ROM_QSTR(MP_QSTR_video_size), MP_ROM_PTR(&rtsp_client_video_size_obj) },
    { MP_ROM_QSTR(MP_QSTR_get_frame), MP_ROM_PTR(&rtsp_client_get_frame_obj) },
    { MP_ROM_QSTR(MP_QSTR_check), MP_ROM_PTR(&rtsp_client_check_obj) },
};
static MP_DEFINE_CONST_DICT(rtsp_client_locals_dict, rtsp_client_locals_dict_table);

MP_DEFINE_CONST_OBJ_TYPE(
    rtsp_client_type,
    MP_QSTR_RtspClient,
    MP_TYPE_FLAG_NONE,
    make_new, mp_rtsp_client_make_new,
    locals_dict, &rtsp_client_locals_dict
);
