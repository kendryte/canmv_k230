export CROSS_COMPILE_DIR=$(SDK_TOOLCHAIN_DIR)/Xuantie-900-gcc-linux-5.10.4-glibc-x86_64-V2.6.0/bin/
export CROSS_COMPILE_PREFIX=riscv64-unknown-linux-gnu-
export CROSS_COMPILE=$(CROSS_COMPILE_DIR)/$(CROSS_COMPILE_PREFIX)

# export AS = $(CROSS_COMPILE)as
# export CC = $(CROSS_COMPILE)gcc
# export CPP = $(CC) -E
# export CXX = $(CROSS_COMPILE)g++
# export GDB = $(CROSS_COMPILE)gdb
# export LD = $(CROSS_COMPILE)ld
# export OBJCOPY = $(CROSS_COMPILE)objcopy
# export SIZE = $(CROSS_COMPILE)size
# export STRIP = $(CROSS_COMPILE)strip
# export AR = $(CROSS_COMPILE)ar

define command_exists
$(shell command -v $(1) >/dev/null 2>&1 && echo 1 || echo 0)
endef
TOOLCHIAN_EXIST=$(call command_exists, $(CROSS_COMPILE)gcc)

ifeq ($(MAKECMDGOALS), install)
ifeq ($(NATIVE_BUILD),1)
	DOWNLOAD_SERVER?=https://ai.b-bug.org/k230/toolchain
else
	DOWNLOAD_SERVER?=https://kendryte-download.canaan-creative.com/k230/toolchain
endif

# for git actions
ifeq ($(CI),true)
	DOWNLOAD_SERVER:=https://github.com/kendryte/canmv_k230/releases/download/v1.1/
endif

toolchain_file_name=Xuantie-900-gcc-linux-5.10.4-glibc-x86_64-V2.6.0.tar.bz2
toolchain_download_url=$(DOWNLOAD_SERVER)/$(toolchain_file_name)
toolchain_install_path=$(SDK_TOOLCHAIN_DIR)/$(toolchain_file_name)

.PHONY: install
install:
	@if [ ! $(TOOLCHIAN_EXIST) -eq 1 ]; then \
		if [ ! -f $(toolchain_install_path) ]; then \
			echo "Download toolchain $(toolchain_file_name) from $(toolchain_download_url)"; \
			wget -q --show-progress -P $(SDK_TOOLCHAIN_DIR) $(toolchain_download_url); \
		fi; \
		echo "Extract toolchains..."; \
		tar xf $(toolchain_install_path) -C $(SDK_TOOLCHAIN_DIR); \
	fi;
	@echo "Toolchain $(toolchain_file_name) installed."
else
ifneq ($(TOOLCHIAN_EXIST),1)
$(error Please run make dl_toolchain to downloading toolchains...)
endif
endif
