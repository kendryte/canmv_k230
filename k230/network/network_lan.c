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
#include "py/obj.h"
#include "py/runtime.h"

#include "network/modnetwork.h"

#ifdef CONFIG_ENABLE_NETWORK_RT_LAN_OVER_USB
/* network_rt_lan ************************************************************/
static mp_obj_t network_rt_lan_isconnected(mp_obj_t self_in)
{
    py_rt_net_obj_t* self = MP_OBJ_TO_PTR(self_in);
    (void)self;

    int isconnected = 0;
    if (0x00 != netmgmt_lan_get_isconnected(&isconnected)) {
        mp_printf(&mp_plat_print, "run get isconnected failed.\n");
        return mp_const_false;
    }
    return mp_obj_new_bool(0x00 != isconnected);
}
static MP_DEFINE_CONST_FUN_OBJ_1(network_rt_lan_isconnected_obj, network_rt_lan_isconnected);

static mp_obj_t network_rt_lan_status(size_t n_args, const mp_obj_t* args)
{
    py_rt_net_obj_t* self = MP_OBJ_TO_PTR(args[0]);
    (void)self;

    if (n_args == 1) {
        int status = 0;

        if (0x00 != netmgmt_lan_get_link_status(&status)) {
            status = 0; // failed

            mp_printf(&mp_plat_print, "run get status failed.\n");
        }
        return MP_OBJ_NEW_SMALL_INT(status);
    }
    mp_raise_ValueError(MP_ERROR_TEXT("unknown status param"));
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(network_rt_lan_status_obj, 1, 2, network_rt_lan_status);

static mp_obj_t network_rt_lan_config(size_t n_args, const mp_obj_t* args, mp_map_t* kwargs)
{
    py_rt_net_obj_t* self = MP_OBJ_TO_PTR(args[0]);
    (void)self;

    if (kwargs->used == 0) {
        // Get config value
        if (n_args != 2) {
            mp_raise_TypeError(MP_ERROR_TEXT("must query one param"));
        }

        switch (mp_obj_str_get_qstr(args[1])) {
        case MP_QSTR_mac: {
            uint8_t buf[6];

            if (0x00 != netmgmt_lan_get_mac(&buf[0])) {
                memset(&buf[0], 0, sizeof(buf)); // failed

                mp_printf(&mp_plat_print, "run get mac failed.\n");
            }

            return mp_obj_new_bytes(buf, 6);
        }
        default:
            mp_raise_ValueError(MP_ERROR_TEXT("unknown config param"));
        }
    } else {
        // Set config value(s)
        if (n_args != 1) {
            mp_raise_TypeError(MP_ERROR_TEXT("can't specify pos and kw args"));
        }

        for (size_t i = 0; i < kwargs->alloc; ++i) {
            if (MP_MAP_SLOT_IS_FILLED(kwargs, i)) {
                mp_map_elem_t* e = &kwargs->table[i];
                switch (mp_obj_str_get_qstr(e->key)) {
                case MP_QSTR_mac: {
                    mp_buffer_info_t buf;
                    mp_get_buffer_raise(e->value, &buf, MP_BUFFER_READ);
                    if (buf.len != 6) {
                        mp_raise_ValueError(NULL);
                    }

                    if (0x00 != netmgmt_lan_set_mac(buf.buf)) {
                        mp_printf(&mp_plat_print, "run set mac failed.\n");
                    }

                    break;
                }
                default:
                    mp_raise_ValueError(MP_ERROR_TEXT("unknown config param"));
                }
            }
        }

        return mp_const_none;
    }
}
static MP_DEFINE_CONST_FUN_OBJ_KW(network_rt_lan_config_obj, 1, network_rt_lan_config);

static mp_obj_t py_rt_eth_lan_type_make_new(const mp_obj_type_t* type, size_t n_args, size_t n_kw, const mp_obj_t* all_args)
{
    static py_rt_net_obj_t network_rt_eth_lan = { { (mp_obj_type_t*)&network_type_eth_lan }, RT_NET_DEV_USB };

    mp_obj_t rt_net_obj = MP_OBJ_FROM_PTR(&network_rt_eth_lan);

    // Register with network module
    mod_network_register_nic(rt_net_obj);

    return rt_net_obj;
}

static const mp_rom_map_elem_t network_type_lan_locals_dict_table[] = {
    { MP_ROM_QSTR(MP_QSTR_isconnected), MP_ROM_PTR(&network_rt_lan_isconnected_obj) },
    { MP_ROM_QSTR(MP_QSTR_status), MP_ROM_PTR(&network_rt_lan_status_obj) },
    { MP_ROM_QSTR(MP_QSTR_config), MP_ROM_PTR(&network_rt_lan_config_obj) },

    // in network_common.c
    { MP_ROM_QSTR(MP_QSTR_active), MP_ROM_PTR(&network_rt_net_active_obj) },
    { MP_ROM_QSTR(MP_QSTR_ifconfig), MP_ROM_PTR(&network_rt_net_ifconfig_obj) },
};
static MP_DEFINE_CONST_DICT(network_type_lan_locals_dict, network_type_lan_locals_dict_table);

/* clang-format off */
MP_DEFINE_CONST_OBJ_TYPE(
    network_type_eth_lan,
    MP_QSTR_eth_lan,
    MP_TYPE_FLAG_NONE,
    make_new, py_rt_eth_lan_type_make_new,
    locals_dict, &network_type_lan_locals_dict,
    protocol, &mod_network_nic_protocol_rtt_posix
);
/* clang-format on */

#endif // CONFIG_ENABLE_NETWORK_RT_LAN_OVER_USB
