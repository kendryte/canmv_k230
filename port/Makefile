include ${SDK_SRC_ROOT_DIR}/.config

CROSS_COMPILE=$(SDK_TOOLCHAIN_DIR)/riscv64-linux-musleabi_for_x86_64-pc-linux-gnu/bin/riscv64-unknown-linux-musl-

# Strip quotes and then whitespaces
qstrip = $(strip $(subst ",,$(1)))

GIT_INFO := $(shell python3 $(SDK_CANMV_SRC_DIR)/tools/get_git_version.py $(SDK_CANMV_SRC_DIR))
$(foreach line,$(GIT_INFO),$(eval export $(line)))

BOARD_DIR = boards/$(call qstrip,$(CONFIG_BOARD))
BUILD = $(SDK_CANMV_BUILD_DIR)

MICROPY_ROM_TEXT_COMPRESSION ?= 1

include ../micropython/py/mkenv.mk

# Use the default frozen manifest, variants may override this.
FROZEN_MANIFEST ?= ${BOARD_DIR}/manifest.py
include boards/mpconfigport.mk
-include ${BOARD_DIR}/mpconfigport.mk

# This should be configured by the mpconfigvariant.mk
PROG ?= micropython

USER_C_MODULES = 3rd-party/ulab

# include py core make definitions
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

INC += -I.
INC += -I$(BUILD)
INC += -I$(SDK_SRC_ROOT_DIR)/include
INC += -I$(BOARD_DIR)
INC += -Iinclude
INC += -Iinclude/ai_cube
INC += -Iinclude/ai_demo
INC += -Iinclude/ai_demo/kws
INC += -Iinclude/ai_demo/tts_zh
INC += -Iinclude/cv_lite
INC += -Iinclude/core
INC += -Iinclude/kpu
INC += -Iinclude/machine
INC += -Iinclude/maix
INC += -Iinclude/mpp
INC += -Iinclude/multi_media
INC += -Iinclude/omv
INC += -Iomv/alloc
INC += -Iomv/boards/canmv
INC += -Iomv/common
INC += -Iomv/imlib
INC += -Iomv/modules
INC += -I3rd-party/ulab
INC += -I3rd-party/lv_bindings
INC += -I$(SDK_RTSMART_SRC_DIR)/mpp/middleware/src/rtsp_server/include
INC += -I$(SDK_RTSMART_SRC_DIR)/mpp/middleware/src/mp4_format/include

INC += -I$(TOP)
INC += -I$(TOP)/py
INC += -I$(TOP)/shared/readline
INC += -I$(TOP)/lib/crypto-algorithms

INC += $(LIB_CFLAGS)

# compiler settings
# Debugging/Optimization
ifdef DEBUG
COPT ?= -Og
else
COPT ?= -Os
# COPT += -DNDEBUG
endif

# Remove unused sections.
COPT += -fdata-sections -ffunction-sections

CWARN := -Wall -Werror 
CWARN += -Wno-int-conversion

CFLAGS_MBEDTLS := -DMBEDTLS_USER_CONFIG_FILE=\"mbedtls_port_config.h\"

CFLAGS += $(INC)
# Always enable symbols -- They're occasionally useful, and don't make it into the
# final .bin/.hex/.dfu so the extra size doesn't matter.
CFLAGS += -g -gdwarf-2

CFLAGS += -fopenmp -march=rv64imafdcv -mabi=lp64d -mcmodel=medany
CFLAGS += -std=gnu99 $(COPT) $(CWARN) $(CFLAGS_EXTRA) $(CDEF) $(CFLAGS_MBEDTLS)

# Workaround gcc 12 bug.
CFLAGS += -Wno-array-bounds

ifeq ($(MICROPY_PY_TERMIOS),1)
CFLAGS += -DMICROPY_PY_TERMIOS=1
endif

CXXFLAGS += -fopenmp -march=rv64imafdcv -mabi=lp64d -mcmodel=medany
CXXFLAGS += $(INC) $(COPT) $(NNCASEINC) $(CFLAGS_MBEDTLS) -std=c++20
CXXFLAGS += $(filter-out -Wmissing-prototypes -Wold-style-definition -std=gnu99, $(CXXFLAGS_MOD))

# Use gcc syntax for map file
LDFLAGS_ARCH = -Wl,-Map=$@.map,--cref -Wl,--gc-sections
LDFLAGS += -T core/link.lds --static

# # rtsp server
# RTSP_SERVER_LIBS := -L$(SDK_RTSMART_SRC_DIR)/mpp/middleware/lib -lrtsp_server -lliveMedia -lgroupsock -lBasicUsageEnvironment -lUsageEnvironment

# LDFLAGS_LIBS := $(NNCASE_LIB_DIR) $(OPENCV_LIB_DIR) $(SDK_MPP_USER_LIB_DIR) $(SDK_MPP_MIDDLEWARE_LIB_DIR) $(RTSMART_HAL_LIB_DIR) $(RTSMART_3RD_PARTY_LIB_DIR)
# LDFLAGS_LIBS += -Wl,--start-group -lm -lpthread -lmp4 $(NNCASE_LIBS) $(OPENCV_LIBS) $(SDK_MPP_USER_LIBS) $(RTSP_SERVER_LIBS) $(RTSMART_HAL_LIBS) $(RTSMART_3RD_PARTY_LIBS) -Wl,--end-group

LDFLAGS += $(LDFLAGS_MOD) $(LDFLAGS_ARCH) $(LIB_LDFLAGS) $(LDFLAGS_EXTRA)

# remove some python project source files
PY_O_EXCLUDE = \
	$(addprefix $(BUILD)/,\
		extmod/modos.o \
		extmod/modcryptolib.o \
		extmod/modhashlib.o \
		extmod/modssl_mbedtls.o\
		extmod/modonewire.o\
		extmod/machine_pwm.o\
		extmod/vfs_posix_file.o\
		py/modgc.o \
	)
PY_O := $(filter-out $(PY_O_EXCLUDE),$(PY_O))

SRC_QSTR_EXCLUDE = \
		extmod/modos.c \
		extmod/modcryptolib.c \
		extmod/modhashlib.c \
		extmod/modssl_mbedtls.c\
		extmod/modonewire.c\
		extmod/machine_pwm.c\
		extmod/vfs_posix_file.c\
		py/modgc.c

SRC_QSTR := $(filter-out $(SRC_QSTR_EXCLUDE),$(SRC_QSTR))

# source files
CANMV_SRC_C :=

# core
CANMV_SRC_C += $(wildcard core/*.c)
# board
CANMV_SRC_C += $(wildcard $(BOARD_DIR)/*.c)
# machine
CANMV_SRC_C += $(wildcard machine/*.c)
# mpp
CANMV_SRC_C += $(wildcard builtin_py/mpp_binding/*.c)

ifeq ($(CONFIG_BOARD_K230_CANMV_YAHBOOM),y)
# yahboom ybMain
CANMV_SRC_C += $(wildcard builtin_py/yahboom/ybMain/*.c)
# yahboom ybUtils
CANMV_SRC_C += $(wildcard builtin_py/yahboom/ybUtils/*.c)
endif

# kpu
CANMV_SRC_C += $(wildcard kpu/*.c)
# aicube
CANMV_SRC_C += $(wildcard ai_cube/*.c)
# aidemo
CANMV_SRC_C += $(wildcard ai_demo/*.c)
# omv
CANMV_SRC_C += $(wildcard omv/*.c)
CANMV_SRC_C += $(wildcard omv/*/*.c)
# multi_media
CANMV_SRC_C += $(wildcard multi_media/*.c)
# drivers
CANMV_SRC_C += $(wildcard drivers/*.c)
# modules
CANMV_SRC_C += $(wildcard modules/*.c)

ifeq ($(CONFIG_ENABLE_MODULE_CV_LITE),y)
$(info Enable CV_Lite)
CANMV_SRC_C += $(wildcard cv_lite/*.c)
endif

# extmod
CANMV_SRC_C += \
	mp_modules/modtermios.c \
	mp_modules/overlay_modos.c \
	mp_modules/overlay_modgc.c \
	mp_modules/overlay_modcryptolib.c \
	mp_modules/overlay_modhashlib.c \
	mp_modules/overlay_modssl_mbedtls.c \
	mp_modules/overlay_modonewire.c \
	mp_modules/overlay_machine_pwm.c \
	mp_modules/overlay_vfs_posix_file.c \

CANMV_SRC_C += $(addprefix shared/,\
	runtime/gchelper_generic.c \
	runtime/pyexec.c \
	runtime/mpirq.c \
	timeutils/timeutils.c \
	readline/readline.c \
	netutils/netutils.c \
	)

CANMV_SRC_C += $(addprefix drivers/,\
	dht/dht.c \
	)

ifneq ($(filter y,$(CONFIG_ENABLE_NETWORK_RT_WLAN) $(CONFIG_ENABLE_NETWORK_RT_LAN_OVER_USB)),)
$(info Enable Network)
CANMV_SRC_C += $(wildcard network/*.c)
endif

# LVGL build rules
CFLAGS += -DMICROPY_FREETYPE=1
LV_CFLAGS := -DMICROPY_FREETYPE=1

LVGL_BINDING_DIR = 3rd-party/lv_bindings
LVGL_DIR = $(LVGL_BINDING_DIR)/lvgl
ALL_LVGL_SRC = $(shell find $(LVGL_DIR) -type f -name '*.h') $(LVGL_BINDING_DIR)/lv_conf.h
LVGL_PP = $(BUILD)/lvgl/lvgl.pp.c
LVGL_MPY = $(BUILD)/lvgl/lv_mpy.c
LVGL_MPY_METADATA = $(BUILD)/lvgl/lv_mpy.json

$(LVGL_MPY): $(ALL_LVGL_SRC) $(LVGL_BINDING_DIR)/gen_mpy.py
	$(ECHO) "LVGL-GEN $@"
	$(Q)mkdir -p $(dir $@)
	$(Q)$(CPP) $(LV_CFLAGS) -DPYCPARSER -x c -I $(LVGL_BINDING_DIR)/pycparser/utils/fake_libc_include $(INC) $(LVGL_DIR)/lvgl.h > $(LVGL_PP)
	$(Q)python $(LVGL_BINDING_DIR)/gen_mpy.py -M lvgl -MP lv -MD $(LVGL_MPY_METADATA) -E $(LVGL_PP) $(LVGL_DIR)/lvgl.h > $@

LVGL_SRC_C_ALL = $(subst $(TOP)/,,$(shell find $(LVGL_DIR)/src -type f -name "*.c") $(LVGL_MPY))
LVGL_SRC_C_EXCLUDE = \
	$(addprefix $(LVGL_DIR)/src/,\
		core/lv_obj.c \
		core/lv_refr.c \
		misc/lv_timer.c \
		libs/png/lodepng.c \
		libs/png/lv_png.c \
		libs/freetype/lv_freetype.c \
	)
LVGL_SRC_C := $(filter-out $(LVGL_SRC_C_EXCLUDE),$(LVGL_SRC_C_ALL))
LVGL_SRC_C += $(LVGL_BINDING_DIR)/src/core/lv_obj.c
LVGL_SRC_C += $(LVGL_BINDING_DIR)/src/core/lv_refr.c
LVGL_SRC_C += $(LVGL_BINDING_DIR)/src/misc/lv_timer.c
LVGL_SRC_C += $(LVGL_BINDING_DIR)/src/libs/png/lodepng.c
LVGL_SRC_C += $(LVGL_BINDING_DIR)/src/libs/png/lv_png.c
LVGL_SRC_C += $(LVGL_BINDING_DIR)/src/libs/freetype/lv_freetype.c

ifeq ($(CONFIG_BOARD_K230_CANMV_YAHBOOM),y)
# add yb_config/lv_font_yb source file
LVGL_SRC_C += $(LVGL_BINDING_DIR)/yb_config/lv_font_yb_cn_16.c
LVGL_SRC_C += $(LVGL_BINDING_DIR)/yb_config/lv_font_yb_cn_22.c
# include yb_config/lv_conf_yb.h
CFLAGS += -I$(LVGL_BINDING_DIR)/yb_config
CFLAGS += -DLV_CONF_PATH=$(LVGL_BINDING_DIR)/yb_config/lv_conf_yb.h
LV_CFLAGS := -DLV_CONF_PATH=$(LVGL_BINDING_DIR)/yb_config/lv_conf_yb.h
endif

CFLAGS += -I$(LVGL_DIR)/src/core

CANMV_SRC_C += $(LVGL_SRC_C)
CLEAN_EXTRA += $(LVGL_PP) $(LVGL_MPY)

# cpp source files
CANMV_SRC_CXX := 
CANMV_SRC_CXX += $(wildcard kpu/*.cpp)
CANMV_SRC_CXX += $(wildcard ai_cube/*.cpp)
CANMV_SRC_CXX += $(wildcard ai_demo/*.cpp)
CANMV_SRC_CXX += $(wildcard ai_demo/kws/*.cpp)
CANMV_SRC_CXX += $(wildcard ai_demo/tts_zh/*.cpp)
CANMV_SRC_CXX += $(wildcard modules/*.cpp)
CANMV_SRC_CXX += $(wildcard modules/*/*.cpp)
CANMV_SRC_CXX += $(wildcard multi_media/*.cpp)

ifeq ($(CONFIG_ENABLE_MODULE_CV_LITE),y)
CANMV_SRC_CXX += $(wildcard cv_lite/opencv_code/*.cpp)
endif

# 
OBJ = $(PY_O)
OBJ += $(addprefix $(BUILD)/, $(CANMV_SRC_C:.c=.o))
OBJ += $(addprefix $(BUILD)/, $(CANMV_SRC_CXX:.cpp=.o))

# List of sources for qstr extraction
SRC_QSTR += $(CANMV_SRC_C) $(CANMV_SRC_CXX)
# Append any auto-generated sources that are needed by sources listed in
# SRC_QSTR
SRC_QSTR_AUTO_DEPS +=

include $(TOP)/py/mkrules.mk
