ifneq ($(MKENV_INCLUDED),1)
export SDK_SRC_ROOT_DIR := $(realpath $(dir $(realpath $(lastword $(MAKEFILE_LIST))))/../../../)
endif

include $(SDK_SRC_ROOT_DIR)/tools/mkenv.mk
include $(SDK_SRC_ROOT_DIR)/.config

CROSS_COMPILE ?= $(SDK_TOOLCHAIN_DIR)/riscv64-linux-musleabi_for_x86_64-pc-linux-gnu/bin/riscv64-unknown-linux-musl-

# Strip quotes and then whitespaces
qstrip = $(strip $(subst ",,$(1)))

GIT_INFO := $(shell python3 $(SDK_CANMV_SRC_DIR)/tools/get_git_version.py $(SDK_CANMV_SRC_DIR))
$(foreach line,$(GIT_INFO),$(eval export $(line)))

BOARD_DIR = boards/$(call qstrip,$(CONFIG_BOARD))
BUILD = $(SDK_CANMV_BUILD_DIR)

ifeq ($(wildcard $(BOARD_DIR)/.),)
    $(error Invalid BOARD specified: $(BOARD_DIR))
endif

QSTR_DEFS += core/qstrdefsport.h
QSTR_GLOBAL_DEPENDENCIES = $(BOARD_DIR)/mpconfigboard.h

# Include py make environment
include ../micropython/py/mkenv.mk

# Include micropython configuration board makefile
# include boards/mpconfigport.mk
# -include $(BOARD_DIR)/mpconfigboard.mk

# MicroPython feature configurations
MICROPY_ROM_TEXT_COMPRESSION ?= 1

# File containing description of content to be frozen into firmware.
FROZEN_MANIFEST ?= $(BOARD_DIR)/manifest.py

PORT_SRC_C :=

# This should be configured by the mpconfigvariant.mk
PROG ?= micropython

# Include py core make definitions
include $(TOP)/py/py.mk
include $(TOP)/extmod/extmod.mk

LIB_CFLAGS :=
LIB_LDFLAGS :=

include $(SDK_RTSMART_SRC_DIR)/libs/mk/libmpp.mk
include $(SDK_RTSMART_SRC_DIR)/libs/mk/libopencv.mk
include $(SDK_RTSMART_SRC_DIR)/libs/mk/libnncase.mk
include $(SDK_RTSMART_SRC_DIR)/libs/mk/librtsmart_hal.mk
include $(SDK_RTSMART_SRC_DIR)/libs/mk/lib3rdparty.mk

-include $(BUILD)/CANMV_VER
CANMV_VER = $(shell git describe --tags --always `git rev-list --tags --max-count=1`)-$(shell git rev-parse --short HEAD)
ifneq ($(CANMV_VER),$(CANMV_VER_OLD))
$(shell echo CANMV_VER_OLD=$(CANMV_VER) > $(BUILD)/CANMV_VER)
$(shell touch core/main.c)
endif
CDEF = -DCANMV_VER="\"$(CANMV_VER)\""

# =============================================================================
# Includes
# =============================================================================

INC += -I.
INC += -Icore
INC += -I$(TOP)
INC += -I$(BUILD)
INC += -I$(BOARD_DIR)
INC += -I$(SDK_SRC_ROOT_DIR)/include

# =============================================================================
# Sources
# =============================================================================
SHARED_SRC_C += \
	shared/netutils/netutils.c \
	shared/netutils/trace.c \
	shared/readline/readline.c \
	shared/runtime/gchelper_generic.c \
	shared/runtime/interrupt_char.c \
	shared/runtime/mpirq.c \
	shared/runtime/pyexec.c \
	shared/runtime/stdout_helpers.c \
	shared/timeutils/timeutils.c \

# C source files
PORT_SRC_C = $(wildcard core/*.c)
PORT_SRC_C += $(wildcard repl/*.c)

# =============================================================================
# QSTR Sources
# =============================================================================
# List of sources for qstr extraction
SRC_QSTR += $(SRC_C) $(SHARED_SRC_C) $(PORT_SRC_C)

# =============================================================================
# Compiler Flags
# =============================================================================

CFLAGS += -g  # always include debug info in the ELF
ifeq ($(DEBUG),1)
CFLAGS += -Og
# Disable text compression in debug builds
MICROPY_ROM_TEXT_COMPRESSION = 0
else
CFLAGS += -Os -DNDEBUG
endif

CFLAGS += \
	$(INC) \
	-DMBEDTLS_USER_CONFIG_FILE=\"mbedtls_port_config.h\" \
	-march=rv64imafdcv \
	-mabi=lp64d \
	-mcmodel=medany \
	-std=gnu99 \
	-fdata-sections \
	-ffunction-sections \
	-Wall \
	-Werror \
	-Wno-int-conversion \
	-Wno-array-bounds \

CFLAGS += $(CFLAGS_EXTRA) $(LIB_CFLAGS)

# =============================================================================
# Linker Flags
# =============================================================================
LDFLAGS += -T link.lds --static -Wl,--gc-sections

LDFLAGS += $(LDFLAGS_MOD) $(LDFLAGS_EXTRA) $(LIB_LDFLAGS)

OBJ += $(PY_O)
OBJ += $(addprefix $(BUILD)/, $(SRC_C:.c=.o))
OBJ += $(addprefix $(BUILD)/, $(SHARED_SRC_C:.c=.o))
OBJ += $(addprefix $(BUILD)/, $(PORT_SRC_C:.c=.o))

include $(TOP)/py/mkrules.mk
