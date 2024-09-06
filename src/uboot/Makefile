include $(SDK_TOOLS_DIR)/toolchain_linux.mk

ifneq ($(shell [ -d ${SDK_BUILD_IMAGES_DIR}/uboot ] && echo 1 || echo 0),1)
$(shell mkdir -p ${SDK_BUILD_IMAGES_DIR}/uboot)
endif

.PHONY: all clean distclean menuconfig

build:
	@cp $(SDK_SRC_ROOT_DIR)/include/generated/autoconf.h $(SDK_UBOOT_SRC_DIR)/uboot/board/kendryte/common/sdk_autoconf.h
	@export ARCH=riscv; \
	make -C uboot $(UBOOT_DEFCONFIG) O=$(SDK_UBOOT_BUILD_DIR) || exit $?; \
	$(SDK_UBOOT_SRC_DIR)/parse_config || exit $?; \
	make -j$(NCPUS) -C $(SDK_UBOOT_BUILD_DIR) || exit $?;

all: build
	$(SDK_UBOOT_SRC_DIR)/gen_image

clean:
	@export ARCH=riscv; \
	make -C $(SDK_UBOOT_BUILD_DIR) clean || exit $?;

distclean: clean
	@rm -rf $(SDK_UBOOT_BUILD_DIR)
	@rm -rf ${SDK_BUILD_IMAGES_DIR}/uboot

menuconfig: clean
	@export ARCH=riscv; \
	make -C uboot $(UBOOT_DEFCONFIG) || exit $?; \
	make -C uboot menuconfig || exit $?; \
	make -C uboot savedefconfig || exit $?; \
	cp uboot/defconfig $(SDK_UBOOT_SRC_DIR)/uboot/configs/$(UBOOT_DEFCONFIG); \
	make -C uboot distclean || exit $?;
