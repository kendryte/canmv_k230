#!/bin/bash
SCRIPT=$(realpath -s "$0")
SCRIPTPATH=$(dirname "$SCRIPT")

export SDK_SRC_ROOT_DIR=$(realpath ${SCRIPTPATH}/../../)
export RTSMART_SRC_DIR=$(realpath ${SDK_SRC_ROOT_DIR}/src/rtsmart/rtsmart)
export MPP_SRC_DIR=$(realpath ${SDK_SRC_ROOT_DIR}/src/rtsmart/mpp)
export RTT_SDK_BUILD_DIR="/tmp"
export RTT_CC=gcc
export RTT_CC_PREFIX=riscv64-unknown-linux-musl-
export RTT_EXEC_PATH=~/.kendryte/k230_toolchains/riscv64-linux-musleabi_for_x86_64-pc-linux-gnu/bin
export PATH=$PATH:$RTT_EXEC_PATH
