ifneq ($(MKENV_INCLUDED),1)
export SDK_SRC_ROOT_DIR := $(realpath $(dir $(realpath $(lastword $(MAKEFILE_LIST))))/../../)
include $(SDK_SRC_ROOT_DIR)/tools/mkenv.mk
endif

subdirs-y :=
include apps.mk

# Add directories to the build system
subdirs := $(sort $(subdirs-y))

ifneq ($(strip $(subdirs-y)),)
	ifneq ($(shell [ -d ${SDK_BUILD_IMAGES_DIR}/sdcard/app/ ] && echo 1 || echo 0),1)
		$(shell mkdir -p ${SDK_BUILD_IMAGES_DIR}/sdcard/app/)
	endif
endif

export SDK_APPS_IMAGE_DIR := ${SDK_BUILD_IMAGES_DIR}/sdcard/app/

.PHONY: all clean distclean

all:
	@$(foreach dir,$(subdirs),$(MAKE) -C $(dir) all;)

clean:
	@$(foreach dir,$(subdirs),$(MAKE) -C $(dir) clean;)

distclean: clean
	@$(foreach dir,$(subdirs),$(MAKE) -C $(dir) distclean;)

.PHONY: gen_kconfig
gen_kconfig:
	@echo "# Dynamic generate by Makefile, DO NOT Modify it.\n" > $(SDK_BUILD_DIR)/Kconfig.app; \
	for dir in $(shell find $(SDK_APPS_SRC_DIR) -maxdepth 1 -mindepth 1 -type d); do \
		echo "source \"$$dir/Kconfig\"" >> $(SDK_BUILD_DIR)/Kconfig.app; \
	done; \
