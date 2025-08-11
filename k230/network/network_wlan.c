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

#include "py/obj.h"
#include "py/qstr.h"
#include "py/runtime.h"

#include "network/modnetwork.h"

#ifdef CONFIG_ENABLE_NETWORK_RT_WLAN
/* rt_wlan_info **************************************************************/
static const mp_obj_type_t py_rt_wlan_info_type;

typedef struct _py_rt_wlan_info_obj_t {
    mp_obj_base_t         base;
    struct rt_wlan_info_t _cobj;
} py_rt_wlan_info_obj_t;

static const char* rt_wlan_security_string(enum rt_wlan_security_t security)
{
    switch (security) {
    case SECURITY_OPEN:
        return "SECURITY_OPEN";
    case SECURITY_WEP_PSK:
        return "SECURITY_WEP_PSK";
    case SECURITY_WEP_SHARED:
        return "SECURITY_WEP_SHARED";
    case SECURITY_WPA_TKIP_PSK:
        return "SECURITY_WPA_TKIP_PSK";
    case SECURITY_WPA_TKIP_8021X:
        return "SECURITY_WPA_TKIP_8021X";
    case SECURITY_WPA_AES_PSK:
        return "SECURITY_WPA_AES_PSK";
    case SECURITY_WPA_AES_8021X:
        return "SECURITY_WPA_AES_8021X";
    case SECURITY_WPA2_AES_PSK:
        return "SECURITY_WPA2_AES_PSK";
    case SECURITY_WPA2_AES_8021X:
        return "SECURITY_WPA2_AES_8021X";
    case SECURITY_WPA2_TKIP_PSK:
        return "SECURITY_WPA2_TKIP_PSK";
    case SECURITY_WPA2_TKIP_8021X:
        return "SECURITY_WPA2_TKIP_8021X";
    case SECURITY_WPA2_MIXED_PSK:
        return "SECURITY_WPA2_MIXED_PSK";
    case SECURITY_WPA_WPA2_MIXED_PSK:
        return "SECURITY_WPA_WPA2_MIXED_PSK";
    case SECURITY_WPA_WPA2_MIXED_8021X:
        return "SECURITY_WPA_WPA2_MIXED_8021X";
    case SECURITY_WPA2_AES_CMAC:
        return "SECURITY_WPA2_AES_CMAC";
    case SECURITY_WPS_OPEN:
        return "SECURITY_WPS_OPEN";
    case SECURITY_WPS_SECURE:
        return "SECURITY_WPS_SECURE";
    case SECURITY_WPA3_AES_PSK:
        return "SECURITY_WPA3_AES_PSK";
    default:
        return "UNKNOWN";
    }

    return NULL;
}

static const char* rt_wlan_band_string(enum rt_802_11_band_t band)
{
    switch (band) {
    case RT_802_11_BAND_5GHZ:
        return "5G";
    case RT_802_11_BAND_2_4GHZ:
        return "2.4G";
    default:
        return "UNKNOWN";
    }

    return NULL;
}

static mp_obj_t py_rt_wlan_info_from_struct(struct rt_wlan_info_t* info)
{
    py_rt_wlan_info_obj_t* o = mp_obj_malloc(py_rt_wlan_info_obj_t, &py_rt_wlan_info_type);

    memcpy(&o->_cobj, info, sizeof(o->_cobj));

    return o;
}

