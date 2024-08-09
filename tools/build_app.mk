-include $(SDK_BUILD_DIR)/.config

# Strip quotes and then whitespaces
qstrip = $(strip $(subst ",,$(1)))

# Only intends to be called as a submethod from other DownloadMethod
#
# We first clone, checkout and then we generate a tar using the
# git archive command to apply any rules of .gitattributes
# To keep consistency with github generated tar archive, we default
# the short hash to 8 (default is 7). (for git log related usage)
define DownloadGit
  @if [ -e $(SDK_APP_SRC_DIR)/$(PKG_DIR) ]; then \
    echo "$(SDK_APP_SRC_DIR)/$(PKG_DIR) already exists, please delete it or manual update it and rerun make sync_app"; \
  else \
    echo "Checking out files from the git repository..."; \
    mkdir -p dl && cd dl; \
    rm -rf $(PKG_DIR); \
    git clone $(OPTS) $(PKG_URL) $(PKG_DIR); \
    cd $(PKG_DIR); \
    git checkout $(SOURCE_VERSION); \
    if [ "$(SUBMODULE)" = "y" ]; then \
      git submodule update --init --progress; \
    fi; \
    cd -; \
    mv $(PKG_DIR) $(SDK_APP_SRC_DIR); \
  fi
endef

# $(1) dir
# $(2) url
# $(3) commit
define validate_app
	if [ -d $(PKG_DIR) ] && [ -d $(PKG_DIR)/.git ]; then \
		CUR_URL=$$(git -C $(PKG_DIR) config --get remote.origin.url); \
		if [ "$$CUR_URL" = "$(PKG_URL)" ]; then \
			CUR_COMMIT=$$(git -C $(PKG_DIR) rev-parse HEAD); \
			if [ "$$CUR_COMMIT" = "$(SOURCE_VERSION)" ]; then \
				echo "VALID"; \
			else \
				echo "VALID Please notice commit $$CUR_COMMIT not equal to $(SOURCE_VERSION)"; \
			fi; \
		else \
			echo "url $$CUR_URL not equal to $(PKG_URL)"; \
		fi; \
	else \
		echo "Either not a git repo or directory $(PKG_DIR) does not exist"; \
	fi
endef

define parse_config
  PKG_ENABLE := $(call qstrip,$(CONFIG_ENABLE_$(1)))
  PKG_DIR := $(call qstrip,$(CONFIG_$(1)_REPO_DIR))
  PKG_URL := $(call qstrip,$(CONFIG_$(1)_REPO_URL))
  SOURCE_VERSION := $(call qstrip,$(CONFIG_$(1)_REPO_COMMIT))
  SUBMODULE := $(call qstrip,$(CONFIG_$(1)_SUBMODULE))
endef

define RegisterApplication
  $(eval $(parse_config))

  $(info SUBMODULE `$(SUBMODULE)`)

  $(eval PKG_VALID := $(strip $(shell $(call validate_app,$(PKG_DIR),$(PKG_URL),$(PKG_VERSION)))))

  $(if $(filter y,$(PKG_ENABLE)),
    $(info Application `$(PKG_DIR)` enabled, configured remote `$(PKG_URL)`, version `$(SOURCE_VERSION)`)

    $(if $(filter VALID,$(PKG_VALID)),
      # package is vaild
      $(info Application $(PKG_DIR) is valid)

      $(eval BUILD_APP_SUB_DIRS += $(PKG_DIR))

      $(if $(filter commit,$(PKG_VALID)),
        $(warning Application `$(PKG_DIR)` is dirty, $(subst VALID ,,$(PKG_VALID)))
        ,
      ), # package is invalid
      $(info Application $(PKG_DIR) is invalid)

      $(foreach dep,DOWNLOAD_APP,
        $(eval $(dep): DNLD_APP_$(PKG_DIR))
      )

      DNLD_APP_$(PKG_DIR):
		@echo "Start download App $(PKG_DIR)"
		$(call DownloadGit)

      $(if $(strip $(BUILD_APP_IGNORE_ERROR_GOALS)),,
        $(error Application `$(PKG_DIR)` is invalid, please run `make sync_app` to update applications)
      )
    )
  )
endef
