ifneq ($(MKENV_INCLUDED),1)
export SDK_SRC_ROOT_DIR := $(realpath $(dir $(realpath $(lastword $(MAKEFILE_LIST))))/../../)
endif

include $(SDK_SRC_ROOT_DIR)/tools/mkenv.mk

.PHONY: all clean distclean

all: gen_image
	@echo "Make canmv done."

clean:
	@make -C port clean
	@rm -rf ${SDK_BUILD_IMAGES_DIR}/sdcard/

distclean: clean
	@rm -rf $(SDK_CANMV_BUILD_DIR)

.PHONY: build
build:
	@$(MAKE) -j$(NCPUS) -C port || exit $?;

.PHONY: gen_image

# Yahboom specific build logic
ifeq ($(CONFIG_BOARD_K230_CANMV_YAHBOOM),y)

gen_image: build copy_sdcard copy_micropython

.PHONY: copy_sdcard
copy_sdcard:
	@echo "Copy sdcard (Yahboom)"
	@mkdir -p ${SDK_BUILD_IMAGES_DIR}/sdcard/
	rsync -aq --delete --exclude='.git' $(SDK_SRC_ROOT_DIR)/src/canmv/resources/ybsdcard/ ${SDK_BUILD_IMAGES_DIR}/sdcard/

.PHONY: copy_micropython
copy_micropython:
	@mkdir -p ${SDK_BUILD_IMAGES_DIR}/sdcard
	@echo "Copy micropython (Yahboom)"
	@if [ ! -e $(SDK_CANMV_BUILD_DIR)/micropython ]; then \
		echo "micropython not exists." && exit 1; \
	fi; \
	cp -rf $(SDK_CANMV_BUILD_DIR)/micropython ${SDK_BUILD_IMAGES_DIR}/sdcard/

else

# Standard build logic
gen_image: build copy_micropython copy_libs copy_sdcard copy_freetype_fonts copy_examples 

.PHONY: copy_micropython
copy_micropython:
	@mkdir -p ${SDK_BUILD_IMAGES_DIR}/sdcard

	@echo "Copy micropython"
	@if [ ! -e $(SDK_CANMV_BUILD_DIR)/micropython ]; then \
		echo "micropython not exists." && exit 1; \
	fi; \
	cp -rf $(SDK_CANMV_BUILD_DIR)/micropython ${SDK_BUILD_IMAGES_DIR}/sdcard/

	@echo "Copying Python scripts"
	@for f in main.py boot.py fallback.py; do \
		src=$(SDK_CANMV_SRC_DIR)/resources/$$f; \
		dst=${SDK_BUILD_IMAGES_DIR}/sdcard/$$f; \
		if [ -f $$src ]; then \
			cp -f $$src $$dst; \
		else \
			rm -f $$dst; \
		fi; \
	done

.PHONY: copy_libs
copy_libs:
	@mkdir -p ${SDK_BUILD_IMAGES_DIR}/sdcard

	@echo "Copy libs"
	@if [ ! -d ${SDK_BUILD_IMAGES_DIR}/sdcard/libs ]; then \
		mkdir -p ${SDK_BUILD_IMAGES_DIR}/sdcard/libs/; \
	fi; \
	rsync -aq --delete $(SDK_CANMV_SRC_DIR)/resources/libs/ ${SDK_BUILD_IMAGES_DIR}/sdcard/libs/

.PHONY: copy_freetype_fonts
copy_freetype_fonts:
	@mkdir -p ${SDK_BUILD_IMAGES_DIR}/sdcard

	@echo "Copy freetype resources"
	@if [ ! -d ${SDK_BUILD_IMAGES_DIR}/sdcard/res/font ]; then \
		mkdir -p ${SDK_BUILD_IMAGES_DIR}/sdcard/res/font/; \
	fi; \
	rsync -aq --delete $(SDK_CANMV_SRC_DIR)/resources/font/ ${SDK_BUILD_IMAGES_DIR}/sdcard/res/font/

