include $(SDK_TOOLS_DIR)/toolchain_rtsmart.mk

export AS = $(CROSS_COMPILE)as
export CC = $(CROSS_COMPILE)gcc
export CPP = $(CC) -E
export CXX = $(CROSS_COMPILE)g++
export GDB = $(CROSS_COMPILE)gdb
export LD = $(CROSS_COMPILE)ld
export OBJCOPY = $(CROSS_COMPILE)objcopy
export SIZE = $(CROSS_COMPILE)size
export STRIP = $(CROSS_COMPILE)strip
export AR = $(CROSS_COMPILE)ar



# enabled apps
subdirs += test
