#include "ai_rvv_kernels.h"

#if defined(__riscv_vector)
#include <riscv_vector.h>
#endif

extern "C" void ai_rvv_f32_affine_inplace(float *data, size_t count,
                                            float subtract, float scale,
                                            float bias)
{
#if defined(__riscv_vector)
    while (count != 0) {
        const size_t vl = vsetvl_e32m4(count);
        vfloat32m4_t values = vle32_v_f32m4(data, vl);
        values = vfsub_vf_f32m4(values, subtract, vl);
        values = vfmul_vf_f32m4(values, scale, vl);
        values = vfadd_vf_f32m4(values, bias, vl);
        vse32_v_f32m4(data, values, vl);
        data += vl;
        count -= vl;
    }
#else
    for (size_t i = 0; i < count; ++i) {
        data[i] -= subtract;
        data[i] *= scale;
        data[i] += bias;
    }
#endif
}

extern "C" void ai_rvv_f32_reverse_affine_inplace(
    float *data, size_t count, float reverse_base, float scale, float bias)
{
#if defined(__riscv_vector)
    while (count != 0) {
        const size_t vl = vsetvl_e32m4(count);
        vfloat32m4_t values = vle32_v_f32m4(data, vl);
        values = vfrsub_vf_f32m4(values, reverse_base, vl);
        values = vfmul_vf_f32m4(values, scale, vl);
        values = vfadd_vf_f32m4(values, bias, vl);
        vse32_v_f32m4(data, values, vl);
        data += vl;
        count -= vl;
    }
#else
    for (size_t i = 0; i < count; ++i) {
        data[i] = reverse_base - data[i];
        data[i] *= scale;
        data[i] += bias;
    }
#endif
}

extern "C" void ai_rvv_f32_sub_scalar_inplace(float *data, size_t count,
                                                float value)
{
#if defined(__riscv_vector)
    while (count != 0) {
        const size_t vl = vsetvl_e32m4(count);
        vfloat32m4_t values = vle32_v_f32m4(data, vl);
        values = vfsub_vf_f32m4(values, value, vl);
        vse32_v_f32m4(data, values, vl);
        data += vl;
        count -= vl;
    }
#else
    for (size_t i = 0; i < count; ++i) {
        data[i] -= value;
    }
#endif
}

extern "C" void ai_rvv_f32_mul_inplace(float *data, const float *weights,
                                        size_t count)
{
#if defined(__riscv_vector)
    while (count != 0) {
        const size_t vl = vsetvl_e32m4(count);
        const vfloat32m4_t values = vle32_v_f32m4(data, vl);
        const vfloat32m4_t factors = vle32_v_f32m4(weights, vl);
        const vfloat32m4_t result = vfmul_vv_f32m4(values, factors, vl);
        vse32_v_f32m4(data, result, vl);
        data += vl;
        weights += vl;
        count -= vl;
    }
#else
    for (size_t i = 0; i < count; ++i) {
        data[i] *= weights[i];
    }
#endif
}

extern "C" void ai_rvv_f32_preemphasis_inplace(float *data, size_t count,
                                                 float coeff)
{
    if (data == nullptr || count == 0 || coeff == 0.0f) {
        return;
    }
#if defined(__riscv_vector)
    size_t end = count;
    while (end > 1) {
        const size_t vl = vsetvl_e32m4(end - 1);
        const size_t start = end - vl;
        const vfloat32m4_t current = vle32_v_f32m4(data + start, vl);
        const vfloat32m4_t previous = vle32_v_f32m4(data + start - 1, vl);
        const vfloat32m4_t result =
            vfnmsac_vf_f32m4(current, coeff, previous, vl);
        vse32_v_f32m4(data + start, result, vl);
        end = start;
    }
    data[0] -= coeff * data[0];
#else
    for (size_t i = count - 1; i > 0; --i) {
        data[i] -= coeff * data[i - 1];
    }
    data[0] -= coeff * data[0];
#endif
}

extern "C" void ai_rvv_f32_power_spectrum(float *power, const float *real,
                                            const float *imag, size_t count)
{
#if defined(__riscv_vector)
    while (count != 0) {
        const size_t vl = vsetvl_e32m4(count);
        const vfloat32m4_t real_values = vle32_v_f32m4(real, vl);
        const vfloat32m4_t imag_values = vle32_v_f32m4(imag, vl);
        vfloat32m4_t result =
            vfmul_vv_f32m4(imag_values, imag_values, vl);
        result = vfmacc_vv_f32m4(result, real_values, real_values, vl);
        vse32_v_f32m4(power, result, vl);
        power += vl;
        real += vl;
        imag += vl;
        count -= vl;
    }
#else
    for (size_t i = 0; i < count; ++i) {
        power[i] = real[i] * real[i] + imag[i] * imag[i];
    }
#endif
}

