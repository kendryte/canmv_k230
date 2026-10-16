# open_kws build switch, shared by src/canmv/Makefile and port/Makefile.
#
# CONFIG_ENABLE_MODULE_OPEN_KWS defaults to y. Only an explicit
# "# CONFIG_ENABLE_MODULE_OPEN_KWS is not set" in .config turns it off, so a
# .config generated before the option existed still builds the module.
ENABLE_OPEN_KWS := $(if $(shell grep -qx '\# CONFIG_ENABLE_MODULE_OPEN_KWS is not set' $(SDK_SRC_ROOT_DIR)/.config 2>/dev/null && echo n),n,y)
