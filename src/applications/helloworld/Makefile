# Use the toolchain defined in apps.mk

ifneq ($(MKENV_INCLUDED),1)
export SDK_SRC_ROOT_DIR := $(realpath $(dir $(realpath $(lastword $(MAKEFILE_LIST))))/../../../)
include $(SDK_SRC_ROOT_DIR)/tools/mkenv.mk
endif

include $(SDK_APPS_SRC_DIR)/toolchain.mk

include $(SDK_RTSMART_SRC_DIR)/librtsmart.mk
include $(SDK_RTSMART_SRC_DIR)/libmpp.mk

SDK_APPS_IMAGE_DIR ?= $(shell pwd)

BUILD = ${SDK_APPS_BUILD_DIR}/helloworld/

SRC_DIRS :=

SFILES :=
SFILES_EXCLUDE :=
SFLAGS :=

CFILES :=
CFILES_EXCLUDE :=
CFLAGS :=

CFILES += main.c

CFLAGS := -march=rv64imafdcv -mabi=lp64d -mcmodel=medany
CFLAGS += -std=gnu99 -fdata-sections -ffunction-sections

CFLAGS += -I$(SDK_SRC_ROOT_DIR)/include/generated
CFLAGS += $(SDK_MPP_USER_INC) $(SDK_RTSMART_INC)

LDFLAGS := -T link.lds --static -Wl,--gc-sections
LDFLAGS += $(SDK_MPP_USER_LIB_DIR) $(SDK_MPP_USER_LIBS)

SFILES_ALL = $(foreach dir, $(SRC_DIRS), $(wildcard $(dir)/*.S))
CFILES_ALL = $(foreach dir, $(SRC_DIRS), $(wildcard $(dir)/*.c))

SFILES += $(filter-out $(SFILES_EXCLUDE), $(SFILES_ALL))
CFILES += $(filter-out $(CFILES_EXCLUDE), $(CFILES_ALL))

SDEPS	:= $(patsubst %, $(BUILD)/%, $(SFILES:.S=.o.d))
CDEPS	:= $(patsubst %, $(BUILD)/%, $(CFILES:.c=.o.d))
DEPS	:= $(SDEPS) $(CDEPS)

SOBJS	:= $(patsubst %, $(BUILD)/%, $(SFILES:.S=.o))
COBJS	:= $(patsubst %, $(BUILD)/%, $(CFILES:.c=.o))
OBJS	:= $(SOBJS) $(COBJS)

BIN := helloworld

.PHONY: all clean distclean
all: $(BIN)
	@cp $(BUILD)/$^ $(SDK_APPS_IMAGE_DIR)

clean:
	@rm -rf $(BUILD)
	@rm -rf $(SDK_APPS_IMAGE_DIR)/$(BIN)

distclean:

$(BIN): $(OBJS)
	@$(CC) $^ -o $(BUILD)/$@ $(CFLAGS) $(LDFLAGS)
	@$(STRIP) $(BUILD)/$@

$(SOBJS) : $(BUILD)/%.o : %.S
	@echo [AS] $<
	@$(AS) $(SFLAGS) -MD -MP -MF $@.d -c $< -o $@

$(COBJS) : $(BUILD)/%.o : %.c
	@echo [CC] $<
	@$(CC) $(CFLAGS) -MD -MP -MF $@.d -c $< -o $@

# $(sort $(var)) removes duplicates
#
# The net effect of this, is it causes the objects to depend on the
# object directories (but only for existence), and the object directories
# will be created if they don't exist.
OBJ_DIRS = $(sort $(dir $(OBJS)))
$(OBJS): | $(OBJ_DIRS)
$(OBJ_DIRS):
	@mkdir -p $@

sinclude $(DEPS)
