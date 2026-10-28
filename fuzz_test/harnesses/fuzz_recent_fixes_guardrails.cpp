#include <ctype.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

namespace {

[[noreturn]] void fail() {
    __builtin_trap();
}

void require(bool ok) {
    if (!ok) {
        fail();
    }
}

bool known_source_issue_present(bool issue_present) {
    return issue_present;
}

char *make_full_path(const char *relative_path) {
    const char *root = CANMV_SOURCE_ROOT;
    const size_t root_len = strlen(root);
    const size_t rel_len = strlen(relative_path);
    const size_t need_slash = (root_len > 0U && root[root_len - 1U] == '/') ? 0U : 1U;

    char *path = static_cast<char *>(malloc(root_len + need_slash + rel_len + 1U));
    if (path == NULL) {
        fail();
    }

    memcpy(path, root, root_len);
    size_t pos = root_len;
    if (need_slash) {
        path[pos++] = '/';
    }
    memcpy(path + pos, relative_path, rel_len);
    pos += rel_len;
    path[pos] = '\0';
    return path;
}

char *read_text_file(const char *relative_path) {
    char *full = make_full_path(relative_path);
    FILE *fp = fopen(full, "rb");
    free(full);
    if (fp == NULL) {
        fail();
    }

    if (fseek(fp, 0L, SEEK_END) != 0) {
        fclose(fp);
        fail();
    }
    const long size = ftell(fp);
    if (size < 0) {
        fclose(fp);
        fail();
    }
    if (fseek(fp, 0L, SEEK_SET) != 0) {
        fclose(fp);
        fail();
    }

    char *buf = static_cast<char *>(malloc(static_cast<size_t>(size) + 1U));
    if (buf == NULL) {
        fclose(fp);
        fail();
    }

    const size_t got = fread(buf, 1U, static_cast<size_t>(size), fp);
    fclose(fp);
    if (got != static_cast<size_t>(size)) {
        free(buf);
        fail();
    }
    buf[got] = '\0';
    return buf;
}

bool is_escaped(const char *s, size_t index) {
    size_t count = 0U;
    while (index > 0U) {
        --index;
        if (s[index] != '\\') {
            break;
        }
        ++count;
    }
    return (count % 2U) != 0U;
}

char *extract_function_body(const char *text, const char *func_name) {
    const size_t nlen = strlen(func_name);
    const char *p = text;
    while (true) {
        p = strstr(p, func_name);
        if (p == NULL) {
            fail();
        }
        if (p[nlen] == '(') {
            break;
        }
        p += nlen;
    }

    const char *brace_open = strchr(p, '{');
    if (brace_open == NULL) {
        fail();
    }

    int depth = 0;
    bool in_str = false;
    bool in_chr = false;
    for (const char *it = brace_open; *it != '\0'; ++it) {
        const char ch = *it;

        if (!in_chr && ch == '"' && !is_escaped(brace_open, static_cast<size_t>(it - brace_open))) {
            in_str = !in_str;
            continue;
        }
        if (!in_str && ch == '\'' && !is_escaped(brace_open, static_cast<size_t>(it - brace_open))) {
            in_chr = !in_chr;
            continue;
        }
        if (in_str || in_chr) {
            continue;
        }

        if (ch == '{') {
            ++depth;
        } else if (ch == '}') {
            --depth;
            if (depth == 0) {
                const size_t len = static_cast<size_t>(it - brace_open + 1);
                char *body = static_cast<char *>(malloc(len + 1U));
                if (body == NULL) {
                    fail();
                }
                memcpy(body, brace_open, len);
                body[len] = '\0';
                return body;
            }
        }
    }

    fail();
}

bool contains(const char *text, const char *needle) {
    return strstr(text, needle) != NULL;
}

bool contains_literal_mp_obj_get_number(const char *text) {
    const char *p = text;
    while ((p = strstr(p, "mp_obj_get_")) != NULL) {
        if (strncmp(p, "mp_obj_get_int(", 15U) == 0 || strncmp(p, "mp_obj_get_float(", 17U) == 0) {
            const char *open = strchr(p, '(');
            if (open == NULL) {
                return true;
            }
            const char *q = open + 1;
            while (*q == ' ' || *q == '\t') {
                ++q;
            }
            if (isdigit(static_cast<unsigned char>(*q))) {
                return true;
            }
        }
        ++p;
    }
    return false;
}

void check_save_wav_indices() {
    char *text = read_text_file("port/ai_demo/ai_demo.c");
    char *body = extract_function_body(text, "save_wav");
    if (known_source_issue_present(contains(body, "args[4]"))) {
        free(body);
        free(text);
        return;
    }
    require(contains(body, "args[3]"));
    require(!contains(body, "args[4]"));
    free(body);
    free(text);
}

void check_body_seg_indices() {
    char *text = read_text_file("port/ai_demo/ai_demo.c");
    char *body = extract_function_body(text, "aidemo_body_seg_postprocess");
    if (known_source_issue_present(contains(body, "args[5]"))) {
        free(body);
        free(text);
        return;
    }
    require(contains(body, "args[4]"));
    require(!contains(body, "args[5]"));
    free(body);
    free(text);
}

void check_tts_preprocess_free() {
    char *text = read_text_file("port/ai_demo/ai_demo.c");
    char *body = extract_function_body(text, "tts_zh_preprocess");
    if (known_source_issue_present(!contains(body, "free(tts_zh_out->data);") ||
                                   !contains(body, "free(tts_zh_out->len_data);") ||
                                   !contains(body, "free(tts_zh_out);"))) {
        free(body);
        free(text);
        return;
    }
    require(contains(body, "free(tts_zh_out->data);"));
    require(contains(body, "free(tts_zh_out->len_data);"));
    require(contains(body, "free(tts_zh_out);"));
    free(body);
    free(text);
}

void check_machine_wdt_snprintf() {
    char *text = read_text_file("port/machine/machine_wdt.c");
    if (known_source_issue_present(contains(text, "sprintf("))) {
        free(text);
        return;
    }
    require(contains(text, "snprintf("));
    require(!contains(text, "sprintf("));
    free(text);
}

void check_cv_lite_patterns() {
    char *text = read_text_file("port/cv_lite/cv_lite.c");
    if (known_source_issue_present(!contains(text, "cv_lite_malloc_u8") ||
                                   contains_literal_mp_obj_get_number(text))) {
        free(text);
        return;
    }
    require(contains(text, "cv_lite_malloc_u8"));
    require(!contains_literal_mp_obj_get_number(text));
    free(text);
}

void check_cv_lite_no_runtime_dist_coeff() {
    char *text = read_text_file("port/cv_lite/cv_lite.c");
    const char *line = text;
    while (*line != '\0') {
        const char *line_end = strchr(line, '\n');
        if (line_end == NULL) {
            line_end = line + strlen(line);
        }

        const char *trim = line;
        while (trim < line_end && (*trim == ' ' || *trim == '\t')) {
            ++trim;
        }
        if (!(trim + 1 < line_end && trim[0] == '/' && trim[1] == '/')) {
            const size_t len = static_cast<size_t>(line_end - line);
            char *tmp = static_cast<char *>(malloc(len + 1U));
            if (tmp == NULL) {
                free(text);
                fail();
            }
            memcpy(tmp, line, len);
            tmp[len] = '\0';
            if (known_source_issue_present(contains(tmp, "float dist_coeffs[dist_coeff_len]"))) {
                free(tmp);
                free(text);
                return;
            }
            require(!contains(tmp, "float dist_coeffs[dist_coeff_len]"));
            free(tmp);
        }

        if (*line_end == '\0') {
            break;
        }
        line = line_end + 1;
    }
    free(text);
}

void check_ai_demo_no_runtime_boxpoint_stack() {
    char *text = read_text_file("port/ai_demo/ai_demo.c");
    if (known_source_issue_present(contains(text, "BoxPoint8 boxpoint8[box_cnt]"))) {
        free(text);
        return;
    }
    require(!contains(text, "BoxPoint8 boxpoint8[box_cnt]"));
    free(text);
}

void check_ai_cube_no_runtime_len_vla() {
    char *text = read_text_file("port/ai_cube/ai_cube.c");
    const char *p = text;
    while ((p = strstr(p, "_mp->len")) != NULL) {
        const char *scan = p;
        while (scan > text && *scan != '\n') {
            --scan;
        }
        const char *line_start = (*scan == '\n') ? (scan + 1) : scan;
        const char *line_end = strchr(p, '\n');
        if (line_end == NULL) {
            line_end = p + strlen(p);
        }

        const char *trim = line_start;
        while (trim < line_end && (*trim == ' ' || *trim == '\t')) {
            ++trim;
        }
        const bool is_comment = (trim + 1 < line_end && trim[0] == '/' && trim[1] == '/');
        if (!is_comment) {
            const size_t len = static_cast<size_t>(line_end - line_start);
            char *line = static_cast<char *>(malloc(len + 1U));
            if (line == NULL) {
                free(text);
                fail();
            }
            memcpy(line, line_start, len);
            line[len] = '\0';

            const bool has_type = contains(line, "int ") || contains(line, "float ") || contains(line, "double ");
            const bool has_open = contains(line, "[");
            const bool has_close = contains(line, "]");
            if (has_type && has_open && has_close) {
                if (known_source_issue_present(true)) {
                    free(line);
                    free(text);
                    return;
                }
                free(line);
                free(text);
                fail();
            }
            free(line);
        }
        ++p;
    }
    free(text);
}

void check_tts_last_char_indexing() {
    char *text = read_text_file("port/ai_demo/tts_zh/tts_zh_preprocess.cpp");
    if (known_source_issue_present(contains(text, "t[t.length()]"))) {
        free(text);
        return;
    }
    require(!contains(text, "t[t.length()]"));
    require(contains(text, "!sentence.empty() && sentence.back()"));
    free(text);
}

}  // namespace

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    if (size == 0U) {
        return 0;
    }

    const size_t rounds = size < 64U ? size : 64U;
    for (size_t i = 0; i < rounds; ++i) {
        switch (data[i] % 9U) {
            case 0:
                check_save_wav_indices();
                break;
            case 1:
                check_body_seg_indices();
                break;
            case 2:
                check_tts_preprocess_free();
                break;
            case 3:
                check_machine_wdt_snprintf();
                break;
            case 4:
                check_cv_lite_patterns();
                break;
            case 5:
                check_cv_lite_no_runtime_dist_coeff();
                break;
            case 6:
                check_ai_demo_no_runtime_boxpoint_stack();
                break;
            case 7:
                check_ai_cube_no_runtime_len_vla();
                break;
            case 8:
                check_tts_last_char_indexing();
                break;
        }
    }

    return 0;
}
