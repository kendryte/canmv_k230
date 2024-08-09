
KCONF=${SDK_TOOLS_DIR}/kconfig/conf
MCONF=${SDK_TOOLS_DIR}/kconfig/mconf
NCONF=${SDK_TOOLS_DIR}/kconfig/nconf

${SDK_TOOLS_DIR}/kconfig/conf:
	@make -C $(SDK_TOOLS_DIR)/kconfig conf

${SDK_TOOLS_DIR}/kconfig/mconf:
	@make -C $(SDK_TOOLS_DIR)/kconfig mconf

${SDK_TOOLS_DIR}/kconfig/nconf:
	@make -C $(SDK_TOOLS_DIR)/kconfig nconf

.PHONY: kconfig-clean
kconfig-clean:
	@make -C $(SDK_TOOLS_DIR)/kconfig clean

.PHONY: kconfig-distclean
kconfig-distclean:
	@make -C $(SDK_TOOLS_DIR)/kconfig clean
