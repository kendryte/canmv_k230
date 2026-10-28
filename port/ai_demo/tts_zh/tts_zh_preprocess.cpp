#include "aidemo_wrap.h"
#include "jieba_utils.h"
#include "zh_frontend.h"
#include "VoxCommon.h"

#include <algorithm>
#include <cstdlib>
#include <fstream>
#include <limits>
#include <map>
#include <memory>
#include <new>
#include <regex>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

struct TtsZh {
    zh_frontend zh;
    std::map<std::string, int> symbol_to_id;
    bool initialized = false;
};

namespace {

// The encoder model consumes fixed-size chunks; sp is also its padding symbol.
constexpr size_t kSequenceLength = 50;

struct EncodedPhonemes {
    std::vector<float> data;
    std::vector<int> lengths;
};

void set_status(TtsZhStatus *status, TtsZhStatus value) {
    if (status != nullptr) {
        *status = value;
    }
}

float symbol_id(const std::string &symbol, const std::map<std::string, int> &ids,
                float pause_id) {
    const auto found = ids.find(symbol);
    if (found != ids.end() && symbol != "_" && symbol != "~") {
        return static_cast<float>(found->second);
    }
    return pause_id;
}

std::vector<std::string> text_to_phonemes(TtsZh &tts, const char *text) {
    static const std::regex number_comma("([0-9])([\\,])([0-9])");
    const std::string normalized = std::regex_replace(std::string(text), number_comma, "$1$3");
    auto sentences = tts.zh.get_phonemes(normalized, false, true, false, false);
    std::vector<std::string> phonemes;
    for (auto &sentence : sentences) {
        if (!sentence.empty() && sentence.back() == "\n") {
            sentence.pop_back();
        }
        phonemes.insert(phonemes.end(), sentence.begin(), sentence.end());
    }
    return phonemes;
}

void append_chunk(EncodedPhonemes &encoded, const std::vector<float> &sequence,
                  float pause_id) {
    encoded.lengths.push_back(static_cast<int>(sequence.size()));
    encoded.data.insert(encoded.data.end(), sequence.begin(), sequence.end());
    encoded.data.insert(encoded.data.end(), kSequenceLength - sequence.size(), pause_id);
}

EncodedPhonemes encode_phonemes(const std::vector<std::string> &phonemes,
                              const std::map<std::string, int> &ids, float pause_id) {
    EncodedPhonemes encoded;
    std::vector<float> sequence;
    sequence.reserve(kSequenceLength);
    for (const auto &phoneme : phonemes) {
        if (sequence.size() == kSequenceLength) {
            append_chunk(encoded, sequence, pause_id);
            sequence.clear();
        }
        sequence.push_back(symbol_id(phoneme, ids, pause_id));
    }
    // Preserve the frontend's trailing-silence behavior, including a full last chunk.
    if (!sequence.empty() && !std::all_of(sequence.begin(), sequence.end(),
            [pause_id](float id) { return id == pause_id; })) {
        append_chunk(encoded, sequence, pause_id);
    }
    return encoded;
}

template <typename T>
T *copy_buffer(const std::vector<T> &source) {
    if (source.size() > std::numeric_limits<size_t>::max() / sizeof(T)) {
        throw std::bad_alloc();
    }
    T *buffer = static_cast<T *>(malloc(source.size() * sizeof(T)));
    if (buffer == nullptr) {
        throw std::bad_alloc();
    }
    std::copy(source.begin(), source.end(), buffer);
    return buffer;
}

TtsZhOutput *allocate_output(const EncodedPhonemes &encoded) {
    // Keep ownership until every allocation succeeds, including both buffers.
    std::unique_ptr<TtsZhOutput, decltype(&tts_zh_output_destroy)> output(
        static_cast<TtsZhOutput *>(calloc(1, sizeof(TtsZhOutput))), tts_zh_output_destroy);
    if (!output) {
        throw std::bad_alloc();
    }
    output->data = copy_buffer(encoded.data);
    output->size = encoded.data.size();
    output->len_data = copy_buffer(encoded.lengths);
    output->len_size = encoded.lengths.size();
    return output.release();
}

}  // namespace

