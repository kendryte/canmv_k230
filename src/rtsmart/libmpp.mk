# sdk lib and inc
mpp_kernel_inc_dir := 
mpp_kernel_inc_dir += $(SDK_RTSMART_SRC_DIR)/mpp/include/
mpp_kernel_inc_dir += $(SDK_RTSMART_SRC_DIR)/mpp/include/comm
mpp_kernel_inc_dir += $(SDK_RTSMART_SRC_DIR)/mpp/include/ioctl

mpp_kernel_lib_dir := $(SDK_RTSMART_SRC_DIR)/mpp/kernel/lib/

mpp_kenerl_libs := $(addprefix -l,$(subst lib, ,$(basename $(notdir $(foreach dir, $(mpp_kernel_lib_dir), $(wildcard $(dir)/*))))))

export SDK_MPP_KERNEL_INC=$(addprefix -I, $(mpp_kernel_inc_dir))
export SDK_MPP_KERNEL_LIBS=$(mpp_kenerl_libs)
export SDK_MPP_KERNEL_LIB_DIR=$(addprefix -L, $(mpp_kernel_lib_dir))

mpp_user_inc_dir := $(SDK_RTSMART_SRC_DIR)/mpp/userapps/api/ $(mpp_kernel_inc_dir)
mpp_user_lib_dir := $(SDK_RTSMART_SRC_DIR)/mpp/userapps/lib/
mpp_user_libs := $(addprefix -l,$(subst lib, ,$(basename $(notdir $(foreach dir, $(mpp_user_lib_dir), $(wildcard $(dir)/*))))))

export SDK_MPP_USER_INC=$(addprefix -I, $(mpp_user_inc_dir))
export SDK_MPP_USER_LIBS=$(mpp_user_libs)
export SDK_MPP_USER_LIB_DIR=$(addprefix -L, $(mpp_user_lib_dir))
