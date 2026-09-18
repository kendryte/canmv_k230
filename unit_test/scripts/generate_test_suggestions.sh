#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT_TEST_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SOURCE_ROOT="$(cd "${UNIT_TEST_DIR}/.." && pwd)"
OUT_FILE="${UNIT_TEST_DIR}/ALL_SOURCE_UNIT_TEST_SUGGESTIONS.md"

suggestion_for() {
    local rel="$1"
    case "$rel" in
        *.py)
            echo "Python/MicroPython module tests: importability, syntax validity, API behavior, and boundary/error handling." ;;
        *.h|*.hpp)
            echo "Header/API contract tests: compile inclusion, macro/type consistency, and source/header declaration drift checks." ;;
        port/core/*)
            echo "Boot/runtime state transitions, init/deinit order, and error-path tests with mocked RTOS/HAL." ;;
        port/machine/*)
            echo "Driver API contract tests: argument validation, boundary values, and HAL-failure handling with mocks." ;;
        port/omv/alloc/*)
            echo "Memory behavior tests: alignment, zero-length, resize semantics, and stress/fuzz safety checks." ;;
        port/omv/common/*)
            echo "Data-structure and utility API tests: ordering, edge conditions, ownership/lifetime, and concurrency assumptions." ;;
        port/omv/imlib/*)
            echo "Golden-vector algorithm tests plus malformed input and size-boundary regression cases." ;;
        port/omv/modules/*)
            echo "Micropython binding tests for argument parsing, exception mapping, and object lifecycle." ;;
        port/kpu/*|port/ai_demo/*|port/ai_cube/*|port/cv_lite/*)
            echo "Inference wrapper contract tests with fake backend: tensor shape/type validation and deterministic output mapping." ;;
        port/multi_media/*)
            echo "Stream/session state-machine tests: start-stop sequencing, buffer ownership, and timeout/retry behavior." ;;
        port/network/*)
            echo "Protocol and socket tests with fake transport: connect/reconnect paths, timeouts, and partial-read handling." ;;
        port/mp_modules/*|port/modules/*)
            echo "Micropython module surface tests: import/init behavior, parameter checking, and return/error consistency." ;;
        port/builtin_py/mpp_binding/*)
            echo "MPP binding tests: module table coverage, wrapper argument validation, and fake-MPP failure propagation." ;;
        resources/examples/*)
            echo "Example validation: syntax checks, board/API availability annotations, and smoke execution where dependencies can be stubbed." ;;
        resources/libs/*)
            echo "Library validation: importability, public API behavior, edge cases, and compatibility with MicroPython constraints." ;;
        tools/*)
            echo "Tooling tests: CLI argument handling, generated-output stability, and malformed-input behavior." ;;
        *)
            echo "Compile/smoke test plus API contract tests for normal, boundary, and failure paths." ;;
    esac
}

priority_for() {
    local rel="$1"
    case "$rel" in
        *.py)
            echo "Medium" ;;
        *.h|*.hpp)
            echo "Medium" ;;
        port/machine/*|port/core/*|port/omv/alloc/*|port/omv/common/*|port/builtin_py/mpp_binding/*)
            echo "High" ;;
        port/omv/imlib/*|port/network/*|port/multi_media/*|port/kpu/*|port/cv_lite/*|port/ai_demo/*|port/ai_cube/*)
            echo "Medium" ;;
        *)
            echo "Low" ;;
    esac
}

mapfile -t sources < <(
    find "${SOURCE_ROOT}" \
        -path "${UNIT_TEST_DIR}" -prune -o \
        -path "${SOURCE_ROOT}/micropython/mpy-cross/build" -prune -o \
        -type f \( -name '*.c' -o -name '*.cc' -o -name '*.cpp' -o -name '*.h' -o -name '*.hpp' -o -name '*.py' \) -print | sort
)

count_c=0
count_cc=0
count_cpp=0
count_h=0
count_hpp=0
count_py=0
for src in "${sources[@]}"; do
    case "$src" in
        *.c) ((++count_c)) ;;
        *.cc) ((++count_cc)) ;;
        *.cpp) ((++count_cpp)) ;;
        *.h) ((++count_h)) ;;
        *.hpp) ((++count_hpp)) ;;
        *.py) ((++count_py)) ;;
    esac
done

{
    echo "# CANMV Source-Wide Unit Test Suggestions"
    echo
    echo "Auto-generated on $(date -u +'%Y-%m-%d %H:%M:%S UTC')."
    echo
    echo "| Source File | Suggested Unit Test Focus | Priority |"
    echo "| --- | --- | --- |"

    for src in "${sources[@]}"; do
        rel="${src#${SOURCE_ROOT}/}"
        suggestion="$(suggestion_for "${rel}")"
        priority="$(priority_for "${rel}")"
        printf '| `%s` | %s | %s |\n' "${rel}" "${suggestion}" "${priority}"
    done

    echo
    echo "Total source files covered: ${#sources[@]}"
    echo "Language breakdown: C=${count_c}, CC=${count_cc}, C++=${count_cpp}, H=${count_h}, HPP=${count_hpp}, Python=${count_py}"
    echo
    echo "## Implemented gtests in this unit_test scaffold"
    echo "- port/omv/common/array.c"
    echo "- port/omv/common/ringbuf.c"
    echo "- port/omv/alloc/unaligned_memcpy.c"
    echo "- port/omv/common/mutex.c"
    echo "- port/omv/common/ff_wrapper.c"
    echo "- All-source catalog validation for C/C++/headers/Python inventory"
    echo
    echo "## Next implementation order"
    echo "1. port/omv/common/* and port/omv/alloc/* remaining files"
    echo "2. port/machine/* with HAL mocks"
    echo "3. port/modules/*, port/mp_modules/*, and port/builtin_py/mpp_binding/* MicroPython binding tests"
    echo "4. port/omv/imlib/* algorithm vectors"
    echo "5. resources/**/*.py syntax/import behavior tests with dependency stubs or on-device execution"
} > "${OUT_FILE}"