.PHONY: copy_examples
copy_examples:
	@mkdir -p ${SDK_BUILD_IMAGES_DIR}/sdcard

	@echo "Copy examples"
	@if [ ! -d ${SDK_BUILD_IMAGES_DIR}/sdcard/examples ]; then \
		mkdir -p ${SDK_BUILD_IMAGES_DIR}/sdcard/examples/; \
	fi; \
	rsync -aq --delete --exclude='.git' $(SDK_CANMV_SRC_DIR)/resources/examples/ ${SDK_BUILD_IMAGES_DIR}/sdcard/examples/

	@echo "Copy kmodels"
	@cp -r ${SDK_RTSMART_SRC_DIR}/libs/kmodel/ai_poc/kmodel/face_detection_320.kmodel ${SDK_BUILD_IMAGES_DIR}/sdcard/examples/18-NNCase/face_detection/
	@if [ ! -d ${SDK_BUILD_IMAGES_DIR}/sdcard/examples/kmodel ]; then \
		mkdir -p ${SDK_BUILD_IMAGES_DIR}/sdcard/examples/kmodel; \
	fi
	@cp -r ${SDK_RTSMART_SRC_DIR}/libs/kmodel/ai_poc/kmodel/face_recognition.kmodel ${SDK_BUILD_IMAGES_DIR}/sdcard/examples/kmodel/
	@cp -r ${SDK_RTSMART_SRC_DIR}/libs/kmodel/ai_poc/kmodel/face_recognition_mobile.kmodel ${SDK_BUILD_IMAGES_DIR}/sdcard/examples/kmodel/
	@cp -r ${SDK_RTSMART_SRC_DIR}/libs/kmodel/ai_poc/kmodel/face_detection_320.kmodel ${SDK_BUILD_IMAGES_DIR}/sdcard/examples/kmodel/
	@cp -r ${SDK_RTSMART_SRC_DIR}/libs/kmodel/ai_poc/kmodel/yolov8n_320.kmodel ${SDK_BUILD_IMAGES_DIR}/sdcard/examples/kmodel/
	@cp -r ${SDK_RTSMART_SRC_DIR}/libs/kmodel/ai_poc/kmodel/yolov8n_seg_320.kmodel ${SDK_BUILD_IMAGES_DIR}/sdcard/examples/kmodel/
	@cp -r ${SDK_RTSMART_SRC_DIR}/libs/kmodel/ai_poc/kmodel/LPD_640.kmodel ${SDK_BUILD_IMAGES_DIR}/sdcard/examples/kmodel/
	@cp -r ${SDK_RTSMART_SRC_DIR}/libs/kmodel/ai_poc/kmodel/ocr_det_int16.kmodel ${SDK_BUILD_IMAGES_DIR}/sdcard/examples/kmodel/
	@cp -r ${SDK_RTSMART_SRC_DIR}/libs/kmodel/ai_poc/kmodel/hand_det.kmodel ${SDK_BUILD_IMAGES_DIR}/sdcard/examples/kmodel/
	@cp -r ${SDK_RTSMART_SRC_DIR}/libs/kmodel/ai_poc/kmodel/face_landmark.kmodel ${SDK_BUILD_IMAGES_DIR}/sdcard/examples/kmodel/
	@cp -r ${SDK_RTSMART_SRC_DIR}/libs/kmodel/ai_poc/kmodel/face_pose.kmodel ${SDK_BUILD_IMAGES_DIR}/sdcard/examples/kmodel/
	@cp -r ${SDK_RTSMART_SRC_DIR}/libs/kmodel/ai_poc/kmodel/face_parse.kmodel ${SDK_BUILD_IMAGES_DIR}/sdcard/examples/kmodel/
	@cp -r ${SDK_RTSMART_SRC_DIR}/libs/kmodel/ai_poc/kmodel/LPD_640.kmodel ${SDK_BUILD_IMAGES_DIR}/sdcard/examples/kmodel/
	@cp -r ${SDK_RTSMART_SRC_DIR}/libs/kmodel/ai_poc/kmodel/licence_reco.kmodel ${SDK_BUILD_IMAGES_DIR}/sdcard/examples/kmodel/
	@cp -r ${SDK_RTSMART_SRC_DIR}/libs/kmodel/ai_poc/kmodel/handkp_det.kmodel ${SDK_BUILD_IMAGES_DIR}/sdcard/examples/kmodel/
	@cp -r ${SDK_RTSMART_SRC_DIR}/libs/kmodel/ai_poc/kmodel/ocr_rec_int16.kmodel ${SDK_BUILD_IMAGES_DIR}/sdcard/examples/kmodel/
	@cp -r ${SDK_RTSMART_SRC_DIR}/libs/kmodel/ai_poc/kmodel/hand_reco.kmodel ${SDK_BUILD_IMAGES_DIR}/sdcard/examples/kmodel/
	@cp -r ${SDK_RTSMART_SRC_DIR}/libs/kmodel/ai_poc/kmodel/person_detect_yolov5n.kmodel ${SDK_BUILD_IMAGES_DIR}/sdcard/examples/kmodel/
	@cp -r ${SDK_RTSMART_SRC_DIR}/libs/kmodel/ai_poc/kmodel/yolov8n-pose.kmodel ${SDK_BUILD_IMAGES_DIR}/sdcard/examples/kmodel/
	@cp -r ${SDK_RTSMART_SRC_DIR}/libs/kmodel/ai_poc/kmodel/kws.kmodel ${SDK_BUILD_IMAGES_DIR}/sdcard/examples/kmodel/
	@cp -r ${SDK_RTSMART_SRC_DIR}/libs/kmodel/ai_poc/kmodel/face_alignment.kmodel ${SDK_BUILD_IMAGES_DIR}/sdcard/examples/kmodel/
	@cp -r ${SDK_RTSMART_SRC_DIR}/libs/kmodel/ai_poc/kmodel/face_alignment_post.kmodel ${SDK_BUILD_IMAGES_DIR}/sdcard/examples/kmodel/
	@cp -r ${SDK_RTSMART_SRC_DIR}/libs/kmodel/ai_poc/kmodel/eye_gaze.kmodel ${SDK_BUILD_IMAGES_DIR}/sdcard/examples/kmodel/
	@cp -r ${SDK_RTSMART_SRC_DIR}/libs/kmodel/ai_poc/kmodel/yolov5n-falldown.kmodel ${SDK_BUILD_IMAGES_DIR}/sdcard/examples/kmodel/
	@cp -r ${SDK_RTSMART_SRC_DIR}/libs/kmodel/ai_poc/kmodel/cropped_test127.kmodel ${SDK_BUILD_IMAGES_DIR}/sdcard/examples/kmodel/
	@cp -r ${SDK_RTSMART_SRC_DIR}/libs/kmodel/ai_poc/kmodel/nanotrack_backbone_sim.kmodel ${SDK_BUILD_IMAGES_DIR}/sdcard/examples/kmodel/
	@cp -r ${SDK_RTSMART_SRC_DIR}/libs/kmodel/ai_poc/kmodel/nanotracker_head_calib_k230.kmodel ${SDK_BUILD_IMAGES_DIR}/sdcard/examples/kmodel/
	@cp -r ${SDK_RTSMART_SRC_DIR}/libs/kmodel/ai_poc/kmodel/gesture.kmodel ${SDK_BUILD_IMAGES_DIR}/sdcard/examples/kmodel/
	@cp -r ${SDK_RTSMART_SRC_DIR}/libs/kmodel/ai_poc/kmodel/recognition.kmodel ${SDK_BUILD_IMAGES_DIR}/sdcard/examples/kmodel/
	@cp -r ${SDK_RTSMART_SRC_DIR}/libs/kmodel/ai_poc/kmodel/hifigan.kmodel ${SDK_BUILD_IMAGES_DIR}/sdcard/examples/kmodel/
	@cp -r ${SDK_RTSMART_SRC_DIR}/libs/kmodel/ai_poc/kmodel/zh_fastspeech_2.kmodel ${SDK_BUILD_IMAGES_DIR}/sdcard/examples/kmodel/
	@cp -r ${SDK_RTSMART_SRC_DIR}/libs/kmodel/ai_poc/kmodel/zh_fastspeech_1_f32.kmodel ${SDK_BUILD_IMAGES_DIR}/sdcard/examples/kmodel/
	@cp -r ${SDK_RTSMART_SRC_DIR}/libs/kmodel/ai_poc/kmodel/body_seg.kmodel ${SDK_BUILD_IMAGES_DIR}/sdcard/examples/kmodel/
	@cp -r ${SDK_RTSMART_SRC_DIR}/libs/kmodel/ai_poc/kmodel/multi_kws.kmodel ${SDK_BUILD_IMAGES_DIR}/sdcard/examples/kmodel/
	@cp -r ${SDK_RTSMART_SRC_DIR}/libs/kmodel/ai_poc/kmodel/yolov8n_224.kmodel ${SDK_BUILD_IMAGES_DIR}/sdcard/examples/kmodel/
	@cp -r ${SDK_RTSMART_SRC_DIR}/libs/kmodel/ai_poc/kmodel/yunet_640.kmodel ${SDK_BUILD_IMAGES_DIR}/sdcard/examples/kmodel/
	@cp -r ${SDK_RTSMART_SRC_DIR}/libs/kmodel/ai_poc/kmodel/yolo11n-obb.kmodel ${SDK_BUILD_IMAGES_DIR}/sdcard/examples/kmodel/
	@cp -r ${SDK_RTSMART_SRC_DIR}/libs/kmodel/ai_poc/kmodel/yolov8n-obb.kmodel ${SDK_BUILD_IMAGES_DIR}/sdcard/examples/kmodel/
	@cp -r ${SDK_RTSMART_SRC_DIR}/libs/kmodel/ai_poc/kmodel/fruit_*.kmodel ${SDK_BUILD_IMAGES_DIR}/sdcard/examples/kmodel/
	@cp -r ${SDK_RTSMART_SRC_DIR}/libs/kmodel/ai_poc/kmodel/face_liveness_rgb.kmodel ${SDK_BUILD_IMAGES_DIR}/sdcard/examples/kmodel/
	@cp -r ${SDK_RTSMART_SRC_DIR}/libs/kmodel/ai_poc/kmodel/yolo_license_plate_det.kmodel ${SDK_BUILD_IMAGES_DIR}/sdcard/examples/kmodel/

.PHONY: copy_sdcard
copy_sdcard:
	@echo "Copy user-customized sdcard resources"

	@mkdir -p ${SDK_BUILD_IMAGES_DIR}/sdcard/

	@if [ -d "$(SDK_CANMV_SRC_DIR)/resources/sdcard/" ]; then \
		rsync -aq "$(SDK_CANMV_SRC_DIR)/resources/sdcard/" "${SDK_BUILD_IMAGES_DIR}/sdcard/"; \
	else \
		echo "No sdcard resources found in $(SDK_CANMV_SRC_DIR)/resources/sdcard/"; \
	fi

endif

