// Host regression harness: real TTS sources/dictionaries, no models or device APIs.
#include "aidemo_wrap.h"
#include "zh_frontend.h"

#include <cassert>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

static int allocations_before_failure = -1;
static size_t live_allocations = 0;
static void *tracked[3]{};

extern "C" void *__real_malloc(size_t);
extern "C" void *__real_calloc(size_t, size_t);
extern "C" void __real_free(void *);

static bool fail_allocation() {
    if (allocations_before_failure < 0) return false;
    if (allocations_before_failure == 0) return true;
    --allocations_before_failure;
    return false;
}

static void *track(void *pointer) {
    if (pointer && allocations_before_failure >= 0) {
        for (auto &slot : tracked) {
            if (!slot) {
                slot = pointer;
                ++live_allocations;
                return pointer;
            }
        }
        assert(false && "unexpected native output allocation");
    }
    return pointer;
}

extern "C" void *__wrap_malloc(size_t size) {
    return fail_allocation() ? nullptr : track(__real_malloc(size));
}

extern "C" void *__wrap_calloc(size_t count, size_t size) {
    return fail_allocation() ? nullptr : track(__real_calloc(count, size));
}

extern "C" void __wrap_free(void *pointer) {
    for (auto &slot : tracked) {
        if (slot && slot == pointer) {
            slot = nullptr;
            --live_allocations;
            break;
        }
    }
    __real_free(pointer);
}

static void expect_error(TtsZh *tts, const char *text, TtsZhStatus expected) {
    TtsZhStatus status = TTS_ZH_OK;
    assert(tts_zh_frontend_preprocess_safe(tts, text, &status) == nullptr);
    assert(status == expected);
}

static void expect_output(TtsZh *tts, const char *text,
                          const std::vector<std::vector<float>> &expected,
                          float padding_id = 357.0f) {
    TtsZhStatus status = TTS_ZH_PREPROCESS_FAILED;
    auto *output = tts_zh_frontend_preprocess_safe(tts, text, &status);
    assert(status == TTS_ZH_OK && output);
    assert(output->len_size == expected.size());
    assert(output->size == 50 * expected.size());
    for (size_t i = 0; i < expected.size(); ++i) {
        assert(output->len_data[i] == static_cast<int>(expected[i].size()));
        for (size_t j = 0; j < 50; ++j) {
            const float wanted = j < expected[i].size() ? expected[i][j] : padding_id;
            assert(output->data[50 * i + j] == wanted);
        }
    }
    tts_zh_output_destroy(output);
}

int main(int argc, char **argv) {
    assert(argc == 3);
    const std::string utils = argv[1], temporary = argv[2];
    const auto dict = utils + "/pinyin.txt";
    const auto phrases = utils + "/small_pinyin.txt";
    const auto map = utils + "/phone_map.txt";
    auto *tts = ttszh_create();
    assert(tts);
    expect_error(nullptr, "你好", TTS_ZH_INVALID_ARGUMENT);
    expect_error(tts, nullptr, TTS_ZH_INVALID_ARGUMENT);
    expect_error(tts, "你好", TTS_ZH_INVALID_ARGUMENT);
    assert(!ttszh_init_safe(tts, nullptr, phrases.c_str(), map.c_str()));
    assert(!ttszh_init_safe(tts, (temporary + "/missing").c_str(), phrases.c_str(), map.c_str()));
    assert(!ttszh_init_safe(tts, dict.c_str(), (temporary + "/missing").c_str(), map.c_str()));
    assert(!ttszh_init_safe(tts, dict.c_str(), phrases.c_str(), (temporary + "/missing").c_str()));
    for (const char *contents : {"", "sp\n", "sp -1\n", "n 159\n"}) {
        const auto bad_map = temporary + "/bad_map.txt";
        std::ofstream(bad_map) << contents;
        assert(!ttszh_init_safe(tts, dict.c_str(), phrases.c_str(), bad_map.c_str()));
    }
    assert(ttszh_init_safe(tts, dict.c_str(), phrases.c_str(), map.c_str()));

    zh_frontend frontend;
    for (const char *text : {"ABCDEFG", "abcdefg", "", "   ", "。", ".", "ABC，"}) {
        expect_error(tts, text, TTS_ZH_NO_PHONEMES);
        assert(tts_zh_frontend_preprocess(tts, text) == nullptr);
    }
    for (const char *text : {"ABCDEFG", "", "   "}) {
        assert(frontend.get_phonemes(text, false, true, false, false).empty());
        assert(frontend.get_phonemes(text, true, true, false, false).empty());
    }
    for (size_t length : {50, 51, 100}) {
        expect_error(tts, std::string(length, '.').c_str(), TTS_ZH_NO_PHONEMES);
    }
    expect_error(tts, "\xff", TTS_ZH_PREPROCESS_FAILED);
    for (int pass = 0; pass < 2; ++pass) {
        // Captured from the implementation before this refactor.
        #include "tts_frontend_fixtures.inc"
    }
    for (int failed = 0; failed < 3; ++failed) {
        allocations_before_failure = failed;
        expect_error(tts, "你好", TTS_ZH_OUT_OF_MEMORY);
        allocations_before_failure = -1;
        assert(live_allocations == 0);
    }
    // Successful reuse after every failure and the legacy entry point.
    auto *output = tts_zh_frontend_preprocess(tts, "你好");
    assert(output && output->size == 50 && output->len_data[0] == 4);
    tts_zh_free_output(output);
    tts_zh_free_output(nullptr);
    tts_zh_output_destroy(nullptr);

    // Padding/fallback/silence must follow sp, even if a speech symbol is 357.
    // Deliberately omit final phonemes to exercise the unknown-symbol fallback.
    const auto custom_map = temporary + "/custom_map.txt";
    std::ofstream(custom_map) << "sp 42\nn 357\nh 154\n";
    assert(ttszh_init_safe(tts, dict.c_str(), phrases.c_str(), custom_map.c_str()));
    expect_output(tts, "你好", {{357, 42, 154, 42}}, 42);
    expect_output(tts, "你好。", {{357, 42, 154, 42, 42}}, 42);
    for (size_t length : {1, 50, 51, 100}) {
        expect_error(tts, std::string(length, '.').c_str(), TTS_ZH_NO_PHONEMES);
    }
    // A final chunk containing only silence is still omitted with remapped sp.
    std::string speech;
    std::vector<float> first_chunk;
    for (int i = 0; i < 25; ++i) {
        speech += "你";
        first_chunk.insert(first_chunk.end(), {357, 42});
    }
    expect_output(tts, (speech + std::string(50, '.')).c_str(), {first_chunk}, 42);
    ttszh_destroy(tts);
    std::cout << "TTS fixtures, pause mappings, empty inputs, merged sentences, error statuses and allocation rollback passed.\n";
}
