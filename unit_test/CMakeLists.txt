cmake_minimum_required(VERSION 3.16)
project(canmv_unit_test LANGUAGES C CXX)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

execute_process(
    COMMAND "${CMAKE_CURRENT_SOURCE_DIR}/scripts/generate_test_suggestions.sh"
    WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
    RESULT_VARIABLE GEN_RESULT
)
if(NOT GEN_RESULT EQUAL 0)
    message(FATAL_ERROR "Failed to generate ALL_SOURCE_UNIT_TEST_SUGGESTIONS.md")
endif()

find_package(Threads REQUIRED)
find_package(GTest REQUIRED)
include(GoogleTest)

enable_testing()

set(CANMV_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/..")

add_library(canmv_host_shims STATIC
    src/xalloc_host.c
    src/micropython_host_stubs.c
)
target_include_directories(canmv_host_shims PRIVATE
    "${CMAKE_CURRENT_SOURCE_DIR}/stubs"
    "${CANMV_ROOT}/port/omv/alloc"
)

add_executable(canmv_unit_tests
    tests/test_all_sources_catalog.cpp
    tests/test_array.cpp
    tests/test_ringbuf.cpp
    tests/test_unaligned_memcpy.cpp
    tests/test_mutex.cpp
    tests/test_ff_wrapper.cpp
    tests/test_python_sources.cpp
    tests/test_recent_fixes_guardrails.cpp
    tests/test_ai_rvv_kernels.cpp
    tests/test_ai_segmentation_ownership.cpp
    tests/test_nanotracker_postprocess.cpp
    "${CANMV_ROOT}/port/ai_demo/nanotracker.cpp"
    "${CANMV_ROOT}/port/ai_demo/ai_rvv_kernels.cpp"
    "${CANMV_ROOT}/port/omv/common/array.c"
    "${CANMV_ROOT}/port/omv/common/ringbuf.c"
    "${CANMV_ROOT}/port/omv/alloc/unaligned_memcpy.c"
    "${CANMV_ROOT}/port/omv/common/mutex.c"
    "${CANMV_ROOT}/port/omv/common/ff_wrapper.c"
)

target_compile_definitions(canmv_unit_tests PRIVATE
    CANMV_SOURCE_ROOT="${CANMV_ROOT}"
    CANMV_UNIT_TEST_ROOT="${CMAKE_CURRENT_SOURCE_DIR}"
)

target_include_directories(canmv_unit_tests PRIVATE
    "${CANMV_ROOT}/port/include"
    "${CANMV_ROOT}/port/include/ai_demo"
    "${CMAKE_CURRENT_SOURCE_DIR}/stubs"
    "${CANMV_ROOT}/port/omv/common"
    "${CANMV_ROOT}/port/omv/alloc"
)

target_link_libraries(canmv_unit_tests PRIVATE
    canmv_host_shims
    GTest::gtest
    GTest::gtest_main
    Threads::Threads
)

gtest_discover_tests(canmv_unit_tests
    DISCOVERY_TIMEOUT 60
)