static mp_obj_t py_rt_wlan_info_make_new(const mp_obj_type_t* type, size_t n_args, size_t n_kw, const mp_obj_t* all_args)
{
    enum { ARG_ssid, ARG_bssid, ARG_channel, ARG_security, ARG_band, ARG_hidden };
    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_ssid, MP_ARG_OBJ, { .u_obj = mp_const_none } },
        { MP_QSTR_bssid, MP_ARG_OBJ, { .u_obj = mp_const_none } },
        { MP_QSTR_channel, MP_ARG_INT, { .u_int = 1 } },
        { MP_QSTR_rssi, MP_ARG_INT, { .u_int = -99 } },
        { MP_QSTR_security, MP_ARG_INT, { .u_int = SECURITY_OPEN } },
        { MP_QSTR_band, MP_ARG_INT, { .u_int = RT_802_11_BAND_2_4GHZ } },
        { MP_QSTR_hidden, MP_ARG_INT, { .u_int = 0 } },
    };
    mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all_kw_array(n_args, n_kw, all_args, MP_ARRAY_SIZE(allowed_args), allowed_args, args);

    struct rt_wlan_info_t info;
    memset(&info, 0, sizeof(info));

    if (mp_const_none != args[ARG_ssid].u_obj) {
        const char* ssid     = mp_obj_str_get_str(args[ARG_ssid].u_obj);
        int         ssid_len = strlen(ssid);
        if ((0x00 == ssid_len) || (RT_WLAN_SSID_MAX_LENGTH < ssid_len)) {
            mp_raise_msg_varg(&mp_type_OSError, MP_ERROR_TEXT("SSID can't be empty, and can't longer than %d"),
                              RT_WLAN_SSID_MAX_LENGTH);
        }
        strncpy((char*)info.ssid.val, ssid, RT_WLAN_SSID_MAX_LENGTH);
        info.ssid.len = strlen(ssid);
    }

    if (mp_const_none != args[ARG_bssid].u_obj) {
        uint8_t   bssid[RT_WLAN_BSSID_MAX_LENGTH];
        mp_obj_t* items;
        mp_obj_get_array_fixed_n(args[ARG_bssid].u_obj, RT_WLAN_BSSID_MAX_LENGTH, &items);
        for (int i = 0; i < RT_WLAN_BSSID_MAX_LENGTH; i++) {
            bssid[i] = (uint8_t)mp_obj_get_int(items[i]);
        }
        memcpy(&info.bssid[0], bssid, RT_WLAN_BSSID_MAX_LENGTH);
    }

    info.channel  = args[ARG_channel].u_int;
    info.security = args[ARG_security].u_int;
    info.band     = args[ARG_band].u_int;
    info.hidden   = args[ARG_hidden].u_int;

    return py_rt_wlan_info_from_struct(&info);
}

static void* py_rt_wlan_info_cobj(mp_obj_t rt_wlan_info)
{
    if (!mp_obj_is_type(rt_wlan_info, &py_rt_wlan_info_type)) {
        mp_raise_TypeError(MP_ERROR_TEXT("expected rt_wlan_info object"));
    }
    return &((py_rt_wlan_info_obj_t*)rt_wlan_info)->_cobj;
}

static void py_rt_wlan_info_print(const mp_print_t* print, mp_obj_t self_in, mp_print_kind_t kind)
{
    py_rt_wlan_info_obj_t* self = self_in;
    struct rt_wlan_info_t* info = py_rt_wlan_info_cobj(self);

    mp_printf(print,
              "{\"ssid\":\"%s\", \"bssid\":%02X:%02X:%02X:%02X:%02X:%02X, \"channel\":%d, \"rssi\":%d, \"security\":\"%s\", "
              "\"band\":\"%s\", \"hidden\":%d}",
              info->ssid.val, info->bssid[0], info->bssid[1], info->bssid[2], info->bssid[3], info->bssid[4], info->bssid[5],
              info->channel, info->rssi, rt_wlan_security_string(info->security), rt_wlan_band_string(info->band),
              info->hidden);
}

static void py_rt_wlan_info_attr(mp_obj_t self_in, qstr attr, mp_obj_t* dest)
{
    py_rt_wlan_info_obj_t* self = self_in;
    struct rt_wlan_info_t* info = py_rt_wlan_info_cobj(self);

    if (MP_OBJ_NULL == dest[0]) {
        // load attribute
        switch (attr) {
        case MP_QSTR_ssid:
            dest[0] = mp_obj_new_bytes(info->ssid.val, info->ssid.len);
            break;
        case MP_QSTR_bssid:
            dest[0] = mp_obj_new_bytes(info->bssid, RT_WLAN_BSSID_MAX_LENGTH);
            break;
        case MP_QSTR_channel:
            dest[0] = MP_OBJ_NEW_SMALL_INT(info->channel);
            break;
        case MP_QSTR_rssi:
            dest[0] = MP_OBJ_NEW_SMALL_INT(info->rssi);
            break;
        case MP_QSTR_security:
            dest[0] = MP_OBJ_NEW_SMALL_INT(info->security);
            break;
        case MP_QSTR_band:
            dest[0] = MP_OBJ_NEW_SMALL_INT(info->band);
            break;
        case MP_QSTR_hidden:
            dest[0] = MP_OBJ_NEW_SMALL_INT(info->hidden);
            break;
        default:
            dest[1] = MP_OBJ_SENTINEL; // continue lookup in locals_dict
            break;
        }
    } else if (MP_OBJ_SENTINEL == dest[0]) {
        // store attribute
        switch (attr) {
        case MP_QSTR_ssid: {
            const char* ssid = mp_obj_str_get_str(dest[1]);

            strncpy((char*)info->ssid.val, ssid, RT_WLAN_SSID_MAX_LENGTH);
            info->ssid.len = strlen(ssid);
        } break;
        case MP_QSTR_bssid: {
            uint8_t   bssid[RT_WLAN_BSSID_MAX_LENGTH];
            mp_obj_t* items;
            mp_obj_get_array_fixed_n(dest[1], RT_WLAN_BSSID_MAX_LENGTH, &items);
            for (int i = 0; i < RT_WLAN_BSSID_MAX_LENGTH; i++) {
                bssid[i] = (uint8_t)mp_obj_get_int(items[i]);
            }
            memcpy(info->bssid, bssid, RT_WLAN_BSSID_MAX_LENGTH);
        } break;
        case MP_QSTR_channel:
            info->channel = MP_OBJ_SMALL_INT_VALUE(dest[1]);
            break;
        case MP_QSTR_rssi:
            info->rssi = MP_OBJ_SMALL_INT_VALUE(dest[1]);
            break;
        case MP_QSTR_security:
            info->security = MP_OBJ_SMALL_INT_VALUE(dest[1]);
            break;
        case MP_QSTR_band:
            info->band = MP_OBJ_SMALL_INT_VALUE(dest[1]);
            break;
        case MP_QSTR_hidden:
            info->hidden = MP_OBJ_SMALL_INT_VALUE(dest[1]);
            break;
        default:
            // not support set, directly return
            return;
        }
        dest[0] = MP_OBJ_NULL;
    }
}

