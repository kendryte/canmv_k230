ifneq ($(MKENV_INCLUDED),1)
export SDK_SRC_ROOT_DIR := $(realpath $(dir $(realpath $(lastword $(MAKEFILE_LIST))))/../../)
include $(SDK_SRC_ROOT_DIR)/tools/mkenv.mk
endif

ifneq ($(shell [ -d ${SDK_BUILD_IMAGES_DIR}/sdcard/ ] && echo 1 || echo 0),1)
$(shell mkdir -p ${SDK_BUILD_IMAGES_DIR}/sdcard/)
endif
export SDK_APPS_IMAGE_DIR := ${SDK_BUILD_IMAGES_DIR}/sdcard/

subdirs :=
include apps.mk

.PHONY: all clean distclean

all:
	@$(foreach dir,$(subdirs),$(MAKE) -C $(dir) all;)

clean:
	@$(foreach dir,$(subdirs),$(MAKE) -C $(dir) clean;)

distclean: clean
	@$(foreach dir,$(subdirs),$(MAKE) -C $(dir) dist-clean;)

.PHONY: gen_kconfig
gen_kconfig:
	@echo "# Dynamic generate by Makefile, DO NOT Modify it.\n" > $(SDK_BUILD_DIR)/Kconfig.app; \
	for dir in $(subdirs); do \
		echo "source \"$(SDK_APPS_SRC_DIR)/$$dir/Kconfig\"" >> $(SDK_BUILD_DIR)/Kconfig.app; \
	done; \
