# open_kws_en build switch, shared by src/canmv/Makefile and port/Makefile.
#
# CONFIG_ENABLE_MODULE_OPEN_KWS_EN defaults to y. Only an explicit
# "# CONFIG_ENABLE_MODULE_OPEN_KWS_EN is not set" in .config turns it off, so a
# .config generated before the option existed still builds the module.
ENABLE_OPEN_KWS_EN := $(if $(shell grep -qx '\# CONFIG_ENABLE_MODULE_OPEN_KWS_EN is not set' $(SDK_SRC_ROOT_DIR)/.config 2>/dev/null && echo n),n,y)
