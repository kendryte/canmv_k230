#!/bin/bash

source ${SDK_SRC_ROOT_DIR}/.config
source ${SDK_TOOLS_DIR}/gen_image_func.sh

gen_image()
{
	local config="$1";
	local image="$2";

	GENIMAGE_TMP="genimage.tmp"; rm -rf "${GENIMAGE_TMP}";
	${TOOL_GENIMAGE} --rootpath "${SDK_BUILD_IMAGES_DIR}" --tmppath "${GENIMAGE_TMP}" --inputpath "${SDK_BUILD_IMAGES_DIR}" --outputpath "${SDK_BUILD_DIR}" --config "${config}"

	rm -rf "${GENIMAGE_TMP}"
	gzip -k -f ${SDK_BUILD_DIR}/${image}
	chmod a+rw ${SDK_BUILD_DIR}/${image} ${SDK_BUILD_DIR}/${image}.gz;
	# gz_file_add_ver ${image}.gz
}

gen_image ${SDK_BOARD_DIR}/${CONFIG_BOARD_GEN_IMAGE_CFG_FILE} sysimage-sdcard.img;