/* clang-format off */
static MP_DEFINE_CONST_OBJ_TYPE(
    py_rt_wlan_info_type,
    MP_QSTR_rt_wlan_info,
    MP_TYPE_FLAG_NONE,
    make_new, py_rt_wlan_info_make_new,
    print, py_rt_wlan_info_print,
    attr, py_rt_wlan_info_attr
);
/* clang-format on */

/* network_rt_wlan ***********************************************************/
static mp_obj_t network_rt_wlan_scan(size_t n_args, const mp_obj_t* args)
{
    py_rt_net_obj_t* self = MP_OBJ_TO_PTR(args[0]);
    mp_obj_t         scan_list;

    int                   ap_num = -1, result = -1;
    struct rt_wlan_info_t ap_infos[RT_WLAN_STA_SCAN_MAX_AP];
    const char*           ssid = NULL;

    if (MOD_NETWORK_STA_IF != self->itf) {
        mp_raise_msg(&mp_type_OSError, MP_ERROR_TEXT("ap mode not support scan"));
    }

    if (0x02 == n_args) {
        ssid = mp_obj_str_get_str(args[1]);
        if (0x00 == strlen(ssid)) {
            ssid = NULL;
        }
    }

    if (ssid) {
        ap_num = 1;
        result = netmgmt_wlan_sta_scan_with_ssid((char*)ssid, ap_infos);
    } else {
        result = netmgmt_wlan_sta_scan(&ap_num, ap_infos);
    }

    if (0x00 != result) {
        ap_num = 0;
        mp_printf(&mp_plat_print, "run scan failed.\n");
    }
    scan_list = mp_obj_new_list(0, NULL);

    for (int32_t i = 0; i < ap_num; i++) {
        mp_obj_t info = py_rt_wlan_info_from_struct(&ap_infos[i]);
        mp_obj_list_append(scan_list, info);
    }

    return scan_list;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(network_rt_wlan_scan_obj, 1, 2, network_rt_wlan_scan);

static mp_obj_t network_rt_wlan_connect(mp_uint_t n_args, const mp_obj_t* pos_args, mp_map_t* kw_args)
{
    py_rt_net_obj_t* self = MP_OBJ_TO_PTR(pos_args[0]);

    enum { ARG_ssid, ARG_key, ARG_info };
    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_ssid, MP_ARG_OBJ, { .u_obj = mp_const_none } },
        { MP_QSTR_key, MP_ARG_REQUIRED | MP_ARG_OBJ, { .u_obj = mp_const_none } },
        { MP_QSTR_info, MP_ARG_KW_ONLY | MP_ARG_OBJ, { .u_obj = mp_const_none } },
    };

    mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all(n_args - 1, pos_args + 1, kw_args, MP_ARRAY_SIZE(allowed_args), allowed_args, args);

    int                   use_info = 0, result = -1;
    struct rt_wlan_info_t info;
    const char*           ssid = NULL;

    if (mp_const_none != args[ARG_ssid].u_obj) {
        use_info = 0x00;

        ssid         = mp_obj_str_get_str(args[ARG_ssid].u_obj);
        int ssid_len = strlen(ssid);
        if ((0x00 == ssid_len) || (RT_WLAN_SSID_MAX_LENGTH < ssid_len)) {
            mp_raise_msg_varg(&mp_type_OSError, MP_ERROR_TEXT("SSID can't be empty, and can't longer than %d"),
                              RT_WLAN_SSID_MAX_LENGTH);
        }
    } else if (mp_const_none != args[ARG_info].u_obj) {
        use_info = 1;

        struct rt_wlan_info_t* _info = py_rt_wlan_info_cobj(args[ARG_info].u_obj);
        memcpy(&info, _info, sizeof(struct rt_wlan_info_t));
    } else {
        mp_raise_msg(&mp_type_OSError, MP_ERROR_TEXT("should set ssid or ap"));
    }

    int         key_len = 0;
    const char* key     = NULL;
    if (mp_const_none != args[ARG_key].u_obj) {
        key     = mp_obj_str_get_str(args[ARG_key].u_obj);
        key_len = strlen(key);
    }

    if ((0x08 > key_len) || (RT_WLAN_PASSWORD_MAX_LENGTH < key_len)) {
        mp_raise_msg_varg(&mp_type_OSError, MP_ERROR_TEXT("Key length(%d) should be 8 - %d"), key_len,
                          RT_WLAN_PASSWORD_MAX_LENGTH);
    }

    if (MOD_NETWORK_STA_IF == self->itf) {
        if (0x00 == use_info) {
            result = netmgmt_wlan_sta_connect_with_ssid((char*)ssid, (char*)key);
        } else {
            result = netmgmt_wlan_sta_connect_with_scan_info(&info, (char*)key);
        }

        if (0x00 != result) {
            mp_printf(&mp_plat_print, "run connect failed.\n");
            return mp_const_false;
        }
    } else {
        if (0x00 == use_info) {
            result = netmgmt_wlan_ap_start_with_ssid((char*)ssid, (char*)key);
        } else {
            result = netmgmt_wlan_ap_start_with_info(&info, (char*)key);
        }

        if (0x00 != result) {
            mp_printf(&mp_plat_print, "start ap failed.\n");
            return mp_const_false;
        }
    }

    return mp_const_true;
}
static MP_DEFINE_CONST_FUN_OBJ_KW(network_rt_wlan_connect_obj, 1, network_rt_wlan_connect);

