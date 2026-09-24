#ifndef AI_RVV_KERNELS_H
#define AI_RVV_KERNELS_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

void ai_rvv_f32_affine_inplace(float *data, size_t count, float subtract,
                               float scale, float bias);
void ai_rvv_f32_reverse_affine_inplace(float *data, size_t count,
                                       float reverse_base, float scale,
                                       float bias);
void ai_rvv_f32_sub_scalar_inplace(float *data, size_t count, float value);
void ai_rvv_f32_mul_inplace(float *data, const float *weights, size_t count);
void ai_rvv_f32_preemphasis_inplace(float *data, size_t count, float coeff);
void ai_rvv_f32_power_spectrum(float *power, const float *real,
                               const float *imag, size_t count);
size_t ai_rvv_f32_argmax(const float *data, size_t count, float *max_value);
size_t ai_rvv_f32_argmax_strided(const float *data, size_t count,
                                 size_t stride, float *max_value);
void ai_rvv_hwc_argmax_color(const float *scores, size_t pixel_count,
                             size_t class_count, const uint32_t *colors,
                             uint32_t *output);

#ifdef __cplusplus
}
#endif

#endif
