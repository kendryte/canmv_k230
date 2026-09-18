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

#ifdef FUNC_IMPL

#define DEF_VOID_FUNC_VOID(x)                   \
STATIC mp_obj_t _##x(void) {                    \
    x();                                        \
    return mp_const_none;                       \
}                                               \
STATIC MP_DEFINE_CONST_FUN_OBJ_0(x##_obj, _##x);

#define DEF_INT_FUNC_VOID(x)                    \
STATIC mp_obj_t _##x(void) {                    \
    size_t ret = x();                           \
    return mp_obj_new_int(ret);                 \
}                                               \
STATIC MP_DEFINE_CONST_FUN_OBJ_0(x##_obj, _##x);

#define DEF_INT_FUNC_INT(x)                     \
STATIC mp_obj_t _##x(mp_obj_t obj) {            \
    size_t ret = x(mp_obj_get_int(obj));        \
    return mp_obj_new_int(ret);                 \
}                                               \
STATIC MP_DEFINE_CONST_FUN_OBJ_1(x##_obj, _##x);

#define DEF_INT_FUNC_STR(x)                     \
STATIC mp_obj_t _##x(mp_obj_t obj) {            \
    size_t ret = x(mp_obj_str_get_str(obj));    \
    return mp_obj_new_int(ret);                 \
}                                               \
STATIC MP_DEFINE_CONST_FUN_OBJ_1(x##_obj, _##x);

#define DEF_INT_FUNC_INT_INT(x)                                 \
STATIC mp_obj_t _##x(mp_obj_t obj0, mp_obj_t obj1) {            \
    size_t ret = x(mp_obj_get_int(obj0), mp_obj_get_int(obj1)); \
    return mp_obj_new_int(ret);                                 \
}                                                               \
STATIC MP_DEFINE_CONST_FUN_OBJ_2(x##_obj, _##x);

#define DEF_INT_FUNC_INT_INT_INT(x)                                 \
STATIC mp_obj_t _##x(mp_obj_t obj0, mp_obj_t obj1, mp_obj_t obj2) { \
    size_t ret = x(mp_obj_get_int(obj0), mp_obj_get_int(obj1),      \
        mp_obj_get_int(obj2));                                      \
    return mp_obj_new_int(ret);                                     \
}                                                                   \
STATIC MP_DEFINE_CONST_FUN_OBJ_3(x##_obj, _##x);

#define DEF_INT_FUNC_INT_INT_STR(x)                                 \
STATIC mp_obj_t _##x(mp_obj_t obj0, mp_obj_t obj1, mp_obj_t obj2) { \
    size_t ret = x(mp_obj_get_int(obj0), mp_obj_get_int(obj1),      \
        mp_obj_str_get_str(obj2));                                  \
    return mp_obj_new_int(ret);                                     \
}                                                                   \
STATIC MP_DEFINE_CONST_FUN_OBJ_3(x##_obj, _##x);

#define DEF_INT_FUNC_STRUCTPTR(x, struct_type)                  \
STATIC mp_obj_t _##x(mp_obj_t obj) {                            \
    mp_buffer_info_t bufinfo;                                   \
    mp_get_buffer_raise(obj, &bufinfo, MP_BUFFER_READ);         \
    if (sizeof(struct_type) != bufinfo.len)                     \
        mp_raise_msg_varg(&mp_type_TypeError,                   \
            MP_ERROR_TEXT("expect size: %u, actual size: %u"),  \
            sizeof(struct_type), bufinfo.len);                  \
    size_t ret = x((struct_type*)(bufinfo.buf));                \
    return mp_obj_new_int(ret);                                 \
}                                                               \
STATIC MP_DEFINE_CONST_FUN_OBJ_1(x##_obj, _##x);

#define DEF_INT_FUNC_STRUCTPTR_STRUCTPTR(x, struct0_type, struct1_type) \
STATIC mp_obj_t _##x(mp_obj_t obj0, mp_obj_t obj1) {                    \
    mp_buffer_info_t bufinfo[2];                                        \
    mp_get_buffer_raise(obj0, &bufinfo[0], MP_BUFFER_READ);             \
    mp_get_buffer_raise(obj1, &bufinfo[1], MP_BUFFER_READ);             \
    if (sizeof(struct0_type) != bufinfo[0].len)                         \
        mp_raise_msg_varg(&mp_type_TypeError,                           \
            MP_ERROR_TEXT("struct 0 expect size: %u, actual size: %u"), \
            sizeof(struct0_type), bufinfo[0].len);                      \
    if (sizeof(struct1_type) != bufinfo[1].len)                         \
        mp_raise_msg_varg(&mp_type_TypeError,                           \
            MP_ERROR_TEXT("struct 1 expect size: %u, actual size: %u"), \
            sizeof(struct1_type), bufinfo[1].len);                      \
    size_t ret = x((struct0_type*)(bufinfo[0].buf),                     \
        (struct1_type*)(bufinfo[1].buf));                               \
    return mp_obj_new_int(ret);                                         \
}                                                                       \
STATIC MP_DEFINE_CONST_FUN_OBJ_2(x##_obj, _##x);

#define DEF_INT_FUNC_STRUCTPTR_STRUCTPTR_INT(x, struct0_type, struct1_type) \
STATIC mp_obj_t _##x(mp_obj_t obj0, mp_obj_t obj1, mp_obj_t obj2) {       \
    mp_buffer_info_t bufinfo[2];                                          \
    mp_get_buffer_raise(obj0, &bufinfo[0], MP_BUFFER_READ);               \
    mp_get_buffer_raise(obj1, &bufinfo[1], MP_BUFFER_READ);               \
    if (sizeof(struct0_type) != bufinfo[0].len)                          \
        mp_raise_msg_varg(&mp_type_TypeError,                            \
            MP_ERROR_TEXT("struct 0 expect size: %u, actual size: %u"),  \
            sizeof(struct0_type), bufinfo[0].len);                       \
    if (sizeof(struct1_type) != bufinfo[1].len)                          \
        mp_raise_msg_varg(&mp_type_TypeError,                            \
            MP_ERROR_TEXT("struct 1 expect size: %u, actual size: %u"),  \
            sizeof(struct1_type), bufinfo[1].len);                       \
    size_t ret = x((struct0_type*)(bufinfo[0].buf),                      \
        (struct1_type*)(bufinfo[1].buf), mp_obj_get_int(obj2));           \
    return mp_obj_new_int(ret);                                          \
}                                                                        \
STATIC MP_DEFINE_CONST_FUN_OBJ_3(x##_obj, _##x);

#define DEF_INT_FUNC_INT_STRUCTPTR_STRUCTPTR(x, struct0_type, struct1_type) \
STATIC mp_obj_t _##x(mp_obj_t obj0, mp_obj_t obj1, mp_obj_t obj2) {     \
    mp_buffer_info_t bufinfo[2];                                        \
    mp_get_buffer_raise(obj1, &bufinfo[0], MP_BUFFER_READ);             \
    mp_get_buffer_raise(obj2, &bufinfo[1], MP_BUFFER_READ);             \
    if (sizeof(struct0_type) != bufinfo[0].len)                         \
        mp_raise_msg_varg(&mp_type_TypeError,                           \
            MP_ERROR_TEXT("struct 0 expect size: %u, actual size: %u"), \
            sizeof(struct0_type), bufinfo[0].len);                      \
    if (sizeof(struct1_type) != bufinfo[1].len)                         \
        mp_raise_msg_varg(&mp_type_TypeError,                           \
            MP_ERROR_TEXT("struct 1 expect size: %u, actual size: %u"), \
            sizeof(struct1_type), bufinfo[1].len);                      \
    size_t ret = x(mp_obj_get_int(obj0), (struct0_type*)(bufinfo[0].buf), \
        (struct1_type*)(bufinfo[1].buf));                               \
    return mp_obj_new_int(ret);                                         \
}                                                                       \
STATIC MP_DEFINE_CONST_FUN_OBJ_3(x##_obj, _##x);

#define DEF_INT_FUNC_INT_STRUCTPTR(x, struct_type)                      \
STATIC mp_obj_t _##x(mp_obj_t obj0, mp_obj_t obj1) {                    \
    mp_buffer_info_t bufinfo;                                           \
    mp_get_buffer_raise(obj1, &bufinfo, MP_BUFFER_READ);                \
    if (sizeof(struct_type) != bufinfo.len)                             \
        mp_raise_msg_varg(&mp_type_TypeError,                           \
            MP_ERROR_TEXT("struct expect size: %u, actual size: %u"),   \
            sizeof(struct_type), bufinfo.len);                          \
    size_t ret = x(mp_obj_get_int(obj0), (struct_type*)(bufinfo.buf));  \
    return mp_obj_new_int(ret);                                         \
}                                                                       \
STATIC MP_DEFINE_CONST_FUN_OBJ_2(x##_obj, _##x);

#define DEF_INT_FUNC_INT_STRUCT(x, struct_type)                         \
STATIC mp_obj_t _##x(mp_obj_t obj0, mp_obj_t obj1) {                    \
    mp_buffer_info_t bufinfo;                                           \
    mp_get_buffer_raise(obj1, &bufinfo, MP_BUFFER_READ);                \
    if (sizeof(struct_type) != bufinfo.len)                             \
        mp_raise_msg_varg(&mp_type_TypeError,                           \
            MP_ERROR_TEXT("struct expect size: %u, actual size: %u"),   \
            sizeof(struct_type), bufinfo.len);                          \
    size_t ret = x(mp_obj_get_int(obj0), *(struct_type*)(bufinfo.buf)); \
    return mp_obj_new_int(ret);                                         \
}                                                                       \
STATIC MP_DEFINE_CONST_FUN_OBJ_2(x##_obj, _##x);

#define DEF_INT_FUNC_ARRAY_INT(x, struct_type)                          \
STATIC mp_obj_t _##x(mp_obj_t obj0, mp_obj_t obj1) {                    \
    mp_buffer_info_t bufinfo;                                           \
    mp_get_buffer_raise(obj0, &bufinfo, MP_BUFFER_READ);                \
    size_t ret = x((struct_type*)(bufinfo.buf), mp_obj_get_int(obj1));  \
    return mp_obj_new_int(ret);                                         \
}                                                                       \
STATIC MP_DEFINE_CONST_FUN_OBJ_2(x##_obj, _##x);

#define DEF_INT_FUNC_INT_ARRAY(x, struct_type)                          \
STATIC mp_obj_t _##x(mp_obj_t obj0, mp_obj_t obj1) {                    \
    mp_buffer_info_t bufinfo;                                           \
    mp_get_buffer_raise(obj1, &bufinfo, MP_BUFFER_READ);                \
    size_t ret = x(mp_obj_get_int(obj0), (struct_type*)(bufinfo.buf));  \
    return mp_obj_new_int(ret);                                         \
}                                                                       \
STATIC MP_DEFINE_CONST_FUN_OBJ_2(x##_obj, _##x);

#define DEF_INT_FUNC_INT_ARRAY_INT(x, struct_type)                      \
STATIC mp_obj_t _##x(mp_obj_t obj0, mp_obj_t obj1, mp_obj_t obj2) {     \
    mp_buffer_info_t bufinfo;                                           \
    mp_get_buffer_raise(obj1, &bufinfo, MP_BUFFER_READ);                \
    size_t ret = x(mp_obj_get_int(obj0), (struct_type*)(bufinfo.buf),   \
        mp_obj_get_int(obj2));                                          \
    return mp_obj_new_int(ret);                                         \
}                                                                       \
STATIC MP_DEFINE_CONST_FUN_OBJ_3(x##_obj, _##x);

#define DEF_INT_FUNC_INT_INT_STRUCTPTR(x, struct_type)                  \
STATIC mp_obj_t _##x(mp_obj_t obj0, mp_obj_t obj1, mp_obj_t obj2) {     \
    mp_buffer_info_t bufinfo;                                           \
    mp_get_buffer_raise(obj2, &bufinfo, MP_BUFFER_READ);                \
    if (sizeof(struct_type) != bufinfo.len)                             \
        mp_raise_msg_varg(&mp_type_TypeError,                           \
            MP_ERROR_TEXT("struct expect size: %u, actual size: %u"),   \
            sizeof(struct_type), bufinfo.len);                          \
    size_t ret = x(mp_obj_get_int(obj0), mp_obj_get_int(obj1),          \
        (struct_type*)(bufinfo.buf));                                   \
    return mp_obj_new_int(ret);                                         \
}                                                                       \
STATIC MP_DEFINE_CONST_FUN_OBJ_3(x##_obj, _##x);

#define DEF_INT_FUNC_INT_INT_STRUCT(x, struct_type)                     \
STATIC mp_obj_t _##x(mp_obj_t obj0, mp_obj_t obj1, mp_obj_t obj2) {     \
    mp_buffer_info_t bufinfo;                                           \
    mp_get_buffer_raise(obj2, &bufinfo, MP_BUFFER_READ);                \
    if (sizeof(struct_type) != bufinfo.len)                             \
        mp_raise_msg_varg(&mp_type_TypeError,                           \
            MP_ERROR_TEXT("struct expect size: %u, actual size: %u"),   \
            sizeof(struct_type), bufinfo.len);                          \
    size_t ret = x(mp_obj_get_int(obj0), mp_obj_get_int(obj1),          \
        *(struct_type*)(bufinfo.buf));                                  \
    return mp_obj_new_int(ret);                                         \
}                                                                       \
STATIC MP_DEFINE_CONST_FUN_OBJ_3(x##_obj, _##x);

#define DEF_INT_FUNC_INT_INT_STRUCTPTR_INT(x, struct_type)              \
STATIC mp_obj_t _##x(size_t n_args, const mp_obj_t *args) {             \
    mp_buffer_info_t bufinfo;                                           \
    mp_get_buffer_raise(args[2], &bufinfo, MP_BUFFER_READ);             \
    if (sizeof(struct_type) != bufinfo.len)                             \
        mp_raise_msg_varg(&mp_type_TypeError,                           \
            MP_ERROR_TEXT("struct expect size: %u, actual size: %u"),   \
            sizeof(struct_type), bufinfo.len);                          \
    size_t ret = x(mp_obj_get_int(args[0]), mp_obj_get_int(args[1]),    \
        (struct_type*)(bufinfo.buf), mp_obj_get_int(args[3]));          \
    return mp_obj_new_int(ret);                                         \
}                                                                       \
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(x##_obj, 4, 4, _##x);

#define DEF_INT_FUNC_INT_STRUCTPTR_INT(x, struct_type)                  \
STATIC mp_obj_t _##x(mp_obj_t obj0, mp_obj_t obj1, mp_obj_t obj2) {     \
    mp_buffer_info_t bufinfo;                                           \
    mp_get_buffer_raise(obj1, &bufinfo, MP_BUFFER_READ);                \
    if (sizeof(struct_type) != bufinfo.len)                             \
        mp_raise_msg_varg(&mp_type_TypeError,                           \
            MP_ERROR_TEXT("struct expect size: %u, actual size: %u"),   \
            sizeof(struct_type), bufinfo.len);                          \
    size_t ret = x(mp_obj_get_int(obj0), (struct_type*)(bufinfo.buf),   \
        mp_obj_get_int(obj2));                                          \
    return mp_obj_new_int(ret);                                         \
}                                                                       \
STATIC MP_DEFINE_CONST_FUN_OBJ_3(x##_obj, _##x);

#define DEF_INT_FUNC_INT_STRUCTPTR_INT_GIL(x, struct_type)              \
STATIC mp_obj_t _##x(mp_obj_t obj0, mp_obj_t obj1, mp_obj_t obj2) {     \
    mp_buffer_info_t bufinfo;                                           \
    mp_get_buffer_raise(obj1, &bufinfo, MP_BUFFER_READ);                \
    if (sizeof(struct_type) != bufinfo.len)                             \
        mp_raise_msg_varg(&mp_type_TypeError,                           \
            MP_ERROR_TEXT("struct expect size: %u, actual size: %u"),   \
            sizeof(struct_type), bufinfo.len);                          \
    MP_THREAD_GIL_EXIT();                                               \
    size_t ret = x(mp_obj_get_int(obj0), (struct_type*)(bufinfo.buf),   \
        mp_obj_get_int(obj2));                                          \
    MP_THREAD_GIL_ENTER();                                              \
    return mp_obj_new_int(ret);                                         \
}                                                                       \
STATIC MP_DEFINE_CONST_FUN_OBJ_3(x##_obj, _##x);

#define DEF_INT_FUNC_INT_STRUCTPTR_STRUCTPTR_INT(x, struct0_type, struct1_type) \
STATIC mp_obj_t _##x(size_t n_args, const mp_obj_t *args) {             \
    mp_buffer_info_t bufinfo[2];                                        \
    mp_get_buffer_raise(args[1], &bufinfo[0], MP_BUFFER_READ);          \
    mp_get_buffer_raise(args[2], &bufinfo[1], MP_BUFFER_READ);          \
    if (sizeof(struct0_type) != bufinfo[0].len)                         \
        mp_raise_msg_varg(&mp_type_TypeError,                           \
            MP_ERROR_TEXT("struct 0 expect size: %u, actual size: %u"), \
            sizeof(struct0_type), bufinfo[0].len);                      \
    if (sizeof(struct1_type) != bufinfo[1].len)                         \
        mp_raise_msg_varg(&mp_type_TypeError,                           \
            MP_ERROR_TEXT("struct 1 expect size: %u, actual size: %u"), \
            sizeof(struct1_type), bufinfo[1].len);                      \
    size_t ret = x(mp_obj_get_int(args[0]), (struct0_type*)(bufinfo[0].buf),    \
        (struct1_type*)(bufinfo[1].buf), mp_obj_get_int(args[3]));      \
    return mp_obj_new_int(ret);                                         \
}                                                                       \
STATIC MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(x##_obj, 4, 4, _##x);

#define DEF_INT_FUNC_STRUCTPTR_INT(x, struct_type)                      \
STATIC mp_obj_t _##x(mp_obj_t obj0, mp_obj_t obj1) {                    \
    mp_buffer_info_t bufinfo;                                           \
    mp_get_buffer_raise(obj0, &bufinfo, MP_BUFFER_READ);                \
    if (sizeof(struct_type) != bufinfo.len)                             \
        mp_raise_msg_varg(&mp_type_TypeError,                           \
            MP_ERROR_TEXT("struct expect size: %u, actual size: %u"),   \
            sizeof(struct_type), bufinfo.len);                          \
    size_t ret = x((struct_type*)(bufinfo.buf), mp_obj_get_int(obj1));  \
    return mp_obj_new_int(ret);                                         \
}                                                                       \
STATIC MP_DEFINE_CONST_FUN_OBJ_2(x##_obj, _##x);

#define DEF_INT_FUNC_STRUCTPTR_INT_GIL(x, struct_type)                      \
STATIC mp_obj_t _##x(mp_obj_t obj0, mp_obj_t obj1) {                    \
    mp_buffer_info_t bufinfo;                                           \
    mp_get_buffer_raise(obj0, &bufinfo, MP_BUFFER_READ);                \
    if (sizeof(struct_type) != bufinfo.len)                             \
        mp_raise_msg_varg(&mp_type_TypeError,                           \
            MP_ERROR_TEXT("struct expect size: %u, actual size: %u"),   \
            sizeof(struct_type), bufinfo.len);                          \
    MP_THREAD_GIL_EXIT();                                               \
    size_t ret = x((struct_type*)(bufinfo.buf), mp_obj_get_int(obj1));  \
    MP_THREAD_GIL_ENTER();                                              \
    return mp_obj_new_int(ret);                                         \
}                                                                       \
STATIC MP_DEFINE_CONST_FUN_OBJ_2(x##_obj, _##x);

#elif defined FUNC_ADD

#define DEF_INT_FUNC_VOID(x)                        \
{ MP_ROM_QSTR(MP_QSTR_##x), MP_ROM_PTR(&x##_obj) },
#define DEF_VOID_FUNC_VOID(x) DEF_INT_FUNC_VOID(x)
#define DEF_INT_FUNC_INT(x) DEF_INT_FUNC_VOID(x)
#define DEF_INT_FUNC_STR(x) DEF_INT_FUNC_VOID(x)
#define DEF_INT_FUNC_INT_INT(x) DEF_INT_FUNC_VOID(x)
#define DEF_INT_FUNC_INT_INT_INT(x) DEF_INT_FUNC_VOID(x)
#define DEF_INT_FUNC_INT_INT_STR(x) DEF_INT_FUNC_VOID(x)
#define DEF_INT_FUNC_STRUCTPTR(x, struct_type) DEF_INT_FUNC_VOID(x)
#define DEF_INT_FUNC_STRUCTPTR_STRUCTPTR(x, struct0_type, struct1_type) \
    DEF_INT_FUNC_VOID(x)
#define DEF_INT_FUNC_STRUCTPTR_STRUCTPTR_INT(x, struct0_type, struct1_type) \
    DEF_INT_FUNC_VOID(x)
#define DEF_INT_FUNC_INT_STRUCT(x, struct_type) DEF_INT_FUNC_VOID(x)
#define DEF_INT_FUNC_INT_STRUCTPTR(x, struct_type) DEF_INT_FUNC_VOID(x)
#define DEF_INT_FUNC_ARRAY_INT(x, struct_type) DEF_INT_FUNC_VOID(x)
#define DEF_INT_FUNC_INT_ARRAY(x, struct_type) DEF_INT_FUNC_VOID(x)
#define DEF_INT_FUNC_INT_ARRAY_INT(x, struct_type) DEF_INT_FUNC_VOID(x)
#define DEF_INT_FUNC_INT_INT_STRUCT(x, struct_type) DEF_INT_FUNC_VOID(x)
#define DEF_INT_FUNC_INT_INT_STRUCTPTR(x, struct_type) DEF_INT_FUNC_VOID(x)
#define DEF_INT_FUNC_INT_STRUCTPTR_INT(x, struct_type) DEF_INT_FUNC_VOID(x)
#define DEF_INT_FUNC_INT_STRUCTPTR_INT_GIL(x, struct_type) DEF_INT_FUNC_VOID(x)
#define DEF_INT_FUNC_INT_INT_STRUCTPTR_INT(x, struct_type) DEF_INT_FUNC_VOID(x)
#define DEF_INT_FUNC_INT_STRUCTPTR_STRUCTPTR(x, struct0_type, struct1_type) DEF_INT_FUNC_VOID(x)
#define DEF_INT_FUNC_INT_STRUCTPTR_STRUCTPTR_INT(x, struct0_type, struct1_type) \
    DEF_INT_FUNC_VOID(x)
#define DEF_INT_FUNC_STRUCTPTR_INT(x, struct_type) DEF_INT_FUNC_VOID(x)
#define DEF_INT_FUNC_STRUCTPTR_INT_GIL(x, struct_type) DEF_INT_FUNC_VOID(x)

#endif

#if defined FUNC_IMPL || defined FUNC_ADD && defined FUNC_FILE
#include FUNC_FILE
#endif

#undef FUNC_IMPL
#undef FUNC_ADD
#undef DEF_INT_FUNC_VOID
#undef DEF_VOID_FUNC_VOID
#undef DEF_INT_FUNC_INT
#undef DEF_INT_FUNC_STR
#undef DEF_INT_FUNC_INT_INT
#undef DEF_INT_FUNC_INT_INT_INT
#undef DEF_INT_FUNC_INT_INT_STR
#undef DEF_INT_FUNC_STRUCTPTR
#undef DEF_INT_FUNC_STRUCTPTR_STRUCTPTR
#undef DEF_INT_FUNC_INT_STRUCT
#undef DEF_INT_FUNC_INT_STRUCTPTR
#undef DEF_INT_FUNC_ARRAY_INT
#undef DEF_INT_FUNC_INT_ARRAY
#undef DEF_INT_FUNC_INT_ARRAY_INT
#undef DEF_INT_FUNC_INT_INT_STRUCT
#undef DEF_INT_FUNC_INT_INT_STRUCTPTR
#undef DEF_INT_FUNC_INT_STRUCTPTR_INT
#undef DEF_INT_FUNC_INT_STRUCTPTR_INT_GIL
#undef DEF_INT_FUNC_INT_INT_STRUCTPTR_INT
#undef DEF_INT_FUNC_STRUCTPTR_STRUCTPTR_INT
#undef DEF_INT_FUNC_INT_STRUCTPTR_STRUCTPTR_INT
#undef DEF_INT_FUNC_INT_STRUCTPTR_STRUCTPTR
#undef DEF_INT_FUNC_STRUCTPTR_INT
#undef DEF_INT_FUNC_STRUCTPTR_INT_GIL
