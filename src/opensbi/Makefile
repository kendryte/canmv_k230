include $(SDK_TOOLS_DIR)/toolchain_linux.mk

ifneq ($(shell [ -d ${SDK_BUILD_IMAGES_DIR}/opensbi ] && echo 1 || echo 0),1)
$(shell mkdir -p ${SDK_BUILD_IMAGES_DIR}/opensbi)
endif

.PHONY: all clean distclean

.parse_config:
	@$(SDK_OPENSBI_SRC_DIR)/parse_config || exit $?
	@touch .parse_config

build: .parse_config
	@rm -rf ${SDK_OPENSBI_BUILD_DIR}/opensbi.bin;
	@rm -rf $(SDK_OPENSBI_SRC_DIR)/opensbi/rtthread.bin;
	@if [ ! -f $(SDK_BUILD_IMAGES_DIR)/rtsmart/rtthread.bin ]; then \
		echo "should run make rtsmart" && exit 1; \
	fi; \
	cp $(SDK_BUILD_IMAGES_DIR)/rtsmart/rtthread.bin $(SDK_OPENSBI_SRC_DIR)/opensbi/;
	@cd $(SDK_OPENSBI_SRC_DIR)/opensbi; \
	export PLATFORM=kendryte/fpgac908; \
	$(MAKE) -j$(NCPUS) FW_FDT_PATH=hw.dtb FW_PAYLOAD_PATH=rtthread.bin O=$(SDK_OPENSBI_BUILD_DIR) OPENSBI_QUIET=1 CROSS_COMPILE=$(CROSS_COMPILE) || exit $?; \
	cp $(SDK_OPENSBI_BUILD_DIR)/platform/kendryte/fpgac908/firmware/fw_payload.bin ${SDK_OPENSBI_BUILD_DIR}/opensbi.bin; \
	cd -

gen_image: build
	@$(SDK_OPENSBI_SRC_DIR)/gen_image

all: gen_image

clean:
	@rm -rf .parse_config
	@rm -rf $(SDK_OPENSBI_BUILD_DIR)
	@rm -rf ${SDK_BUILD_IMAGES_DIR}/opensbi

distclean: clean
