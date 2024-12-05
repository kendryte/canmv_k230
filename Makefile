export SDK_SRC_ROOT_DIR := $(dir $(realpath $(lastword $(MAKEFILE_LIST))))

include $(SDK_SRC_ROOT_DIR)/tools/mkenv.mk

.PHONY: all genimage clean distclean 
all: genimage
	@echo "Board $(CONFIG_BOARD), config $(MK_LIST_DEFCONFIG)"
	@echo "Build K230 CanMV done, image is at $(SDK_BUILD_DIR)"

include $(SDK_TOOLS_DIR)/kconfig.mk
include $(SDK_TOOLS_DIR)/genimage.mk

ifeq ($(strip $(filter $(MAKECMDGOALS),clean distclean list_def dl_toolchain)),)
$(SDK_SRC_ROOT_DIR)/.config: $(KCONF)
	$(call gen_kconfig,$(SDK_CANMV_SRC_DIR),canmv)
	$(call gen_kconfig,$(SDK_RTSMART_SRC_DIR)/examples,rtt_examples)
	@make -C $(SDK_APPS_SRC_DIR) gen_kconfig || exit $?

	@$(KCONF) --defconfig $(SDK_SRC_ROOT_DIR)/configs/$(MK_LIST_DEFCONFIG) $(SDK_SRC_ROOT_DIR)/Kconfig || exit $?

$(SDK_SRC_ROOT_DIR)/.config.old: $(SDK_SRC_ROOT_DIR)/.config
	@cp -f $(SDK_SRC_ROOT_DIR)/.config $(SDK_SRC_ROOT_DIR)/.config.old
	@$(KCONF) --syncconfig $(SDK_SRC_ROOT_DIR)/Kconfig || exit $?
endif

.PHONY: menuconfig
menuconfig: $(MCONF) $(SDK_SRC_ROOT_DIR)/.config
	$(call del_mark)

	$(call gen_kconfig,$(SDK_CANMV_SRC_DIR),canmv)
	$(call gen_kconfig,$(SDK_RTSMART_SRC_DIR)/examples,rtt_examples)
	@make -C $(SDK_APPS_SRC_DIR) gen_kconfig || exit $?

	@$(MCONF) $(SDK_SRC_ROOT_DIR)/Kconfig || exit $?

.PHONY: savedefconfig
savedefconfig: $(KCONF) $(SDK_SRC_ROOT_DIR)/.config
	$(call gen_kconfig,$(SDK_CANMV_SRC_DIR),canmv)
	$(call gen_kconfig,$(SDK_RTSMART_SRC_DIR)/examples,rtt_examples)
	@make -C $(SDK_APPS_SRC_DIR) gen_kconfig || exit $?

	@$(KCONF) --savedefconfig=$(SDK_SRC_ROOT_DIR)/configs/$(MK_LIST_DEFCONFIG) $(SDK_SRC_ROOT_DIR)/Kconfig || exit $?

.PHONY: .autoconf
.autoconf: $(SDK_SRC_ROOT_DIR)/.config.old

%_defconfig: $(KCONF)
	$(call del_mark)

	$(call gen_kconfig,$(SDK_CANMV_SRC_DIR),canmv)
	$(call gen_kconfig,$(SDK_RTSMART_SRC_DIR)/examples,rtt_examples)
	@make -C $(SDK_APPS_SRC_DIR) gen_kconfig || exit $?

	@$(KCONF) --defconfig $(SDK_SRC_ROOT_DIR)/configs/$@ $(SDK_SRC_ROOT_DIR)/Kconfig || exit $?

	@if [ ! -d "$(SDK_CANMV_SRC_DIR)" ]; then \
		echo "canmv does not exist, updating CONFIG_SDK_ENABLE_CANMV in .config"; \
		sed -i '/^CONFIG_SDK_ENABLE_CANMV=y/c\# CONFIG_SDK_ENABLE_CANMV is not set' .config; \
	fi

	@echo "Apply $(@) success"

.PHONY: list_def
list_def:
	@echo "Available configs:"
	@ls $(SDK_SRC_ROOT_DIR)/configs/ | awk -v current="$(MK_LIST_DEFCONFIG)" '{if ($$0 == current) print NR, "[*]", $$0; else print NR, "[ ]", $$0}'


.PHONY: uboot uboot-clean uboot-distclean uboot-menuconfig
uboot: .autoconf
	@$(MAKE) -C $(SDK_UBOOT_SRC_DIR) all
uboot-clean:
	@$(MAKE) -C $(SDK_UBOOT_SRC_DIR) clean
uboot-distclean:
	@$(MAKE) -C $(SDK_UBOOT_SRC_DIR) distclean
uboot-menuconfig:
	@$(MAKE) -C $(SDK_UBOOT_SRC_DIR) menuconfig


.PHONY: rtsmart rtsmart-clean rtsmart-distclean rtsmart-menuconfig
rtsmart: .autoconf
	@$(MAKE) -C $(SDK_RTSMART_SRC_DIR) all
rtsmart-clean:
	@$(MAKE) -C $(SDK_RTSMART_SRC_DIR) clean
rtsmart-distclean:
	@$(MAKE) -C $(SDK_RTSMART_SRC_DIR) distclean
rtsmart-menuconfig:
	@$(MAKE) -C $(SDK_RTSMART_SRC_DIR) menuconfig