TtsZh *ttszh_create() {
    try {
        return new TtsZh;
    } catch (...) {
        return nullptr;
    }
}

void ttszh_destroy(TtsZh *tts) {
    delete tts;
}

bool ttszh_init_safe(TtsZh *tts, const char *dictfile, const char *phasefile, const char *mapfile) {
    if (tts == nullptr || dictfile == nullptr || phasefile == nullptr || mapfile == nullptr) {
        return false;
    }
    try {
        std::ifstream dictionary(dictfile), phrases(phasefile), mapping(mapfile);
        if (!dictionary || !phrases || !mapping) {
            return false;
        }
        std::map<std::string, int> ids;
        std::string line;
        while (std::getline(mapping, line)) {
            if (line.find_first_not_of(" \t\r") == std::string::npos) {
                continue;
            }
            std::istringstream entry(line);
            std::string symbol;
            int id;
            if (!(entry >> symbol >> id) || id < 0) {
                return false;
            }
            ids[symbol] = id;
        }
        // Unknown symbols, padding and silence detection share this mapping.
        if (mapping.bad() || ids.find("sp") == ids.end()) {
            return false;
        }
        pypinyin.Init(dictfile, phasefile);
        tts->symbol_to_id.swap(ids);
        tts->initialized = true;
        return true;
    } catch (...) {
        return false;
    }
}

void ttszh_init(TtsZh *tts, const char *dictfile, const char *phasefile, const char *mapfile) {
    (void)ttszh_init_safe(tts, dictfile, phasefile, mapfile);
}

TtsZhOutput *tts_zh_frontend_preprocess_safe(TtsZh *tts, const char *text, TtsZhStatus *status) {
    set_status(status, TTS_ZH_INVALID_ARGUMENT);
    if (tts == nullptr || text == nullptr || !tts->initialized) {
        return nullptr;
    }
    try {
        const auto phonemes = text_to_phonemes(*tts, text);
        const float pause_id = static_cast<float>(tts->symbol_to_id.at("sp"));
        const auto encoded = encode_phonemes(phonemes, tts->symbol_to_id, pause_id);
        // Reject silence-only text even when it spans more than one chunk.
        if (encoded.data.empty() || std::all_of(encoded.data.begin(), encoded.data.end(),
                [pause_id](float id) { return id == pause_id; })) {
            set_status(status, TTS_ZH_NO_PHONEMES);
            return nullptr;
        }
        auto *output = allocate_output(encoded);
        set_status(status, TTS_ZH_OK);
        return output;
    } catch (const std::bad_alloc &) {
        set_status(status, TTS_ZH_OUT_OF_MEMORY);
    } catch (...) {
        set_status(status, TTS_ZH_PREPROCESS_FAILED);
    }
    return nullptr;
}

TtsZhOutput *tts_zh_frontend_preprocess(TtsZh *tts, const char *text) {
    return tts_zh_frontend_preprocess_safe(tts, text, nullptr);
}

void tts_zh_output_destroy(TtsZhOutput *output) {
    if (output != nullptr) {
        free(output->data);
        free(output->len_data);
        free(output);
    }
}

void tts_zh_free_output(void *context) {
    tts_zh_output_destroy(static_cast<TtsZhOutput *>(context));
}

void tts_save_wav(float *wav_data, int wav_len, const char *wav_filename, int sample_rate) {
    try {
        std::vector<float> samples(wav_data, wav_data + wav_len);
        VoxUtil::ExportWAV(wav_filename, samples, sample_rate);
    } catch (...) {
        // Do not allow an STL or I/O exception to cross the C ABI boundary.
    }
}
