// Constants
{ MP_ROM_QSTR(MP_QSTR_STA_IF), MP_ROM_INT(MOD_NETWORK_STA_IF) },
{ MP_ROM_QSTR(MP_QSTR_AP_IF), MP_ROM_INT(MOD_NETWORK_AP_IF) },

{ MP_ROM_QSTR(MP_QSTR_get_dev_list), MP_ROM_PTR(&network_rt_get_dev_list_obj) },

{ MP_ROM_QSTR(MP_QSTR_set_default_dev), MP_ROM_PTR(&network_rt_set_dft_dev_obj) },

{ MP_ROM_QSTR(MP_QSTR_get_default_dev), MP_ROM_PTR(&network_rt_get_dft_dev_obj) },