.PHONY: opensbi opensbi-clean opensbi-distclean
opensbi: .autoconf rtsmart
	@$(MAKE) -C $(SDK_OPENSBI_SRC_DIR) all
opensbi-clean:
	@$(MAKE) -C $(SDK_OPENSBI_SRC_DIR) clean
opensbi-distclean:
	@$(MAKE) -C $(SDK_OPENSBI_SRC_DIR) distclean


.PHONY: canmv canmv-clean canmv-distclean
canmv: .autoconf
ifeq ($(CONFIG_SDK_ENABLE_CANMV),y)
	@$(MAKE) -C $(SDK_CANMV_SRC_DIR) all
endif
canmv-clean:
ifeq ($(CONFIG_SDK_ENABLE_CANMV),y)
	@$(MAKE) -C $(SDK_CANMV_SRC_DIR) clean
endif
canmv-distclean:
ifeq ($(CONFIG_SDK_ENABLE_CANMV),y)
	@$(MAKE) -C $(SDK_CANMV_SRC_DIR) distclean
endif

.PHONY: app app-clean app-distclean
app: .autoconf
	@$(MAKE) -C $(SDK_APPS_SRC_DIR) all
app-clean:
	@$(MAKE) -C $(SDK_APPS_SRC_DIR) clean
app-distclean:
	@$(MAKE) -C $(SDK_APPS_SRC_DIR) distclean

.PHONY: rm_image
rm_image:
	@rm -rf $(SDK_BUILD_IMAGES_DIR)

genimage: $(TOOL_GENIMAGE) rm_image uboot rtsmart opensbi canmv app
	@$(SDK_TOOLS_DIR)/gen_image.sh

clean: kconfig-clean $(TOOL_GENIMAGE)-clean uboot-clean rtsmart-clean opensbi-clean canmv-clean app-clean
	@echo "Clean done."

distclean: kconfig-distclean $(TOOL_GENIMAGE)-distclean uboot-distclean rtsmart-distclean opensbi-distclean canmv-distclean app-distclean
	$(call del_mark)
	@rm -rf $(SDK_BUILD_DIR)
	@rm -rf $(SDK_SRC_ROOT_DIR)/.config
	@rm -rf $(SDK_SRC_ROOT_DIR)/.config.old
	@rm -rf $(SDK_SRC_ROOT_DIR)/defconfig
	@rm -rf $(SDK_SRC_ROOT_DIR)/uboot_defconfig
	@rm -rf $(SDK_SRC_ROOT_DIR)/rtsmart_defconfig
	@rm -rf $(SDK_SRC_ROOT_DIR)/compile_commands.json
	@rm -rf $(SDK_SRC_ROOT_DIR)/log.txt
	@echo "distclean done."

.PHONY: log
log:
ifeq ($(BEAR_EXISTS),yes)
	@$(BEAR_COMMAND) $(MAKE) 2>&1 | tee log.txt
else
	@$(MAKE) 2>&1 | tee log.txt
endif

.PHONY: dl_toolchain
dl_toolchain:
	@$(MAKE) -f $(SDK_TOOLS_DIR)/toolchain_linux.mk install
	@$(MAKE) -f $(SDK_TOOLS_DIR)/toolchain_rtsmart.mk install

.PHONY: help
help:
	@echo "Usage: "
	@echo "make xxxx_defconfig";
	@echo "make"
	@echo "Supported compilation options"
	@echo "make                          -- Build all for k230";
	@echo "make xxxx_defconfig           -- Select board configure";
	@echo "make menuconfig               -- Update configures";
	@echo "make savedefconfig            -- After menuconfig, generate the default config, can update board defconfig";
	@echo "make list_def                 -- List the configs supported";
	@echo "make clean                    -- Clean build artifacts";
	@echo "make distclean                -- Clean build artifacts";
	@echo "make uboot                    -- Make uboot single";
	@echo "make uboot-clean              -- Clean uboot build artifacts";
	@echo "make uboot-distclean          -- Clean uboot build artifacts";
	@echo "make uboot-menuconfig         -- Update uboot configures";
	@echo "make rtsmart                  -- Make rtsmart single";
	@echo "make rtsmart-clean            -- Clean rtsmart build artifacts";
	@echo "make rtsmart-distclean        -- Clean rtsmart build artifacts";
	@echo "make rtsmart-menuconfig       -- Update rtsmart configures";
	@echo "make opensbi                  -- Make opensbi single";
	@echo "make opensbi-clean            -- Clean opensbi build artifacts";
	@echo "make opensbi-distclean        -- Clean opensbi build artifacts";
ifeq ($(CONFIG_SDK_ENABLE_CANMV),y)
	@echo "make canmv                    -- Make canmv single";
	@echo "make canmv-clean              -- Clean canmv build artifacts";
	@echo "make canmv-distclean          -- Clean canmv build artifacts";
else
	@echo "make app                      -- Make applications single";
	@echo "make app-clean                -- Clean applications build artifacts";
	@echo "make app-distclean            -- Clean applications build artifacts";
endif
	@echo "make log                      -- Make all and generate log.txt";
	@echo "make dl_toolchain             -- Download toolchain, only need run at first time";
	@echo "Supported board configs";
	@ls $(SDK_SRC_ROOT_DIR)/configs/ | awk '{print "\t", $$0}'
