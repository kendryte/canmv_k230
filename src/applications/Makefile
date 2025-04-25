ifneq ($(MKENV_INCLUDED),1)
export SDK_SRC_ROOT_DIR := $(realpath $(dir $(realpath $(lastword $(MAKEFILE_LIST))))/../../)

include $(SDK_SRC_ROOT_DIR)/tools/mkenv.mk

endif

export SDK_APPS_IMAGE_DIR := ${SDK_BUILD_IMAGES_DIR}/sdcard/app/

subdirs-y :=
include apps.mk

# Add directories to the build system
subdirs := $(sort $(subdirs-y))

.PHONY: all clean distclean

# Target to check and create the directory if it doesn't exist
check_dir:
ifneq ($(strip $(subdirs)),)
	@if [ ! -d ${SDK_APPS_IMAGE_DIR} ]; then \
		echo "Directory does not exist, creating it..."; \
		mkdir -p ${SDK_APPS_IMAGE_DIR}; \
	fi
endif

all: check_dir
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
