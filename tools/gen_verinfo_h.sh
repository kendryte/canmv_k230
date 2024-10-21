#!/bin/bash

source ${SDK_SRC_ROOT_DIR}/.config


parse_nncase_version()
{
    # Extract the version from the header file
    VERSION=$(grep -oP '(?<=#define NNCASE_VERSION ")[^"]*' ${SDK_RTSMART_SRC_DIR}/libs/nncase/riscv64/nncase/include/nncase/version.h)

    echo "$VERSION"
}
gen_version_file()
{
    local version_file="$1"

    local nncase_version=$(parse_nncase_version)
    local sdk_ver="unknown"
    local canmv_ver="unknown"

    pushd "${SDK_SRC_ROOT_DIR}" > /dev/null
        local commitid="unknown"
        local last_tag="unknown"
        git rev-parse --short HEAD  &&  commitid=$(git rev-parse --short HEAD)
        git describe --tags `git rev-list --tags --max-count=1` && last_tag=$(git describe --tags `git rev-list --tags --max-count=1`)
        git describe --tags --exact-match  && last_tag=$(git describe --tags --exact-match)
        sdk_ver="${last_tag}-$(date "+%Y%m%d-%H%M%S")-$(whoami)-$(hostname)-${commitid}"
    popd > /dev/null


    if [ "$CONFIG_SDK_ENABLE_CANMV" = "y" ]; then
        pushd "${SDK_CANMV_SRC_DIR}" > /dev/null
            local commitid="unknown"
            local last_tag="unknown"
            git rev-parse --short HEAD  &&  commitid=$(git rev-parse --short HEAD)
            git describe --tags `git rev-list --tags --max-count=1` && last_tag=$(git describe --tags `git rev-list --tags --max-count=1`)
            git describe --tags --exact-match  && last_tag=$(git describe --tags --exact-match)
            canmv_ver="${last_tag}-$(date "+%Y%m%d-%H%M%S")-$(whoami)-$(hostname)-${commitid}"
        popd > /dev/null
    fi
    echo -e "#ifndef __VER___INFO___H__\n#define __VER___INFO___H__\n" >${version_file}
    echo "#define SDK_VERSION_  \"${sdk_ver}\"" >> ${version_file}
    echo "#define NNCASE_VERSION_ \"${nncase_version}\"" >> ${version_file}
    [ "$CONFIG_SDK_ENABLE_CANMV" = "y" ] && echo "#define CANMV_VERSION_ \"${canmv_ver}\"" >> ${version_file}
    echo -e "#endif \n" >>${version_file}
    #cat $repo_info_file >> ${version_file}
}
gen_version_file $1
