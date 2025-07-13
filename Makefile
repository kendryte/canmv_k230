ifneq ($(MKENV_INCLUDED),1)
export SDK_SRC_ROOT_DIR := $(realpath $(dir $(realpath $(lastword $(MAKEFILE_LIST))))/../../)
endif

include $(SDK_SRC_ROOT_DIR)/tools/mkenv.mk

ifneq ($(shell [ -d ${SDK_BUILD_IMAGES_DIR}/sdcard/ ] && echo 1 || echo 0),1)
$(shell mkdir -p ${SDK_BUILD_IMAGES_DIR}/sdcard/)
endif

.PHONY: all clean distclean

.PHONY: copy_micropython
copy_micropython:
	@echo "Copy micropython"
	@if [ ! -e $(SDK_CANMV_BUILD_DIR)/micropython ]; then \
		echo "micropython not exists." && exit 1; \
	fi; \
	cp -rf $(SDK_CANMV_BUILD_DIR)/micropython ${SDK_BUILD_IMAGES_DIR}/sdcard/

.PHONY: build
build:
	@$(MAKE) -j$(NCPUS) -C k230 || exit $?;

.PHONY: gen_image
gen_image: build copy_micropython

all: gen_image
	@echo "Make canmv done."

clean:
	@rm -rf ${SDK_BUILD_IMAGES_DIR}/sdcard/
	@make -C k230 clean

distclean: clean
	@rm -rf $(SDK_CANMV_BUILD_DIR)
