#!/usr/bin/env python3
"""Exercise production TTS normalization and concurrent first-use regex setup."""

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "unit_test/stubs/tts_regex_cases.json"
SOURCES = ("_utils", "char_convert", "chronology", "finals", "num", "phonecode",
           "pinyin_utils", "pypinyin", "quantifier", "standard",
           "text_normalization", "tone")

HARNESS = r'''
#include <cassert>
#include <atomic>
#include <fstream>
#include <iostream>
#include <map>
#include <regex>
#include <string>
#include <thread>
#include <vector>
#include "text_normalization.h"
#include "pypinyin.h"
#include "standard.h"
#include "tone.h"
#include "chronology.h"

const std::regex *other_date_pattern();
static void check_shared_first_use() {
    std::atomic<bool> ready{false};
    const std::regex *addresses[8]{};
    std::vector<std::thread> threads;
    for (int i = 0; i < 8; ++i) {
        threads.emplace_back([&, i] {
            while (!ready.load()) std::this_thread::yield();
            addresses[i] = i % 2 ? other_date_pattern() : &RE_DATE();
            assert(std::regex_match("2026年", *addresses[i]));
        });
    }
    ready.store(true);
    for (auto &thread : threads) thread.join();
    for (auto address : addresses) assert(address == addresses[0]);
    assert(&RE_DATE() == addresses[0]);
}

int main(int argc, char **argv) {
    assert(argc == 2);
    std::ofstream report(argv[1]);
    assert(report);
    check_shared_first_use();
    Pypinyin pinyin;
    pinyin.PINYIN_DICT = {{0x4e2d, "zhōng"}, {0x56fd, "guó"}, {0x4f60, "nǐ"},
                         {0x597d, "hǎo"}, {0x5973, "nǚ"}, {0x7eff, "lǜ"}};
    std::string input;
    while (std::getline(std::cin, input)) {
        char mode = input.at(0);
        std::string text = input.substr(2);
        if (mode == 'N') {
            report << normalize_sentence(text);
        } else if (mode == 'T') {
            report << to_tone3(text);
        } else if (mode == 'F') {
            report << convert_finals(text);
        } else if (mode == 'P') {
            auto result = pinyin.lazy_pinyin(text, Style::TONE3, false, "default", true);
            bool first = true;
            for (const auto &group : result) {
                for (const auto &syllable : group) {
                    if (!first) report << '|';
                    report << syllable;
                    first = false;
                }
            }
        } else {
            return 2;
        }
        report << '\n';
    }
}
'''


def build_runner(port, directory, *, source_names=SOURCES, harness_text=HARNESS,
                 extra_flags=(), link_flags=()):
    compiler = shlex.split(os.environ.get("CXX", "c++"))
    includes = port / "include/ai_demo/tts_zh"
    sources = [port / "ai_demo/tts_zh" / f"{name}.cpp" for name in source_names]
    harness = directory / "harness.cpp"
    harness.write_text(harness_text)
    sources.append(harness)
    other = directory / "other.cpp"
    other.write_text('#include "chronology.h"\n'
                     'const std::regex *other_date_pattern() { return &RE_DATE(); }\n')
    sources.append(other)
    # Older target headers supplied these integer types transitively.
    flags = ["-std=c++20", "-O0", "-g", "-pthread", "-include", "cstdint",
             "-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-I", str(includes)]
    flags.extend(extra_flags)

    def compile_source(item):
        i, source = item
        obj = directory / f"{i}.o"
        subprocess.run(compiler + flags + ["-c", str(source), "-o", str(obj)], check=True)
        return obj

    with ThreadPoolExecutor(max_workers=4) as pool:
        objects = list(pool.map(compile_source, enumerate(sources)))
    executable = directory / "tts_test"
    subprocess.run(compiler + flags + [str(obj) for obj in objects] +
                   [*link_flags, "-o", str(executable)], check=True)
    return executable


def run_cases(executable, cases):
    request = "".join(f"{case['mode']}\t{case['input']}\n" for case in cases)
    # Legacy TTS helpers print debugging to stdout; capture return values separately.
    report = executable.parent / "results.txt"
    result = subprocess.run([str(executable), str(report)], input=request, capture_output=True,
                            text=True)
    if result.returncode:
        raise AssertionError(f"TTS runner exited {result.returncode}: {result.stderr}")
    if result.stderr:
        raise AssertionError(result.stderr)
    return report.read_text().splitlines()


def main():
    cases = json.loads(FIXTURES.read_text())
    with tempfile.TemporaryDirectory(prefix="canmv-tts-regex-") as directory:
        executable = build_runner(ROOT / "port", Path(directory))
        # Two passes exercise both initial creation and reuse by real TTS calls.
        observed = run_cases(executable, cases + cases)
        expected = [case["expected"] for case in cases] * 2
        assert len(observed) == len(expected), (len(observed), len(expected))
        for case, actual, wanted in zip(cases + cases, observed, expected):
            assert actual == wanted, (case, actual)
        print(f"{len(observed)} TTS results match the pre-change fixtures; "
              "concurrent first use and sharing across translation units passed.")


if __name__ == "__main__":
    main()
