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

#include "shared/netutils/netutils.h"

#include "network/modnetwork.h"

static mp_obj_t network_rt_set_dft_dev(mp_obj_t name)
{
    const char* dev_name = mp_obj_str_get_str(name);
    int         name_len = strlen(dev_name);

    if ((0x00 >= name_len) || (32 <= name_len)) {
        mp_raise_ValueError(MP_ERROR_TEXT("invalid device name"));
    }

    if (0x00 != netmgmt_utils_set_defeault_dev((char*)dev_name)) {
        mp_printf(&mp_plat_print, "run set default netdev failed.\n");
        return mp_const_false;
    }

    return mp_const_true;
}
MP_DEFINE_CONST_FUN_OBJ_1(network_rt_set_dft_dev_obj, network_rt_set_dft_dev);

static mp_obj_t network_rt_get_dft_dev(void)
{
    char dev_name[32];

    if (0x00 != netmgmt_utils_get_defeault_dev(dev_name)) {
        mp_printf(&mp_plat_print, "run get default netdev failed.\n");
        return mp_const_none;
    }

    return mp_obj_new_str_via_qstr(dev_name, strlen(dev_name));
}
MP_DEFINE_CONST_FUN_OBJ_0(network_rt_get_dft_dev_obj, network_rt_get_dft_dev);

static mp_obj_t network_rt_get_dev_list(void)
{
    int  dev_num = 0;
    char names[NET_DEV_MAX_CNT][32];

    mp_obj_t dev_list;

    if (0x00 != netmgmt_utils_get_dev_list(&dev_num, names)) {
        mp_printf(&mp_plat_print, "run get netdev list failed.\n");
        return mp_const_none;
    }

    dev_list = mp_obj_new_list(0, NULL);
    for (int i = 0; i < dev_num; i++) {
        mp_obj_t name_obj = mp_obj_new_str_via_qstr(names[i], strlen(names[i]));
        mp_obj_list_append(dev_list, name_obj);
    }

    return dev_list;
}
MP_DEFINE_CONST_FUN_OBJ_0(network_rt_get_dev_list_obj, network_rt_get_dev_list);

static mp_obj_t network_rt_net_active(size_t n_args, const mp_obj_t* args)
{
    py_rt_net_obj_t* self = MP_OBJ_TO_PTR(args[0]);

    if (n_args == 1) {
        int             isactive = -1;
        enum rt_netif_t itf      = self->itf;

        if (0x00 != netmgmt_utils_probe_device(itf, &isactive)) {
            mp_printf(&mp_plat_print, "run get isactive failed.\n");
            return mp_const_false;
        }
        return mp_obj_new_bool(0x00 != isactive);
    } else {
        mp_printf(&mp_plat_print, "Network (rt-smart) is always active and cannot be disabled.\n");

        return mp_const_none;
    }
}
MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(network_rt_net_active_obj, 1, 2, network_rt_net_active);

static mp_obj_t network_rt_net_ifconfig(size_t n_args, const mp_obj_t* args)
{
    py_rt_net_obj_t*  self = MP_OBJ_TO_PTR(args[0]);
    enum rt_netif_t   itf  = self->itf;
    struct ifconfig_t ifconfig;

    if (n_args == 1) {
        if (0x00 != netmgmt_utils_get_ifconfig(itf, &ifconfig)) {
            mp_printf(&mp_plat_print, "get ifconfig failed.\n");
            return mp_const_none;
        }

        mp_obj_t tuple[4] = {
            netutils_format_ipv4_addr((uint8_t*)&ifconfig.ip.addr, NETUTILS_BIG),
            netutils_format_ipv4_addr((uint8_t*)&ifconfig.netmask.addr, NETUTILS_BIG),
            netutils_format_ipv4_addr((uint8_t*)&ifconfig.gw.addr, NETUTILS_BIG),
            netutils_format_ipv4_addr((uint8_t*)&ifconfig.dns.addr, NETUTILS_BIG),
        };

        return mp_obj_new_tuple(4, tuple);
    } else {
        if (mp_obj_is_str(args[1])) {
            switch (mp_obj_str_get_qstr(args[1])) {
            case MP_QSTR_dhcp: {
                if (0x00 != netmgmt_utils_set_ifconfig_dhcp(itf)) {
                    mp_printf(&mp_plat_print, "set ifconfig dhcp failed.\n");
                    return mp_const_false;
                }
            } break;
            default: {
                mp_raise_ValueError(MP_ERROR_TEXT("unknown config param"));
            } break;
            }
        } else {
            mp_obj_t* items;
            mp_obj_get_array_fixed_n(args[1], 4, &items);
            netutils_parse_ipv4_addr(items[0], (uint8_t*)&ifconfig.ip.addr, NETUTILS_BIG);
            netutils_parse_ipv4_addr(items[1], (uint8_t*)&ifconfig.netmask.addr, NETUTILS_BIG);
            netutils_parse_ipv4_addr(items[2], (uint8_t*)&ifconfig.gw.addr, NETUTILS_BIG);
            netutils_parse_ipv4_addr(items[3], (uint8_t*)&ifconfig.dns.addr, NETUTILS_BIG);

            if (0x00 != netmgmt_utils_set_ifconfig_static(itf, &ifconfig)) {
                mp_printf(&mp_plat_print, "set ifconfig static failed.\n");
                return mp_const_false;
            }
        }

        return mp_const_true;
    }
}
MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(network_rt_net_ifconfig_obj, 1, 2, network_rt_net_ifconfig);
