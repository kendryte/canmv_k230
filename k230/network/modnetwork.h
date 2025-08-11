/*
 * This file is part of the MicroPython project, http://micropython.org/
 *
 * The MIT License (MIT)
 *
 * Copyright (c) 2017 "Eric Poulsen" <eric@zyxod.com>
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 */
#pragma once

#include "py/mpconfig.h"
#include "py/obj.h"

#include "hal_netmgmt.h"

#include "extmod/modnetwork.h"

typedef struct _py_rt_net_obj_t {
    mp_obj_base_t   base;
    enum rt_netif_t itf;
} py_rt_net_obj_t;

extern const mod_network_nic_protocol_t mod_network_nic_protocol_rtt_posix;

MP_DECLARE_CONST_FUN_OBJ_1(network_rt_set_dft_dev_obj);
MP_DECLARE_CONST_FUN_OBJ_0(network_rt_get_dft_dev_obj);
MP_DECLARE_CONST_FUN_OBJ_0(network_rt_get_dev_list_obj);

MP_DECLARE_CONST_FUN_OBJ_VAR_BETWEEN(network_rt_net_active_obj);
MP_DECLARE_CONST_FUN_OBJ_VAR_BETWEEN(network_rt_net_ifconfig_obj);

extern const struct _mp_obj_type_t network_type_eth_lan;
MP_DECLARE_CONST_FUN_OBJ_VAR_BETWEEN(network_wlan_make_new_obj);