static mp_obj_t network_rt_wlan_disconnect(size_t n_args, const mp_obj_t* args)
{
    py_rt_net_obj_t* self = MP_OBJ_TO_PTR(args[0]);

    if (MOD_NETWORK_STA_IF == self->itf) {
        if (0x00 != netmgmt_wlan_sta_disconnect_ap()) {
            mp_printf(&mp_plat_print, "run disconnect failed.\n");
            return mp_const_false;
        }
    } else {
        uint8_t   mac[6];
        mp_obj_t* items;
        mp_obj_get_array_fixed_n(args[1], 6, &items);
        for (int i = 0; i < 6; i++) {
            mac[i] = (uint8_t)mp_obj_get_int(items[i]);
        }

        if (0x00 != netmgmt_wlan_ap_disconnect_sta(mac)) {
            mp_printf(&mp_plat_print, "run ap deauth failed.\n");
            return mp_const_false;
        }
    }

    return mp_const_true;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(network_rt_wlan_disconnect_obj, 1, 2, network_rt_wlan_disconnect);

static mp_obj_t network_rt_wlan_isconnected(mp_obj_t self_in)
{
    py_rt_net_obj_t* self   = MP_OBJ_TO_PTR(self_in);
    int              status = -1;

    if (MOD_NETWORK_STA_IF != self->itf) {
        mp_raise_msg(&mp_type_OSError, MP_ERROR_TEXT("ap mode not support connect"));
    }

    if (0x00 != netmgmt_wlan_sta_isconnected(&status)) {
        status = false;
        mp_printf(&mp_plat_print, "run isconnected failed.\n");
    }

    return mp_obj_new_bool(status);
}
static MP_DEFINE_CONST_FUN_OBJ_1(network_rt_wlan_isconnected_obj, network_rt_wlan_isconnected);

static mp_obj_t _network_rt_wlan_sta_config(size_t n_args, const mp_obj_t* pos_args, mp_map_t* kw_args)
{
    // py_rt_net_obj_t *self = MP_OBJ_TO_PTR(pos_args[0]);

    if (kw_args->used == 0) {
        // Get config value
        if (n_args != 2) {
            mp_raise_TypeError(MP_ERROR_TEXT("must query one param.\n"));
        }
        qstr attr = mp_obj_str_get_qstr(pos_args[1]);

        switch (attr) {
        case MP_QSTR_mac: {
            uint8_t mac[6];

            if (0x00 != netmgmt_wlan_sta_get_mac(&mac[0])) {
                mp_printf(&mp_plat_print, "run get mac failed.\n");
                return mp_const_none;
            }

            return mp_obj_new_bytes(mac, sizeof(mac));
        } break;
        case MP_QSTR_auto_reconnect: {
            int auto_reconnect = 0;

            if (0x00 != netmgmt_wlan_sta_get_auto_reconnect(&auto_reconnect)) {
                auto_reconnect = 0;
                mp_printf(&mp_plat_print, "run get auto reconnect failed.\n");
            }
            return mp_obj_new_bool(auto_reconnect);
        } break;
        }
    } else {
        enum { ARG_mac, ARG_auto_reconnect };
        static const mp_arg_t allowed_args[] = {
            { MP_QSTR_mac, MP_ARG_OBJ, { .u_obj = mp_const_none } },
            { MP_QSTR_auto_reconnect, MP_ARG_OBJ, { .u_obj = mp_const_none } },
        };
        mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
        mp_arg_parse_all(n_args - 1, pos_args + 1, kw_args, MP_ARRAY_SIZE(allowed_args), allowed_args, args);

        if (mp_const_none != args[ARG_mac].u_obj) {
            uint8_t   mac[6];
            mp_obj_t* items;
            mp_obj_get_array_fixed_n(args[ARG_mac].u_obj, 6, &items);
            for (int i = 0; i < 6; i++) {
                mac[i] = (uint8_t)mp_obj_get_int(items[i]);
            }

            if (0x00 != netmgmt_wlan_sta_set_mac(&mac[0])) {
                mp_printf(&mp_plat_print, "run set mac failed.\n");
                return mp_const_false;
            }
        }

        if (mp_const_none != args[ARG_auto_reconnect].u_obj) {
            int auto_reconnect = 0;

            if (mp_obj_is_true(args[ARG_auto_reconnect].u_obj)) {
                auto_reconnect = 1;
            }

            if (0x00 != netmgmt_wlan_sta_set_auto_reconnect(auto_reconnect)) {
                mp_printf(&mp_plat_print, "run set auto_reconnect failed.\n");
                return mp_const_false;
            }
        }
    }

    return mp_const_true;
}

static mp_obj_t _network_rt_wlan_ap_get_info(mp_obj_t self_in)
{
    py_rt_net_obj_t* self = MP_OBJ_TO_PTR(self_in);

    if (MOD_NETWORK_AP_IF != self->itf) {
        mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("only ap if can get info"));
    }

    struct rt_wlan_info_t info;

    if (0x00 != netmgmt_wlan_ap_get_info(&info)) {
        mp_printf(&mp_plat_print, "run get ap info failed.\n");
        return mp_const_none;
    }

    return py_rt_wlan_info_from_struct(&info);
}
static MP_DEFINE_CONST_FUN_OBJ_1(network_rt_wlan_ap_get_info_obj, _network_rt_wlan_ap_get_info);

