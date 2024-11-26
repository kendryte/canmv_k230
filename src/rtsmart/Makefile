include $(SDK_TOOLS_DIR)/toolchain_rtsmart.mk

ifneq ($(shell [ -d ${SDK_BUILD_IMAGES_DIR}/rtsmart ] && echo 1 || echo 0),1)
$(shell mkdir -p ${SDK_BUILD_IMAGES_DIR}/rtsmart)
endif

ifneq ($(shell [ -d ${SDK_BUILD_IMAGES_DIR}/bin/ ] && echo 1 || echo 0),1)
$(shell mkdir -p ${SDK_BUILD_IMAGES_DIR}/bin/)
endif

ifneq ($(shell [ -d ${SDK_BUILD_IMAGES_DIR}/sdcard/ ] && echo 1 || echo 0),1)
$(shell mkdir -p ${SDK_BUILD_IMAGES_DIR}/sdcard/)
endif

.PHONY: all clean distclean menuconfig

.parse_config:
	@export RTT_CC=gcc; \
	export RTT_CC_PREFIX=$(CROSS_COMPILE_PREFIX); \
	export RTT_EXEC_PATH=$(CROSS_COMPILE_DIR); \
	export RTSMART_SRC_DIR=$(SDK_RTSMART_SRC_DIR)/rtsmart; \
	export RTT_SDK_BUILD_DIR=$(SDK_RTSMART_BUILD_DIR); \
	export MPP_SRC_DIR=$(SDK_RTSMART_SRC_DIR)/mpp; \
	cp -f $(SDK_SRC_ROOT_DIR)/include/generated/autoconf.h $(SDK_RTSMART_SRC_DIR)/mpp/include/comm/k_autoconf_comm.h; \
	cp -f $(SDK_SRC_ROOT_DIR)/include/generated/autoconf.h $(SDK_RTSMART_SRC_DIR)/rtsmart/kernel/bsp/maix3/k_autoconf_comm.h; \
	$(SDK_RTSMART_SRC_DIR)/parse_config || exit $?; \
	cd $(SDK_RTSMART_SRC_DIR)/rtsmart/kernel/bsp/maix3; \
	if [ ! -f configs/${SDK_DEFCONFIG} ]; then \
		echo "Error: Configuration file '${SDK_DEFCONFIG}' not found."; \
		echo "Please ensure that '${SDK_DEFCONFIG}' exists in the 'configs' directory."; \
		exit 1; \
	fi; \
	rm -rf rtconfig.h; \
	scons --useconfig=configs/${SDK_DEFCONFIG} || exit $?; \
	cd -; \
	touch .parse_config

.mpp_built:
	@export PATH="$(CROSS_COMPILE_DIR):$(PATH)"; \
	export MPP_SRC_DIR=$(SDK_RTSMART_SRC_DIR)/mpp; \
	export RTSMART_SRC_DIR=$(SDK_RTSMART_SRC_DIR)/rtsmart; \
	export MPP_BUILD_DIR=$(SDK_RTSMART_BUILD_DIR)/mpp; \
	$(MAKE) -C $(SDK_RTSMART_SRC_DIR)/mpp/kernel || exit $?; \
	$(MAKE) -C $(SDK_RTSMART_SRC_DIR)/mpp/userapps/src || exit $?; \
	$(MAKE) -C $(SDK_RTSMART_SRC_DIR)/mpp/middleware/src || exit $?; \
	touch .mpp_built

.mpp_samples:
ifneq ($(CONFIG_SDK_ENABLE_CANMV),y)
	@export PATH="$(CROSS_COMPILE_DIR):$(PATH)"; \
	export MPP_SRC_DIR=$(SDK_RTSMART_SRC_DIR)/mpp; \
	export RTSMART_SRC_DIR=$(SDK_RTSMART_SRC_DIR)/rtsmart; \
	export MPP_BUILD_DIR=$(SDK_RTSMART_BUILD_DIR)/mpp; \
	$(MAKE) -C $(SDK_RTSMART_SRC_DIR)/mpp/userapps/sample || exit $?; \
	$(MAKE) -C $(SDK_RTSMART_SRC_DIR)/mpp/middleware/sample || exit $?
endif
	touch .mpp_samples

mpp: .mpp_built .mpp_samples

kernel: .parse_config
	@$(SDK_SRC_ROOT_DIR)/tools/gen_verinfo_h.sh $(SDK_RTSMART_SRC_DIR)/rtsmart/kernel/bsp/maix3/applications/sdk_version.h
	@export RTT_CC=gcc; \
	export RTT_CC_PREFIX=$(CROSS_COMPILE_PREFIX); \
	export RTT_EXEC_PATH=$(CROSS_COMPILE_DIR); \
	export RTSMART_SRC_DIR=$(SDK_RTSMART_SRC_DIR)/rtsmart; \
	export RTT_SDK_BUILD_DIR=$(SDK_RTSMART_BUILD_DIR); \
	export MPP_SRC_DIR=$(SDK_RTSMART_SRC_DIR)/mpp; \
	cd $(SDK_RTSMART_SRC_DIR)/rtsmart/kernel/bsp/maix3; \
	rm -f rtthread.{elf,bin}; \
	scons -j$(NCPUS) || exit $?; \
	cp rtthread.bin ${SDK_BUILD_IMAGES_DIR}/rtsmart; \
	cd -;

app:

.rtt_samples:
ifneq ($(CONFIG_RTT_ENABLE_BUILD_EXAMPLES),y)
	@$(MAKE) -C $(SDK_RTSMART_SRC_DIR)/examples all || exit $?
