
export TOOL_GENIMAGE=${SDK_TOOLS_DIR}/genimage/genimage

# https://github.com/pengutronix/genimage/releases/download/v18/genimage-18.tar.xz

${SDK_TOOLS_DIR}/genimage/genimage:
	@cd $(SDK_TOOLS_DIR)/genimage && chmod +x autogen.sh && ./autogen.sh && ./configure && make && cd -

.PHONY: $(TOOL_GENIMAGE)-clean
$(TOOL_GENIMAGE)-clean:
	@if [ -f ${SDK_TOOLS_DIR}/genimage/Makefile ]; then \
		make -C ${SDK_TOOLS_DIR}/genimage clean; \
	fi

.PHONY: $(TOOL_GENIMAGE)-distclean
$(TOOL_GENIMAGE)-distclean:
	@if [ -f ${SDK_TOOLS_DIR}/genimage/Makefile ]; then \
		make -C ${SDK_TOOLS_DIR}/genimage distclean; \
	fi