static mp_obj_t _network_rt_wlan_ap_config(size_t n_args, const mp_obj_t* pos_args, mp_map_t* kw_args)
{
    // py_rt_net_obj_t *self = MP_OBJ_TO_PTR(args[0]);

    if (kw_args->used == 0) {
        // Get config value
        if (n_args != 2) {
            mp_raise_TypeError(MP_ERROR_TEXT("must query one param"));
        }
        qstr attr = mp_obj_str_get_qstr(pos_args[1]);

        switch (attr) {
        case MP_QSTR_info: {
            return _network_rt_wlan_ap_get_info(pos_args[0]);
        } break;
        case MP_QSTR_country: {
            int country = -1;

            if (0x00 != netmgmt_wlan_ap_get_country(&country)) {
                mp_printf(&mp_plat_print, "run get ap country failed.\n");
            }
            return MP_OBJ_NEW_SMALL_INT(country);
        } break;
        }
    } else {
        mp_map_elem_t* ssid
            = mp_map_lookup(kw_args, MP_OBJ_NEW_QSTR(MP_QSTR_ssid), MP_MAP_LOOKUP); // same in network_rt_wlan_connect
        mp_map_elem_t* key
            = mp_map_lookup(kw_args, MP_OBJ_NEW_QSTR(MP_QSTR_key), MP_MAP_LOOKUP); // same in network_rt_wlan_connect
        mp_map_elem_t* info
            = mp_map_lookup(kw_args, MP_OBJ_NEW_QSTR(MP_QSTR_info), MP_MAP_LOOKUP); // same in network_rt_wlan_connect

        if ((NULL != key) && ((NULL != ssid) || (NULL != info))) {
            // Call connect to set WiFi access point.
            return network_rt_wlan_connect(n_args, pos_args, kw_args);
        }

        enum { ARG_country };
        static const mp_arg_t allowed_args[] = {
            { MP_QSTR_country, MP_ARG_INT, { .u_int = -1 } },
        };
        mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
        mp_arg_parse_all(n_args - 1, pos_args + 1, kw_args, MP_ARRAY_SIZE(allowed_args), allowed_args, args);

        if ((-1) != args[ARG_country].u_int) {
            int country = args[ARG_country].u_int;

            if (0x00 != netmgmt_wlan_ap_set_country(country)) {
                mp_printf(&mp_plat_print, "run set ap country failed.\n");
                return mp_const_false;
            }
        }
    }

    return mp_const_true;
}

