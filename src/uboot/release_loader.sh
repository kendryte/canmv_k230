#!/bin/bash

set -e

source build_env.sh

# Temporary output folder base name
output_base="loader/build_"

# Get current time for folder name
timestamp=$(date +%Y%m%d_%H%M%S)

# Create a single temporary output folder for all configurations
temp_folder="${output_base}${timestamp}"
mkdir -p "$temp_folder"

temp_folder=$(realpath "$temp_folder")

pushd uboot

# make loader for mmc
make distclean
make k230_burntool_mmc_defconfig
make -j
mv u-boot.bin "$temp_folder/loader_mmc.bin"

# make loader for spi nand
make distclean
make k230_burntool_spi_nand_defconfig
make -j
mv u-boot.bin "$temp_folder/loader_spi_nand.bin"

# make loader for spi nor
make distclean
make k230_burntool_spi_nor_defconfig
make -j
mv u-boot.bin "$temp_folder/loader_spi_nor.bin"

# clean
make distclean

popd
