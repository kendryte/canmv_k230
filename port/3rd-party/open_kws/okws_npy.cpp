/* Copyright (c) 2026, Canaan Bright Sight Co., Ltd
 * SPDX-License-Identifier: BSD-3-Clause
 */
#include "okws_npy.h"

#include <cstdint>
#include <cstdio>
#include <cstring>

namespace okws {

namespace {

std::string shape_str(const std::vector<size_t> &shape)
{
    std::string s = "(";
    for (size_t i = 0; i < shape.size(); i++) {
        s += std::to_string(shape[i]);
        if (shape.size() == 1 || i + 1 < shape.size())
            s += ",";
        if (i + 1 < shape.size())
            s += " ";
    }
    return s + ")";
}

std::string compact(const std::string &s)
{
    std::string out;
    for (char c : s)
        if (c != ' ')
            out += c;
    return out;
}

} // namespace

bool load_npy_f32(const std::string &path, const std::vector<size_t> &shape,
                  std::vector<float> &out, std::string &err)
{
    FILE *fp = fopen(path.c_str(), "rb");
    if (!fp) {
        err = "cannot open " + path;
        return false;
    }
    unsigned char magic[10];
    bool ok = fread(magic, 1, 10, fp) == 10 && memcmp(magic, "\x93NUMPY", 6) == 0;
    size_t hlen = 0;
    if (ok) {
        if (magic[6] == 1) {
            hlen = magic[8] | (magic[9] << 8);
        } else {
            unsigned char ext[2];
            ok = fread(ext, 1, 2, fp) == 2;
            hlen = magic[8] | (magic[9] << 8) | (ext[0] << 16) | ((size_t)ext[1] << 24);
        }
    }
    std::string header(hlen, '\0');
    if (ok)
        ok = fread(&header[0], 1, hlen, fp) == hlen;
    if (!ok) {
        fclose(fp);
        err = "bad npy header: " + path;
        return false;
    }
    std::string h = compact(header);
    if (h.find("'descr':'<f4'") == std::string::npos ||
        h.find("'fortran_order':False") == std::string::npos) {
        fclose(fp);
        err = "npy must be <f4 C-order: " + path;
        return false;
    }
    std::string want = "'shape':" + compact(shape_str(shape));
    if (h.find(want) == std::string::npos) {
        fclose(fp);
        err = "npy shape mismatch, want " + shape_str(shape) + ": " + path;
        return false;
    }
    size_t n = 1;
    for (size_t d : shape)
        n *= d;
    out.resize(n);
    ok = fread(out.data(), sizeof(float), n, fp) == n;
    fclose(fp);
    if (!ok) {
        err = "npy truncated: " + path;
        return false;
    }
    return true;
}

} // namespace okws
