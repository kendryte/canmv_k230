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

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <fcntl.h>
#include <unistd.h>
#include <signal.h>
#include <errno.h>
#include <math.h>
#include <sys/ioctl.h>

#include "py/runtime.h"
#include "py/obj.h"

#include "modmachine.h"
#include "mpi_fft_api.h"

typedef struct _machine_fft_obj_t {
    mp_obj_base_t base;
    short* byte_addr; 
    uint32_t points;
    uint32_t shift;
    short i_real[FFT_MAX_POINT];//实数
    short i_imag[FFT_MAX_POINT];//虚数
    short o_h_real[FFT_MAX_POINT];
    short o_h_imag[FFT_MAX_POINT];
    short o_h_ifft_real[FFT_MAX_POINT];
    short o_h_ifft_imag[FFT_MAX_POINT];    
} machine_fft_obj_t;

STATIC mp_obj_t machine_fft_obj_init_helper(machine_fft_obj_t *self, size_t n_args, const mp_obj_t *pos_args, mp_map_t *kw_args) {
    enum{ARG_byte,
         ARG_points,
         ARG_shift,
        //  ARG_direction,
    };
    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_byte, MP_ARG_OBJ, {.u_obj = mp_const_none} },
        { MP_QSTR_points, MP_ARG_INT, {.u_int = 64} },
        { MP_QSTR_shift, MP_ARG_INT, {.u_int = 0} },
        // { MP_QSTR_direction, MP_ARG_INT, {.u_int = FFT_DIR_FORWARD} },
    };
    mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all(n_args, pos_args, kw_args, MP_ARRAY_SIZE(allowed_args), allowed_args, args);
    self->points = args[ARG_points].u_int;
    self->shift = args[ARG_shift].u_int;
    // uint32_t direction = args[ARG_direction].u_int;
    
    if(self->points != 64 && self->points != 128 && self->points != 256 && self->points != 512 && self->points != 1024 && self->points != 2048 && self->points != 4096)
    {
        mp_raise_ValueError(MP_ERROR_TEXT("[CANMV]FFT:invalid points"));
    }

    uint32_t byte_len = 0;

    if( args[ARG_byte].u_obj != mp_const_none)
    {
        mp_obj_t byte = args[ARG_byte].u_obj;
        mp_buffer_info_t bufinfo;
        mp_get_buffer_raise(byte, &bufinfo, MP_BUFFER_READ);
        byte_len = bufinfo.len;
        self->byte_addr = (short*)bufinfo.buf;
    }
    else
    {
        mp_raise_ValueError(MP_ERROR_TEXT("[CANMV]FFT:invalid byte"));
    }
    if(byte_len % 4 != 0)
    {
        mp_raise_ValueError(MP_ERROR_TEXT("[CANMV]FFT:Buffer length must be a multiple of 4"));
    }
    // // how to get the length of i2s buffer?
    // if(byte_len < self->points * 4)
    // {
    //     mp_printf(&mp_plat_print, "[CANMV]FFT:Zero padding\r\n");
    //     memset(self->byte_addr+byte_len, 0, self->points * 4 - byte_len );//Zero padding
    // }

    return mp_const_none;
}

STATIC mp_obj_t mp_machine_fft_make_new(const mp_obj_type_t *type, size_t n_args, size_t n_kw, const mp_obj_t *args) {
    
    mp_arg_check_num(n_args, n_kw, 1, 3, false);
    machine_fft_obj_t *self = mp_obj_malloc(machine_fft_obj_t, &machine_fft_type);
    mp_map_t kw_args;
    mp_map_init_fixed_table(&kw_args, n_kw, args + n_args);
    machine_fft_obj_init_helper(self, n_args, args, &kw_args);


    return MP_OBJ_FROM_PTR(self);
}


STATIC mp_obj_t machine_fft_run(size_t n_args, const mp_obj_t *pos_args, mp_map_t *kw_args)
 {
    //----------parse parameter---------------
    machine_fft_obj_t *self = MP_OBJ_TO_PTR(pos_args[0]);

    //------------------get data----------------------
    for(int i = 0; i < self->points; ++i)
    {
        self->i_real[i] = self->byte_addr[i];                   
        self->i_imag[i] = 0;
        // printf("self->i_real[%d] = 0x%04x\n",i,self->i_real[i]);  
    }

    //run fft
    MP_THREAD_GIL_EXIT();
    kd_mpi_fft(self->points,RIRI,RR_II_OUT, 0, self->shift,self->i_real, self->i_imag, self->o_h_real, self->o_h_imag);
    MP_THREAD_GIL_ENTER();

    //return a list
    // for(int i = 0; i < self->points; ++i)
    //     printf("self->o_h_real[%d] = 0x%04x\n",i,self->o_h_real[i]);
    mp_obj_list_t* ret_list = (mp_obj_list_t*)m_new(mp_obj_list_t,sizeof(mp_obj_list_t));//m_new
    mp_obj_list_init(ret_list, 0);
    mp_obj_t tuple_1[2];
    for (int i = 0; i < self->points ; i++)
    {
        tuple_1[0] = mp_obj_new_int(self->o_h_real[i]);
        tuple_1[1] = mp_obj_new_int(self->o_h_imag[i]);
        mp_obj_list_append(ret_list, mp_obj_new_tuple(MP_ARRAY_SIZE(tuple_1), tuple_1));
    }
    // kd_mpi_ifft(self->points,  RIRI,RR_II_OUT, 0, self->shift,self->o_h_real, self->o_h_imag, self->o_h_ifft_real, self->o_h_ifft_imag);
    // for(int i = 0; i < self->points; ++i)
    //     printf("self->o_h_ifft_real[%d] = 0x%04x\n",i,self->o_h_ifft_real[i]);
    return MP_OBJ_FROM_PTR(ret_list);
}

