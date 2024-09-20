#!/bin/bash

source ${SDK_SRC_ROOT_DIR}/.config
source ${SDK_TOOLS_DIR}/gen_image_func.sh

gen_repo_info()
{
	pushd ${SDK_SRC_ROOT_DIR} > /dev/null

	input_data=`repo info`
	temp_file=${SDK_BUILD_DIR}/repo_info.tmp

	> $temp_file
	# Process the input data
	echo "$input_data" | awk '
	/^Project:/ {project=$2}
	/Current revision:/ {
		revision=$3
		# Extract last segment of the project path
		split(project, parts, "/")
		last_segment=parts[length(parts)]
		print last_segment "=" revision >> "'$temp_file'"
	}'

	sed 's/-/_/g' $temp_file > $repo_info_file

    echo "Build time $(date)" >> $repo_info_file

	popd > /dev/null
}

gen_image()
{
	local config="$1";
	local image="$2";

	GENIMAGE_TMP="genimage.tmp"; rm -rf "${GENIMAGE_TMP}";
	${TOOL_GENIMAGE} --rootpath "${SDK_BUILD_IMAGES_DIR}" --tmppath "${GENIMAGE_TMP}" --inputpath "${SDK_BUILD_IMAGES_DIR}" --outputpath "${SDK_BUILD_DIR}" --config "${config}"

	rm -rf "${GENIMAGE_TMP}"
    mv ${SDK_BUILD_DIR}/sysimage-sdcard.img ${SDK_BUILD_DIR}/${image}

    echo "Compress image ${image}.gz, it will took a while"

    gzip -k -f ${SDK_BUILD_DIR}/${image}
    chmod a+rw ${SDK_BUILD_DIR}/${image} ${SDK_BUILD_DIR}/${image}.gz;
    md5sum ${SDK_BUILD_DIR}/${image} ${SDK_BUILD_DIR}/${image}.gz > ${SDK_BUILD_DIR}/${image}.gz.md5
}

parse_repo_version()
{
    pushd "${SDK_CANMV_SRC_DIR}" > /dev/null

    # Get the revision and store it in a variable
    revision=$(git describe --long --tag --dirty --always)

    popd > /dev/null

    # Print the revision to be captured by the caller
    echo "$revision"
}

parse_nncase_version()
{
    # Extract the version from the header file
    VERSION=$(grep -oP '(?<=#define NNCASE_VERSION ")[^"]*' ${SDK_RTSMART_SRC_DIR}/libs/nncase/riscv64/nncase/include/nncase/version.h)

    echo "$VERSION"
}

# generate nncase version
nncase_version=$(parse_nncase_version)

repo_info_file=${SDK_BUILD_DIR}/repo_info
gen_repo_info
cp -f $repo_info_file ${SDK_BUILD_IMAGES_DIR}/sdcard/revision.txt

# Read the file line by line
while IFS='=' read -r key value; do
  # Skip empty lines or lines that don't contain '='
  if [ -z "$key" ] || [ -z "$value" ]; then
    continue
  fi

  # Assign the value to the variable
  eval "$key=\"$value\""

  # Print the variable to verify
  echo "Repo '$key' commit is '${!key}'"
done < "$repo_info_file"

# Delete kmodels if running in CI
if [ "$IS_CI" = "2" ]; then
    mkdir -p ${SDK_BUILD_IMAGES_DIR}/sdcard/examples/kmodel/
    rm -rf ${SDK_BUILD_IMAGES_DIR}/sdcard/examples/kmodel/*

    output_file="${SDK_BUILD_IMAGES_DIR}/sdcard/README.txt"
    cat <<EOF > "$output_file"
请从网络下载模型文件并解压，将“ai_poc/kmodel”下的模型文件复制到SDCARD分区的“examples/kmodel”目录
Please download the model file from the Internet and decompress it. Copy the model file under "ai_poc/kmodel" to the "examples/kmodel" directory of the SDCARD partition.
下载地址为https://kendryte-download.canaan-creative.com/k230/downloads/kmodel/kmodel_v$nncase_version.tgz
EOF
fi

# generate image name
if [ "$IS_CI" = "1" ] || [ "$IS_CI" = "2" ]; then
    if [ "$CONFIG_SDK_ENABLE_CANMV" = "y" ]; then
        canmv_revision=$(parse_repo_version ${SDK_CANMV_SRC_DIR})
        image_name="${MK_IMAGE_NAME}_micropython_PreRelease_nncase_v${nncase_version}.img"
    else
        rtsmart_revision=$(parse_repo_version ${SDK_RTSMART_SRC_DIR})
        image_name="${MK_IMAGE_NAME}_rtsmart_PreRelease_nncase_v${nncase_version}.img"
    fi
else
    if [ "$CONFIG_SDK_ENABLE_CANMV" = "y" ]; then
        if [ -z "$CI" ]; then
            canmv_revision="local"
        else
            canmv_revision=$(parse_repo_version ${SDK_CANMV_SRC_DIR})
        fi
        echo "canmv_revision '${canmv_revision}'"
        image_name="${MK_IMAGE_NAME}_micropython_${canmv_revision}_nncase_v${nncase_version}.img"
    else
        if [ -z "$CI" ]; then
            rtsmart_revision="local"
        else
            rtsmart_revision=$(parse_repo_version ${SDK_RTSMART_SRC_DIR})
        fi
        image_name="${MK_IMAGE_NAME}_rtsmart_${rtsmart_revision}nncase_v${nncase_version}.img"
    fi
fi

gen_image ${SDK_BOARD_DIR}/${CONFIG_BOARD_GEN_IMAGE_CFG_FILE} $image_name;
