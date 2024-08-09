rtsmart_inc_dir := 
rtsmart_inc_dir += $(SDK_RTSMART_SRC_DIR)/rtsmart/userapps
rtsmart_inc_dir += $(SDK_RTSMART_SRC_DIR)/rtsmart/userapps/sdk/rt-thread/include
rtsmart_inc_dir += $(SDK_RTSMART_SRC_DIR)/rtsmart/userapps/sdk/rt-thread/components/drivers
rtsmart_inc_dir += $(SDK_RTSMART_SRC_DIR)/rtsmart/userapps/sdk/rt-thread/components/drivers

rtsmart_lib_dir :=
rtsmart_libs := $(addprefix -l,$(subst lib, ,$(basename $(notdir $(foreach dir, $(rtsmart_lib_dir), $(wildcard $(dir)/*))))))

export SDK_RTSMART_INC=$(addprefix -I, $(rtsmart_inc_dir))
export SDK_RTSMART_LIBS=$(rtsmart_libs)
export SDK_RTSMART_LIB_DIR=$(addprefix -L, $(rtsmart_lib_dir))
