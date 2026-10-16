/* Copyright (c) 2026, Canaan Bright Sight Co., Ltd
 * SPDX-License-Identifier: BSD-3-Clause
 */
#pragma once

#include <memory>
#include <string>

namespace okws {

// Acoustic model: float32 [1,1,40,96] features -> float32 [1,24,59] logits.
// The board uses the nncase kmodel; host tests plug in onnxruntime.
class Model {
public:
    virtual ~Model() = default;
    virtual bool run(const float *in, float *out) = 0;
};

// Implemented in okws_model_nncase.cpp (board only).
std::unique_ptr<Model> create_kmodel(const std::string &path, std::string &err);

// Return freed KPU tensor memory to the system after the model is destroyed.
void shrink_model_pool();

} // namespace okws
