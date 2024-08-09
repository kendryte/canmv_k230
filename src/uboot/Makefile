include $(SDK_TOOLS_DIR)/toolchain_linux.mk

ifneq ($(shell [ -d ${SDK_BUILD_IMAGES_DIR}/uboot ] && echo 1 || echo 0),1)
$(shell mkdir -p ${SDK_BUILD_IMAGES_DIR}/uboot)
endif

.PHONY: all clean distclean

${SDK_BUILD_IMAGES_DIR}/uboot/fn_ug_u-boot.bin:
	@cp $(SDK_SRC_ROOT_DIR)/include/generated/autoconf.h $(SDK_UBOOT_SRC_DIR)/uboot/board/kendryte/common/sdk_autoconf.h
	@export ARCH=riscv; \
	make -C uboot $(SDK_DEFCONFIG) O=$(SDK_UBOOT_BUILD_DIR) || exit $?; \
	$(SDK_UBOOT_SRC_DIR)/parse_config || exit $?; \
	make -j$(NCPUS) -C $(SDK_UBOOT_BUILD_DIR) || exit $?;

build: ${SDK_BUILD_IMAGES_DIR}/uboot/fn_ug_u-boot.bin

gen_image: build
	$(SDK_UBOOT_SRC_DIR)/gen_image

all: gen_image

clean:
	@rm -rf .parse_config
	@rm -rf ${SDK_BUILD_IMAGES_DIR}/uboot/fn_ug_u-boot.bin

distclean: clean
	@rm -rf $(SDK_UBOOT_BUILD_DIR)
	@rm -rf ${SDK_BUILD_IMAGES_DIR}/uboot
