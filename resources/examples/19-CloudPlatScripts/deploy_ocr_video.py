# -*- coding: utf-8 -*-
'''
Script: deploy_ocr_video.py
脚本名称：deploy_ocr_video.py

Description:
    This script runs a real-time OCR (Optical Character Recognition) application on an embedded device.
    It uses a pipeline to capture video frames, performs text detection using a pre-trained Kmodel,
    then runs text recognition on detected regions, and finally displays the results on screen.

    The detection and recognition model configurations are retrieved from the Canaan online training platform via separate JSON config files.

脚本说明：
    本脚本在嵌入式设备上运行实时 OCR（光学字符识别）应用。它通过捕获视频帧，使用预训练的 Kmodel 进行文本检测， 然后对检测到的区域进行文本识别，最后在屏幕上显示识别结果。

    检测和识别模型的配置文件分别通过 Canaan 在线训练平台提供的 JSON 文件加载。

Author: Canaan Developer
作者：Canaan 开发者
'''


import os, gc
from libs.PlatTasks import OCRDetectionApp, OCRRecognitionApp
from libs.PipeLine import PipeLine
from libs.Utils import *

# Set display mode: options are 'hdmi', 'lcd', 'lt9611', 'st7701', 'hx8399'
# auto按开发板选择默认驱动；可手动覆盖为hdmi/lcd/st7701等模式
display_mode="auto"
# None使用SDK默认分辨率；更换屏幕时可指定[640, 480]等尺寸
display_size=None

# Define the input size for the RGB888P video frames
rgb888p_size = [640, 360]

# Set root path and load config for OCR detection model
ocrdet_root_path = "/sdcard/ocrdet_mp_deployment_source/"
ocrdet_deploy_conf = read_json(ocrdet_root_path + "/deploy_config.json")
ocrdet_kmodel_path = ocrdet_root_path + ocrdet_deploy_conf["kmodel_path"]    # Detection kmodel path
mask_threshold = ocrdet_deploy_conf["mask_threshold"]                        # Mask threshold
box_threshold = ocrdet_deploy_conf["box_threshold"]                          # Box threshold
ocrdet_model_input_size = ocrdet_deploy_conf["img_size"]                     # Detection model input size

# Set root path and load config for OCR recognition model
ocrrec_root_path = "/sdcard/ocrrec_mp_deployment_source/"
ocrrec_deploy_conf = read_json(ocrrec_root_path + "/deploy_config.json")
ocrrec_kmodel_path = ocrrec_root_path + ocrrec_deploy_conf["kmodel_path"]    # Recognition kmodel path
dict_path = ocrrec_root_path + "dict.txt"                                    # Character dictionary path

# Load dictionary for recognition model
with open(dict_path, 'r') as file:
    line_one = file.read(100000)
    line_list = line_one.split("\n")
DICT = {num: char.replace("\r", "").replace("\n", "") for num, char in enumerate(line_list)}

ocrrec_model_input_size = ocrrec_deploy_conf["img_size"]                     # Recognition model input size

# Inference settings
inference_mode = "video"                                                     # Inference mode: 'video'
debug_mode = 0                                                               # Debug mode flag

# Initialize the PipeLine. rgb888p_size is the AI input resolution and display_size is the display resolution
pl = PipeLine(rgb888p_size=rgb888p_size, display_mode=display_mode, display_size=display_size)
# Create the PipeLine. Pass sensor_id to select a camera when needed, for example pl.create(sensor_id=2)
pl.create()
display_size = pl.get_display_size()

# Initialize OCR detection and recognition applications
ocrdet_app = OCRDetectionApp(inference_mode, ocrdet_kmodel_path, ocrdet_model_input_size,mask_threshold, box_threshold, rgb888p_size, display_size, debug_mode=debug_mode)
ocrdet_app.config_preprocess()

ocrrec_app = OCRRecognitionApp(inference_mode, ocrrec_kmodel_path, ocrrec_model_input_size,DICT, rgb888p_size, display_size, debug_mode=debug_mode)

rec_texts = []  # List to store recognition results

# Main loop: capture, run OCR detection and recognition, display results
while True:
    with ScopedTiming("total", 1):
        img = pl.get_frame()                                      # Capture current frame
        det_res = ocrdet_app.run(img)                             # Run text detection
        rec_texts.clear()
        for i in range(len(det_res["boxes"])):                    # For each detected box
            det_ = det_res["crop_images"][i][0]                   # Get cropped text region
            det_chw = hwc2chw(det_)                               # Convert image to CHW format
            ocrrec_app.config_preprocess(input_image_size=[det_chw.shape[2], det_chw.shape[1]])  # Configure recognition input size for each cropped region
            res = ocrrec_app.run(det_chw)                         # Run text recognition
            rec_texts.append(res["text"])                         # Store recognized text
        ocrrec_app.draw_result(pl.osd_img, det_res["boxes"], rec_texts)  # Draw boxes and text results
        pl.show_image()                                           # Show final image on display
        gc.collect()                                              # Run garbage collection to free memory

# Cleanup: These lines will only run if the loop is interrupted (e.g., by an IDE break or external interruption)
ocrdet_app.deinit()                                               # De-initialize OCR detection app
ocrrec_app.deinit()                                               # De-initialize OCR recognition app
pl.destroy()                                                      # Destroy pipeline instance
