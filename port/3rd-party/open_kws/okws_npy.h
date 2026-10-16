/* Copyright (c) 2026, Canaan Bright Sight Co., Ltd
 * SPDX-License-Identifier: BSD-3-Clause
 */
#pragma once

#include <string>
#include <vector>

namespace okws {

// Load a little-endian float32, C-ordered .npy file and check its shape.
// Returns false and fills err on any mismatch.
bool load_npy_f32(const std::string &path, const std::vector<size_t> &shape,
                  std::vector<float> &out, std::string &err);

} // namespace okws