extern "C" size_t ai_rvv_f32_argmax(const float *data, size_t count,
                                      float *max_value)
{
    if (data == nullptr || count == 0) {
        if (max_value != nullptr) {
            *max_value = 0.0f;
        }
        return 0;
    }

    float best = data[0];
    if (best != best) {
        if (max_value != nullptr) {
            *max_value = best;
        }
        return 0;
    }
#if defined(__riscv_vector)
    const float *cursor = data;
    size_t remaining = count;
    while (remaining != 0) {
        const size_t vl = vsetvl_e32m4(remaining);
        const vfloat32m4_t values = vle32_v_f32m4(cursor, vl);
        const vfloat32m1_t seed = vfmv_v_f_f32m1(best, 1);
        const vfloat32m1_t reduced =
            vfredmax_vs_f32m4_f32m1(seed, values, seed, vl);
        best = vfmv_f_s_f32m1_f32(reduced);
        cursor += vl;
        remaining -= vl;
    }
#else
    for (size_t i = 1; i < count; ++i) {
        if (data[i] > best) {
            best = data[i];
        }
    }
#endif

    if (best != best) {
        best = data[0];
        for (size_t i = 1; i < count; ++i) {
            if (data[i] > best) {
                best = data[i];
            }
        }
    }
    size_t best_index = 0;
#if defined(__riscv_vector)
    const float *index_cursor = data;
    size_t index_remaining = count;
    while (index_remaining != 0) {
        const size_t vl = vsetvl_e32m4(index_remaining);
        const vfloat32m4_t values = vle32_v_f32m4(index_cursor, vl);
        const vbool8_t matches = vmfeq_vf_f32m4_b8(values, best, vl);
        const long offset = vfirst_m_b8(matches, vl);
        if (offset >= 0) {
            best_index = (size_t)(index_cursor - data) + (size_t)offset;
            break;
        }
        index_cursor += vl;
        index_remaining -= vl;
    }
#else
    while (best_index + 1 < count && data[best_index] != best) {
        ++best_index;
    }
#endif
    if (max_value != nullptr) {
        *max_value = best;
    }
    return best_index;
}

extern "C" size_t ai_rvv_f32_argmax_strided(
    const float *data, size_t count, size_t stride, float *max_value)
{
    if (data == nullptr || count == 0 || stride == 0) {
        if (max_value != nullptr) *max_value = 0.0f;
        return 0;
    }

    float best = data[0];
    if (best != best) {
        if (max_value != nullptr) *max_value = best;
        return 0;
    }
#if defined(__riscv_vector)
    const ptrdiff_t byte_stride = (ptrdiff_t)(stride * sizeof(float));
    const float *cursor = data;
    size_t remaining = count;
    while (remaining != 0) {
        const size_t vl = vsetvl_e32m4(remaining);
        const vfloat32m4_t values = vlse32_v_f32m4(cursor, byte_stride, vl);
        const vfloat32m1_t seed = vfmv_v_f_f32m1(best, 1);
        const vfloat32m1_t reduced =
            vfredmax_vs_f32m4_f32m1(seed, values, seed, vl);
        best = vfmv_f_s_f32m1_f32(reduced);
        cursor += vl * stride;
        remaining -= vl;
    }
#else
    for (size_t i = 1; i < count; ++i) {
        if (data[i * stride] > best) best = data[i * stride];
    }
#endif

    if (best != best) {
        best = data[0];
        for (size_t i = 1; i < count; ++i) {
            if (data[i * stride] > best) best = data[i * stride];
        }
    }

    size_t best_index = 0;
#if defined(__riscv_vector)
    cursor = data;
    remaining = count;
    while (remaining != 0) {
        const size_t vl = vsetvl_e32m4(remaining);
        const vfloat32m4_t values = vlse32_v_f32m4(cursor, byte_stride, vl);
        const vbool8_t matches = vmfeq_vf_f32m4_b8(values, best, vl);
        const long offset = vfirst_m_b8(matches, vl);
        if (offset >= 0) {
            best_index = (size_t)((cursor - data) / (ptrdiff_t)stride) +
                         (size_t)offset;
            break;
        }
        cursor += vl * stride;
        remaining -= vl;
    }
#else
    while (best_index + 1 < count && data[best_index * stride] != best) {
        ++best_index;
    }
#endif
    if (max_value != nullptr) *max_value = best;
    return best_index;
}

extern "C" void ai_rvv_hwc_argmax_color(
    const float *scores, size_t pixel_count, size_t class_count,
    const uint32_t *colors, uint32_t *output)
{
    if (scores == nullptr || colors == nullptr || output == nullptr ||
        pixel_count == 0 || class_count == 0) {
        return;
    }

#if defined(__riscv_vector)
    const ptrdiff_t stride = (ptrdiff_t)(class_count * sizeof(float));
    size_t pixel = 0;
    while (pixel < pixel_count) {
        const size_t vl = vsetvl_e32m4(pixel_count - pixel);
        const float *base = scores + pixel * class_count;
        vfloat32m4_t best = vlse32_v_f32m4(base, stride, vl);
        vuint32m4_t indices = vmv_v_x_u32m4(0, vl);

        for (size_t cls = 1; cls < class_count; ++cls) {
            const vfloat32m4_t current =
                vlse32_v_f32m4(base + cls, stride, vl);
            const vbool8_t greater = vmfgt_vv_f32m4_b8(current, best, vl);
            best = vmerge_vvm_f32m4(greater, best, current, vl);
            const vuint32m4_t current_index =
                vmv_v_x_u32m4((uint32_t)cls, vl);
            indices =
                vmerge_vvm_u32m4(greater, indices, current_index, vl);
        }

        const vuint32m4_t byte_offsets = vsll_vx_u32m4(indices, 2, vl);
        const vuint32m4_t pixel_colors =
            vluxei32_v_u32m4(colors, byte_offsets, vl);
        vse32_v_u32m4(output + pixel, pixel_colors, vl);
        pixel += vl;
    }
#else
    for (size_t pixel = 0; pixel < pixel_count; ++pixel) {
        const float *pixel_scores = scores + pixel * class_count;
        float best = pixel_scores[0];
        size_t best_index = 0;
        for (size_t cls = 1; cls < class_count; ++cls) {
            if (pixel_scores[cls] > best) {
                best = pixel_scores[cls];
                best_index = cls;
            }
        }
        output[pixel] = colors[best_index];
    }
#endif
}
