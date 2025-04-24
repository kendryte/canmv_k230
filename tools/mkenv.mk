export SDK_TOOLCHAIN_DIR?=$(shell echo $$HOME)/.kendryte/k230_toolchains
export SDK_TOOLS_DIR=$(SDK_SRC_ROOT_DIR)/tools

# Default target
.DEFAULT_GOAL := all

# Strip quotes and then whitespaces
qstrip = $(strip $(subst ",,$(1)))

define check_build_dir
$(shell \
  if [ ! -d $(1) ]; then \
    mkdir -p $(1); \
  fi; \
)
endef

define del_mark
$(shell find $(SDK_SRC_ROOT_DIR) -type f -name ".parse_config" | xargs rm -rf {})
endef

# 1 src
# 2 dst
define sync_dir
	@echo "Source: $(1)"
	@echo "Destination: $(2)"
	@rm -rf $(2)/*
	@mkdir -p $(2) || exit 1
	@rsync -aq --delete $(1)/ $(2)/
endef

define gen_kconfig
@if [ -f "$(1)/Kconfig" ]; then \
    cp -f $(1)/Kconfig $(SDK_BUILD_DIR)/Kconfig.$(2); \
else \
    echo "" > $(SDK_BUILD_DIR)/Kconfig.$(2); \
fi
endef

# Do not print "Entering directory ...",
# but we want to display it when entering to the output directory
# so that IDEs/editors are able to understand relative filenames.
MAKEFLAGS += --no-print-directory

JOBS := $(shell ps -o args= $(MAKEPPID) | grep -o -E -- '-j[0-9]+' | head -n 1 | cut -c3-)
ifneq ($(JOBS),)
  ifneq ($(JOBS),1)
    $(error not support parallel build now)
  endif
endif

# Check if 'bear' command exists
BEAR_EXISTS := $(shell command -v bear >/dev/null 2>&1 && echo yes || echo no)

BEAR_COMMAND ?= bear

ifeq ($(BEAR_EXISTS),yes)
  # Capture the Bear version
  BEAR_VERSION := $(shell bear --version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')

  # Convert BEAR_VERSION to a single integer and compare it to 30000
  BEAR_VERSION_INT := $(shell echo $(BEAR_VERSION) | awk -F. '{print ($$1*10000 + $$2*100 + $$3)}')

  # Check if the Bear version is 3.0.0 or greater
  ifneq ($(shell [ $(BEAR_VERSION_INT) -ge 30000 ] && echo true),)
      BEAR_COMMAND := bear --
  endif
endif

export BEAR_COMMAND

PARALLEL ?= $(shell if command -v nproc > /dev/null 2>&1; then nproc; \
            elif [ -f /proc/cpuinfo ]; then grep -c '^processor' /proc/cpuinfo; \
            elif command -v sysctl > /dev/null 2>&1; then sysctl -n hw.ncpu; \
            else echo 1; fi)

export NCPUS?=$(PARALLEL)

CONFIG_SDK_ENABLE_CANMV ?= n

def_config :=$(filter %_defconfig,$(MAKECMDGOALS))
ifneq ($(def_config),)
  ifeq ($(shell if [ -f $(SDK_SRC_ROOT_DIR)/configs/$(def_config) ]; then echo 1; else echo 0; fi;), 0)
    $(error "Please specify a valid CONFIG")
  endif

  CONFIG_BOARD_CONFIG_NAME := $(def_config)
else
  -include $(SDK_SRC_ROOT_DIR)/.config
endif

export CONFIG_SDK_ENABLE_CANMV

ifeq ($(strip $(filter $(MAKECMDGOALS),list_def list-def dl_toolchain)),)
  ifeq ($(CONFIG_BOARD_CONFIG_NAME),)
    $(error "Please run make xxx_defconfig first. Use 'make list-def' to see available configurations.")
  endif
endif

MK_LIST_DEFCONFIG?=$(CONFIG_BOARD_CONFIG_NAME)
export MK_LIST_DEFCONFIG

export UBOOT_DEFCONFIG=$(patsubst %,%_defconfig,$(call qstrip,$(CONFIG_UBOOT_CONFIG_FILE)))
export RTSMART_DEFCONFIG=$(patsubst %,%_defconfig,$(call qstrip,$(CONFIG_RTSMART_CONFIG_FILE)))

export SDK_BOARDS_DIR=$(SDK_SRC_ROOT_DIR)/boards
export SDK_BOARD_DIR=$(SDK_BOARDS_DIR)/$(call qstrip,$(CONFIG_BOARD))

export SDK_OPENSBI_SRC_DIR=$(SDK_SRC_ROOT_DIR)/src/opensbi
export SDK_RTSMART_SRC_DIR=$(SDK_SRC_ROOT_DIR)/src/rtsmart
export SDK_UBOOT_SRC_DIR=$(SDK_SRC_ROOT_DIR)/src/uboot
export SDK_CANMV_SRC_DIR=$(SDK_SRC_ROOT_DIR)/src/canmv
export SDK_APPS_SRC_DIR=$(SDK_SRC_ROOT_DIR)/src/applications

export SDK_BUILD_DIR=$(SDK_SRC_ROOT_DIR)/output/$(call qstrip,$(CONFIG_BOARD_CONFIG_NAME))

export SDK_OPENSBI_BUILD_DIR=$(SDK_BUILD_DIR)/opensbi
export SDK_RTSMART_BUILD_DIR=$(SDK_BUILD_DIR)/rtsmart
export SDK_UBOOT_BUILD_DIR=$(SDK_BUILD_DIR)/uboot
export SDK_CANMV_BUILD_DIR=$(SDK_BUILD_DIR)/canmv
export SDK_APPS_BUILD_DIR=$(SDK_BUILD_DIR)/applications

export SDK_BUILD_IMAGES_DIR=$(SDK_BUILD_DIR)/images

ifeq ($(strip $(filter $(MAKECMDGOALS),list_def list-def dl_toolchain)),)
  $(call check_build_dir, $(SDK_BUILD_IMAGES_DIR))

  $(call check_build_dir, $(SDK_OPENSBI_BUILD_DIR))
  $(call check_build_dir, $(SDK_RTSMART_BUILD_DIR))
  $(call check_build_dir, $(SDK_UBOOT_BUILD_DIR))
  $(call check_build_dir, $(SDK_CANMV_BUILD_DIR))
  $(call check_build_dir, $(SDK_APPS_BUILD_DIR))

  $(call check_build_dir, $(SDK_TOOLCHAIN_DIR))
endif

export MKENV_INCLUDED = 1
export MPP_FOR_CANMV_SDK = 1

MK_IMAGE_NAME?=$(call qstrip,$(CONFIG_BOARD_NAME))
export MK_IMAGE_NAME