static mp_obj_t network_rt_wlan_config(size_t n_args, const mp_obj_t* args, mp_map_t* kwargs)
{
    py_rt_net_obj_t* self = MP_OBJ_TO_PTR(args[0]);

    if (MOD_NETWORK_STA_IF == self->itf) {
        return _network_rt_wlan_sta_config(n_args, args, kwargs);
    }
    return _network_rt_wlan_ap_config(n_args, args, kwargs);
}
static MP_DEFINE_CONST_FUN_OBJ_KW(network_rt_wlan_config_obj, 1, network_rt_wlan_config);

static mp_obj_t _network_rt_wlan_get_sta_status(size_t n_args, const mp_obj_t* args)
{
    py_rt_net_obj_t* self = MP_OBJ_TO_PTR(args[0]);

    if (0x01 == n_args) {
        return network_rt_wlan_isconnected(MP_OBJ_FROM_PTR(self));
    }

    switch (mp_obj_str_get_qstr(args[1])) {
    case MP_QSTR_rssi: {
        int rssi = -99;

        if (0x00 != netmgmt_wlan_sta_get_rssi(&rssi)) {
            rssi = -99;
            mp_printf(&mp_plat_print, "run sta get rssi failed.\n");
        }
        return MP_OBJ_NEW_SMALL_INT(rssi);
    } break;
    case MP_QSTR_ap: {
        struct rt_wlan_info_t info;

        if (0x00 != netmgmt_wlan_sta_get_ap_info(&info)) {
            mp_printf(&mp_plat_print, "run get ap info failed.\n");
            return mp_const_none;
        }

        return py_rt_wlan_info_from_struct(&info);
    } break;
    }

    mp_raise_ValueError(MP_ERROR_TEXT("unknown status param"));
}

static mp_obj_t _network_rt_wlan_get_ap_status(size_t n_args, const mp_obj_t* args)
{
    if (0x01 == n_args) {
        // check is actived
        int active = 0;

        if (0x00 != netmgmt_wlan_ap_isactived(&active)) {
            mp_printf(&mp_plat_print, "run ap isactive failed.\n");
            return mp_const_false;
        }
        return mp_obj_new_bool(active);
    }

    switch (mp_obj_str_get_qstr(args[1])) {
    case MP_QSTR_stations: {
        int                   sta_num = 0;
        struct rt_wlan_info_t sta_infos[RT_WLAN_STA_SCAN_MAX_AP];

        if (0x00 != netmgmt_wlan_ap_get_sta_info(&sta_num, sta_infos)) {
            mp_printf(&mp_plat_print, "run ap get connected station info failed.\n");
            return mp_const_none;
        }

        mp_obj_t station_list = mp_obj_new_list(0, NULL);

        for (int32_t i = 0; i < sta_num; i++) {
            struct rt_wlan_info_t* info  = &sta_infos[i];
            mp_obj_t               bssid = mp_obj_new_bytes(info->bssid, RT_WLAN_BSSID_MAX_LENGTH);
            mp_obj_list_append(station_list, bssid);
        }

        return station_list;
    } break;
    }

    mp_raise_ValueError(MP_ERROR_TEXT("unknown status param"));
}

