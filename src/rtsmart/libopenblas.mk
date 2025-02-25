
openblas_inc_dir := $(SDK_RTSMART_SRC_DIR)/libs/openblas/include

OPENBLAS_INC = $(addprefix -I, $(openblas_inc_dir))
OPENBLAS_LIBS = -lopenblas
OPENBLAS_LIB_DIR = -L$(SDK_RTSMART_SRC_DIR)/libs/openblas/lib
