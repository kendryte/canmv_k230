#include "feature_pipeline.h"
#include "aidemo_wrap.h"
#include <iostream>
#include <memory>

// feature_pipelien class
struct feature_pipeline
{
    wenet::FeaturePipeline *feature_pipe;
};

struct processed_feat
{
    const float *feats_ptr;
    size_t feats_length;
};

feature_pipeline *feature_pipeline_create()
{
    try {
        std::unique_ptr<feature_pipeline> fp(new feature_pipeline);
        fp->feature_pipe = new wenet::FeaturePipeline();
        return fp.release();
    } catch (...) {
        return nullptr;
    }
}

void release_final_feats(float* feats)
{
    if (feats != nullptr)
    {
        delete[] feats;
    }
}

void release_preprocess_class(feature_pipeline *fp)
{
    if (fp == nullptr) {
        return;
    }
    delete fp->feature_pipe;
    delete fp;
}


bool wav_preprocess(feature_pipeline *fp, float *wav, size_t wav_length, float* final_feats)
{
    try {
    // 将数组输入转为vector适配函数输入
    std::vector<float> wav_vector(wav, wav + wav_length);

    // 预处理函数
    fp->feature_pipe->AcceptWaveform(wav_vector);

    if (fp->feature_pipe->NumQueuedFrames() < 30) {
        return false;
    }

    std::vector<std::vector<float>> feats;
    bool ok = fp->feature_pipe->Read(30, &feats);
    if (!ok) {
        return false;
    }
    
    size_t offset = 0;
    for (const auto& feat : feats) {
        hal_rvv_memcpy(final_feats + offset, feat.data(),
                       feat.size() * sizeof(float));
        offset += feat.size();
    }
    return true;
    } catch (...) {
        // Keep C++ allocation errors inside the C ABI boundary.
        return false;
    }
}