static mp_obj_t network_rt_wlan_status(size_t n_args, const mp_obj_t* args)
{
    py_rt_net_obj_t* self = MP_OBJ_TO_PTR(args[0]);

    if (MOD_NETWORK_STA_IF == self->itf) {
        return _network_rt_wlan_get_sta_status(n_args, args);
    }
    return _network_rt_wlan_get_ap_status(n_args, args);
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(network_rt_wlan_status_obj, 1, 2, network_rt_wlan_status);

static mp_obj_t network_rt_wlan_stop(mp_obj_t self_in)
{
    py_rt_net_obj_t* self = MP_OBJ_TO_PTR(self_in);

    if (MOD_NETWORK_AP_IF != self->itf) {
        mp_raise_msg(&mp_type_OSError, MP_ERROR_TEXT("sta mode not support stop"));
    }

    if (0x00 != netmgmt_wlan_ap_stop()) {
        mp_printf(&mp_plat_print, "run stop failed.\n");
        return mp_const_false;
    }

    return mp_const_true;
}
static MP_DEFINE_CONST_FUN_OBJ_1(network_rt_wlan_stop_obj, network_rt_wlan_stop);

/* Constants *****************************************************************/

/* clang-format off */
#define RT_WLAN_AP_STA_LOCALS_DICT_TABLE                                                                                       \
    { MP_ROM_QSTR(MP_QSTR_active), MP_ROM_PTR(&network_rt_net_active_obj) },                                                   \
    { MP_ROM_QSTR(MP_QSTR_ifconfig), MP_ROM_PTR(&network_rt_net_ifconfig_obj) },                                               \
    { MP_ROM_QSTR(MP_QSTR_disconnect), MP_ROM_PTR(&network_rt_wlan_disconnect_obj) },                                          \
    { MP_ROM_QSTR(MP_QSTR_config), MP_ROM_PTR(&network_rt_wlan_config_obj) },                                                  \
    { MP_ROM_QSTR(MP_QSTR_status), MP_ROM_PTR(&network_rt_wlan_status_obj) },                                                  \
    { MP_ROM_QSTR(MP_QSTR_SECURITY_OPEN), MP_ROM_INT(SECURITY_OPEN) },                                                         \
    { MP_ROM_QSTR(MP_QSTR_SECURITY_WEP_PSK), MP_ROM_INT(SECURITY_WEP_PSK) },                                                   \
    { MP_ROM_QSTR(MP_QSTR_SECURITY_WEP_SHARED), MP_ROM_INT(SECURITY_WEP_SHARED) },                                             \
    { MP_ROM_QSTR(MP_QSTR_SECURITY_WPA_TKIP_PSK), MP_ROM_INT(SECURITY_WPA_TKIP_PSK) },                                         \
    { MP_ROM_QSTR(MP_QSTR_SECURITY_WPA_TKIP_8021X), MP_ROM_INT(SECURITY_WPA_TKIP_8021X) },                                     \
    { MP_ROM_QSTR(MP_QSTR_SECURITY_WPA_AES_PSK), MP_ROM_INT(SECURITY_WPA_AES_PSK) },                                           \
    { MP_ROM_QSTR(MP_QSTR_SECURITY_WPA_AES_8021X), MP_ROM_INT(SECURITY_WPA_AES_8021X) },                                       \
    { MP_ROM_QSTR(MP_QSTR_SECURITY_WPA2_AES_PSK), MP_ROM_INT(SECURITY_WPA2_AES_PSK) },                                         \
    { MP_ROM_QSTR(MP_QSTR_SECURITY_WPA2_AES_8021X), MP_ROM_INT(SECURITY_WPA2_AES_8021X) },                                     \
    { MP_ROM_QSTR(MP_QSTR_SECURITY_WPA2_TKIP_PSK), MP_ROM_INT(SECURITY_WPA2_TKIP_PSK) },                                       \
    { MP_ROM_QSTR(MP_QSTR_SECURITY_WPA2_TKIP_8021X), MP_ROM_INT(SECURITY_WPA2_TKIP_8021X) },                                   \
    { MP_ROM_QSTR(MP_QSTR_SECURITY_WPA2_MIXED_PSK), MP_ROM_INT(SECURITY_WPA2_MIXED_PSK) },                                     \
    { MP_ROM_QSTR(MP_QSTR_SECURITY_WPA_WPA2_MIXED_PSK), MP_ROM_INT(SECURITY_WPA_WPA2_MIXED_PSK) },                             \
    { MP_ROM_QSTR(MP_QSTR_SECURITY_WPA_WPA2_MIXED_8021X), MP_ROM_INT(SECURITY_WPA_WPA2_MIXED_8021X) },                         \
    { MP_ROM_QSTR(MP_QSTR_SECURITY_WPA2_AES_CMAC), MP_ROM_INT(SECURITY_WPA2_AES_CMAC) },                                       \
    { MP_ROM_QSTR(MP_QSTR_SECURITY_WPS_OPEN), MP_ROM_INT(SECURITY_WPS_OPEN) },                                                 \
    { MP_ROM_QSTR(MP_QSTR_SECURITY_WPS_SECURE), MP_ROM_INT(SECURITY_WPS_SECURE) },                                             \
    { MP_ROM_QSTR(MP_QSTR_SECURITY_WPA3_AES_PSK), MP_ROM_INT(SECURITY_WPA3_AES_PSK) },                                         \
    { MP_ROM_QSTR(MP_QSTR_SECURITY_UNKNOWN), MP_ROM_INT(SECURITY_UNKNOWN) },                                                   \
    { MP_ROM_QSTR(MP_QSTR_BAND_5GHZ), MP_ROM_INT(RT_802_11_BAND_5GHZ) },                                                       \
    { MP_ROM_QSTR(MP_QSTR_BAND_2_4GHZ), MP_ROM_INT(RT_802_11_BAND_2_4GHZ) },

static const mp_rom_map_elem_t rt_wlan_sta_locals_dict_table[] = {
    RT_WLAN_AP_STA_LOCALS_DICT_TABLE

    { MP_ROM_QSTR(MP_QSTR_scan), MP_ROM_PTR(&network_rt_wlan_scan_obj) }, // only for sta
    { MP_ROM_QSTR(MP_QSTR_connect), MP_ROM_PTR(&network_rt_wlan_connect_obj) }, // only for sta
    { MP_ROM_QSTR(MP_QSTR_isconnected), MP_ROM_PTR(&network_rt_wlan_isconnected_obj) }, // only for sta
};
static MP_DEFINE_CONST_DICT(rt_wlan_sta_locals_dict, rt_wlan_sta_locals_dict_table);

static MP_DEFINE_CONST_OBJ_TYPE(
    network_type_wlan_sta,
    MP_QSTR_rt_wlan_sta,
    MP_TYPE_FLAG_NONE,
    locals_dict, &rt_wlan_sta_locals_dict,
    protocol, &mod_network_nic_protocol_rtt_posix
);

static const mp_rom_map_elem_t rt_wlan_ap_locals_dict_table[] = {
    RT_WLAN_AP_STA_LOCALS_DICT_TABLE

    { MP_ROM_QSTR(MP_QSTR_stop), MP_ROM_PTR(&network_rt_wlan_stop_obj) }, // only for ap
    { MP_ROM_QSTR(MP_QSTR_info), MP_OBJ_FROM_PTR(&network_rt_wlan_ap_get_info_obj) },
};
static MP_DEFINE_CONST_DICT(rt_wlan_ap_locals_dict, rt_wlan_ap_locals_dict_table);

static MP_DEFINE_CONST_OBJ_TYPE(
    network_type_wlan_ap,
    MP_QSTR_rt_wlan_ap,
    MP_TYPE_FLAG_NONE,
    locals_dict, &rt_wlan_ap_locals_dict,
    protocol, &mod_network_nic_protocol_rtt_posix
);
/* clang-format on */

static mp_obj_t network_wlan_make_new(size_t n_args, const mp_obj_t* args)
{
    static py_rt_net_obj_t network_rt_wlan_sta = { { (mp_obj_type_t*)&network_type_wlan_sta }, MOD_NETWORK_STA_IF };
    static py_rt_net_obj_t network_rt_wlan_ap  = { { (mp_obj_type_t*)&network_type_wlan_ap }, MOD_NETWORK_AP_IF };

    py_rt_net_obj_t* self = NULL;

    int itf = MOD_NETWORK_STA_IF;

    if (0x01 == n_args) {
        itf = mp_obj_get_int(args[0]);
    }

    if (MOD_NETWORK_STA_IF == itf) {
        self = &network_rt_wlan_sta;
    } else if (MOD_NETWORK_AP_IF == itf) {
        self = &network_rt_wlan_ap;
    } else {
        mp_raise_ValueError(MP_ERROR_TEXT("invalid network interface type"));
    }

    // Register with network module
    mod_network_register_nic(self);

    return MP_OBJ_FROM_PTR(self);
}
MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(network_wlan_make_new_obj, 0, 1, network_wlan_make_new);

#endif // CONFIG_ENABLE_NETWORK_RT_WLAN
