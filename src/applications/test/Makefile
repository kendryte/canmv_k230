CFLAGS := -march=rv64imafdcv -mabi=lp64d -mcmodel=medany -std=gnu99 
CFLAGS += -fdata-sections -ffunction-sections

LDFLAGS := -T link.lds --static -Wl,--gc-sections

.PHONY: all clean distclean
all:
	@echo "Make test"
	@$(CC) test.c -o test $(CFLAGS) $(LDFLAGS)
	@$(STRIP) test
	@cp test $(SDK_APPS_IMAGE_DIR)

clean:
	@rm -rf test

distclean: clean