endif
	touch .rtt_samples

examples: .rtt_samples

build: mpp kernel app examples

all: .parse_config build
	@echo "Copy sensor configs."
	@rsync -aq --delete $(SDK_RTSMART_SRC_DIR)/rtsmart/userapps/root/bin/ ${SDK_BUILD_IMAGES_DIR}/bin/
ifneq ($(CONFIG_SDK_ENABLE_CANMV),y)
	@rm -rf ${SDK_BUILD_IMAGES_DIR}/sdcard/elf/*
	@if [ ! -d ${SDK_BUILD_IMAGES_DIR}/sdcard/elf/userapps/ ]; then \
		mkdir -p ${SDK_BUILD_IMAGES_DIR}/sdcard/elf/userapps/; \
	fi; \
	rsync -aq $(SDK_RTSMART_SRC_DIR)/mpp/userapps/sample/elf/ ${SDK_BUILD_IMAGES_DIR}/sdcard/elf/userapps/
	@if [ ! -d ${SDK_BUILD_IMAGES_DIR}/sdcard/elf/middleware/ ]; then \
		mkdir -p ${SDK_BUILD_IMAGES_DIR}/sdcard/elf/middleware/; \
	fi; \
	rsync -aq $(SDK_RTSMART_SRC_DIR)/mpp/middleware/elf/ ${SDK_BUILD_IMAGES_DIR}/sdcard/elf/middleware/
endif
ifneq ($(CONFIG_RTT_ENABLE_BUILD_EXAMPLES),y)
	@if [ ! -d ${SDK_BUILD_IMAGES_DIR}/sdcard/elf/examples/ ]; then \
		mkdir -p ${SDK_BUILD_IMAGES_DIR}/sdcard/elf/examples/; \
	fi; \
	rsync -aq $(SDK_RTSMART_SRC_DIR)/examples/elf/ ${SDK_BUILD_IMAGES_DIR}/sdcard/elf/examples/
endif
	@echo "Generate ${SDK_BUILD_IMAGES_DIR}/bin/config.txt"
	@$(SDK_SRC_ROOT_DIR)/src/rtsmart/gen_config

mpp-clean:
	@export PATH="$(CROSS_COMPILE_DIR):$(PATH)"; \
	export MPP_SRC_DIR=$(SDK_RTSMART_SRC_DIR)/mpp; \
	export RTSMART_SRC_DIR=$(SDK_RTSMART_SRC_DIR)/rtsmart; \
	export MPP_BUILD_DIR=$(SDK_RTSMART_BUILD_DIR)/mpp; \
	$(MAKE) -C $(SDK_RTSMART_SRC_DIR)/mpp/kernel clean || exit $?; \
	$(MAKE) -C $(SDK_RTSMART_SRC_DIR)/mpp/userapps/src clean || exit $?; \
	$(MAKE) -C $(SDK_RTSMART_SRC_DIR)/mpp/userapps/sample clean || exit $?; \
	$(MAKE) -C $(SDK_RTSMART_SRC_DIR)/mpp/middleware/sample clean || exit $?; \
	rm -rf .mpp_built .mpp_samples; \
	rm -rf $(SDK_RTSMART_SRC_DIR)/rtsmart/userapps/root/bin

kernel-clean:
	@export RTT_CC=gcc; \
	export RTT_CC_PREFIX=$(CROSS_COMPILE_PREFIX); \
	export RTT_EXEC_PATH=$(CROSS_COMPILE_DIR); \
	export RTSMART_SRC_DIR=$(SDK_RTSMART_SRC_DIR)/rtsmart; \
	export RTT_SDK_BUILD_DIR=$(SDK_RTSMART_BUILD_DIR); \
	export MPP_SRC_DIR=$(SDK_RTSMART_SRC_DIR)/mpp; \
	cd $(SDK_RTSMART_SRC_DIR)/rtsmart/kernel/bsp/maix3; \
	rm -f rtthread.elf .config .config.old k_autoconf_comm.h link_stacksize.lds link.lds rtconfig.h; \
	scons -c || exit $?; \
	cd -; \
	rm -rf ${SDK_BUILD_IMAGES_DIR}/rtsmart;

app-clean:

clean: mpp-clean kernel-clean app-clean
	@rm -rf .parse_config
	@rm -rf ${SDK_BUILD_IMAGES_DIR}/rtsmart

distclean: clean

menuconfig:
	@rm -rf .parse_config
	@rm -rf ${SDK_BUILD_IMAGES_DIR}/rtsmart
	@export RTT_CC=gcc; \
	export RTT_CC_PREFIX=$(CROSS_COMPILE_PREFIX); \
	export RTT_EXEC_PATH=$(CROSS_COMPILE_DIR); \
	export RTSMART_SRC_DIR=$(SDK_RTSMART_SRC_DIR)/rtsmart; \
	export RTT_SDK_BUILD_DIR=$(SDK_RTSMART_BUILD_DIR); \
	export MPP_SRC_DIR=$(SDK_RTSMART_SRC_DIR)/mpp; \
	cd $(SDK_RTSMART_SRC_DIR)/rtsmart/kernel/bsp/maix3; \
	rm -rf rtconfig.h .config .config.old; \
	scons --useconfig=configs/${SDK_DEFCONFIG} || exit $?; \
	scons --genconfig; \
	scons --menuconfig; \
	cp .config configs/${SDK_DEFCONFIG}; \
	cd -;