MP_DEFINE_CONST_FUN_OBJ_KW(machine_fft_run_obj,1, machine_fft_run);

STATIC mp_obj_t machine_fft_freq(size_t n_args, const mp_obj_t *pos_args, mp_map_t *kw_args)
 {
    //----------parse parameter---------------
    enum{ARG_points,
         ARG_sample_rate,
    };
    static const mp_arg_t allowed_args[] = {
        { MP_QSTR_points, MP_ARG_INT, {.u_int = 64} },
        { MP_QSTR_sample_rate, MP_ARG_INT, {.u_int = 16000} },
    };
    machine_fft_obj_t *self = MP_OBJ_TO_PTR(pos_args[0]);

    mp_arg_val_t args[MP_ARRAY_SIZE(allowed_args)];
    mp_arg_parse_all(n_args -1 , pos_args + 1, kw_args, MP_ARRAY_SIZE(allowed_args), allowed_args, args);
    uint32_t sample_rate = args[ARG_sample_rate].u_int;
    self->points = args[ARG_points].u_int;

    uint32_t step = sample_rate/self->points;
    mp_obj_list_t* ret_list = (mp_obj_list_t*)m_new(mp_obj_list_t,sizeof(mp_obj_list_t));//m_new
    mp_obj_list_init(ret_list, 0);
    for(int i = 0; i < self->points; i++)
    {
        mp_obj_list_append(ret_list, mp_obj_new_int(step * i));
    }
    return MP_OBJ_FROM_PTR(ret_list);
}

MP_DEFINE_CONST_FUN_OBJ_KW(machine_fft_freq_obj,1, machine_fft_freq);


STATIC mp_obj_t machine_fft_amplitude(mp_obj_t self_o,const mp_obj_t list_obj)
 {
    machine_fft_obj_t *self = MP_OBJ_TO_PTR(self_o);
    if(&mp_type_list != mp_obj_get_type(list_obj))
    {
        mp_raise_ValueError(MP_ERROR_TEXT("[CANMV]FFT:obj is not a list"));
    }
    mp_obj_list_t* ret_list = (mp_obj_list_t*)m_new(mp_obj_list_t,sizeof(mp_obj_list_t));//m_new
    mp_obj_list_init(ret_list, 0);
    mp_obj_list_t* list = MP_OBJ_TO_PTR(list_obj);
    uint32_t index = 0;
    mp_obj_t list_iter;
    mp_obj_tuple_t* tuple;
    for(index = 0; index < list->len; index++)
    {
        list_iter = list->items[index];
        tuple = MP_OBJ_FROM_PTR(list_iter);
        uint32_t r_val = MP_OBJ_SMALL_INT_VALUE(tuple->items[0]);
        uint32_t i_val = MP_OBJ_SMALL_INT_VALUE(tuple->items[1]);
        uint32_t amplitude = sqrt(r_val * r_val + i_val * i_val);
        uint32_t hard_power = 0;
        //Convert to power
        if(index == 0)
            hard_power = amplitude/list->len;            
        else 
            hard_power = 2*amplitude/list->len;

        if(self->shift){
            uint32_t num_one = 0;
            uint32_t i = 0;
            for (i=0;i < log2(self->points); i++ )
                if(self->shift & (1<<i) )
                    num_one++;            
            hard_power = hard_power<<num_one;
            
        }            
        mp_obj_list_append(ret_list,mp_obj_new_int(hard_power));
    }
    return MP_OBJ_FROM_PTR(ret_list);
}
MP_DEFINE_CONST_FUN_OBJ_2(machine_fft_amplitude_obj, machine_fft_amplitude);

STATIC const mp_rom_map_elem_t machine_fft_locals_dict_table[] = {
    { MP_ROM_QSTR(MP_QSTR_run), MP_ROM_PTR(&machine_fft_run_obj) },
    { MP_ROM_QSTR(MP_QSTR_freq), MP_ROM_PTR(&machine_fft_freq_obj) },
    { MP_ROM_QSTR(MP_QSTR_amplitude), MP_ROM_PTR(&machine_fft_amplitude_obj) },
    
};

STATIC MP_DEFINE_CONST_DICT(machine_fft_locals_dict, machine_fft_locals_dict_table);

MP_DEFINE_CONST_OBJ_TYPE(
    machine_fft_type,
    MP_QSTR_FFT,
    MP_TYPE_FLAG_NONE,
    make_new, mp_machine_fft_make_new,
    locals_dict, &machine_fft_locals_dict
    );
