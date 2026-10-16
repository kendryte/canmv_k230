/* Copyright (c) 2026, Canaan Bright Sight Co., Ltd
 * SPDX-License-Identifier: BSD-3-Clause
 */
#include <cstring>
#include <fstream>

#include "nncase/runtime/interpreter.h"
#include "nncase/runtime/runtime_tensor.h"
#include "nncase/runtime/util.h"
#include "okws_config.h"
#include "okws_model.h"

using namespace nncase;
using namespace nncase::runtime;

namespace okws {

namespace {

constexpr size_t kInBytes = OKWS_N_MELS * OKWS_T_WIN * sizeof(float);
constexpr size_t kOutBytes = OKWS_T_OUT * OKWS_N_UNITS * sizeof(float);

bool shape_is(const dims_t &d, std::initializer_list<size_t> want)
{
    if (d.size() != want.size())
        return false;
    size_t i = 0;
    for (size_t w : want)
        if ((size_t)d[i++] != w)
            return false;
    return true;
}

class KModel : public Model {
public:
    bool load(const std::string &path, std::string &err)
    {
        std::ifstream ifs(path, std::ios::binary);
        if (!ifs) {
            err = "cannot open " + path;
            return false;
        }
        if (!interp_.load_model(ifs).is_ok()) {
            err = "kmodel load failed: " + path;
            return false;
        }
        if (interp_.inputs_size() != 1 || interp_.outputs_size() < 1 ||
            !shape_is(interp_.input_shape(0), {1, 1, OKWS_N_MELS, OKWS_T_WIN}) ||
            !shape_is(interp_.output_shape(0), {1, OKWS_T_OUT, OKWS_N_UNITS}) ||
            interp_.input_desc(0).datatype != dt_float32 ||
            interp_.output_desc(0).datatype != dt_float32) {
            err = "kmodel must be f32 [1,1,40,96] -> f32 [1,24,59]";
            return false;
        }
        auto in = hrt::create(dt_float32, interp_.input_shape(0), hrt::pool_shared);
        auto out = hrt::create(dt_float32, interp_.output_shape(0), hrt::pool_shared);
        if (!in.is_ok() || !out.is_ok()) {
            err = "cannot allocate kmodel tensors";
            return false;
        }
        in_ = std::move(in).unwrap();
        out_ = std::move(out).unwrap();
        if (!interp_.input_tensor(0, in_).is_ok() || !interp_.output_tensor(0, out_).is_ok()) {
            err = "cannot bind kmodel tensors";
            return false;
        }
        return true;
    }

    bool run(const float *in, float *out) override
    {
        {
            auto m = hrt::map(in_, map_access_t::map_write);
            if (!m.is_ok())
                return false;
            auto buf = std::move(m).unwrap();
            if (buf.buffer().size() < kInBytes)
                return false;
            memcpy(buf.buffer().data(), in, kInBytes);
        } // unmapped here, before the cache write-back
        if (!hrt::sync(in_, sync_op_t::sync_write_back, true).is_ok())
            return false;
        if (!interp_.run().is_ok())
            return false;
        if (!hrt::sync(out_, sync_op_t::sync_invalidate, true).is_ok())
            return false;
        auto m = hrt::map(out_, map_access_t::map_read);
        if (!m.is_ok())
            return false;
        auto buf = std::move(m).unwrap();
        if (buf.buffer().size() < kOutBytes)
            return false;
        memcpy(out, buf.buffer().data(), kOutBytes);
        return true;
    }

private:
    interpreter interp_;
    runtime_tensor in_;
    runtime_tensor out_;
};

} // namespace

std::unique_ptr<Model> create_kmodel(const std::string &path, std::string &err)
{
    std::unique_ptr<KModel> m(new KModel());
    if (!m->load(path, err))
        return nullptr;
    return m;
}

void shrink_model_pool()
{
    nncase::runtime::shrink_memory_pool();
}

} // namespace okws
